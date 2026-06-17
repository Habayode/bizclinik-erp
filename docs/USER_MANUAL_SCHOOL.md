# Trakit365 School ERP — User Manual

A plain-English guide for running your school on Trakit365: enrolment, school
fees, attendance, results, teachers, parent notifications — and the bursary
(accounting) that ties it all together.

> This manual is written for the people who run the school office — the
> head teacher, bursar, admin clerk and accounts officer. You do **not** need to
> be an accountant. Where money is involved, the system does the bookkeeping for
> you in the background; this guide tells you which button to press and what
> happens when you do.

Throughout, we follow your school — **OTASCH School**, Ota, Ogun State — through a
full term so every step has a concrete picture. The classes and fees used in the
examples are the ones set up in your system; change any amount whenever your real
figures differ.

---

## How to read this manual

- **Bold** words are exactly what you see on the screen — a menu item, a tab, a
  button or a field, e.g. click **Generate fees**.
- Menus are written as a trail: **School → School Fees → Bulk issue** means open
  the **School** group in the left sidebar, click **School Fees**, then the
  **Bulk issue** tab.
- "The books" / "the ledger" / "the GL" all mean the school's accounting records
  (what auditors look at). You rarely touch these directly — fees and payments
  update them automatically.
- ₦ is the Naira. Fees are entered in Naira.

---

# 1. Getting started

## 1.1 Signing in

Open your school's web address (for example `yourschool-erp.hagai.online`). You
will see a sign-in card showing **your school's name** and **🏫 School portal**.
Enter your **Username** and **Password** and click **Sign in**.

