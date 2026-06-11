# BizClinik ERP — User Manual

**A complete, worked guide — built around a real case-study company, *GreenLeaf Stores Ltd*, with a full month of transactions posted across every module and the resulting financial statements.**

Every financial figure in this manual is *real*: it was produced by posting the transactions below into a live copy of the system (`scripts/demo_seed.py`) and reading back the actual reports. Nothing is invented. (The newer People & HR, Approvals and Plans sections describe how those modules work, with worked examples.)

- **Case study:** GreenLeaf Stores Ltd — a Lagos retail + delivery SME
- **Period:** May 2026
- **Result:** Trial Balance **₦9,541,875 DR = ₦9,541,875 CR** (balanced ✓)
- **Workspace:** the ERP groups every module into **Overview · Finance & Accounting · CRM · HR · System**, with an always-available help assistant.

---

## How to read this manual

| Part | What it covers |
|------|----------------|
| **1. Getting started** | Logging in, the layout, the dashboard |
| **2. Data model** | Every record type, its key fields, and a real example |
| **3. Onboarding** | Setting up GreenLeaf (company, COA, customers, suppliers, products, staff, bank, branding) |
| **4. Module guide** | Each module: what it does → the flow → the GL impact → GreenLeaf's real entries. Includes **People & HR** and **Approvals** |
| **5. The month in review** | GreenLeaf's full May 2026, transaction by transaction |
| **6. Reports** | The actual P&L, Balance Sheet, Cash Flow, agings, VAT, budget — with figures |
| **7. Platform features** | Multi-business, plans & access, approvals, REST API, billing, backups, the assistant |
| **8. Screenshots** | Visual reference of each screen |

> **Conventions.** *DR* = debit, *CR* = credit. Every transaction posts a **balanced double-entry journal** automatically — you never touch the ledger by hand. The functional currency is the **Naira (₦)**; foreign documents post to the ledger in ₦ at the day's rate.

---

# 1. Getting started

## 1.1 Signing in
Open the app URL in any browser. You'll see the **sign-in card**. Enter your **username** and **password** (your administrator creates user accounts under *Settings → Users*). After five wrong attempts the session locks — refresh to retry.

> On a brand-new install the first sign-in uses the bootstrap admin (`admin`) with the password set during setup.

## 1.2 The layout
- **Left sidebar** — navigation, organised into collapsible **groups** so related modules sit together:
  - **Overview** — Dashboard
  - **Finance & Accounting** — Sales, Purchases, Inventory, Banking, Bank Reconciliation, Fixed Assets, Recurring, FIRS E-invoice, Currencies, General Ledger, Budgets, Month-End, Statements, Reports, **Approvals**
  - **CRM** — Leads, pipeline, follow-ups
  - **HR** — Employees, Recruitment, Leave, Payroll
  - **System** — Onboarding, Settings, Admin, Notifications, Data, Tenants, Billing, **User Manual**
- **Main panel** — the active module.
- **Plan badge** — the active subscription plan shows in the sidebar; **Sign-out** is at the bottom.
- **Help assistant** — a floating **💬 bubble** (bottom-right of every page) answers how-to questions *and* questions about your live numbers (e.g. "What's my revenue this month?", "How many approvals are pending?").
- **This manual** is also available inside the app under **System → User Manual**.

## 1.3 The dashboard (Home)
The Home page is a live snapshot **as of today**, showing:
- **KPI cards** — Revenue YTD, Direct Costs, Operating Expenses, Net Profit; Cash & Bank, Inventory at Cost, AR/AP Outstanding; Total Assets / Liabilities / Equity and a **Balance Sheet: Balanced ✓** check.
- **Performance chart** — revenue vs expense by month.
- **Expenses by account** — where the money goes.

For GreenLeaf at month-end, the dashboard shows **Total Assets ₦7,435,375**, **Balanced ✓**, **Cash & Bank ₦2,914,425**.

![GreenLeaf dashboard](manual_images/01_dashboard.png)

