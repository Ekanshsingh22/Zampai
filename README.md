# Invoice AP Processor (PS-1: PDF → reasoned decision)

## Run it (2 minutes)
```
pip install -r requirements.txt
python gen.py        # creates data/vendors.csv, data/pos.csv, samples/*.pdf
python app.py        # open http://localhost:5000
```
Optional: `export ANTHROPIC_API_KEY=...` enables an LLM fallback that fills missing invoice no./date/total when the rule-based parser fails (told to return null rather than guess).

## Process map
Invoice PDF → 1 Ingest → 2 Extract text (no text layer ⇒ REVIEW/OCR) → 3 Parse fields (regex over multiple layouts; fuzzy vendor match) → 4 Completeness (missing ⇒ HOLD) → 5 Arithmetic (subtotal+tax=total) → 6 Vendor master (blocked ⇒ REJECT, unknown ⇒ REVIEW) → 7 Duplicate check (vendor + invoice no.) → 8 PO match (explicit ref, else infer if vendor has exactly one PO) → 9 Amount check against *remaining* PO balance, 2% tolerance → Decision + plain-English reason, stored in SQLite.

Decisions: **APPROVED · REVIEW** (human needed) **· HOLD** (go back to vendor) **· REJECTED**.

## Assumptions (state these in the interview)
- Invoices arrive as PDFs; test data is synthetic (2 invoice layouts, 4 vendors, 4 POs).
- Tolerance = 2% of PO amount, applied to *cumulative* billing, not per invoice.
- Only APPROVED invoices count toward PO billed amount. Duplicate = same vendor + invoice number against an APPROVED/REVIEW run.
- Deterministic rules decide; AI is only an extraction fallback, so every decision is auditable. Never auto-approve when unsure: ambiguity routes to REVIEW.
- Out of scope: OCR (scanned → REVIEW), multi-currency, line-item/GRN 3-way match, email ingestion, auth.

## Demo script – run in this order
| # | File | Shows | Expected |
|---|------|-------|----------|
| 1 | 01_happy_acme | Happy path | APPROVED, 4,400 of 10,000 |
| 2 | 02_tolerance_globex | Near-miss amount | APPROVED, 0.83% over (within 2%) |
| 3 | 03 + 04 split_initech | One PO split over two invoices | Both APPROVED; PO fully billed 5,000/5,000 |
| 4 | 05_duplicate_acme | Resubmitted invoice in a different layout | REJECTED duplicate of run #1 |
| 5 | 06_missing_fields | No invoice no. / date | HOLD, back to vendor |
| 6 | 07_blocked_umbrella | Blocked vendor | REJECTED |
| 7 | 08_over_po_acme | Cumulative over PO by 76% | REVIEW, escalate to buyer |
| 8 | 09_implied_po_hooli | No PO reference | APPROVED, PO inferred |
| 9 | 10_scanned_image | No text layer | REVIEW (needs OCR) |
Click "Reset demo data" on the Dashboard before every recording or interview.

## 5-minute video script
- 0:00–0:30 Problem and who it's for (tired AP clerk on a Friday). Show the 9-step pipeline.
- 0:30–1:45 Happy path: run #1 live, narrate each stage; open Dashboard.
- 1:45–4:15 Edge cases: split PO (3+4), duplicate (5), missing fields (6), over-PO (8). For each: why the logic behaves differently, and what a human sees.
- 4:15–5:00 Design choices: rules decide, AI assists; REVIEW over guessing; what I'd build next (OCR, email intake, 3-way match, ERP write-back).

## Likely interview questions
- Why deterministic rules instead of an LLM deciding? → auditability, no hallucinated approvals.
- Why tolerance on cumulative billing? → prevents slow overbilling via many small invoices.
- What breaks? → unseen layouts (LLM fallback helps), scans (needs OCR), vendor-name variants below 0.8 similarity.
- Next: Tesseract/vision OCR, Gmail ingestion, line-item matching, approval workflow, audit export.
