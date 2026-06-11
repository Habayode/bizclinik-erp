# Trakit365 ERP — Path to a Great Accounting Product

Reviewer roles: chartered-accountant + financial-reporting lens, product-manager lens.
Status today: a working ERP with double-entry GL, sales/purchase/inventory/banking/payroll/reports,
deployed at `erp.hagai.online`. To go from "works for one SME" → "the obvious choice for
Nigerian SMEs", here is what's missing and how I'd sequence the work.

The TL;DR

1. **Trust** the books — audit trail, period close, reversal workflow.
2. **Fit** Nigeria — graduated PAYE, FIRS e-invoice, WHT certificates, Moniepoint imports.
3. **Sell** to many customers — multi-tenant, users + roles, billing, onboarding.

---

## Tier 1 — Required before a single paying client trusts it

These are not nice-to-haves. They are what makes the difference between "a Streamlit app" and
"accounting software your auditor will sign off on".

### 1.1 Audit trail on every record
Today: a row gets created, you can't see who or when.

Add to every model:
- `created_by_user_id`, `created_at`
- `modified_by_user_id`, `modified_at`
- `version` (optimistic lock counter)

Plus a separate `audit_log` table with `(timestamp, user_id, entity_type, entity_id,
action, before_snapshot, after_snapshot)` and a Streamlit "Audit log" page on the
General Ledger module.

**Why it matters:** every external audit asks "who posted this entry, and when". Currently
the only answer is "the app". That alone disqualifies us from any regulated client.

**Effort:** 2–3 days. Touches every service + UI + a one-time DB migration.

### 1.2 Users + roles + per-module permissions
Today: single password gate. Everyone can do everything.

Required minimum roles:
- **Admin** — anything, including period close
- **Accountant** — post JEs, run reports, manage masters
- **Sales clerk** — create quotes/SOs/invoices/receipts only
- **AP clerk** — bills/payments only
- **View-only** — reports + master records read

Wire `streamlit-authenticator` or build a small `User`/`Role`/`Permission` table.
Lock pages behind `require_role()` checks.

**Why:** the moment you have 2 humans using the same DB, you need to know which one
issued an ₦8m credit note.

**Effort:** 4–5 days.

### 1.3 Fiscal periods + period close
Today: nothing stops you from back-dating a JE into last year's already-published P&L.

Add `fiscal_period(id, year, month, status)` with status in `{open, closed, locked}`.
`post_journal()` refuses entries whose `entry_date` falls in a `closed` period unless the
poster has the `period_override` permission. Closing a period writes a row that's
visible in the GL.

**Why:** without this, "Net Profit YTD" can silently change after the fact — a fireable
offense in any real business.

**Effort:** 2 days.

### 1.4 Reverse / void workflow
Today: to undo a posted invoice you'd manually post a reversing JE and hope to remember
the linkage.

Add a single `services.ledger.reverse_journal()` UI flow (the function already exists),
and "Void invoice"/"Void bill"/"Void receipt" actions that:
1. Post the reversing JE.
2. Flip the source document to `status=CANCELLED`.
3. Store the reversal link both ways (`reversed_by_je_id`, `reverses_je_id`).

Surface as a button on each document page with a confirmation modal.

**Why:** accountants reverse, they don't delete. The current UX implies deletion.

**Effort:** 1–2 days.

### 1.5 Real bank reconciliation
Today: `services.banking.reconcile()` returns a single number — "you're off by ₦27,400".
Useless beyond that.

Build a proper reconciliation:
- `bank_statement(id, bank_account_id, period_start, period_end, opening_bal, closing_bal, status)`
- `bank_statement_line(id, statement_id, date, description, amount, reference, matched_je_line_id)`
- CSV importer for Moniepoint / GTB / Access / FBN / Zenith export formats
- Auto-match by `(amount, date ± 3 days)` against unreconciled bank-account JE lines
- UI: side-by-side panes — statement on left, GL on right; click to match; remaining
  unmatched items become reconciling items in the snapshot
- "Mark statement reconciled" locks the matches and produces a printable reconciliation report

**Why:** bank rec is the single most common task an SME accountant does. Doing it well
is the #1 reason to switch from QuickBooks.

**Effort:** 1–1.5 weeks. The importer code is the bulk.

### 1.6 Proper Nigerian PAYE
Today: per-employee flat `paye_rate`. Wrong.

Implement the CITA-graduated bands (₦300k @ 7%, next 300k @ 11%, etc.) plus:
- Consolidated relief allowance (₦200k + 20% of gross)
- Pension contribution exemption (7.5% × gross)
- NHIS, NHF deductions

Surface in Settings → Payroll as configurable bands so the rates can move when FIRS
updates them without a code change.

