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
