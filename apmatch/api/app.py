"""The APMatch HTTP API.

FastAPI app wiring the full deterministic pipeline:
  upload images -> OCR -> parse -> validate -> match -> score -> audit -> response

Run on the host: ``uvicorn apmatch.api:app`` (containerization is P1-12c).

Auth: X-API-Key header validated against the APMATCH_API_KEY env var
(fail-fast at config import; no default key). Errors are enum-coded via
ErrorResponse — no stack traces, no document content, no file names in
responses or logs.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apmatch.api import config
from apmatch.api.pipeline import recheck_documents, run_pipeline
from apmatch.api.schemas import (
    AuditResponse,
    CodeCountOut,
    DecisionRequest,
    ErrorResponse,
    FailureOut,
    HealthResponse,
    MatchResponse,
    RecentRunOut,
    RecheckRequest,
    RouteCountsOut,
    SimilarityMatchOut,
    TemplatesOut,
)
from apmatch.audit.entry import AuditEntry
from apmatch.audit.kpis import (
    case_history,
    count_by_route,
    count_cases_by_route,
    failure_code_counts,
    list_customers,
    recent_runs,
    review_queue,
)
from apmatch.audit.repository import AuditEntryNotFound, AuditRepository
from apmatch.matching.result import MatchFailure
from apmatch.remarks.matching import remark_for_match
from apmatch.remarks.templates import remark_for
from apmatch.scoring.result import Route, RouteReason

logging.basicConfig(level=config.APMATCH_LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("apmatch.api")


class ApiError(Exception):
    """Enum-coded API error. ``detail`` never contains user data."""

    def __init__(self, status_code: int, error_code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Heavy objects built ONCE at startup.
    from apmatch.embeddings.model import EmbeddingModel
    from apmatch.layout.structure import LayoutEngine
    from apmatch.ocr.router import OCRRouter

    app.state.router = OCRRouter()
    app.state.layout = LayoutEngine()
    # ~5-10 s (weights hash + load); per-request construction would multiply
    # that latency (D-088).
    app.state.embedding_model = EmbeddingModel()
    logger.info("EmbeddingModel loaded: version=%s", app.state.embedding_model.model_version)
    app.state.db_engine = create_engine(config.DATABASE_URL)
    yield
    app.state.db_engine.dispose()


app = FastAPI(title="APMatch", version="0.1.0", lifespan=lifespan)

# Browser frontend (frontend/index.html) calls the API cross-origin, including
# a preflight for the X-API-Key header. Auth is unchanged: every call still
# needs a valid key.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.APMATCH_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error_code": exc.error_code, "detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the traceback server-side; the response stays enum-coded.
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error_code": "HTTP_ERROR", "detail": "Request error"})
    return JSONResponse(status_code=500, content={"error_code": "INTERNAL", "detail": "Internal server error"})


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    # Never log document content, file names, or API keys.
    logger.info("%s %s -> %d (%.0f ms)", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


async def require_api_key(x_api_key: str | None = Header(None)) -> None:
    if not x_api_key:
        raise ApiError(401, "AUTH_MISSING", "X-API-Key header required")
    if x_api_key != config.APMATCH_API_KEY:
        raise ApiError(401, "AUTH_INVALID", "Invalid API key")


def get_session(request: Request):
    with Session(request.app.state.db_engine) as session:
        yield session


# PaddleOCR dispatches on the file suffix; an unknown/missing one makes
# predict() return an empty result. Keep the upload's suffix if it is one of
# these, else default to .png.
_IMAGE_SUFFIXES = {".bmp", ".dib", ".jpeg", ".jpg", ".png", ".webp", ".pbm", ".pgm", ".ppm", ".pnm", ".sr", ".ras", ".tiff", ".tif"}

# Multi-tenant tag (D-091): lowercase alphanumerics, underscore, hyphen.
_CUSTOMER_ID_RE = re.compile(r"^[a-z0-9_-]{1,64}$")


def _suffix_for(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    return suffix if suffix in _IMAGE_SUFFIXES else ".png"


def _failure_message(failure) -> str:
    try:
        return remark_for_match(failure) if isinstance(failure, MatchFailure) else remark_for(failure)
    except Exception:  # a message is a convenience; never fail the response for it
        return ""


def _failure_out(failure) -> FailureOut:
    return FailureOut(
        code=failure.code.value,
        severity=failure.severity.value,
        location=failure.location,
        expected=failure.expected,
        actual=failure.actual,
        delta=failure.delta,
        message=_failure_message(failure),
    )


def _recent_out(r) -> RecentRunOut:
    return RecentRunOut(
        run_id=r.run_id,
        run_timestamp=r.run_timestamp,
        invoice_number=r.invoice_number,
        route=r.route.value,
        route_reason=r.route_reason.value,
        score=float(r.score_value),
        remark=r.remark,
        case_id=r.case_id,
        customer_id=r.customer_id,
        decided_by=r.decided_by,
    )


def _similarity_out(sm) -> SimilarityMatchOut:
    return SimilarityMatchOut(
        location=sm.location,
        invoice_text=sm.invoice_text,
        counterpart_text=sm.counterpart_text,
        score=str(sm.score),
        threshold_review=str(sm.threshold_review),
        threshold_accept=str(sm.threshold_accept),
        band=sm.band,
        model_version=sm.model_version,
    )


# The four /match upload fields; also the document names in storage.
_DOC_NAMES = ("invoice", "po", "grni", "pard")
_RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _storage_dir() -> Path:
    return Path(config.APMATCH_STORAGE_DIR)


def _persist_run(entry: AuditEntry, paths: dict[str, Path], extracted: dict) -> None:
    """Save the uploaded images + the extraction sidecar for the review UI.

    Images: storage/images/{run_id}_{name}{suffix}; sidecar:
    storage/runs/{run_id}.json. Failures here must not fail the match —
    the decision is already made; the review UI just degrades to no image.
    """
    try:
        img_dir = _storage_dir() / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        for name, path in paths.items():
            shutil.copyfile(path, img_dir / f"{entry.run_id}_{name}{path.suffix}")
        runs_dir = _storage_dir() / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / f"{entry.run_id}.json").write_text(
            json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        logger.warning("could not persist run artifacts for %s", entry.run_id, exc_info=True)


def _validate_images(paths: dict[str, Path]) -> None:
    """Reject uploads PIL cannot decode (400 INVALID_IMAGE, not 500).

    PaddleOCR raises a generic Exception on a bad image, so a malformed
    upload is indistinguishable from a real pipeline fault by exception type.
    Validate with PIL at the boundary instead: if it cannot decode the bytes,
    the upload is user error, not a server fault.
    """
    for path in paths.values():
        try:
            with Image.open(path) as img:
                img.load()
        except Exception as e:
            raise ApiError(400, "INVALID_IMAGE", "One or more uploaded files is not a valid image") from e


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    # No auth — health checks must work without credentials.
    return HealthResponse(status="ok", version=app.version)


@app.post("/match", response_model=MatchResponse, dependencies=[Depends(require_api_key)])
def match(
    request: Request,
    invoice: UploadFile = File(...),
    po: UploadFile | None = File(None),
    grni: UploadFile | None = File(None),
    pard: UploadFile | None = File(None),
    customer_id: str = Query("default"),
    session: Session = Depends(get_session),
) -> MatchResponse:
    """Full pipeline: up to 4 images in -> decision + one audit_log row.

    Sync on purpose: the OCR pipeline is blocking, so FastAPI runs this in
    its threadpool instead of stalling the event loop.
    """
    # Validate before any pipeline work: a bad tag must not cost an OCR run.
    if not _CUSTOMER_ID_RE.fullmatch(customer_id):
        raise ApiError(400, "INVALID_CUSTOMER_ID", "customer_id must match ^[a-z0-9_-]{1,64}$")

    contents: dict[str, tuple[bytes, str]] = {}
    for name, upload in (("invoice", invoice), ("po", po), ("grni", grni), ("pard", pard)):
        if upload is None:
            continue
        data = upload.file.read()
        if len(data) > config.APMATCH_MAX_UPLOAD_BYTES:
            raise ApiError(400, "UPLOAD_TOO_LARGE", f"field {name} exceeds the maximum upload size")
        contents[name] = (data, _suffix_for(upload))

    with tempfile.TemporaryDirectory() as tmp:
        paths: dict[str, Path] = {}
        for name, (data, suffix) in contents.items():
            path = Path(tmp) / (uuid4().hex + suffix)  # uuid-named; tempdir cleaned on exit
            path.write_bytes(data)
            paths[name] = path
        _validate_images(paths)  # malformed upload -> 400 INVALID_IMAGE, not 500
        try:
            _, _, decision, entry, extracted = run_pipeline(
                paths["invoice"],
                paths.get("po"),
                paths.get("grni"),
                paths.get("pard"),
                router=request.app.state.router,
                layout=request.app.state.layout,
                embedding_model=request.app.state.embedding_model,
                ocr_debug=config.APMATCH_OCR_DEBUG,
                customer_id=customer_id,
                session=session,
            )
        except ApiError:
            raise
        except Exception:
            logger.exception("pipeline failed")
            raise ApiError(500, "PIPELINE_ERROR", "Pipeline failed; see server logs")
        # Persist inside the with-block: the temp files vanish on exit.
        _persist_run(entry, paths, extracted)

    AuditRepository.append(session, entry)
    session.commit()
    logger.info("run_id=%s route=%s reason=%s", entry.run_id, entry.route.value, entry.route_reason.value)

    return MatchResponse(
        run_id=entry.run_id,
        route=entry.route.value,
        route_reason=entry.route_reason.value,
        score=decision.score.value,
        remark=entry.remark,
        invoice_number=entry.invoice_number,
        po_number=entry.po_number,
        grn_number=entry.grn_number,
        pard_ref=entry.pard_ref,
        validation_failures=[_failure_out(f) for f in entry.validation_failures],
        match_failures=[_failure_out(f) for f in entry.match_failures],
        similarity_matches=[_similarity_out(sm) for sm in entry.similarity_matches],
        customer_id=entry.customer_id,
    )


@app.get("/audit/{run_id}", response_model=AuditResponse, dependencies=[Depends(require_api_key)])
def get_audit(run_id: str, session: Session = Depends(get_session)) -> AuditResponse:
    try:
        entry = AuditRepository.get(session, run_id)
    except AuditEntryNotFound:
        raise ApiError(404, "AUDIT_NOT_FOUND", "No audit entry with that run_id")
    return _audit_response(entry, session)


def _read_sidecar(run_id: str) -> dict | None:
    sidecar = _storage_dir() / "runs" / f"{run_id}.json"
    return json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.is_file() else None


def _write_sidecar(run_id: str, extracted: dict | None) -> None:
    if extracted is None:
        return
    try:
        runs_dir = _storage_dir() / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / f"{run_id}.json").write_text(json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.warning("could not write sidecar for %s", run_id, exc_info=True)


def _audit_response(entry: AuditEntry, session: Session | None = None) -> AuditResponse:
    # Extraction sidecar written by /match; absent for older runs.
    extracted = _read_sidecar(entry.run_id)
    case_id = entry.case_id or entry.run_id
    history = [_recent_out(r) for r in case_history(session, case_id)] if session is not None else []
    return AuditResponse(
        run_id=entry.run_id,
        run_timestamp=entry.run_timestamp,
        route=entry.route.value,
        route_reason=entry.route_reason.value,
        score=float(entry.score_value),
        remark=entry.remark,
        invoice_number=entry.invoice_number,
        po_number=entry.po_number,
        grn_number=entry.grn_number,
        pard_ref=entry.pard_ref,
        validation_failures=[_failure_out(f) for f in entry.validation_failures],
        match_failures=[_failure_out(f) for f in entry.match_failures],
        input_hash=entry.input_hash,
        similarity_matches=[_similarity_out(sm) for sm in entry.similarity_matches],
        customer_id=entry.customer_id,
        extraction_source=entry.extraction_source,
        extracted=extracted,
        case_id=case_id,
        decided_by=entry.decided_by,
        history=history,
    )


@app.get("/documents/{run_id}/{name}/image", dependencies=[Depends(require_api_key)])
def document_image(run_id: str, name: str, session: Session = Depends(get_session)) -> FileResponse:
    """The uploaded scan for one run, for the review UI's image viewer.

    Corrections and reviewer decisions have no uploads of their own: their
    images are the case's original ones (stored under the case_id).
    """
    if not _RUN_ID_RE.fullmatch(run_id) or name not in _DOC_NAMES:
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "No document image with that id")
    try:
        stem = AuditRepository.get(session, run_id).case_id or run_id
    except AuditEntryNotFound:
        stem = run_id
    for path in (_storage_dir() / "images").glob(f"{stem}_{name}.*"):
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type)
    raise ApiError(404, "DOCUMENT_NOT_FOUND", "No document image with that id")


@app.get("/templates", response_model=TemplatesOut, dependencies=[Depends(require_api_key)])
def list_templates() -> TemplatesOut:
    """The style templates shipped with the image (templates/*.yaml)."""
    tdir = Path(__file__).resolve().parents[2] / "templates"
    return TemplatesOut(templates=sorted(p.name for p in tdir.glob("*.yaml")) if tdir.is_dir() else [])


@app.get("/kpis/routes", response_model=RouteCountsOut, dependencies=[Depends(require_api_key)])
def kpis_routes(
    since: datetime | None = None,
    customer_id: str | None = None,
    session: Session = Depends(get_session),
) -> RouteCountsOut:
    counts = count_by_route(session, since, customer_id)
    return RouteCountsOut(
        auto_approve=counts.auto_approve,
        human_review=counts.human_review,
        reject=counts.reject,
        total=counts.total,
    )


@app.get("/kpis/recent", response_model=list[RecentRunOut], dependencies=[Depends(require_api_key)])
def kpis_recent(
    limit: int = 50,
    customer_id: str | None = None,
    session: Session = Depends(get_session),
) -> list[RecentRunOut]:
    return [_recent_out(r) for r in recent_runs(session, limit, customer_id)]


# --- Review workflow -------------------------------------------------------
# Corrections and reviewer decisions are NEW audit rows with the same case_id:
# the log stays append-only and every step of a case is kept.


def _load_entry(session: Session, run_id: str) -> AuditEntry:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ApiError(404, "AUDIT_NOT_FOUND", "No audit entry with that run_id")
    try:
        return AuditRepository.get(session, run_id)
    except AuditEntryNotFound:
        raise ApiError(404, "AUDIT_NOT_FOUND", "No audit entry with that run_id") from None


def _require_open_case(session: Session, entry: AuditEntry) -> str:
    """A reviewer may act only on the newest step of a case that is still open.

    Open means the newest step is HUMAN_REVIEW, or a REJECT made by the system
    (a misread can be corrected). Anything approved, or decided by a reviewer,
    is final: acting again would let one invoice be approved twice.
    """
    case_id = entry.case_id or entry.run_id
    history = case_history(session, case_id)
    if history and history[-1].run_id != entry.run_id:
        raise ApiError(409, "STALE_RUN", "This is not the newest step of the case")
    closed = entry.route is Route.AUTO_APPROVE or entry.decided_by == "reviewer"
    if closed:
        raise ApiError(409, "CASE_CLOSED", "This case already has a final decision")
    return case_id


@app.post("/runs/{run_id}/recheck", response_model=AuditResponse, dependencies=[Depends(require_api_key)])
def recheck_run(
    run_id: str, body: RecheckRequest, request: Request, session: Session = Depends(get_session)
) -> AuditResponse:
    """Re-decide a case from the documents a reviewer corrected. No OCR, no VLM."""
    original = _load_entry(session, run_id)
    case_id = _require_open_case(session, original)
    try:
        _, _, _, entry, extracted = recheck_documents(
            body.documents,
            customer_id=original.customer_id,
            case_id=case_id,
            session=session,
            embedding_model=getattr(request.app.state, "embedding_model", None),
        )
    except (ValueError, TypeError, ArithmeticError, KeyError):
        raise ApiError(400, "INVALID_DOCUMENT", "A corrected value could not be read") from None
    AuditRepository.append(session, entry)
    session.commit()
    _write_sidecar(entry.run_id, extracted)
    logger.info("recheck case=%s run_id=%s route=%s", case_id, entry.run_id, entry.route.value)
    return _audit_response(entry, session)


@app.post("/runs/{run_id}/decision", response_model=AuditResponse, dependencies=[Depends(require_api_key)])
def decide_run(run_id: str, body: DecisionRequest, session: Session = Depends(get_session)) -> AuditResponse:
    """Record a reviewer's final decision (approve / reject) with a note."""
    original = _load_entry(session, run_id)
    case_id = _require_open_case(session, original)
    approve = body.decision == "approve"
    entry = AuditEntry(
        run_id=uuid4().hex,
        run_timestamp=datetime.now(UTC),
        invoice_number=original.invoice_number,
        po_number=original.po_number,
        grn_number=original.grn_number,
        pard_ref=original.pard_ref,
        route=Route.AUTO_APPROVE if approve else Route.REJECT,
        route_reason=RouteReason.REVIEWER_APPROVED if approve else RouteReason.REVIEWER_REJECTED,
        score_value=original.score_value,
        remark=f"Reviewer {'approved' if approve else 'rejected'}: {body.note.strip()}"[:1024],
        validation_failures=original.validation_failures,
        match_failures=original.match_failures,
        input_hash=original.input_hash,
        similarity_matches=original.similarity_matches,
        customer_id=original.customer_id,
        extraction_source=original.extraction_source,
        case_id=case_id,
        decided_by="reviewer",
    )
    AuditRepository.append(session, entry)
    session.commit()
    _write_sidecar(entry.run_id, _read_sidecar(original.run_id))
    logger.info("decision case=%s run_id=%s route=%s", entry.case_id, entry.run_id, entry.route.value)
    return _audit_response(entry, session)


@app.get("/review-queue", response_model=list[RecentRunOut], dependencies=[Depends(require_api_key)])
def get_review_queue(
    customer_id: str | None = None, limit: int = 200, session: Session = Depends(get_session)
) -> list[RecentRunOut]:
    """Cases waiting for a person: latest run is HUMAN_REVIEW, oldest first."""
    if not 1 <= limit <= 500:
        raise ApiError(400, "INVALID_LIMIT", "limit must be between 1 and 500")
    return [_recent_out(r) for r in review_queue(session, customer_id, limit)]


@app.get("/kpis/cases", response_model=RouteCountsOut, dependencies=[Depends(require_api_key)])
def kpis_cases(customer_id: str | None = None, session: Session = Depends(get_session)) -> RouteCountsOut:
    """Route counts per CASE (latest run of each submission)."""
    c = count_cases_by_route(session, customer_id)
    return RouteCountsOut(auto_approve=c.auto_approve, human_review=c.human_review, reject=c.reject, total=c.total)


@app.get("/kpis/failure-codes", response_model=list[CodeCountOut], dependencies=[Depends(require_api_key)])
def kpis_failure_codes(
    customer_id: str | None = None, limit: int = 8, session: Session = Depends(get_session)
) -> list[CodeCountOut]:
    if not 1 <= limit <= 50:
        raise ApiError(400, "INVALID_LIMIT", "limit must be between 1 and 50")
    return [CodeCountOut(code=c.code, count=c.count) for c in failure_code_counts(session, customer_id, limit)]


@app.get("/customers", response_model=list[str], dependencies=[Depends(require_api_key)])
def get_customers(session: Session = Depends(get_session)) -> list[str]:
    return list(list_customers(session))


# Browser frontend (static/index.html), served same-origin at / so the UI
# and the API share one URL. Mounted LAST so every API route above wins; the
# guard keeps the API working in trees/images without a frontend directory.
_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "static"
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
