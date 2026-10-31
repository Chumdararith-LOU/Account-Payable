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

import logging
import re
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apmatch.api import config
from apmatch.api.pipeline import run_pipeline
from apmatch.api.schemas import (
    AuditResponse,
    ErrorResponse,
    FailureOut,
    HealthResponse,
    MatchResponse,
    RecentRunOut,
    RouteCountsOut,
    SimilarityMatchOut,
)
from apmatch.audit.entry import AuditEntry
from apmatch.audit.kpis import count_by_route, recent_runs
from apmatch.audit.repository import AuditEntryNotFound, AuditRepository

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


def _failure_out(failure) -> FailureOut:
    return FailureOut(
        code=failure.code.value,
        severity=failure.severity.value,
        location=failure.location,
        expected=failure.expected,
        actual=failure.actual,
        delta=failure.delta,
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
            _, _, decision, entry = run_pipeline(
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
    return _audit_response(entry)


def _audit_response(entry: AuditEntry) -> AuditResponse:
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
    )


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
    return [
        RecentRunOut(
            run_id=r.run_id,
            run_timestamp=r.run_timestamp,
            invoice_number=r.invoice_number,
            route=r.route.value,
            route_reason=r.route_reason.value,
            score=float(r.score_value),
            remark=r.remark,
        )
        for r in recent_runs(session, limit, customer_id)
    ]