---

# 2. Data model — every record, with a real example

BizClinik is a double-entry ledger with master data in front of it. These are the record types you'll work with.

### Company
The business profile printed on documents and used for tax IDs.
| Field | Example (GreenLeaf) |
|-------|---------------------|
| name | GreenLeaf Stores Ltd |
| rc_number | RC 1843022 |
| tin | TIN-20471188-0001 |
| address | 14 Adeniyi Jones Avenue, Ikeja, Lagos |
| email / phone | accounts@greenleafstores.ng · +234 803 555 0142 |
| vat_number | TIN-20471188-0001 |

### Account (Chart of Accounts)
A node in the ledger. Hierarchical (parent → children); only **postable** leaf accounts take entries.
| Field | Example |
|-------|---------|
| code · name | `1130` · Accounts Receivable |
| type | ASSET / LIABILITY / EQUITY / INCOME / EXPENSE |
| parent_id | `1100` Current Assets |
| is_postable | true |

GreenLeaf uses the seeded Nigerian SME chart (44 accounts): 1000 Assets, 1120 Bank, 1130 AR, 1140 Inventory, 1150 Input VAT, 1210 Equipment, 1290 Accumulated Depreciation, 2110 AP, 2120 Output VAT, 2140 Pension Payable, 2160 Accrued Expenses, 3100 Share Capital, 4100 Sales, 5100 COGS, 6100 Salaries … 6600 Depreciation.

### Customer / Supplier
| Field | Customer example | Supplier example |
|-------|------------------|------------------|
| code · name | C001 · Sunrise Restaurant Ltd | S001 · FreshFarm Produce Ltd |
| email · phone · address | pay@sunrise.ng · 0803… · 5 Allen Ave | sales@freshfarm.ng · 0701… |

### Product
A thing you sell/stock. **Stockable** products carry inventory + average cost; **service** products don't.
| Field | Example (stockable) | Example (service) |
|-------|---------------------|-------------------|
| sku · name | RICE50 · Rice 50kg Bag | DELIV · Delivery Service |
| unit | bag | trip |
| standard_price / standard_cost | 45,000 / 38,000 | 5,000 / 0 |
| is_stockable | true | false |

### Employee
| Field | Example |
|-------|---------|
| code · name | E001 · Chioma Okeke |
| monthly_gross | 250,000 |
| pension_rate (employee) | 8% |
| pension_employer_rate | 10% |

### Sales Invoice / Bill (and their lines)
A customer invoice (AR) or supplier bill (AP). Each has **lines** (product/description, qty, unit price/cost, tax rate), a status, `amount_paid`, and — for foreign documents — `currency_code` + `fx_rate`.
*Example:* Invoice INV-2026-0001 to Sunrise — 10 × Rice @ ₦45,000 + 1 × Delivery @ ₦5,000, 7.5% VAT → grand total **₦489,025**.

### Receipt / Payment
Cash in from a customer / cash out to a supplier, linked to an invoice/bill and a bank account.

### Journal Entry / Journal Line
The underlying double-entry record. Every document above generates one or more balanced journal entries automatically; you can also post manual journals.

### Other records
**FixedAsset** (register + depreciation), **BankStatement / BankStatementLine** (reconciliation), **RecurringTemplate** (auto-repeating documents), **Budget / BudgetLine**, **Currency / ExchangeRate**, **InvoiceTemplate** (per-business branding), **Lead / Deal / Activity** (CRM), **JobOpening / Candidate / JobApplication** and **LeaveRequest** (HR), **ApprovalLimit / ApprovalRequest** (approval workflow), and the multi-tenant **Tenant / Subscription** control-plane records.

---

# 3. Onboarding GreenLeaf Stores Ltd

A new business is set up once. Here's GreenLeaf's setup (all under **Settings**, plus **Currencies** and **CRM**).

