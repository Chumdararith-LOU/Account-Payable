#!/usr/bin/env python3
"""
Run the labeled batch through the pipeline and produce a structured
pass/fail report.

Usage:
  python scripts/run_batch.py \
      --batch-dir <path> \
      --csv <path>/labels.csv \
      --out reports/batch-<date>.json \
      [--style kh|us|in] \
      [--limit N] \
      [--resume]

Runs on the GPU server (inside the apmatch:dev-gpu image). Uses
run_pipeline() per case — no HTTP, no DB. The heavy engines (OCR router,
layout, embedding model) are loaded ONCE and shared across cases.

Stdlib only for file/CLI/json (json, csv, argparse, pathlib, time, datetime).
The apmatch pipeline imports are the legitimate heavy dependencies.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Route mapping (fixed, documented):
#   expected MATCH        -> pass if route == AUTO_APPROVE
#   expected DISCREPANCY  -> pass if route in (HUMAN_REVIEW, REJECT)
#   expected PENDING INFO -> pass if route == HUMAN_REVIEW
PASS_ROUTES = {
    "MATCH": {"AUTO_APPROVE"},
    "DISCREPANCY": {"HUMAN_REVIEW", "REJECT"},
    "PENDING INFO": {"HUMAN_REVIEW"},
}

# CSV column -> run_pipeline kwarg.
DOC_FIELDS = {
    "invoice_file": "invoice_path",
    "po_file": "po_path",
    "grn_file": "grni_path",
    "pard_file": "pard_path",
}


def _serialize_failures(failures) -> list[dict]:
    out = []
    for f in failures:
        out.append({
            "code": f.code.value,
            "severity": f.severity.value,
            "location": f.location,
            "expected": f.expected,
            "actual": f.actual,
            "delta": f.delta,
        })
    return out


def load_cases(csv_path: Path, style: str | None, limit: int | None) -> list[dict]:
    with csv_path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    if style:
        rows = [r for r in rows if r.get("style") == style]
    rows.sort(key=lambda r: r.get("case_id", ""))
    if limit is not None:
        rows = rows[:limit]
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the labeled batch through the pipeline.")
    ap.add_argument("--batch-dir", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--style", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    batch_dir = Path(args.batch_dir)
    csv_path = Path(args.csv)
    out_path = Path(args.out)
    progress_path = out_path.parent / ".run_batch_progress.json"

    cases = load_cases(csv_path, args.style, args.limit)
    if not cases:
        print("error: no cases matched the filter", file=sys.stderr)
        sys.exit(2)

    # Resume: load already-completed case results.
    done: dict[str, dict] = {}
    if args.resume and progress_path.is_file():
        try:
            done = json.loads(progress_path.read_text()).get("completed", {})
        except Exception:
            done = {}
        print(f"[resume] {len(done)} cases already done, skipping them")

    # Load the heavy engines ONCE.
    print("[init] loading OCR router, layout engine, embedding model ...", flush=True)
    t0 = time.time()
    from apmatch.api.pipeline import run_pipeline
    from apmatch.embeddings.model import EmbeddingModel
    from apmatch.layout.structure import LayoutEngine
    from apmatch.ocr.router import OCRRouter

    router = OCRRouter()
    layout = LayoutEngine()
    embedding_model = EmbeddingModel()
    print(f"[init] engines ready in {time.time() - t0:.1f}s "
          f"(embedding version {embedding_model.model_version[:12]}...)", flush=True)

    results: list[dict] = []
    hard_errors = 0
    started_at = datetime.now(timezone.utc)
    run_start = time.time()

    for i, row in enumerate(cases, start=1):
        case_id = row.get("case_id", f"row{i}")
        if case_id in done:
            results.append(done[case_id])
            continue

        style = row.get("style", "")
        expected = row.get("expected_status", "").strip()
        customer_id = f"batch_{style}" if style else "batch"

        # Build absolute paths; empty/missing doc -> None.
        paths: dict[str, Path | None] = {}
        missing_invoice = False
        for col, kwarg in DOC_FIELDS.items():
            rel = (row.get(col) or "").strip()
            if not rel:
                paths[kwarg] = None
                if kwarg == "invoice_path":
                    missing_invoice = True
            else:
                p = batch_dir / rel
                paths[kwarg] = p if p.is_file() else None
                if kwarg == "invoice_path" and not p.is_file():
                    missing_invoice = True

        t_case = time.time()
        if missing_invoice:
            result = {
                "case_id": case_id, "style": style, "expected": expected,
                "actual_route": "ERROR", "actual_reason": "file_missing",
                "passed": False, "duration_seconds": round(time.time() - t_case, 3),
                "failures": [], "run_id": None,
            }
        else:
            try:
                _, validation, decision, entry = run_pipeline(
                    paths["invoice_path"], paths["po_path"],
                    paths["grni_path"], paths["pard_path"],
                    router=router, layout=layout,
                    embedding_model=embedding_model,
                    customer_id=customer_id,
                )
                route = decision.route.value
                passed = route in PASS_ROUTES.get(expected, set())
                failures = _serialize_failures(validation.checks_failed) + \
                    _serialize_failures(entry.match_failures)
                result = {
                    "case_id": case_id, "style": style, "expected": expected,
                    "actual_route": route, "actual_reason": decision.reason.value,
                    "passed": passed,
                    "duration_seconds": round(time.time() - t_case, 3),
                    "failures": failures, "run_id": entry.run_id,
                }
            except Exception as e:  # keep going on a per-case crash
                hard_errors += 1
                result = {
                    "case_id": case_id, "style": style, "expected": expected,
                    "actual_route": "ERROR", "actual_reason": f"{type(e).__name__}: {str(e)[:200]}",
                    "passed": False, "duration_seconds": round(time.time() - t_case, 3),
                    "failures": [], "run_id": None,
                }

        results.append(result)
        done[case_id] = result
        line = (f"[{i}/{len(cases)}] {case_id} {expected} -> {result['actual_route']} "
                f"({'PASS' if result['passed'] else 'FAIL'}) {result['duration_seconds']}s")
        if result["actual_route"] == "ERROR":
            line += f"  [{result['actual_reason']}]"
        print(line, flush=True)

        # Checkpoint every 10 cases.
        if i % 10 == 0:
            progress_path.write_text(json.dumps({"completed": done}, indent=2))

    # Finalize.
    finished_at = datetime.now(timezone.utc)
    duration = time.time() - run_start
    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    by_style: dict[str, dict] = {}
    by_expected: dict[str, dict] = {}
    for r in results:
        for key, bucket in ((r["style"], by_style), (r["expected"], by_expected)):
            b = bucket.setdefault(key, {"total": 0, "passed": 0, "failed": 0})
            b["total"] += 1
            if r["passed"]:
                b["passed"] += 1
            else:
                b["failed"] += 1

    report = {
        "batch_id": started_at.strftime("%Y%m%dT%H%M%SZ"),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round(duration, 1),
        "batch_dir": str(batch_dir),
        "csv": str(csv_path),
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / len(results), 4) if results else 0.0,
        "hard_errors": hard_errors,
        "by_style": by_style,
        "by_expected": by_expected,
        "cases": results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    progress_path.write_text(json.dumps({"completed": done}, indent=2))

    # Summary table.
    print("\n" + "=" * 60)
    print(f"Total: {len(results)}  Passed: {passed}  Failed: {failed}  "
          f"Rate: {report['pass_rate'] * 100:.1f}%  Hard errors: {hard_errors}")
    print(f"Duration: {duration / 60:.1f} min")
    print("By style:")
    for s in sorted(by_style):
        c = by_style[s]
        print(f"  {s}: {c['passed']}/{c['total']}")
    print("By expected:")
    for e in sorted(by_expected):
        c = by_expected[e]
        print(f"  {e}: {c['passed']}/{c['total']}")
    print(f"Report: {out_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
