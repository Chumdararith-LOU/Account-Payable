# DECISIONS.md — decision log

| ID | Decision | Date | Rationale |
|---|---|---|---|
| D-001 | Use conda env `anpr` as the Phase 1 dev env | 2026-09-26 | Only env on this machine with the Paddle stack plus a Khmer-OCR candidate; rebuilding from scratch is expensive. |
| D-002 | No generative model in the decision path | 2026-09-26 | From Plan.md §5. Remarks become deterministic Python templates. |
| D-003 | PP-OCRv6 comes via `paddleocr>=3.7.0`, not a standalone pkg | 2026-09-26 | Verified in P1-00. |
| D-004 | Khmer OCR is a separate model, not part of PP-OCRv6 | 2026-09-26 | Verified in P1-00; candidate: `tror-yong-ocr` (unaudited). |
| D-005 | Remove LLM/generative code entirely | 2026-09-26 | Plan.md §5 requires a deterministic decision path. Deleted: remark_generator.py, set_api_key_visible.py, .env (contained ANTHROPIC_API_KEY). No LLM call remains in the repo. Deterministic template remark module arrives in P1-07. |
| D-006 | Vendor PP-OCRv6 weights into models/, enforce offline env vars | 2026-09-26 | HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1, PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True set inside LatinOCREngine.__init__ before paddleocr import. Proven by scripts/verify_offline.py, which blocks socket.connect and runs a full OCR pass. |
| D-007 | Vendor tror-yong-ocr weights to models/khmer | 2026-09-26 | tror-yong-ocr's PyTorchModelHubMixin.from_pretrained is the documented entry point and reaches HF at runtime without a local path. Vendored copy + HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1 make Khmer OCR fully offline. Proven by scripts/verify_offline_khmer.py. |
| D-008 | Khmer engine default seed = 168 | 2026-09-26 | Determinism requires a fixed seed for the sampling-based API. Value locked in apmatch/ocr/khmer.py. (Engine also runs greedy, temperature=0, and zeroes the package's attention-dropout probabilities, which the functional SDPA applies even in eval mode.) |
| D-009 | PP-StructureV3 for tables, weights vendored alongside PP-OCRv6 | 2026-09-27 | Deterministic table/layout extraction; no generative postprocessing. HTML output matches the prototype JSON schema verbatim. Offline proven by scripts/verify_offline_structure.py. |
| D-010 | Disable formula/seal/chart recognition in PP-StructureV3, drop PP-FormulaNet weights | 2026-09-27 | AP invoices contain none of these. Disabling saves 702 MB of vendored cache and simplifies the offline footprint. No functional impact on table extraction. |
| D-011 | Frozen dataclasses in apmatch/schema/, Decimal-only money, float rejection | 2026-09-27 | Prevents silent monetary drift; schema is the contract every downstream module consumes. |
| D-012 | ValidationResult uses enum codes + severity, not message strings | 2026-09-27 | Keeps remarks, matching, and audit log decoupled from each other. New failure modes are added by extending CheckCode, never by string-matching messages. |
| D-013 | tax_rate/discount_rate optional; two-mode tax/discount checks | 2026-09-27 | When a rate is provided, TAX_MISMATCH is a real arithmetic check (BLOCKER). When absent, it degrades to a sanity check (WARNING) with an explicit "sanity-only" location tag so audit logs are unambiguous. |
| D-014 | Drop created_at from document dataclasses | 2026-09-27 | DB metadata, not document content. Keeps validation results reproducible across runs. |
| D-015 | Template-based remarks, no LLM | 2026-09-27 | Replaces the deleted remark_generator.py (D-005). Every CheckCode maps to exactly one template string. Import-time assertion fails loudly if a code lacks a template; silent fallbacks are forbidden. Determinism and no-LLM-in-path are both regression-tested. |
| D-016 | summarize() contract: "N issue(s). Most severe: ..." for multi-failure results | 2026-09-27 | The result's checks_failed tuple is already ordered by severity (P1-06 contract), so summarize() can trust the first element. Removes ambiguity for reviewers reading logs. |
| D-017 | Tolerances are Python constants, not config files | 2026-09-27 | Determinism and reviewability; config files invite per-install drift and hidden state. |
| D-018 | normalize_text strips only low-risk OCR noise | 2026-09-27 | The /[a-z]{1,8}\b regex targets observed noise (e.g. "/nnw") while preserving legitimate slashes followed by uppercase, digits, or long runs. Errs toward keeping content. |
| D-019 | Legacy ai_engine.py is not ported directly; its normalize_text and tolerances are re-derived here | 2026-09-27 | P1-08b builds on these primitives; the legacy file will be replaced (not refactored in place) when the new engine lands. |
