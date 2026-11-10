"""Accuracy-test metrics and offline re-scoring of a stored batch report."""

import json
from pathlib import Path

from apmatch.evaluation import case_passed, format_summary, summarize, target_passed
from scripts.rematch_report import rescore

FIXTURES = Path(__file__).resolve().parents[1] / "integration" / "fixtures"


def _r(case_id, expected, route, style="kh"):
    return {"case_id": case_id, "style": style, "expected": expected, "actual_route": route,
            "passed": case_passed(expected, route)}


def test_pass_rules():
    assert case_passed("MATCH", "AUTO_APPROVE")
    assert not case_passed("MATCH", "HUMAN_REVIEW")
    assert case_passed("DISCREPANCY", "REJECT") and case_passed("DISCREPANCY", "HUMAN_REVIEW")
    assert not case_passed("DISCREPANCY", "AUTO_APPROVE")
    assert case_passed("PENDING INFO", "HUMAN_REVIEW") and not case_passed("PENDING INFO", "REJECT")


def test_summary_reports_the_honest_numbers():
    results = [
        _r("C1", "MATCH", "AUTO_APPROVE"),
        _r("C2", "MATCH", "HUMAN_REVIEW"),
        _r("C3", "DISCREPANCY", "REJECT"),
        _r("C4", "DISCREPANCY", "AUTO_APPROVE"),  # the dangerous error
        _r("C5", "PENDING INFO", "HUMAN_REVIEW", style="us"),
    ]
    s = summarize(results)
    assert s["passed"] == 3
    assert s["straight_through"] == {"passed": 1, "total": 2, "rate": 0.5}
    assert s["false_approvals"] == {"count": 1, "case_ids": ["C4"]}
    assert s["review_all_baseline"]["passed"] == 3  # C3, C4, C5 would pass as HUMAN_REVIEW
    assert s["route_matrix"]["DISCREPANCY"] == {"REJECT": 1, "AUTO_APPROVE": 1}
    assert s["target"]["met"] is False and s["target"]["passed_min"] == 5
    text = format_summary(s)
    assert "false approvals (must be 0): 1" in text and "NOT MET" in text


def test_target_scales_with_batch_size():
    assert target_passed(120) == 100
    assert target_passed(200) == 167


def _docs(path: Path) -> dict:
    return {k: json.loads((path / f"{k}.json").read_text()) for k in ("invoice", "po", "grni", "pard")}


def test_rescore_rebuilds_documents_and_reroutes():
    report = {"cases": [
        dict(_r("C1", "MATCH", "HUMAN_REVIEW"), documents=_docs(FIXTURES / "happy_path")),
        dict(_r("C2", "DISCREPANCY", "AUTO_APPROVE"), documents=_docs(FIXTURES / "discrepancy_path")),
        dict(_r("C3", "MATCH", "ERROR")),  # no documents: left as is
    ]}
    out = {r["case_id"]: r for r in rescore(report)}
    assert out["C1"]["actual_route"] == "AUTO_APPROVE" and out["C1"]["passed"]
    assert out["C1"]["previous_route"] == "HUMAN_REVIEW"
    assert out["C2"]["actual_route"] in ("HUMAN_REVIEW", "REJECT") and out["C2"]["passed"]
    assert out["C3"]["actual_route"] == "ERROR"
