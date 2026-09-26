"""
remark_generator.py

Turns raw AP-matching findings into a short, reviewer-facing one-line
remark using the Claude API (Claude Haiku 4.5). Falls back to the raw
reason text if no ANTHROPIC_API_KEY is configured, or if the API call
fails for any reason — the pipeline never depends on the LLM step to
function, matching the "graceful degradation" design already described
in the project proposal (Section 8).

Setup:
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."      # or put it in a .env file

Usage (from ai_engine.py):
    from remark_generator import generate_remark

    remark = generate_remark(
        status="DISCREPANCY",
        reasons=["Qty Invoiced (12) > Qty Received (10)",
                 "Price variance 6.2% exceeds 5% tolerance"],
        case_id="INV-2026-1123",
    )
    # -> "Quantity and price both exceed tolerance; hold for reviewer sign-off."
"""

import os
from anthropic import Anthropic

MODEL = "claude-haiku-4-5-20251001"

_client = None


def _get_client():
    """Lazily create the Anthropic client so a missing API key doesn't
    crash at import time — only when a remark is actually requested."""
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        _client = Anthropic(api_key=api_key)
    return _client


def generate_remark(status: str, reasons: list, case_id: str = "") -> str:
    """
    Generate a one-line, reviewer-facing remark summarizing why a case
    was routed to MATCH / DISCREPANCY / PENDING INFO.

    Args:
        status: one of "MATCH", "DISCREPANCY", "PENDING INFO"
        reasons: list of raw reason strings from the rule engine, e.g.
                 ["Qty Invoiced (12) > Qty Received (10)",
                  "Price variance 6.2% exceeds 5% tolerance"]
        case_id: optional invoice/case id, used only for error logging

    Returns:
        A short remark string for the MATCH_RESULT.Remark field.
        Falls back to a plain join of the raw reasons if no API key is
        set or the call fails — this function never raises.
    """
    raw_fallback = "; ".join(reasons) if reasons else f"{status}: no issues found."

    client = _get_client()
    if client is None:
        return raw_fallback

    prompt = (
        f"You are summarizing an accounts-payable matching result for a "
        f"human reviewer. Status: {status}. Raw findings: "
        f"{'; '.join(reasons) if reasons else 'none'}. "
        f"Write ONE short, plain-English sentence (under 20 words) a "
        f"reviewer can scan quickly. No preamble, just the sentence."
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=60,
            messages=[{"role": "user", "content": prompt}],
        )
        remark = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        return remark or raw_fallback
    except Exception as e:
        print(f"⚠️  Claude API remark generation failed for {case_id or '(case)'}: {e}")
        print("    Falling back to raw reason text.")
        return raw_fallback


if __name__ == "__main__":
    # Quick manual test — run directly with: python remark_generator.py
    test_cases = [
        ("MATCH", [], "INV-TEST-001"),
        (
            "DISCREPANCY",
            ["Qty Invoiced (12) > Qty Received (10)",
             "Price variance 6.2% exceeds 5% tolerance"],
            "INV-TEST-002",
        ),
        ("PENDING INFO", ["PO not found for vendor ABC Ltd"], "INV-TEST-003"),
    ]
    for status, reasons, case_id in test_cases:
        print(f"[{case_id}] {status} -> {generate_remark(status, reasons, case_id)}")