1. **Company profile** — name, RC, TIN, address, contact (Settings → Company).
2. **Invoice branding** — accent colour `#0A7D33`, payment instructions *"GTBank 0123456789 — GreenLeaf Stores Ltd"*, thank-you note, footer (Settings → Invoice template).
3. **Chart of Accounts** — the Nigerian SME template is seeded automatically; extend as needed.
4. **Customers** — C001 Sunrise Restaurant, C002 Mama Tobi Kitchen, C003 Adeyemi Household, C004 Global Imports LLC (US, invoiced in USD).
5. **Suppliers** — S001 FreshFarm Produce, S002 PackRight Supplies, S003 Lagos Properties.
6. **Products** — RICE50, OIL25, CARTON (stockable) and DELIV (service).
7. **Employees** — E001 Chioma (₦250k), E002 Bola (₦180k), E003 Emeka (₦120k).
8. **Bank account** — Primary Bank (GL 1120). A Cash account is also seeded.
9. **Opening capital** — the owner injects **₦5,000,000**: *DR Bank 5,000,000 / CR Share Capital 5,000,000*.

---

# 4. Module guide — flow + GL impact + GreenLeaf entries

## 4.1 Sales
**What it does:** quotes → invoices → receipts, tracking what customers owe (AR).
**Flow:** *(Optional)* create a **Quotation** → convert to **Sales Order** → **Issue Invoice** → **Record Receipt** when paid.
**GL impact of issuing an invoice (in ₦):**
```
DR Accounts Receivable     gross
   CR Sales                 net
   CR Output VAT            VAT
DR Cost of Goods Sold      cost      (stockable lines)
   CR Inventory            cost
```
plus a stock movement reducing on-hand for each stockable line.

**GreenLeaf's May invoices:**
| Invoice | Customer | Lines | Grand total |
|---------|----------|-------|-------------|
| INV-2026-0001 | Sunrise Restaurant | 10 Rice + 1 Delivery | ₦489,025 |
| INV-2026-0002 | Mama Tobi Kitchen | 8 Veg Oil | ₦283,800 |
| INV-2026-0003 | Adeyemi Household | 2 Rice + 20 Cartons | ₦135,450 |
| INV-2026-0004 | Global Imports (USD) | 10 Veg Oil export @ $25 | $250 (₦387,500 @ 1,550) |

Receipts: Sunrise and Mama Tobi paid in full (DR Bank / CR AR). Adeyemi (₦135,450) and the USD invoice remain open at month-end — see AR aging.

## 4.2 Purchases
**What it does:** supplier bills (AP) → payments. Inventory bills raise stock; expense/asset bills hit the right account.
**Flow:** *(Optional)* Purchase Order → **Receive Bill** → **Record Payment**.
**GL impact of receiving a stock bill:** `DR Inventory + DR Input VAT / CR Accounts Payable`. A non-stock line posts to whichever account you choose (an expense like Rent, or a fixed-asset account like Equipment).

**GreenLeaf's May bills:**
| Bill | Supplier | Content | Effect |
|------|----------|---------|--------|
| Stock #1 | FreshFarm | 40 Rice + 30 Oil | +Inventory ₦1,520,000, +Input VAT ₦114,000 |
| Stock #2 | PackRight | 500 Cartons | +Inventory ₦600,000 |
| Equipment | PackRight | Cold-room freezer | DR Equipment ₦1,800,000 |
| Rent | Lagos Properties | May rent | DR Rent & Utilities ₦350,000 |

Payments: rent ₦350,000 and ₦2,000,000 to FreshFarm were paid; the rest sit in AP (see AP aging).

## 4.3 Inventory
Inventory is **driven by purchases and sales** — you rarely touch it directly. Receiving a bill increases on-hand at cost; selling decreases it and books COGS at **average cost**. GreenLeaf ends May with **₦1,976,000** of inventory at cost.

