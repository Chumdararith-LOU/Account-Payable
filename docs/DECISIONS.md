# DECISIONS.md — decision log

| ID | Decision | Date | Rationale |
|---|---|---|---|
| D-001 | Use conda env `anpr` as the Phase 1 dev env | 2026-09-26 | Only env on this machine with the Paddle stack plus a Khmer-OCR candidate; rebuilding from scratch is expensive. |
| D-002 | No generative model in the decision path | 2026-09-26 | From Plan.md §5. Remarks become deterministic Python templates. |
| D-003 | PP-OCRv6 comes via `paddleocr>=3.7.0`, not a standalone pkg | 2026-09-26 | Verified in P1-00. |
| D-004 | Khmer OCR is a separate model, not part of PP-OCRv6 | 2026-09-26 | Verified in P1-00; candidate: `tror-yong-ocr` (unaudited). |
| D-005 | Remove LLM/generative code entirely | 2026-09-26 | Plan.md §5 requires a deterministic decision path. Deleted: remark_generator.py, set_api_key_visible.py, .env (contained ANTHROPIC_API_KEY). No LLM call remains in the repo. Deterministic template remark module arrives in P1-07. |