**Why:** flat-rate PAYE is wrong for everyone. Real-world net pay calculations will
differ from ours by 5–15% — the first thing an HR officer will spot.

**Effort:** 3–4 days, well-tested.

### 1.7 Fixed-asset register + auto-depreciation
Today: 1210 Equipment and 1290 Accumulated Depreciation accounts exist, but there is
no per-asset record.

Add:
- `fixed_asset(id, code, name, category, acquired_date, cost, useful_life_months,
  salvage_value, depreciation_method, gl_asset_account_id, gl_dep_account_id, gl_exp_account_id)`
- Monthly "Run depreciation" action that posts JEs: DR Depreciation Expense / CR Accumulated Depreciation
- Disposal workflow with gain/loss on disposal posting
- Asset register report (cost, accumulated dep, NBV per asset)

**Why:** without this, fixed assets just sit on the BS forever. Depreciation never hits
the P&L. The numbers are silently wrong.

**Effort:** 1 week.

---

## Tier 2 — What makes it Nigerian-first, not generic

Once Tier 1 lands you have *correct* accounting. Tier 2 is what makes it the *obvious*
choice over Sage / Zoho / QuickBooks for an SME in Lagos.

### 2.1 FIRS e-invoice export
Required for VAT-registered businesses post-2026. The FIRS portal accepts a specific
JSON schema. Generate it from a posted invoice with one click, plus the QR code that
must be printed on every invoice.

**Effort:** 1 week including schema validation.

### 2.2 WHT certificates
Generate FIRS WHT-002 PDF certificate per supplier per period showing each invoice,
WHT rate, WHT amount. Bulk-print at month-end.

**Effort:** 3 days (template + report).

### 2.3 Bank-statement parsers for Nigerian banks
Each bank exports a different mess of a CSV/PDF. Build per-bank parsers:
- Moniepoint (CSV)
- GTBank (Excel + PDF)
- Access (CSV)
- Zenith (Excel)
- First Bank (PDF — needs OCR)
- UBA (CSV)

Drop the file in, parser normalizes to `bank_statement_line` rows.

**Effort:** 1 day per bank, ongoing.

### 2.4 Recurring transactions
Monthly rent, subscriptions, salaries, retainer invoices. Define once, auto-post on
schedule. Reuses the journal-entry service.

**Effort:** 4 days.

### 2.5 Multi-currency + FX
Suppliers in USD, customers in NGN. Add:
- `currency(code, name)` and `exchange_rate(currency, date, rate)`
- Documents carry `currency` + `fx_rate_at_posting`
- Realized FX gain/loss posted at settlement
- Unrealized FX revaluation JE at period-end
- Reports default to functional currency (NGN) with a toggle

**Effort:** 1.5 weeks. Touches every transaction model.

### 2.6 Customer statements + email
Generate a PDF "Statement of Account" for any customer showing aged outstanding
invoices. One-click email via SMTP.

**Effort:** 3 days.

### 2.7 Budgets + variance reporting
Define a monthly budget per account. Reports tab gets a "Budget vs Actual" view with
variance % and a waterfall chart for the biggest swings.

**Effort:** 1 week.

### 2.8 Accrual & adjusting entry helpers
A guided "Month-end close" workflow:
- Accrued salaries, prepaid expenses, deferred revenue, accrued interest
- Each one a templated JE with the period dates pre-filled

**Effort:** 4 days.

---

## Tier 3 — Product, not project

This is what turns the codebase into a sellable SaaS that HAG_Ai's consulting clients
sign up for in 5 minutes.

### 3.1 Multi-tenant
Each business gets its own SQLite file (or Postgres schema) in
`data/tenants/{tenant_slug}/`. Subdomain routing (`acme.erp.hagai.online`) or path
routing. Auth tied to a `tenant_user` table.

**Effort:** 2 weeks. Touches db.py, every page, hosting.

### 3.2 Onboarding wizard
First-time setup walkthrough:
1. Company info (name, RC, address, fiscal year)
2. Industry → suggested COA template (retail, services, manufacturing, hospitality)
3. Opening balances entry
4. First user invite
5. Optional BizClinik xlsx import

**Effort:** 1 week.

### 3.3 Mobile-responsive UI
Streamlit is OK on tablets, awkward on phones. Two options:
- Add `st.html` overrides to fix the column collapse + KPI tile reflow
- Build a thin React frontend over a FastAPI version of the services layer (much
  bigger lift but unlocks a real mobile experience)

I'd start with option A — 3 days — and only do B if real customer demand emerges.

### 3.4 Custom invoice / statement templates
Today: ReportLab hardcoded layout. Customer wants their logo. Add `invoice_template`
table with chosen colors, logo path, header HTML, footer HTML.

**Effort:** 1 week.

### 3.5 Automated backups
Nightly SQLite snapshot → Cloudflare R2 (or B2, or S3). One-click restore. 30-day
retention. Critical the moment you have real customer money in the books.