## 4.4 Banking & Bank reconciliation
**Banking** records bank charges and transfers. **Bank Reconciliation** matches a bank statement to the ledger.
**Flow:** create a **statement** for the period → **import lines** (paste/upload CSV from GTB/Access/Zenith/FBN/Moniepoint, *or* push them in via the API) → **auto-match** (amount within ₦0.01, date within ±3 days) → review unmatched → **finalize**.
GreenLeaf imported its May GTBank statement (capital, rent, the Sunrise receipt, a ₦2,500 charge); auto-match cleared 4 lines.

## 4.5 Payroll
**What it does:** runs Nigerian **graduated PAYE** + pension and posts the payroll journal.
**Flow:** pick the period + pay date → select employees (gross defaults from each employee) → **Run Payroll**. The system computes banded PAYE, 8% employee pension, 10% employer pension, and posts salaries, the pension liability, and the net paid from the bank.
GreenLeaf's May run (3 staff, ₦550,000 gross): **Salaries ₦550,000**, **Employer pension ₦55,000**, **Pension Payable ₦99,000**.

## 4.6 Fixed assets & depreciation
**Flow:** **Add Asset** (cost, useful life, salvage, the asset/accum-dep/expense accounts) → run **Depreciation** at month-end (straight-line). Depreciation begins the **month after** acquisition, so GreenLeaf's freezer (acquired 3 May) starts depreciating in June — May shows ₦0, which is correct.
GreenLeaf asset: **FA-001 Cold-room Freezer**, ₦1,800,000, 60 months, ₦300,000 salvage → ₦25,000/month from June.

## 4.7 Multi-currency & FX
Invoice/bill in any currency; the ledger posts in ₦ at the rate. On settlement, the difference vs the booking rate is a **realized FX gain/loss**. At month-end, open foreign balances can be **revalued** (unrealized).
GreenLeaf's USD export ($250 @ ₦1,550 = ₦387,500). With the rate rising to ₦1,600 by 31 May, the **unrealized FX gain = ₦12,500** (Currencies → Run revaluation).

## 4.8 Recurring transactions
Set up a template (invoice/bill/journal) with a frequency; the system raises the document when due. GreenLeaf created a **monthly retainer invoice** for Sunrise (₦150,000 + VAT) starting June.

## 4.9 Month-end
Helpers for **accruals** (expense incurred but not billed → DR expense / CR Accrued Expenses) and a **close checklist**. GreenLeaf accrued **₦45,000** of May utilities. The checklist confirms invoices/bills posted and the **trial balance balances**.

## 4.10 Budgets
Create a yearly budget, set planned amounts per account per month, then compare to actuals.
GreenLeaf's May budget vs actual:
| Account | Budget | Actual | Variance |
|---------|--------|--------|----------|
| Salaries & Wages | 600,000 | 550,000 | −50,000 (−8.3%) |
| Rent & Utilities | 350,000 | 350,000 | 0 |
| Marketing & Branding | 100,000 | 120,000 | +20,000 (+20%) |

## 4.11 Tax (VAT & WHT)
The **VAT return** nets output VAT (on sales) against input VAT (on purchases). The **WHT position** tracks withholding tax suffered/withheld.
GreenLeaf May VAT: output **₦63,375** − input **₦222,000** = **₦158,625 refundable/creditable** (a stock-heavy month).

## 4.12 FIRS e-invoice
Generate a FIRS MBS-style e-invoice **draft** (+ QR) from any invoice. It's clearly marked DRAFT until you're onboarded to the FIRS platform (then the CSID/QR become real).
GreenLeaf draft IRN for INV-2026-0001: `INV20260001-TIN204711880001-20260506`.

## 4.13 CRM
**Flow:** capture **Leads** → work **Deals** through stages (Lead → Qualified → Proposal → Negotiation → Won/Lost) → log **follow-up activities** → **convert** a won lead into a Customer.
GreenLeaf pipeline: 2 open deals worth **₦1,350,000** (Tunde/TB Mega Foods ₦900k Qualified; Eze Catering ₦450k Proposal), plus a follow-up call due.

## 4.14 People & HR
The **HR** group manages your people end to end. **Payroll** (4.5) lives here too.

