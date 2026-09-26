AI-Powered AP Invoice Matching — Project Proposal
From hackathon prototype to production system Prepared by: Kong Vong & Team | Turing Hackathon Cycle 11

1. Executive Summary
The team has already validated a working prototype (7 of 11 core components complete) that automates 4-way AP reconciliation — matching Purchase Orders, Goods Received Notes, Invoices, and Payment Advice documents. The architecture is being hardened toward a fully deterministic, hallucination-resistant pipeline: classical (non-generative) OCR for text recognition, deterministic layout/table structuring, arithmetic self-consistency checks, and template-based (not LLM-generated) reviewer remarks — meaning no document content ever needs to leave the customer's infrastructure or touch an external API. This proposal lays out the plan to finish the MVP on that architecture, land a credible first customer, and sequence go-to-market around what actually works in Cambodia: lead with on-premise sales into banks, use that as a reference case to open a BPO/accounting-firm channel, and treat self-serve SaaS as a secondary tier rather than the primary engine.

2. Problem Statement
AP reconciliation across PO, GRNI, Invoice, and Payment Advice documents is still mostly manual for mid-sized enterprises, banks, and government finance teams. It's slow, error-prone, and hard to audit. In lower-wage markets like Cambodia, the standard "we save you headcount" pitch is weaker than in the US/EU, since manual reconciliation labor is comparatively cheap — so the value case has to rest on speed, accuracy, and auditability rather than labor-cost replacement.

3. Objectives
Convert the validated prototype into a production-ready MVP.
Land one reference customer — ideally a bank, where data-sovereignty needs make the on-premise pitch strongest and procurement is faster than government.
Stand up a repeatable go-to-market motion across the three pricing models already scoped.
4. Proposed Solution
An engine that ingests PO, GRNI, Invoice, and PARD documents via classical OCR, validates extracted fields against configurable matching/tolerance rules and arithmetic self-consistency checks, flags discrepancies with a confidence score, and routes each case to one of three outcomes: Match, Discrepancy, or Pending Info. A template-based Python module turns the rule engine's output into a one-line, plain-language remark for the reviewer — fully deterministic, so the same input always produces the same remark, with no generative model anywhere in the decision path.

5. System Architecture & Tech Stack
Layer	Choice	Notes
Text recognition (Latin/numeric)	PaddleOCR PP-OCRv6 (self-hosted)	Classical detect-then-classify, not generative; open source; fast enough on CPU alone
Text recognition (Khmer script)	Dedicated Khmer model (community PaddleOCR build or Tesseract Khmer pack)	PP-OCRv6's unified model doesn't cover Khmer script; route by detected script
Layout & table structuring	PaddleOCR PP-StructureV3	Deterministic table/layout detection; exports directly to structured Markdown
Validation layer	Arithmetic self-consistency checks (pure Python)	Line items vs. subtotal, tax math, format checks — catches misreads before they reach the decision
Matching engine	Deterministic rule engine	Every decision explainable; not a black box
Confidence scoring	OCR confidence + discrepancy count + validation-check pass/fail	Drives human-review routing
Reviewer remarks	Template-based Python module	Deterministic, zero cost, zero external calls
Storage	Migrate SQLite (prototype) → PostgreSQL	Needed for production concurrency and reporting
Deployment	Docker, on-prem or private cloud	REST API for ERP integration; CPU-only viable
Data privacy boundary: with the remark-generation LLM replaced by a template module, the entire pipeline can now run with zero external API calls — document images and all extracted data can stay fully on the customer's infrastructure. This meaningfully strengthens the Model 2 "no internet required" pitch to banks and government.

6. Development Roadmap
Phase	Focus	Rough duration
0 — Done	Hackathon prototype, 7/11 components validated end-to-end	Complete
1	Upgrade to PP-OCRv6 + PP-StructureV3, add Khmer-script recognition module and script-routing, build the arithmetic validation layer, replace LLM remarks with the template module, migrate to PostgreSQL, harden dashboard & audit logging	5–7 weeks
2	Pilot with one design-partner bank	6–10 weeks
3	Package pilot as reference case; open BPO/accounting-firm channel conversations	Ongoing after Phase 2
4	Broader GTM across all three pricing models	Post-pilot
7. Go-to-Market & Pricing
Model 2 (On-premise, $15K–30K + 20% AMS) — the lead wedge. Banks and large conglomerates have the budget, and "no internet required, full data control" is a genuinely sharp pitch for them. Consider separating a professional-services/implementation fee from the license, and scaling the license by institution size rather than one flat band.
Model 3 (White-label BPO enabler) — second wave, sold through accounting/audit firms already serving the garment-manufacturing and foreign-SME base, using the bank pilot as proof. Per-document tiers still need real numbers (draft off Model 1's ~$0.30/doc baseline with volume discounts) before this goes in front of a partner.
Model 1 (Self-serve SaaS, $99/$299/mo) — keep as a secondary tier for already-digitized or foreign-managed businesses. Reframe the pitch around speed and audit trail rather than labor savings, and consider annual pre-paid contracts to sidestep the fact that recurring card billing isn't the local default.
8. Target Segments in Cambodia
Banks and large conglomerates (Model 2 lead)
Government/MEF-adjacent bodies — approach only through formal tender channels, not a cold pitch, given slow, largely manual procurement processes
Manufacturing and garment-sector companies, noting many are foreign-owned and decisions may run through a regional or HQ buyer
Accounting firms and shared-service/BPO operators serving the SME layer (Model 3 channel)
9. Risks & Mitigations
Risk	Mitigation
Government procurement is slow and still largely manual	Don't lead the pipeline with government; use a bank pilot first
Recurring card billing isn't the local default	Move to annual, invoiced contracts
Cambodia's domestic market is small relative to global SaaS benchmarks	Treat Cambodia as a reference-customer market; plan regional expansion (Vietnam/Thailand) once there's a proof point
Model 3 pricing is still undefined	Finalize per-doc tiers before any partner conversation
General OCR/VLM models perform poorly on native Khmer script	Use a dedicated Khmer-trained model alongside PP-OCRv6, validated on real bilingual samples before launch
10. Success Metrics
Remaining 4/11 prototype components shipped
Arithmetic-validation pass rate and dual-engine agreement rate on a real bilingual document sample
One signed pilot in the Model 2 segment
Match accuracy and time-to-reconcile vs. the manual baseline
MRR & churn (Model 1) · signed license value (Model 2) · partner count & throughput (Model 3)
11. Team
Kong Vong · Lou Chandaerith (AI Engineer) · Thai Taiwan (Team Lead) · Pholl Chanphayuk (Cloud Engineer) · Bun Sengleang (IT Engineer) · Loy Lyher (Marketing & Growth)

12. Ask
[Fill in: funding/runway needed for Phase 1–2, target pilot introduction, or hackathon-specific ask.]

This proposal synthesizes the technical prototype, pricing analysis, and Cambodia market context already developed by the team.