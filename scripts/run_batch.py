#!/usr/bin/env python3
"""
Run the labeled batch through the pipeline and produce a structured
pass/fail report — the accuracy test (D-098, D-112).

Usage (on the GPU server, repo root, inside the apmatch:dev-gpu image):
  python scripts/run_batch.py \
      --batch-dir <path> \
      --csv <path>/labels.csv \
      --out reports/batch-<name>.json \
      [--backend vlm|ocr]          # default vlm (VLM first, OCR fallback)
      [--cache-dir <dir>]          # cache extractions; re-runs skip OCR/VLM
      [--style kh|us|in] [--cases CASE-0001,CASE-0007] [--limit N] [--resume]

Every case in the report carries the extracted documents and the extraction
diagnostics (source, VLM model/digest/prompt version, raw model output, field
errors), so failures can be diagnosed — and re-scored offline with
scripts/rematch_report.py — without re-running OCR or the VLM.

Uses run_pipeline() per case — no HTTP, no DB. The embedding model is loaded
once; the OCR engines are loaded lazily, only if some document falls back to
the OCR path.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Make `apmatch` importable when run as `python scripts/run_batch.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apmatch.evaluation import case_passed, format_summary, summarize

# CSV column -> run_pipeline kwarg.
DOC_FIELDS = {
    "invoice_file": "invoice_path",
    "po_file": "po_path",
    "grn_file": "grni_path",
    "pard_file": "pard_path",
}


def _serialize_failures(failures) -> list[dict]:
    return [
        {
            "code": f.code.value,
            "severity": f.severity.value,
            "location": f.location,
            "expected": f.expected,
            "actual": f.actual,
            "delta": f.delta,
        }
        for f in failures
    ]


def load_cases(csv_path: Path, style: str | None, cases: set[str] | None, limit: int | None) -> list[dict]:
    with csv_path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    if style:
        rows = [r for r in rows if r.get("style") == style]
    if cases:
        rows = [r for r in rows if r.get("case_id") in cases]
    rows.sort(key=lambda r: r.get("case_id", ""))
    if limit is not None:
        rows = rows[:limit]
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the labeled batch through the pipeline.")
    ap.add_argument("--batch-dir", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--backend", choices=("vlm", "ocr"), default="vlm")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--style", default=None)
    ap.add_argument("--cases", default=None, help="comma-separated case ids")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    # The pipeline reads the backend from the environment at call time.
    os.environ["EXTRACTION_BACKEND"] = args.backend

    batch_dir = Path(args.batch_dir)
    out_path = Path(args.out)
    progress_path = out_path.parent / f".{out_path.stem}.progress.json"
    case_filter = {c.strip() for c in args.cases.split(",")} if args.cases else None

    cases = load_cases(Path(args.csv), args.style, case_filter, args.limit)
    if not cases:
        print("error: no cases matched the filter", file=sys.stderr)
        sys.exit(2)

    done: dict[str, dict] = {}
    if args.resume and progress_path.is_file():
        try:
            done = json.loads(progress_path.read_text()).get("completed", {})
        except Exception:
            done = {}
        print(f"[resume] {len(done)} cases already done, skipping them")

    print(f"[init] backend={args.backend} cache={args.cache_dir or 'off'}; loading embedding model ...",
          flush=True)
    t0 = time.time()
    from apmatch.api.pipeline import invoice_key, lazy_ocr_engines, run_pipeline
    from apmatch.embeddings.model import EmbeddingModel
    from apmatch.parse import vlm

    router, layout = lazy_ocr_engines()
    embedding_model = EmbeddingModel()
    print(f"[init] ready in {time.time() - t0:.1f}s (embedding {embedding_model.model_version[:12]}..., "
          f"vlm model {vlm.VLM_MODEL} prompt {vlm.PROMPT_VERSION})", flush=True)

    # Duplicate check across the batch (D-116): supplier + invoice number seen
    # in an earlier case. Rebuilt from completed cases when resuming.
    from apmatch.schema.serialize import invoice_from_dict

    seen_invoices: dict = {}
    for prev in sorted(done.values(), key=lambda r: r["case_id"]):
        inv_doc = (prev.get("documents") or {}).get("invoice")
        if inv_doc and prev.get("run_id"):
            key = invoice_key(invoice_from_dict(inv_doc))
            if key is not None:
                seen_invoices.setdefault(key, prev["run_id"])

    results: list[dict] = []
    hard_errors = 0
    started_at = datetime.now(UTC)
    run_start = time.time()

    for i, row in enumerate(cases, start=1):
        case_id = row.get("case_id", f"row{i}")
        if case_id in done:
            results.append(done[case_id])
            continue

        style = row.get("style", "")
        expected = row.get("expected_status", "").strip()
        customer_id = f"batch_{style}" if style else "batch"

        paths: dict[str, Path | None] = {}
        missing_invoice = False
        for col, kwarg in DOC_FIELDS.items():
            rel = (row.get(col) or "").strip()
            p = batch_dir / rel if rel else None
            paths[kwarg] = p if p is not None and p.is_file() else None
            if kwarg == "invoice_path" and paths[kwarg] is None:
                missing_invoice = True

        t_case = time.time()
        base = {"case_id": case_id, "style": style, "expected": expected}
        if missing_invoice:
            result = dict(base, actual_route="ERROR", actual_reason="file_missing", passed=False,
                          failures=[], run_id=None)
        else:
            try:
                match, validation, decision, entry, extracted = run_pipeline(
                    paths["invoice_path"], paths["po_path"], paths["grni_path"], paths["pard_path"],
                    router=router, layout=layout,
                    embedding_model=embedding_model,
                    customer_id=customer_id,
                    extraction_cache_dir=args.cache_dir,
                    seen_invoices=seen_invoices,
                )
                route = decision.route.value
                extraction = extracted.pop("_extraction", {})
                result = dict(
                    base,
                    actual_route=route,
                    actual_reason=decision.reason.value,
                    passed=case_passed(expected, route),
                    match_outcome=match.outcome.value,
                    score=decision.score.value,
                    failures=_serialize_failures(validation.checks_failed)
                    + _serialize_failures(entry.match_failures),
                    similarity_matches=[
                        {"location": s.location, "invoice_text": s.invoice_text,
                         "counterpart_text": s.counterpart_text, "score": str(s.score), "band": s.band}
                        for s in match.similarity_matches
                    ],
                    run_id=entry.run_id,
                    documents=extracted,
                    extraction=extraction,
                )
            except Exception as e:  # keep going on a per-case crash
                hard_errors += 1
                result = dict(base, actual_route="ERROR",
                              actual_reason=f"{type(e).__name__}: {str(e)[:200]}",
                              passed=False, failures=[], run_id=None)
        result["duration_seconds"] = round(time.time() - t_case, 3)

        results.append(result)
        done[case_id] = result
        sources = ",".join(
            f"{k}:{str((v or {}).get('source') or '-')[:1]}" for k, v in (result.get("extraction") or {}).items() if v
        )
        line = (f"[{i}/{len(cases)}] {case_id} {expected} -> {result['actual_route']} "
                f"({'PASS' if result['passed'] else 'FAIL'}) {result['duration_seconds']}s {sources}")
        if result["actual_route"] == "ERROR":
            line += f"  [{result['actual_reason']}]"
        print(line, flush=True)

        if i % 10 == 0:
            progress_path.write_text(json.dumps({"completed": done}))

    finished_at = datetime.now(UTC)
    duration = time.time() - run_start
    summary = summarize(results)

    report = {
        "batch_id": started_at.strftime("%Y%m%dT%H%M%SZ"),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round(duration, 1),
        "batch_dir": str(batch_dir),
        "csv": str(args.csv),
        "backend": args.backend,
        "vlm_model": vlm.VLM_MODEL,
        "prompt_version": vlm.PROMPT_VERSION,
        "hard_errors": hard_errors,
        # Legacy top-level fields kept for older tooling.
        "total": summary["total"],
        "passed": summary["passed"],
        "failed": summary["failed"],
        "pass_rate": summary["pass_rate"],
        "by_style": summary["by_style"],
        "by_expected": summary["by_expected"],
        "summary": summary,
        "cases": results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    progress_path.write_text(json.dumps({"completed": done}))

    print()
    print(format_summary(summary))
    print(f"hard errors: {hard_errors}   duration: {duration / 60:.1f} min")
    print(f"report: {out_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