**Effort:** 2 days.

### 3.6 Payments + subscriptions (if commercializing)
Stripe + Paystack integration. Monthly plan tiers. Free trial. Self-serve cancel.

**Effort:** 1 week.

### 3.7 API + webhooks
`POST /api/invoices` for POS / e-comm integrations. Webhook fire on `invoice.paid`,
`bill.overdue`. Token-scoped per tenant.

**Effort:** 1.5 weeks.

### 3.8 Notifications
Daily email digest: top 5 overdue invoices, upcoming bills, cash position.
Threshold alerts: bank balance below ₦X, stock below reorder level.

**Effort:** 1 week.

---

## Foundations to fix while doing the above

These are technical debts that will hurt later if left untreated.

### F.1 Production-grade Streamlit deployment
Today's pain: Scheduled Task / cloudflared / Streamlit keep losing each other after
restarts. Move to **NSSM** for Streamlit + cloudflared as proper Windows services with
log files. Or migrate to a Linux VPS with systemd — Streamlit + cloudflared both run
cleanly there with one-liner unit files.

### F.2 Test suite
`pytest` against the services layer, asserting accounting invariants:
- TB always balances after every test scenario
- Inventory weighted-avg cost is monotonic on receipts
- Revaluation entries reverse cleanly
- Period close blocks back-dating

This is the #1 thing that lets us refactor with confidence later.

**Effort:** 1 week to a meaningful base.

### F.3 SQLite → Postgres path
SQLite is fine to ~1M rows / single tenant. Multi-tenant + real concurrent users →
Postgres. SQLAlchemy 2.0 lets us swap with a connection-string change — but date,
boolean and JSON types want testing.

Plan now, switch when first paying customer crosses a usage threshold.

### F.4 CI/CD
GitHub Actions: lint + pytest on PR, auto-tag releases, auto-deploy to VPS on merge to
`main`. Today every change is a manual zip-and-RDP.

**Effort:** 2 days.

### F.5 Observability
Sentry for Python errors. Lightweight uptime ping (Better Uptime / UptimeRobot) on the
public URL. A small daily-snapshot script that captures TB totals and emails the diff
— if our numbers move unexpectedly we want to know within hours, not weeks.

**Effort:** 1 day.

---

## What I'd actually do — sequenced

Concrete next 12-week plan, in order of dependency and ROI:

| Week | Build | Why now |
|------|-------|---------|
| 1 | Audit trail + period close (Tier 1.1, 1.3) | Foundation everything else needs |
| 2 | NSSM service install + test suite skeleton (F.1, F.2) | Stop the deploy bleeding |
| 3 | Users + roles (Tier 1.2) | Unlocks multi-person use today |
| 4 | Void/reverse workflow + graduated PAYE (Tier 1.4, 1.6) | Closes biggest correctness gaps |
| 5–6 | Real bank reconciliation + Moniepoint parser (Tier 1.5, 2.3) | The single biggest day-to-day pain we kill |
| 7 | Fixed assets + depreciation (Tier 1.7) | Required for accurate P&L/BS |
| 8 | Onboarding wizard + automated backups (Tier 3.2, 3.5) | Lets first paying client self-serve |
| 9–10 | Multi-tenant + Postgres migration (Tier 3.1, F.3) | Unlocks selling to more than one customer |
| 11 | FIRS e-invoice + WHT certificates (Tier 2.1, 2.2) | The marquee Nigerian differentiator |
| 12 | Stripe/Paystack billing + API + webhooks (Tier 3.6, 3.7) | Commercialization |

After week 12 you're competing seriously with QuickBooks/Zoho/Sage in this market —
and beating them on Nigerian-specific compliance.

---

## What I would *not* build (yet)

- Full IFRS notes / accounting policies module — most SMEs don't need this; consultancy
  wrap-around can deliver it on top
- Manufacturing BOM / work-order tracking — too far from core; chase only if a customer demands it
- Mobile native app (iOS/Android) — responsive web is good enough until 100+ paying SMEs
- Built-in payroll tax filing to FIRS — wait until they publish the API; XML export
  meanwhile is enough

---

## How to know we're winning

Success metrics for the next quarter:
- **Trust:** 100% of test scenarios assert TB-balanced + audit-trail present
- **Speed:** time to first invoice on a fresh tenant < 5 min
- **Accuracy:** independent CA can sign off the P&L without manual adjustments
- **Stickiness:** 2nd-month retention > 80% on paid tenants
- **Differentiation:** FIRS e-invoice export demoed and working before any competitor

Final note — Tier 1.1 (audit trail) is the single highest-leverage thing on this list.
Until it ships, every other feature carries the asterisk "but who actually did this".
Start there.
