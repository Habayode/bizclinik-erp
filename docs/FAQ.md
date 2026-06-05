# BizClinik ERP — Frequently Asked Questions

*Built & operated by HAG_Ai for BizClinik. Last updated: 2026-06-06.*

This FAQ answers the questions businesses ask most often when using BizClinik ERP.
For step-by-step walkthroughs with screenshots, see the **User Manual**
(`docs/USER_MANUAL.md`).

---

## Contents
1. [Getting started](#1-getting-started)
2. [Accounting & the ledger](#2-accounting--the-ledger)
3. [Sales, purchases & inventory](#3-sales-purchases--inventory)
4. [Banking & reconciliation](#4-banking--reconciliation)
5. [Payroll & tax (PAYE, VAT, WHT, FIRS)](#5-payroll--tax)
6. [CRM](#6-crm)
7. [Multi-currency](#7-multi-currency)
8. [Reports & month-end](#8-reports--month-end)
9. [Plans, billing & feature access](#9-plans-billing--feature-access)
10. [Users, roles & security](#10-users-roles--security)
11. [Running multiple businesses](#11-running-multiple-businesses)
12. [Data, backups & recovery](#12-data-backups--recovery)
13. [API & integrations](#13-api--integrations)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Getting started

**Q: What is BizClinik ERP?**
A complete, double-entry accounting and business-management system built for Nigerian
SMEs. It covers your ledger, sales, purchases, inventory, banking, payroll, tax, fixed
assets, budgets, reporting, CRM and more — in one place, with proper books behind every
transaction.

**Q: Do I need to be an accountant to use it?**
No. The day-to-day screens (raise an invoice, record a bill, pay staff) use plain
business language. Behind the scenes every action posts a balanced double-entry journal,
so your Trial Balance, P&L and Balance Sheet are always correct without you touching a
ledger.

**Q: How do I log in?**
Open the ERP in your web browser and sign in with the username and password your
administrator created for you. On first login you may be asked to change your password.

**Q: I'm brand new — how do I set up my business?**
Use the **Onboarding** page. It walks you through your company details and loads a
ready-made Chart of Accounts template so you can start posting immediately.

**Q: What does it cost?**
There are three plans — Free, Starter and Business. See
[Plans, billing & feature access](#9-plans-billing--feature-access).

---

## 2. Accounting & the ledger

**Q: Is this real double-entry accounting?**
Yes. Every transaction posts equal debits and credits to the General Ledger. The system
will not let an unbalanced entry through.

**Q: Where do I see the full ledger?**
The **General Ledger** page shows every journal line. The **Reports** page gives you the
Trial Balance, Profit & Loss and Balance Sheet computed from those journals.

**Q: Can I post a manual journal?**
Yes — for adjustments, accruals and corrections. Use the General Ledger / journal entry
screen. Manual entries are audited like everything else.

**Q: I made a mistake on a posted invoice or bill. Can I delete it?**
You don't delete posted documents — that would break the audit trail. Instead you
**void or reverse** the document, which posts a reversing entry. The original and its
reversal both remain on record.

**Q: What is a Chart of Accounts and can I change it?**
It's the list of accounts your transactions post to (cash, sales, VAT, etc.). A standard
template is loaded during onboarding, and you can add or rename accounts under
**Settings**.

---

## 3. Sales, purchases & inventory

**Q: How do I invoice a customer?**
Go to **Sales**, pick the customer, add line items (products or services), and post. The
invoice updates the customer's balance, recognises revenue, and books VAT automatically.

**Q: Can I brand my invoices?**
Yes. Under **Settings** you can set a logo, colours and company details. Each business
(tenant) gets its own invoice branding, and invoices export to PDF.

**Q: How do I record a supplier bill or a purchase?**
Use the **Purchases** page. Posting a bill increases what you owe (Accounts Payable) and
records the expense or the stock received.

**Q: Does it track stock?**
Yes. The **Inventory** page tracks stockable products, quantities and valuation. Selling
or buying stockable items moves inventory and posts cost of goods sold.

**Q: Can I issue a quotation before an invoice?**
Yes — the system includes a sales quotation generator, so you can send a quote and
convert it to an invoice when the customer agrees.

---

## 4. Banking & reconciliation

**Q: How do I record money in and out?**
Use the **Banking** page to record receipts, payments and transfers against your bank and
cash accounts.

**Q: What is bank reconciliation and do I need it?**
Reconciliation matches your ledger against your actual bank statement so you can prove
your cash balance is correct. The **Bank Reconciliation** page imports a statement,
auto-matches what it can, and lets you match the rest by hand. It supports multiple banks,
including a Moniepoint statement parser. *(Available on Starter and Business plans.)*

**Q: Can it pull transactions in automatically?**
The reconciliation module supports a push-in feed so transactions can arrive
automatically where that integration is configured.

---

## 5. Payroll & tax

**Q: Does it do Nigerian payroll?**
Yes. The **Payroll** page runs staff pay and calculates **graduated PAYE** using the
Nigerian tax bands, then posts the salary, tax and net-pay entries for you.

**Q: Does it handle VAT?**
Yes. VAT is calculated automatically on sales and purchases and tracked in the ledger, so
your VAT position is always visible for filing.

**Q: What about Withholding Tax (WHT)?**
WHT is supported, including the ability to produce WHT credit certificates.

**Q: Can I produce FIRS e-invoices?**
Yes. The **FIRS E-Invoice** page builds a FIRS-compliant e-invoice payload (with QR) from
a sales invoice. **Important:** these are drafts for review — they are not transmitted to
the FIRS Merchant Buyer Solution, so the CSID and QR are placeholders until FIRS
countersigns. Set your TIN and FIRS Service ID under **Settings → Company** for a correct
IRN. *(Available on Starter and Business plans.)*

**Q: Can I generate customer statements?**
Yes. The **Statements** page produces customer account statements, which can be emailed
when email is configured.

---

## 6. CRM

**Q: What does the CRM do?**
The **CRM** page manages **leads**, a **deal pipeline**, and **follow-up activities**. You
capture leads, move deals through stages, log calls/meetings, and convert a won lead into
a customer (optionally opening a deal at the same time). *(Available on the Business plan.)*

**Q: Does the CRM connect to invoicing?**
Yes — converting a lead creates a customer record you can immediately invoice from the
Sales page, so there's no re-typing between sales and accounting.

---

## 7. Multi-currency

**Q: Can I invoice or buy in foreign currency?**
Yes, on the Business plan. The ledger's functional currency is always **NGN**, but you can
issue and receive foreign-denominated invoices and bills. They convert to NGN at the rate
captured when posted.

**Q: How are exchange-rate gains and losses handled?**
The **Currencies** page tracks exchange rates and supports both **realized FX** (on
settlement) and an **unrealized FX revaluation** report that marks open foreign-currency
items to a chosen date. Review revaluation figures with your accountant before booking a
period-end entry.

---

## 8. Reports & month-end

**Q: What reports do I get?**
Trial Balance, Profit & Loss, Balance Sheet, plus budgets/variance, customer statements,
and module-level views. The **Reports** page is the hub.

**Q: What is "month-end" and what does it do?**
The **Month-End** page helps you close a period cleanly — accrual helpers and the
month-end routine — so each accounting period is finalised consistently.

**Q: Can I lock a period so no one posts into it after closing?**
Yes. Fiscal periods can be **closed** (and reopened by an administrator if needed),
preventing accidental edits to finalised months.

**Q: Can I budget and compare to actuals?**
Yes. The **Budgets** page lets you set budgets and produces variance reporting against
actuals. *(Available on the Business plan.)*

**Q: Can I set up transactions that repeat?**
Yes. The **Recurring** page automates regularly repeating transactions (e.g. rent,
subscriptions). *(Available on Starter and Business plans.)*

---

## 9. Plans, billing & feature access

**Q: What are the plans?**

| Plan | Price | Users | What's included |
|------|-------|-------|-----------------|
| **Free** | ₦0/mo | Up to 2 | Core accounting: sales, purchases, inventory, banking, payroll, tax, fixed assets, reports, GL, statements, month-end |
| **Starter** | ₦15,000/mo | Up to 5 | Everything in Free **+** Bank Reconciliation, Recurring transactions, FIRS e-invoice drafts |
| **Business** | ₦45,000/mo | Unlimited | Everything in Starter **+** Multi-currency, CRM, Budgets, REST API & webhooks, priority support |

*(Prices are configurable and may be tailored to your agreement.)*

**Q: Is core accounting ever locked behind a plan?**
No. Sales, purchases, inventory, banking, payroll, tax, fixed assets, the general ledger,
statements, month-end and reports are available on **every** plan, including Free. Plans
only gate the premium add-ons listed above.

**Q: How do I subscribe or change plan?**
Go to the **Billing** page. It shows your current plan, what it unlocks (a ✅/🔒 list),
your user limit, and lets you choose another plan. The Free plan activates instantly; paid
plans take you to a secure checkout once a payment provider is configured.

**Q: I opened a premium page and it says it's locked. Why?**
Your current plan doesn't include that feature. The page shows which plan unlocks it —
upgrade on the **Billing** page and it becomes available immediately.

**Q: What happens to my data if my subscription lapses?**
Nothing is lost. Your books and history stay intact. The system simply **downgrades you to
Free**: core accounting keeps working, and the premium features lock until you renew.

**Q: We hit our user limit. How do we add more people?**
Each plan caps active users (Free 2, Starter 5, Business unlimited). When you reach the
cap, the Admin page will stop new user creation and prompt you to upgrade. Upgrading on the
Billing page raises the limit.

**Q: Which payment methods are supported?**
The billing engine is provider-agnostic and supports **Paystack, Flutterwave and
Moniepoint**. The active provider is configured on the server.

---

## 10. Users, roles & security

**Q: How do I add a user?**
An administrator adds users on the **Admin** page, setting a username, role and initial
password (with an option to force a password change on first login).

**Q: What roles are available?**
Users are assigned roles with per-module permissions, so staff only see and do what their
role allows. Administrators manage roles and can deactivate accounts.

**Q: Is there an audit trail?**
Yes. Records carry created/modified tracking and there is an audit log, so you can see who
did what and when.

**Q: How are passwords stored?**
Passwords are never stored in plain text — they're salted and hashed (PBKDF2). Repeated
failed logins are tracked.

**Q: Is the connection secure?**
Yes. The ERP is served over an encrypted connection via a secured tunnel; there are no
open inbound ports on the server.

---

## 11. Running multiple businesses

**Q: Can I run more than one company in BizClinik ERP?**
Yes. It is **multi-tenant**: each business (tenant) has its own fully isolated database.
One company's data is never visible to another.

**Q: How do I switch between businesses?**
Use the **Tenants** page to create or select the active business. Billing, users and data
all follow the selected tenant.

**Q: Is each business billed separately?**
Yes — subscriptions are per business, so each tenant has its own plan and user limit.

---

## 12. Data, backups & recovery

**Q: Where is my data kept?**
In a production-grade **PostgreSQL** database, with a separate database for each business
(tenant) for strong isolation.

**Q: Are there backups?**
Yes. Encrypted backups run **nightly**: the database is dumped, encrypted, and stored
off-site in cloud object storage. Backups are AES-encrypted before they leave the server.

**Q: Can data be restored if something goes wrong?**
Yes. Backups are restorable, and the recovery passphrase is held securely off-system by
HAG_Ai as part of operating the platform for you.

**Q: Can I export my own data?**
Yes — the **Data** page and the reports support export (e.g. PDF invoices/statements and
report downloads).

---

## 13. API & integrations

**Q: Is there an API?**
Yes — a REST API with webhooks, secured by per-business API keys. It's intended for
connecting other systems (e.g. e-commerce, custom dashboards) to your ERP data.
*(Available on the Business plan.)*

**Q: How do I get an API key?**
API keys are issued per business by an administrator. Each key only sees its own tenant's
data.

**Q: My API calls return "402 Payment Required". Why?**
API access is a **Business-plan** feature. A business on Free or Starter is blocked with
HTTP 402 until it upgrades to Business on the Billing page.

**Q: Can I receive payment confirmations automatically?**
Yes. Billing supports provider webhooks, so a successful payment can activate a
subscription automatically.

---

## 14. Troubleshooting

**Q: My dashboard shows zero revenue but I've posted invoices.**
Check the **date** on your transactions and the period the dashboard is showing. Figures
only appear for the period they fall in — future-dated entries won't show in the current
month.

**Q: A page asks me to log in again.**
Your session expired or you opened the app in a way that started a new session. Sign in
again from the home page; navigate between modules using the **sidebar links** rather than
pasting a page URL.

**Q: I can't add a user / a feature is greyed out or locked.**
This is almost always a plan limit. Open the **Billing** page to see your plan, your user
cap, and what's unlocked — then upgrade if you need more.

**Q: A foreign-currency document was skipped during revaluation.**
That means there's no exchange rate on file for that currency and date. Add the rate on the
**Currencies** page, then re-run the revaluation.

**Q: Something looks wrong and I can't resolve it.**
Contact HAG_Ai support. As the team that builds and operates BizClinik ERP for you, HAG_Ai
handles hosting, backups, upgrades and recovery. Business-plan customers receive priority
support.

---

*BizClinik ERP is built and operated by **HAG_Ai**. For support or to change your plan,
contact HAG_Ai or use the in-app **Billing** page.*
