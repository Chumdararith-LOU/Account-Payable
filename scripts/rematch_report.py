#!/usr/bin/env python3
"""
Re-score a batch report offline: validation + matching + routing only.

Reads a report written by scripts/run_batch.py (which stores each case's
extracted documents), rebuilds the documents, runs the deterministic half of
the pipeline again with the CURRENT code, and prints the new accuracy summary
plus every case whose route changed. No OCR, no VLM, no GPU — it runs in
seconds on any machine.

Use it to try a matching/routing change against real extractions before
paying for a full batch run.

Usage:
  python scripts/rematch_report.py reports/batch-vlm-YYYYMMDD.json
      [--embeddings]          # load the MiniLM model (needs models/embeddings)
      [--out reports/rematch.json]
      [--show-failures]       # print the failure codes of every failing case
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apmatch.api.pipeline import decide_documents
from apmatch.evaluation import case_passed, format_summary, summarize
from apmatch.parse.derive import derive
from apmatch.schema.serialize import documents_from_canonical


def rescore(report: dict, embedding_model=None) -> list[dict]:
    out = []
    for case in report["cases"]:
        docs = case.get("documents")
        if not docs:
            out.append(dict(case))  # ERROR / missing-file cases stay as they were
            continue
        invoice, po, grni, pard = (derive(d) for d in documents_from_canonical(docs))
        validation, match, decision = decide_documents(invoice, po, grni, pard, embedding_model)
        route = decision.route.value
        failures = [
            {"code": f.code.value, "severity": f.severity.value, "location": f.location,
             "expected": f.expected, "actual": f.actual}
            for f in (*validation.checks_failed, *match.failures)
        ]
        out.append(dict(
            case,
            previous_route=case.get("actual_route"),
            actual_route=route,
            actual_reason=decision.reason.value,
            passed=case_passed(case["expected"], route),
            failures=failures,
        ))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-score a batch report with the current logic.")
    ap.add_argument("report")
    ap.add_argument("--embeddings", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--show-failures", action="store_true")
    args = ap.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    if not any(c.get("documents") for c in report["cases"]):
        print("error: this report has no stored documents (made by an older run_batch.py)",
              file=sys.stderr)
        sys.exit(2)

    embedding_model = None
    if args.embeddings:
        from apmatch.embeddings.model import EmbeddingModel

        embedding_model = EmbeddingModel()

    before = summarize(report["cases"])
    results = rescore(report, embedding_model)
    after = summarize(results)

    print(f"before: {before['passed']}/{before['total']}   after: {after['passed']}/{after['total']}")
    changed = [r for r in results if r.get("previous_route") and r["previous_route"] != r["actual_route"]]
    for r in changed:
        print(f"  {r['case_id']} {r['expected']}: {r['previous_route']} -> {r['actual_route']} "
              f"({'PASS' if r['passed'] else 'FAIL'})")
    if args.show_failures:
        for r in results:
            if not r["passed"]:
                codes = sorted({f["code"] for f in r.get("failures", [])})
                print(f"  FAIL {r['case_id']} {r['style']} {r['expected']} -> {r['actual_route']}: "
                      f"{', '.join(codes)}")
    print(format_summary(after))

    if args.out:
        Path(args.out).write_text(json.dumps(dict(report, summary=after, cases=results), indent=1,
                                             ensure_ascii=False))
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