- Your school administrator creates a login for each staff member and gives them
  a **role** that decides what they can do (see [section 12](#12-who-can-do-what-roles)).
- After five wrong attempts the screen locks for that session — refresh the page
  and try again.
- Change your password after your first sign-in: **System → Admin**.

## 1.2 Finding your way around

The left sidebar is grouped. A school sees, in order:

| Group | What lives here |
|-------|-----------------|
| **School** | The school's day-to-day: Dashboard, Setup, Students, Fees, Attendance, Results, Teachers, Parent Notifications. |
| **Bursary** | The money side: a finance dashboard, banking, purchases/bills, the general ledger and all financial reports. |
| **HR** | Staff: Employees, Recruitment, Leave, Payroll. |
| **System** | Settings, Admin (users), Notifications, Data and this Manual. |

The **School Dashboard** is your home page — it opens first when you sign in.

## 1.3 The order of work

Set the school up once, then repeat the termly cycle:

1. **Set up** (once a year, [section 3](#3-school-setup)): the academic session
   and terms, your classes, your fee types and the fee amounts.
2. **Enrol students** ([section 4](#4-students)): one at a time or the whole
   roster from a spreadsheet.
3. **Bill the term** ([section 5](#5-school-fees)): one click per class.
4. **Collect & follow up**: record payments, watch the defaulters list, send
   reminders.
5. **Run the school**: attendance, results and report cards through the term.
6. **See the numbers**: the School Dashboard and the Bursary reports.

---

# 2. How the school's records fit together

A few ideas explain everything else. Read this once and the rest is obvious.

- **Every student is also a billing account.** When you enrol a student, the
  system quietly creates their billing record too. That is why you never set up
  "customers" separately — the student *is* the account that fees are charged to,
  and the guardian's phone/email ride along for reminders.
- **A fee type is wired to an income account.** When you create a fee — Tuition,
  Exam, Transport — you point it at an income account once. From then on,
  whenever you bill that fee the money automatically lands in the right place in
  the books. School fees are **VAT-exempt**, so no tax is added.
- **Billing a term creates a real invoice; a payment is a receipt.** "Bill the
  JSS1 class for Term 1" raises one invoice per student. Recording a payment
  files a receipt against that invoice. Both update the ledger on their own — you
  never write an accounting entry by hand for fees.
- **The school calendar and the accounting calendar are separate.** Academic
  **sessions** and **terms** organise the school year. The accounting periods
  used at month-end (Bursary) are separate — you don't need to line them up.
- **Teachers are your HR employees with a school hat on.** A teacher's pay and
  leave live in **HR**; the **Teachers** page just adds school details (subjects,
  classes, qualification) on top.

The education chart of accounts already includes the usual school income lines —
Tuition, Registration, Examination, Uniform, Books, Transport, Boarding and
Levies — plus their cost and expense accounts, so reports read sensibly out of
the box.

---

# 3. School Setup

**School → School Setup.** This is master data — names, classes and prices.
Nothing here touches the books; you are just describing your school. The page has
five tabs, and it is easiest to fill them left to right.

## 3.1 Sessions (the academic year)

The **📅 Sessions** tab.

1. In **Session code** type the year, e.g. `2025/2026`.
2. Set **Start date** and **End date** (optional but recommended).
3. Tick **Set as the current session** for the year you are running now.
4. Click **Add session**.

The "current" session is what the Dashboard and the enrolment/billing screens
default to, so always mark the active year current.

## 3.2 Terms

The **🗓️ Terms** tab. For the session, add each term:

1. Pick the **Session**.
2. Choose **Term** — 1, 2 or 3.
3. Set the term's **Start date** and **End date**.
4. Click **Add term**. Repeat for all three terms.

## 3.3 Classes

The **🏷️ Classes** tab.

1. **Class code** — a short tag you will reuse everywhere, e.g. `JSS1A`, `PRY3`,
   `KG1`. Keep these tidy; the bulk student importer matches on them.
2. **Class name** — the full name, e.g. `Junior Secondary 1A`.
3. **Form level**, **Arm** and **Capacity** are optional.
4. **Form tutor (optional)** — pick a member of staff (they must be an HR
   employee first).
5. Click **Add class**.

OTASCH uses five classes: `KG1` (Kindergarten 1), `PRY3` (Primary 3), `JSS1A`
(Junior Secondary 1A), `JSS2A` (Junior Secondary 2A) and `SSS1A` (Senior
Secondary 1A).

## 3.4 Fee types

The **💰 Fee types** tab. A fee type is a charge you can bill — and it is wired
to the income account where its money should land.

1. **Fee code** — short, e.g. `TUI`.
2. **Fee name** — e.g. `Tuition`.
3. **Income account** — pick from the list (e.g. *4400 — Tuition*). This is the
   one-time wiring that keeps your books correct.
4. **Mandatory (billed to every student)** — leave ticked for fees everyone pays
   (tuition); untick for optional ones (transport, boarding).
5. Click **Add fee type**.

OTASCH sets up: **Tuition**, **Registration & Admission**, **Examination**,
**Uniform** and **PTA / Development Levy** as the standard charges, plus
**Transport / Bus**, **Boarding & Feeding** and **Books & Stationery** as
optional fee types for ad-hoc billing.

## 3.5 Fee schedule (the price grid)

The **🧮 Fee schedule** tab — *how much* each class pays for each fee, per term.
This is the heart of billing.

1. Pick the **Session** and the **Fee type**.
2. **Class** — choose a specific class, or **All classes** for a school-wide
   price (e.g. a uniform price everyone pays).
3. **Applies to** — choose **Term 1/2/3** for a per-term charge, or
   **Annual / one-off** for something billed once a session (registration,
   uniform).
4. Enter the **Amount (₦)**.
5. Click **Set fee amount**. Setting the same combination again simply updates
   the price (no duplicates).

> **Mixed cadences are fine.** Tuition can be per-term while registration is
> annual — just choose the right **Applies to** for each line.

Example for OTASCH's JSS1A: Tuition `₦70,000` for each of Term 1/2/3 and
Examination `₦5,000` per term; Registration & Admission `₦20,000` and Uniform
`₦15,000` as **Annual / one-off**; PTA / Development Levy `₦10,000` set on
**All classes** as **Annual**. Tuition varies by class — KG1 `₦40,000`, PRY3
`₦50,000`, JSS1A `₦70,000`, JSS2A `₦75,000`, SSS1A `₦95,000` per term.

---

# 4. Students

**School → Students.** Three tabs: **📋 Directory**, **🎓 Enrol**,
**📥 Bulk import**.

## 4.1 Directory

The roll. Filter by class with **Filter by class**. Each row shows the admission
number, name, class, status, and the guardian's name and phone.

## 4.2 Enrol one student

The **🎓 Enrol** tab. Enrolling creates the student, their class enrolment for
the session, **and** their billing record — in one step.

1. **First name** and **Last name** (required).
2. **Academic session** and **Class**.
3. **Admission no (optional)** — leave blank to auto-number `STU-0001`,
   `STU-0002`, …, or type your own (e.g. `SUN/2025/014`).
4. **Gender**, **Date of birth**, **Date admitted** — optional.
5. **Guardian name**, **Guardian phone**, **Guardian email** — the phone and
   email are used for fee reminders and statements, so capture them.
6. Click **Enrol student**.

## 4.3 Bulk import a whole roster

The **📥 Bulk import** tab — load an entire class or the whole school from a
spreadsheet.

1. Choose **Enrol into session** (defaults to the current session).
2. Click **⬇ Download student template (.xlsx)**.
3. Fill one row per student. Columns:

   | Column | Required? | Notes |
   |--------|-----------|-------|
   | `first_name` | Yes | |
   | `last_name` | Yes | |
   | `class_code` | Yes | Must match a class in **School Setup → Classes** (e.g. `JSS1A`). |
   | `admission_no` | No | Auto-numbered `STU-####` if blank. |
   | `gender` | No | M or F. |
   | `dob` | No | `YYYY-MM-DD`. |
   | `guardian_name` | No | The fee payer. |
   | `guardian_phone` | No | Used for SMS reminders. |
   | `guardian_email` | No | Used for emailed statements. |
   | `date_admitted` | No | `YYYY-MM-DD`; defaults to today. |

4. Click **Upload your filled roster**, check the **Preview**, then click
   **Enrol all**.

The importer is forgiving and safe:
- A row whose **class_code** doesn't exist, or which is missing a name, is
  **skipped with a clear message** — the rest still import.
- A duplicate **admission_no** is skipped, so you can fix a few rows and
  re-upload the same file without creating doubles.
- Each row creates the student, their enrolment **and** their billing record, so
  you can bill fees immediately afterwards.

> This is the right way to load your roster. (The generic "customer" import on
> the Settings page only creates billing records — use **Students → Bulk import**
> for actual pupils.)

---

# 5. School Fees

**School → School Fees.** This is where money first reaches the books. Four tabs:
**💰 Bulk issue**, **💵 Record payment**, **📊 Fee status / defaulters**,
**📋 Billing log**.

## 5.1 Bill a class for the term (Bulk issue)

The **💰 Bulk issue** tab raises each student's fees for a term as a real
invoice, using the price grid from Setup.

1. Pick the **Academic session** and the **Class**.
2. Choose the **Term** (or **Annual / one-off**).
3. Set the **Invoice date**.
4. Tick **Also include annual / one-off fees** if you want to add the once-a-year
   items (registration, uniform) onto this run — typically for Term 1.
5. Click **Generate fees**.

You'll see a summary like *"Billed 30, skipped 2"*. **Skipped** means those
students were already billed for that term — so re-running a class is completely
safe and never double-charges. Behind the scenes each student gets a sales
invoice and the revenue lands in the right income accounts automatically.

## 5.2 Record a payment

The **💵 Record payment** tab.

1. Pick the **Student invoice** — the list shows admission number, name, invoice
   number and the outstanding amount.
2. Enter the **Amount** (defaults to the full outstanding balance — change it for
   a part-payment).
3. Set the **Payment date**.
4. Choose the **Bank account** the money went into and the **Method**
   (BANK / CASH / TRANSFER / CARD).
5. Add a **Reference** (teller number, transfer ref) if you have one.
6. Click **Record payment**.

This files a receipt and updates the books (money into the bank, the student's
balance reduced) automatically.

## 5.3 Fee status & defaulters

The **📊 Fee status / defaulters** tab. Choose an **Academic session** and a
**Class** to see:

- **Class roll** — each billed student and where they stand.
- **Defaulters (session)** — everyone with an outstanding balance, with a
  **Total outstanding** figure. If everyone has paid you'll see *"No defaulters
  — all billed fees are settled."*

This is the list you act on from **Parent Notifications** ([section 9](#9-parent-notifications)).

## 5.4 Billing log

The **📋 Billing log** tab is the full history of every fee billing run —
student, session, term, invoice number, amount and date.

---

# 6. Attendance

**School → Attendance.** Daily registers. Nothing here touches the books. Two
tabs: **✅ Mark attendance** and **📊 Summary**.

## 6.1 Mark attendance

1. Pick the **Class** and the **Date** (defaults to today).
2. For each student, set the status: **PRESENT**, **ABSENT**, **LATE** or
   **EXCUSED**.
3. Click **Save attendance**.

Only active students in the class appear. Re-saving for the same day updates the
marks.

## 6.2 Summary

Pick a **Class** and **Date** to see the day's tally — Present, Absent, Late,
Excused and Total.

---

# 7. Results & report cards

**School → Results.** Per-subject scores and a report-card preview. Nothing here
touches the books. Two tabs: **✍️ Enter result** and **🧾 Report card**.

## 7.1 Enter a result

1. Pick the **Student**, the **Session**, the **Class** and the **Term**.
2. Type the **Subject** (e.g. `Mathematics`).
3. Enter the **CA score** and the **Exam score**. The system computes
   **Total = CA + Exam** and assigns the **grade** automatically.
4. Optionally pick the **Teacher** and add **Remarks**.
5. Click **Save result**.

Repeat per subject. Saving a subject again for the same student/term updates it.

## 7.2 Report card

The **🧾 Report card** tab. Choose the **Student**, **Session** and **Term** to
see every subject, the totals and grades, and the **Average** for the term.

---

# 8. Teachers

**School → Teachers.** Two tabs: **👩‍🏫 Teaching staff** and **📊 Dashboard**.

A teacher is one of your **HR employees** with school details added on top — so
**add the person under HR → Employees first**, then give them a teaching profile
here. Their salary, leave and payroll stay in HR.

## 8.1 Add / update a teaching profile

1. Pick the **Employee**.
2. Choose the **Staff type** — **Teaching** or **Non-teaching**.
3. Fill **Qualification** (e.g. `B.Ed Mathematics`), **Registration number**
   (e.g. `TRCN/12345`), **Subjects taught** and **Classes assigned**.
4. Click **Save profile**. There is one profile per employee; saving again
   updates it.

## 8.2 Dashboard tab

A read-only snapshot. Pick an **Academic session** (or **All sessions**) to see
active students, teaching staff, defaulters and the fee position, plus enrolment
by class.

---

# 9. Parent notifications

**School → Parent Notifications.** Send fee reminders and statements to guardians
by SMS or email. Three tabs: **🔔 Fee reminders**, **📃 Statements**, **📜 Log**.

> **A note on sending.** At the top of the page a banner tells you the channel
> status. Out of the box, **SMS is in log/demo mode** — reminders are *recorded
> but not actually sent* until a real SMS gateway is switched on. Likewise email
> only sends once the school's email (SMTP) details are configured. Ask your
> Trakit365 operator to enable these when you're ready to send for real; until
> then you can use the screens safely to see exactly what *would* go out.

## 9.1 Fee reminders

1. Choose the **Channel** — **SMS** or **EMAIL**.
2. Choose **Send to** — **All defaulters** (everyone with an outstanding balance)
   or **One student**.
3. For one student, pick them and click **Send reminder**; for everyone, click
   **Send to all defaulters**.

You'll get a tally of how many were sent, logged, failed or skipped (a student
with nothing outstanding is skipped).

## 9.2 Statements

The **📃 Statements** tab emails a student's fee statement (PDF) to the guardian
on file. Pick the **Student**, set **Period start** and **Period end**, and click
**Email statement**. (Requires email/SMTP configured.)

## 9.3 Log

Every reminder and statement — when, to whom, channel, status and any error — is
listed in the **📜 Log** tab.

---

# 10. The School Dashboard

**School → School Dashboard** (your home page). A live, read-only snapshot of the
**current session**:

- **Students enrolled**, **Teaching & staff**, **Fee defaulters**.
- **Fees billed**, **Fees collected**, **Outstanding**, with a bar showing the
  percentage of billed fees collected.
- **Enrolment by class** — a table and chart.

If you haven't set a current session yet, the page tells you to go to
**School Setup → Sessions** first.

---

# 11. The Bursary — the money side

The **Bursary** group is the school's accounting. Fees flow here automatically,
so much of it looks after itself, but this is where you handle everything that
*isn't* a fee and where you get your financial reports.

- **Banking** — record bank accounts, lodgements and charges, and reconcile the
  bank statement.
- **Purchases** — record suppliers' **bills** (diesel, books, maintenance) and
  pay them.
- **General Ledger** — post manual journal entries when you genuinely need to
  (accruals, corrections); fees never need this.
- **Reports** — your **Trial Balance**, **Income & Expenditure** (Profit & Loss),
  **Balance Sheet**, **Cash Flow** and receivables aging (who still owes fees).
- **Month-End** — close a period when the month's records are complete.
- **Finance Dashboard** — the generic financial overview.

Two everyday tasks:

**Record a supplier bill:** **Bursary → Purchases** → enter the supplier, the
items/amount and the date → save; then record the payment when you pay it.

**Check what fees are still owed across the school:** **Bursary → Reports** →
the AR aging report (or use **School Fees → Fee status / defaulters** for the
per-class view).

For the full accounting detail, see the standard Trakit365 User Manual; the
mechanics (sales, purchases, banking, reports, VAT/WHT) are identical — a school
simply drives most of its income through the Fees screens instead of typing
invoices by hand.

**Settings.** **System → Settings** is where your **school profile** lives (name,
address, logo on documents) and where the **Students / Parents** records can be
reviewed.

---

# 12. Who can do what (roles)

Each login has a role. The school features (Setup, Students, Fees, Attendance,
Results, Teachers, Notifications) are available to **Admin** and **Accountant**
roles. In broad terms:

| Role | Typical user | Can do |
|------|--------------|--------|
| **Admin** | Head / proprietor / bursar | Everything, including user accounts and closing periods. |
| **Accountant** | Bursar / accounts officer | All school + bursary work: setup, billing, payments, results, reports. |
| **Sales** | Front-desk / fees clerk | Raise invoices and record receipts. |
| **AP** | Purchasing clerk | Record and pay supplier bills. |
| **Viewer** | Auditor / proprietor | Read-only — view reports, no changes. |

Give each staff member the narrowest role that lets them do their job. Create and
manage logins under **System → Admin**.

---

# 13. A term at OTASCH School (worked example)

1. **Set up the year.** Add session **2025/2026** (set current) and **Terms 1–3**.
   Add classes **KG1, PRY3, JSS1A, JSS2A, SSS1A**. Create fee types (Tuition,
   Examination, Registration & Admission, Uniform, PTA / Development Levy, …)
   wired to their income accounts. Enter the price grid — tuition per term (KG1
   `₦40,000` … SSS1A `₦95,000`), examination per term, and registration, uniform
   and levy as annual one-offs.
2. **Load students.** Download the template, fill the pupils across the classes,
   **Enrol all**. Each gets an admission number and a billing record.
3. **Bill Term 1.** **School Fees → Bulk issue**, pick JSS1A, **Term 1**, tick
   **Also include annual / one-off fees** (to add registration + levy), **Generate
   fees**. Repeat for each class. Invoices are raised; income hits the books.
4. **Collect.** As parents pay, **Record payment** against each student's invoice,
   choosing the bank and method. The Dashboard's "collected" figure climbs.
5. **Chase defaulters.** **Fee status / defaulters** shows who's outstanding;
   **Parent Notifications → Fee reminders → All defaulters** nudges them by SMS.
6. **Run the term.** Mark **Attendance** daily; enter **Results** per subject and
   print **Report cards** at term's end.
7. **See the position.** The **School Dashboard** shows enrolment and the fee
   position at a glance; **Bursary → Reports** gives the Trial Balance and Income
   & Expenditure for the term.

---

# 14. Tips & troubleshooting

- **"Add a session/class first."** Most screens need the calendar and classes in
  place — do **School Setup** before enrolling or billing.
- **A bulk-import row was skipped.** The message says why — almost always a
  **class_code** that doesn't match **School Setup → Classes**, or a missing name.
  Fix those rows and re-upload the same file; already-imported pupils are skipped.
- **Re-running a billing didn't add anything.** That's correct — students already
  billed for that term are skipped so you never double-charge.
- **A reminder said "logged", not "sent".** SMS/email aren't switched to live yet
  (see [section 9](#9-parent-notifications)) — ask your operator to enable the
  gateway.
- **A page reloaded with a "failed to fetch" message right after an update.**
  Hard-refresh the page (Ctrl+Shift+R) and it clears.
- **Lost the menu item you wanted.** Some items (Tenants, Billing) are reserved
  for the platform operator and won't appear in your school's menu — that's by
  design.

## Getting help

Contact your Trakit365 operator (HAG_Ai) for support, to switch on live SMS/email,
or for training. The standard Trakit365 User Manual covers the accounting modules
in full depth.
