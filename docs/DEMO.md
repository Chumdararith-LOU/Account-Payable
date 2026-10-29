# Demo Day Narrative

**Audience:** SME prospects (hotel, restaurant) and possibly a partner or
investor.

**Duration:** 10 minutes spoken, 5 minutes Q&A.

**Technical prerequisite:** the deployed server is live at
`http://100.88.94.91:8001` (verified via `/healthz` 10 minutes before the
demo). The pipeline runs on the GPU — a single 4-document case takes ~15–20s.

## The pitch (1 minute)

> "You send me invoices. I process them for you. You get a decision within
> 30 minutes: approved, rejected, or flagged for your review. You pay per
> document — no subscription. Your data never leaves my server. Every
> decision is logged with a hash of the original documents, so if there's
> ever a dispute, we can prove what was seen and what was decided. No AI
> black box — every rejection is explainable."

## The 5-minute live demo

### Setup (30 seconds)

Show the four demo fixture images on screen (PO, Invoice, GRN, PARD). Same
transaction, four documents. Point out that a few line-item descriptions are
worded differently between the PO and the Invoice (e.g. "office chair" vs
"chair, office, metal frame, black") — that's the part the system has to
bridge.

### Step 1 — Run the pipeline (~20 seconds)

```bash
python scripts/run_demo_case.py
```

**Narrate while it runs:** "This is the four documents for one invoice. OCR
reads them, extracts the fields, validates the arithmetic, and matches them
against each other. On my GPU server this takes about 15 seconds."

**Expected output:**
```
Route:            AUTO_APPROVE
Score:            1.0000
Invoice number:   INV-2026-1123
Remark:           Validated OK.

Similarity matches: 6  (embedding fallback)
  - [accept] chair, office, metal frame, black ~ office chair  (score 0.7344)
  - [accept] lamp for desk, adjustable ~ desk lamp  (score 0.8832)
  ...
```

**The before/after story (this is the point):** "Six of these line items are
worded differently on the PO versus the Invoice. A naive exact-match would
have flagged all six as mismatches and sent this to a human. The system
falls back to a deterministic similarity check, matches all six (every score
is above the 0.70 auto-accept line), and approves the invoice. That's the
difference between 'reject anything that isn't character-identical' and
'understand the documents'."

### Step 2 — Show the audit trail (90 seconds)

```bash
APMATCH_API_KEY=... curl -sS \
  -H "X-API-Key: $KEY" \
  "http://100.88.94.91:8001/audit/<run_id>"
```

**Narrate:** "Here's the audit row. It has the exact route decision, the
exact rule that fired, the exact OCR text, the six similarity scores with
their thresholds, and a SHA-256 hash of the four input documents. If this
SME ever disputes the decision six months from now, we can show them exactly
what happened. That's the audit trail that makes this defensible for their
accountant."

### Step 3 — Show the KPIs (60 seconds)

```bash
APMATCH_API_KEY=... curl -sS \
  -H "X-API-Key: $KEY" \
  "http://100.88.94.91:8001/kpis/routes?customer_id=demo"
```

**Narrate:** "Per-customer metrics. This is what makes the BPO model work —
I can tell you exactly how many of Hotel A's invoices were auto-approved
last month, how many needed review, and how many were rejected. You get the
same view for your own invoices in your monthly statement."

### Step 4 — Close (30 seconds)

> "The system is running today. If you have invoices from last month, I can
> process a sample batch for free this week, show you the auto-processing
> rate on your actual documents, and you can decide based on real numbers,
> not a demo."

## Q&A preparation

**Q: What if a document has a format you've never seen?**
A: "Every SME sends a different format. The first time I see one, I add a
template. It takes 15–30 minutes per vendor format. The pipeline handles the
new format automatically from then on. This is a one-time onboarding cost,
usually absorbed into the first month's invoice."

**Q: What happens if the system can't read something?**
A: "It routes to human review. You see exactly which field couldn't be read
and why, and one of my team checks it. That's the review queue — usually
10–20% of documents."

**Q: What if my invoice format changes?**
A: "The system detects the change and flags new documents for review. You or
I add a new template in 15 minutes. No downtime."

**Q: Is this using AI?**
A: "It uses AI for OCR — reading the text from images. It does NOT use an
LLM for decisions. Every decision is a deterministic rule. That's why every
rejection is explainable and every audit row has a hash. If you ask 'why was
this rejected', the system points to the exact rule that fired."

**Q: What about data privacy?**
A: "The pipeline runs entirely on my server. Your documents are tagged with a
customer_id and never touch the internet. No external APIs, no cloud AI. The
full pipeline is air-gapped once deployed. This matters for accounting firms
and anyone with data residency requirements."

**Q: What does it cost?**
A: "$0.25 per document. No setup fee for the first three vendors. Volume
discounts above 1,000 documents/month. The first 100 documents processed for
free so you can see the accuracy on your real invoices."

**Q: What if I disagree with a rejection?**
A: "Reply to the rejection email with the reason. The audit log shows the
exact rule that fired and the OCR text that was read. If it's an OCR
mistake, we fix the template. If it's a genuine mismatch, we can override and
learn from the correction (a new exception rule for that vendor). Every
override is logged."

## What NOT to show

- Don't show the code (unless specifically asked).
- Don't demo the /batch endpoint (not built yet).
- Don't promise "any invoice format" — promise "your formats, after a
  15-minute template setup."
- Don't say "AI-powered" as a headline — say "deterministic and auditable"
  as the headline.

## Fallback if the server is down

- **Fallback 1:** run the pipeline locally on the Mac. Same script,
  `--server http://localhost:8000`. Requires the local dev deployment up.
- **Fallback 2:** show the saved output. `docs/demo-screenshots/` has
  `expected-output.txt` (the full terminal output) and `expected-audit.json`
  (the audit row) from a real run — paste them on screen.

## Pre-demo checklist (run 30 minutes before)

- [ ] `curl http://100.88.94.91:8001/healthz` returns ok
- [ ] `python scripts/run_demo_case.py` runs clean (test it)
- [ ] `docs/demo-screenshots/` output is current (regenerate if the server
      was redeployed)
- [ ] Demo machine connected to the same network (Tailscale) as the server
- [ ] Terminal font size increased (16pt+)
- [ ] Browser zoom set if showing JSON output
- [ ] Phone on silent