**Employees** — the staff directory. Each person has a code, department, job title, employment type, pay (monthly gross, PAYE & pension rates) and an **annual leave entitlement** (default 20 days). Activate/deactivate here; active staff flow into Payroll and Leave.
*GreenLeaf:* E001 Chioma, E002 Bola, E003 Emeka.

**Recruitment** — a lightweight applicant tracker that mirrors the CRM shape:
**Flow:** open a **Job Opening** (title, department, headcount) → add **Candidates** → file **Applications** and move them through stages (Applied → Screening → Interview → Offer → Hired/Rejected) → **Hire**. Hiring creates a real **Employee** from the candidate and marks the opening *Filled*, so Payroll takes over with no re-keying.
*GreenLeaf:* "Store Cashier" is open with Chidi Nwosu at the **Interview** stage; Funke Adebayo was **hired** into "Warehouse Assistant" (₦95,000/month) — the hire created her employee record and filled that opening.

**Leave** — request, approve and track time off.
**Flow:** an employee's **leave request** (type, dates → days computed) is **Pending** until a manager **approves/rejects** it. The **balance** = annual entitlement − approved *annual* days taken this year (sick/unpaid/other are tracked but don't reduce the annual balance).
*GreenLeaf:* Chioma's 8–12 Jun annual leave (5 days) is approved → her balance shows 20 − 5 = **15 days**; Bola's 2-day sick leave is pending.

![Employees](manual_images/21_employees.png)
![Recruitment](manual_images/22_recruitment.png)
![Leave](manual_images/23_leave.png)

## 4.15 Approvals — spending controls
Money-out documents (**Bills, Purchase Orders, Payments**) and **Payroll runs** that exceed the submitter's **role limit** are **blocked from posting** and routed to **Finance & Accounting → Approvals**.

**How it works:**
- Each **role** has an NGN authorisation limit (defaults, editable by an Admin on *Approvals → Limits*): **Admin = unlimited · Accountant ₦1,000,000 · AP ₦250,000 · Sales/Viewer ₦0**.
- If you submit something **within** your limit, it posts immediately. **Above** it, you see a 🔒 notice and it becomes a **Pending** request — nothing hits the ledger yet.
- An **approver whose limit covers the amount** approves it on the Approvals page, and *only then* is the document created and posted. You **cannot approve your own** request, and an approver can't clear an amount above their own limit.
- Rejected requests never post (and never consume a document number). Requesters can withdraw their own pending requests.

*GreenLeaf:* an AP clerk (₦250k limit) submits a **₦645,000** FreshFarm bill → it sits in the Pending queue below; a ₦387,000 PackRight PO was approved by the Accountant, and a ₦300,000 advance payment was rejected ("not budgeted"). The **Approvals** page shows the queue, your own requests, full history, and (Admin) the limit editor.

![Approvals](manual_images/24_approvals.png)

---

# 5. GreenLeaf's month in review — May 2026

| Date | Event | Module | Effect |
|------|-------|--------|--------|
| 1 May | Owner capital ₦5,000,000 | Journal | DR Bank / CR Share Capital |
| 1 May | May rent bill ₦350,000 | Purchases | DR Rent / CR AP |
| 2 May | Stock in (Rice+Oil) ₦1,520,000 | Purchases/Inventory | +Inventory +Input VAT / +AP |
| 3 May | Cartons ₦600,000 | Purchases/Inventory | +Inventory / +AP |
| 3 May | Freezer ₦1,800,000 + register FA-001 | Purchases/Assets | DR Equipment / +AP |
| 4 May | Pay rent ₦350,000 | Purchases | DR AP / CR Bank |
| 6–18 May | 4 sales invoices (incl. USD export) | Sales | +AR +Sales +Output VAT; +COGS / −Inventory |
| 19–22 May | Receipts from Sunrise & Mama Tobi | Sales | DR Bank / CR AR |
| 12 May | Marketing bill ₦120,000 | Purchases | DR Marketing / +AP |
| 20 May | Pay FreshFarm ₦2,000,000 | Purchases | DR AP / CR Bank |
| 28 May | Payroll (3 staff) | Payroll | Salaries, pension, net to bank |
| 30 May | Bank charge ₦2,500 | Banking | DR Bank Charges / CR Bank |
| 31 May | Bank reconciliation (GTBank) | Bank Rec | 4 lines auto-matched |
| 31 May | Utilities accrual ₦45,000 | Month-end | DR Rent / CR Accrued Expenses |
| 31 May | FX revaluation (USD) | Currencies | Unrealized gain ₦12,500 |
| — | CRM leads/deals, FIRS draft, budget | CRM/Tax | pipeline ₦1.35M; IRN draft |

