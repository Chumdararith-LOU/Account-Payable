"""Batch evaluation metrics — the accuracy test (D-098, D-112).

Pure, stdlib-only. Shared by ``scripts/run_batch.py`` (full run on the GPU
server) and ``scripts/rematch_report.py`` (offline re-scoring of a stored
report), so both report exactly the same numbers.

Pass rule per case (unchanged from PROD-B0):
  expected MATCH        -> pass if route == AUTO_APPROVE
  expected DISCREPANCY  -> pass if route in (HUMAN_REVIEW, REJECT)
  expected PENDING INFO -> pass if route == HUMAN_REVIEW

The pass rate alone is misleading: routing EVERY case to HUMAN_REVIEW already
passes all DISCREPANCY and PENDING INFO cases. So the summary also reports:
  - straight_through: MATCH cases auto-approved (the product's value)
  - false_approvals:  DISCREPANCY / PENDING INFO cases auto-approved
                      (the money-losing error; must be 0)
  - review_all_baseline: the pass rate of "send everything to a human"

Acceptance target (D-112): passed >= TARGET_PASSED AND false_approvals == 0.
"""

from __future__ import annotations

PASS_ROUTES = {
    "MATCH": {"AUTO_APPROVE"},
    "DISCREPANCY": {"HUMAN_REVIEW", "REJECT"},
    "PENDING INFO": {"HUMAN_REVIEW"},
}

TARGET_PASSED = 100  # of the 120-case labeled batch (D-098 target "100+")


def case_passed(expected: str, route: str) -> bool:
    return route in PASS_ROUTES.get(expected, set())


def summarize(results: list[dict]) -> dict:
    """Aggregate per-case results (each has expected, actual_route, passed, style)."""
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    by_style: dict[str, dict] = {}
    by_expected: dict[str, dict] = {}
    routes: dict[str, dict[str, int]] = {}
    for r in results:
        for key, bucket in ((r.get("style", ""), by_style), (r["expected"], by_expected)):
            b = bucket.setdefault(key, {"total": 0, "passed": 0, "failed": 0})
            b["total"] += 1
            b["passed" if r["passed"] else "failed"] += 1
        row = routes.setdefault(r["expected"], {})
        row[r["actual_route"]] = row.get(r["actual_route"], 0) + 1

    match_total = by_expected.get("MATCH", {}).get("total", 0)
    straight = sum(1 for r in results if r["expected"] == "MATCH" and r["actual_route"] == "AUTO_APPROVE")
    false_approvals = [
        r["case_id"] for r in results
        if r["expected"] != "MATCH" and r["actual_route"] == "AUTO_APPROVE"
    ]
    review_all = sum(1 for r in results if case_passed(r["expected"], "HUMAN_REVIEW"))

    sources: dict[str, int] = {}
    vlm_failures = 0
    for r in results:
        for info in (r.get("extraction") or {}).values():
            if not info:
                continue
            src = info.get("source") or "unknown"
            sources[src] = sources.get(src, 0) + 1
            if (info.get("vlm") or {}).get("error"):
                vlm_failures += 1

    def rate(n: int, d: int) -> float:
        return round(n / d, 4) if d else 0.0

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": rate(passed, total),
        "straight_through": {"passed": straight, "total": match_total, "rate": rate(straight, match_total)},
        "false_approvals": {"count": len(false_approvals), "case_ids": false_approvals},
        "review_all_baseline": {"passed": review_all, "rate": rate(review_all, total)},
        "target": {
            "passed_min": TARGET_PASSED,
            "false_approvals_max": 0,
            "met": passed >= TARGET_PASSED and not false_approvals,
        },
        "route_matrix": routes,
        "by_style": by_style,
        "by_expected": by_expected,
        "extraction_sources": sources,
        "vlm_failures": vlm_failures,
    }


def format_summary(s: dict) -> str:
    """Human-readable summary block for the console."""
    lines = [
        "=" * 64,
        f"PASSED {s['passed']}/{s['total']} ({s['pass_rate'] * 100:.1f}%)   "
        f"target >= {s['target']['passed_min']} with 0 false approvals: "
        f"{'MET' if s['target']['met'] else 'NOT MET'}",
        f"straight-through (MATCH -> AUTO_APPROVE): {s['straight_through']['passed']}/"
        f"{s['straight_through']['total']} ({s['straight_through']['rate'] * 100:.1f}%)",
        f"false approvals (must be 0): {s['false_approvals']['count']} "
        f"{s['false_approvals']['case_ids'] or ''}",
        f"'send everything to review' baseline: {s['review_all_baseline']['passed']}/{s['total']}",
        "route matrix (expected -> actual):",
    ]
    for exp in sorted(s["route_matrix"]):
        cells = ", ".join(f"{k} {v}" for k, v in sorted(s["route_matrix"][exp].items()))
        lines.append(f"  {exp:<13} {cells}")
    lines.append("by style: " + ", ".join(
        f"{k} {v['passed']}/{v['total']}" for k, v in sorted(s["by_style"].items())
    ))
    if s["extraction_sources"]:
        lines.append(
            "extraction sources: "
            + ", ".join(f"{k} {v}" for k, v in sorted(s["extraction_sources"].items()))
            + f"   (VLM failures: {s['vlm_failures']})"
        )
    lines.append("=" * 64)
    return "\n".join(lines)