---

# 6. Reports — the actual figures (May 2026)

The **Reports** page produces Profit & Loss, Balance Sheet, Cash Flow, AR/AP aging and the VAT return for any period:

![Financial reports — Profit & Loss](manual_images/19_reports.png)

## 6.1 Trial Balance
**DR ₦9,541,875.00 = CR ₦9,541,875.00 — balanced ✓** (17 active accounts).

## 6.2 Profit & Loss
| Line | ₦ |
|------|---|
| **Revenue (Sales)** | 1,232,500 |
| **Cost of Goods Sold** | (984,000) |
| **Gross profit** | **248,500** |
| Salaries & Wages | (550,000) |
| Pension (employer) | (55,000) |
| Rent & Utilities | (395,000) |
| Marketing & Branding | (120,000) |
| Bank Charges | (2,500) |
| **Operating expenses** | **(1,122,500)** |
| **Net profit (loss)** | **(874,000)** |

> A loss in month one is expected — GreenLeaf stocked up heavily (₦2.1M of inventory) and bought a ₦1.8M freezer; those become profit as the stock sells.

## 6.3 Balance Sheet (as at 31 May 2026)
| Assets | ₦ | | Liabilities & Equity | ₦ |
|--------|---|---|----------------------|---|
| Bank — Operating | 2,914,425 | | Accounts Payable | 3,102,000 |
| Accounts Receivable | 522,950 | | Output VAT | 63,375 |
| Inventory — Stock | 1,976,000 | | Pension Payable | 99,000 |
| Input VAT | 222,000 | | Accrued Expenses | 45,000 |
| Equipment | 1,800,000 | | **Total liabilities** | **3,309,375** |
| | | | Share Capital | 5,000,000 |
| | | | Current-year earnings | (874,000) |
| | | | **Total equity** | **4,126,000** |
| **Total assets** | **7,435,375** | | **Total L + E** | **7,435,375** |

**Assets = Liabilities + Equity ✓**

## 6.4 Cash Flow
| | ₦ |
|---|---|
| Operating activities | (429,575) |
| Investing (equipment) | (1,800,000) |
| Financing (capital) | 5,000,000 |
| **Net change in cash** | **2,770,425** |

## 6.5 AR aging (who owes GreenLeaf)
| Customer | Total | 0–30 | 90+ |
|----------|-------|------|-----|
| Adeyemi Household | 135,450 | 135,450 | — |
| Global Imports (USD) | 250 ($) | — | 250 |

## 6.6 AP aging (who GreenLeaf owes)
| Supplier | Total | 0–30 |
|----------|-------|------|
| FreshFarm Produce | 537,000 | 537,000 |
| PackRight Supplies | 2,565,000 | 2,565,000 |

## 6.7 VAT return
Output ₦63,375 − Input ₦222,000 = **₦158,625 creditable**.

---

# 7. Platform features

- **Plans & access (entitlements).** Three plans gate the premium add-ons; **core accounting is on every plan**. Manage under **System → Billing**, which shows what your plan unlocks and your user cap:

  | Plan | Users | Unlocks |
  |------|-------|---------|
  | **Free** | up to 2 | Core accounting (sales, purchases, inventory, banking, payroll, tax, fixed assets, GL, statements, month-end, reports) |
  | **Starter** | up to 5 | + Bank Reconciliation, Recurring, FIRS e-invoice drafts |
  | **Business** | unlimited | + Multi-currency, CRM, Budgets, REST API & webhooks |

  Open a locked module and it shows which plan unlocks it; if a subscription lapses you drop to **Free** (core stays usable, premium locks until you renew). Adding users beyond your plan's cap is blocked until you upgrade.

- **Approvals & limits.** Per-role spending limits with a block-until-approved queue for money-out and payroll — see **§4.15**.
- **Multi-business (multi-tenant).** Run many businesses from one login; each is a fully isolated database with its own subdomain and its own invoice branding. Manage under **System → Tenants**.
- **REST API + webhooks.** Every core function is reachable via the REST API with a per-business API key (`X-API-Key`): customers, products, invoices, reports, bank feed, CRM, billing. *(Business plan.)*
- **Billing.** Subscriptions via Paystack / Flutterwave / Moniepoint (switchable), under **Billing**.
- **In-app help assistant.** A floating 💬 bubble on every page answers how-to questions and live-data questions (revenue, cash, AR/AP, pending approvals, counts) for the current business.
- **User Manual in-app.** This guide is available under **System → User Manual** (with a download button).
- **Backups & recovery.** Nightly, the system `pg_dump`s every database, **encrypts** it, and uploads it off-site. The encryption passphrase is your recovery key — keep it in a password manager. (See the separate operations/secrets reference.)
- **Security.** No open inbound ports (secured tunnel), per-user roles, audit trail on every change, period locks, and approval limits on spend.

---

# 8. Screenshots — visual reference

Captured live from the GreenLeaf demo (May 2026 data, plus the June HR/approvals examples). Every figure shown matches the reports above.

### Dashboard
![Dashboard](manual_images/01_dashboard.png)

### Sales
![Sales](manual_images/02_sales.png)

### Purchases
![Purchases](manual_images/03_purchases.png)

### Inventory
![Inventory](manual_images/04_inventory.png)

### Banking
![Banking](manual_images/05_banking.png)

### Bank Reconciliation
![Bank Reconciliation](manual_images/06_bank_reconciliation.png)

### Payroll
![Payroll](manual_images/07_payroll.png)

### Fixed Assets
![Fixed Assets](manual_images/08_fixed_assets.png)

### General Ledger (Trial Balance)
![General Ledger](manual_images/09_general_ledger.png)

### Customer Statements
![Statements](manual_images/10_statements.png)

### Month End
![Month End](manual_images/11_month_end.png)

### Budgets
![Budgets](manual_images/12_budgets.png)

### Currencies & FX
![Currencies](manual_images/13_currencies.png)

### FIRS E-invoice
![FIRS E-invoice](manual_images/14_firs_einvoice.png)

### CRM
![CRM](manual_images/15_crm.png)

### Settings (Company & Invoice template)
![Settings](manual_images/16_settings.png)

### Tenants (multi-business)
![Tenants](manual_images/17_tenants.png)

### Billing
![Billing](manual_images/18_billing.png)

### Financial Reports (P&L · Balance Sheet · Cash Flow · Aging · VAT)
![Reports](manual_images/19_reports.png)

### Recurring transactions
![Recurring](manual_images/20_recurring.png)

### Employees (HR)
![Employees](manual_images/21_employees.png)

### Recruitment (HR)
![Recruitment](manual_images/22_recruitment.png)

### Leave (HR)
![Leave](manual_images/23_leave.png)

### Approvals (spending controls)
![Approvals](manual_images/24_approvals.png)

---

*BizClinik ERP · built & operated by HAG_Ai · Updated 2026-06-11 (adds People & HR, Approvals, Plans & access, and the in-app assistant). The financial figures are reproducible: run `python scripts/demo_seed.py` against a fresh database to regenerate GreenLeaf and every figure above.*
