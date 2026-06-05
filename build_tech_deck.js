// BizClinik ERP — Technical Documentation deck (build / modules / flows / stack / ops)
// Navy + teal brand. 16:9. Dense but readable. pptxgenjs.
// NOTE: secret VALUES are never printed here — only their names, locations, and procedures.

const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "HAG_Ai";
pres.company = "HAG_Ai";
pres.title = "BizClinik ERP — Technical Documentation";

// ---- Brand --------------------------------------------------------------
const NAVY = "1F3864", NAVY_DARK = "16284F", TEAL = "0EA5A4", INK = "0F172A",
      MUTED = "64748B", BG = "F4F6FB", SURFACE = "FFFFFF", BORDER = "E5E7EB",
      SUCCESS = "16A34A", WARN = "F59E0B", DANGER = "DC2626", INFO = "2563EB",
      CODEBG = "0B1220", CODEFG = "D1FAE5";
const HEAD = "Calibri", BODY = "Calibri Light", MONO = "Consolas";
const W = 10, H = 5.625;

let TOTAL = 0; // set after slides are declared
const builders = [];
function slide(fn) { builders.push(fn); }

function brandBar(s) {
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: W, h: 0.4, fill: { color: NAVY }, line: { color: NAVY } });
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0.4, w: W, h: 0.045, fill: { color: TEAL }, line: { color: TEAL } });
  s.addText("BizClinik ERP — Technical Documentation", { x: 0.35, y: 0, w: 7, h: 0.4, fontSize: 11, fontFace: HEAD, bold: true, color: "FFFFFF", valign: "middle", margin: 0 });
  s.addText("HAG_Ai", { x: W - 1.7, y: 0, w: 1.4, h: 0.4, fontSize: 10, fontFace: BODY, color: "DBEAFE", align: "right", valign: "middle", margin: 0 });
}
function pageNum(s, n) {
  s.addText(`${n} / ${TOTAL}`, { x: W - 1.0, y: H - 0.35, w: 0.8, h: 0.28, fontSize: 8.5, fontFace: BODY, color: MUTED, align: "right" });
}
function title(s, eyebrow, t, sub) {
  s.addText(eyebrow, { x: 0.45, y: 0.62, w: 9, h: 0.28, fontSize: 10.5, fontFace: HEAD, bold: true, color: TEAL, charSpacing: 4 });
  s.addText(t, { x: 0.45, y: 0.9, w: 9.1, h: 0.6, fontSize: 25, fontFace: HEAD, bold: true, color: INK });
  if (sub) s.addText(sub, { x: 0.45, y: 1.5, w: 9.1, h: 0.35, fontSize: 12, fontFace: BODY, color: MUTED });
}
function card(s, x, y, w, h, accent) {
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: SURFACE }, line: { color: BORDER, width: 0.5 },
    shadow: { type: "outer", color: "1F3864", blur: 6, offset: 2, angle: 90, opacity: 0.05 } });
  s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.06, h, fill: { color: accent || NAVY }, line: { color: accent || NAVY } });
}
function chip(s, x, y, w, h, glyph, label, desc, accent) {
  card(s, x, y, w, h, accent);
  s.addShape(pres.shapes.OVAL, { x: x + 0.22, y: y + 0.2, w: 0.5, h: 0.5, fill: { color: accent || NAVY }, line: { color: accent || NAVY } });
  s.addText(glyph, { x: x + 0.22, y: y + 0.2, w: 0.5, h: 0.5, fontSize: 15, fontFace: HEAD, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
  s.addText(label, { x: x + 0.85, y: y + 0.16, w: w - 0.95, h: 0.32, fontSize: 12.5, fontFace: HEAD, bold: true, color: INK, margin: 0 });
  s.addText(desc, { x: x + 0.85, y: y + 0.46, w: w - 0.95, h: h - 0.5, fontSize: 9.5, fontFace: BODY, color: MUTED, margin: 0 });
}
function bullets(s, x, y, w, h, items, opts) {
  opts = opts || {};
  s.addText(items.map(t => ({ text: t, options: { bullet: { code: "2022" }, color: opts.color || INK, fontSize: opts.fontSize || 11, fontFace: BODY, paraSpaceAfter: 4 } })),
    { x, y, w, h, valign: "top", margin: 0 });
}
function codeBox(s, x, y, w, h, lines) {
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: CODEBG }, line: { color: NAVY_DARK, width: 0.5 } });
  s.addText(lines.join("\n"), { x: x + 0.15, y: y + 0.1, w: w - 0.3, h: h - 0.2, fontSize: 9.5, fontFace: MONO, color: CODEFG, valign: "top", margin: 0, lineSpacingMultiple: 1.05 });
}
function kvTable(s, x, y, w, rows, colW) {
  // rows: [[k, v], ...]; renders a clean 2-col table
  const tableRows = rows.map((r, i) => ([
    { text: r[0], options: { fontFace: HEAD, bold: true, fontSize: 9.5, color: NAVY, fill: i % 2 ? "EEF2F9" : "FFFFFF", valign: "middle" } },
    { text: r[1], options: { fontFace: BODY, fontSize: 9.5, color: INK, fill: i % 2 ? "EEF2F9" : "FFFFFF", valign: "middle" } },
  ]));
  s.addTable(tableRows, { x, y, w, colW: colW || [w * 0.34, w * 0.66], border: { type: "solid", color: BORDER, pt: 0.5 }, rowH: 0.0, margin: 3, autoPage: false });
}
function footerTeal(s) { s.addShape(pres.shapes.RECTANGLE, { x: 0, y: H - 0.12, w: W, h: 0.12, fill: { color: TEAL }, line: { color: TEAL } }); }

// =========================================================================
// 1. TITLE
// =========================================================================
slide((s) => {
  s.background = { color: NAVY };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: H - 0.16, w: 4.2, h: 0.16, fill: { color: TEAL }, line: { color: TEAL } });
  s.addText("BizClinik ERP", { x: 0.6, y: 1.5, w: 9, h: 0.9, fontSize: 50, fontFace: HEAD, bold: true, color: "FFFFFF", charSpacing: -1 });
  s.addText("Technical Documentation", { x: 0.6, y: 2.45, w: 9, h: 0.7, fontSize: 30, fontFace: HEAD, bold: true, color: TEAL });
  s.addText("Build · Modules · Flows · Tech stack · Secrets · Backup & recovery · Operations", { x: 0.62, y: 3.35, w: 9, h: 0.5, fontSize: 14, fontFace: BODY, color: "DBEAFE" });
  s.addText("HAG_Ai  ·  erp.hagai.online  ·  Production on PostgreSQL", { x: 0.62, y: H - 0.7, w: 9, h: 0.35, fontSize: 11, fontFace: HEAD, bold: true, color: "BAE6FD", charSpacing: 2 });
});

// =========================================================================
// 2. WHAT THIS COVERS
// =========================================================================
slide((s) => {
  s.background = { color: BG }; brandBar(s);
  title(s, "CONTENTS", "What this document covers");
  const items = [
    ["1", "System architecture", "Components, hosting, request path", NAVY],
    ["2", "Modules", "The full accounting + SaaS feature set", TEAL],
    ["3", "Core flows", "Sales, purchase, CRM, billing, bank, FIRS", INFO],
    ["4", "Tech stack", "Languages, frameworks, infrastructure", NAVY],
    ["5", "Database", "PostgreSQL, database-per-tenant, migration", SUCCESS],
    ["6", "Secrets & credentials", "Inventory, locations, rotation", DANGER],
    ["7", "Backup & recovery", "pg_dump → encrypt → R2, restore steps", WARN],
    ["8", "Operations runbook", "Deploy, monitor, common tasks", TEAL],
  ];
  const cols = 2, cw = 4.5, chh = 0.85, gx = 0.3;
  const x0 = (W - (cols * cw + gx)) / 2;
  items.forEach((it, i) => {
    const x = x0 + (i % cols) * (cw + gx), y = 1.9 + Math.floor(i / cols) * (chh + 0.18);
    chip(s, x, y, cw, chh, it[0], it[1], it[2], it[3]);
  });
  pageNum(s, 2);
});

// =========================================================================
// 3. ARCHITECTURE
// =========================================================================
slide((s) => {
  s.background = { color: BG }; brandBar(s);
  title(s, "ARCHITECTURE", "How the system fits together",
    "Zero open ports — all public traffic enters through a Cloudflare named tunnel.");
  const box = (x, y, w, h, t, sub, accent) => {
    card(s, x, y, w, h, accent);
    s.addText(t, { x: x + 0.18, y: y + 0.12, w: w - 0.3, h: 0.3, fontSize: 12, fontFace: HEAD, bold: true, color: INK, margin: 0 });
    s.addText(sub, { x: x + 0.18, y: y + 0.42, w: w - 0.3, h: h - 0.5, fontSize: 9, fontFace: BODY, color: MUTED, margin: 0 });
  };
  box(0.5, 2.1, 2.0, 1.0, "Browser", "Users on web / mobile (responsive UI)", INFO);
  box(2.85, 2.1, 2.2, 1.0, "Cloudflare", "Tunnel + TLS + DNS\nerp / api / *-erp.hagai.online", TEAL);
  box(5.4, 1.45, 2.1, 0.95, "Streamlit UI", ":8501 · 23 pages\nsystemd: bizclinik-erp", NAVY);
  box(5.4, 2.65, 2.1, 0.95, "FastAPI", ":8600 · REST + webhooks\nsystemd: bizclinik-api", NAVY);
  box(7.85, 2.1, 1.7, 1.0, "PostgreSQL", "16 · DB-per-tenant\nlocalhost:5432", SUCCESS);
  box(5.4, 3.85, 2.1, 0.9, "Backups", "pg_dump → encrypt → R2\nnightly 02:30 UTC", WARN);
  box(7.85, 3.85, 1.7, 0.9, "Cloudflare R2", "Encrypted offsite\nbizclinik-backups", DANGER);
  // arrows (simple connectors)
  const arr = (x1, y1, x2, y2) => s.addShape(pres.shapes.LINE, { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color: MUTED, width: 1, endArrowType: "triangle" } });
  arr(2.5, 2.6, 2.85, 2.6); arr(5.05, 2.4, 5.4, 1.9); arr(5.05, 2.8, 5.4, 3.1);
  arr(7.5, 1.9, 7.85, 2.4); arr(7.5, 3.1, 7.85, 2.5); arr(7.5, 4.3, 7.85, 4.3); arr(6.45, 3.6, 6.45, 3.85);
  pageNum(s, 3);
});

// =========================================================================
// 4. REPOSITORY & BUILD
// =========================================================================
slide((s) => {
  s.background = { color: BG }; brandBar(s);
  title(s, "BUILD", "Repository, layout & delivery");
  card(s, 0.45, 1.95, 4.5, 3.2, NAVY);
  s.addText("Repository layout", { x: 0.65, y: 2.05, w: 4, h: 0.3, fontSize: 12, fontFace: HEAD, bold: true, color: INK });
  bullets(s, 0.65, 2.45, 4.2, 2.6, [
    "bizclinik_erp/  — package: models, services, exporters, importers, db layer",
    "app/  — Streamlit multi-page UI (Home + 23 pages)",
    "api/  — FastAPI app (REST + webhooks)",
    "scripts/  — backup CLI, ops scripts",
    "deploy/linux/  — setup, update, healthcheck, add-tenant-subdomain",
    "tests/  — 150+ pytest tests (accounting invariants, services, API)",
  ], { fontSize: 10 });
  card(s, 5.15, 1.95, 4.4, 3.2, TEAL);
  s.addText("Delivery pipeline", { x: 5.35, y: 2.05, w: 4, h: 0.3, fontSize: 12, fontFace: HEAD, bold: true, color: INK });
  bullets(s, 5.35, 2.45, 4.0, 1.2, [
    "GitHub: Habayode/bizclinik-erp (main)",
    "CI: GitHub Actions runs full pytest on every push/PR",
    "Deploy: git pull → migrate (if schema) → systemctl restart",
  ], { fontSize: 10 });
  codeBox(s, 5.35, 3.75, 4.0, 1.25, [
    "git pull --ff-only",
    "python -m bizclinik_erp migrate   # additive",
    "systemctl restart bizclinik-erp bizclinik-api",
  ]);
  pageNum(s, 4);
});

// =========================================================================
// 5. MODULE MAP
// =========================================================================
slide((s) => {
  s.background = { color: BG }; brandBar(s);
  title(s, "MODULES", "The full feature set", "Double-entry accounting core, Nigerian tax fit, and SaaS platform layers.");
  const mods = [
    ["Ledger", "Double-entry GL, journal posting, trial balance", NAVY],
    ["Sales", "Quotes, orders, invoices, receipts, AR", NAVY],
    ["Purchases", "Bills, payments, AP", NAVY],
    ["Inventory", "Stock moves, avg cost, COGS", NAVY],
    ["Banking + Recon", "Multi-bank import + bank-feed, auto-match", INFO],
    ["Payroll", "Graduated Nigerian PAYE, payslips", SUCCESS],
    ["Tax", "VAT, WHT certificates", SUCCESS],
    ["FIRS e-invoice", "Draft payload + QR (MBS-ready)", SUCCESS],
    ["Fixed assets", "Register + auto depreciation", NAVY],
    ["Reports", "P&L, Balance Sheet, Cash Flow, agings", NAVY],
    ["Multi-currency", "Foreign docs, realized + unrealized FX", WARN],
    ["Multi-tenant", "Per-tenant DBs, subdomains, isolation", TEAL],
    ["REST API", "Per-tenant keys, webhooks", TEAL],
    ["Billing", "Paystack / Flutterwave / Moniepoint", TEAL],
    ["CRM", "Leads, pipeline, follow-ups, convert", INFO],
    ["Invoice templates", "Per-tenant branding (logo, colour)", NAVY],
    ["Budgets + Month-end", "Variance, accruals, close", NAVY],
    ["Backups + Monitoring", "Encrypted R2, watchdog, CI, Sentry", DANGER],
  ];
  const cols = 3, cw = 3.05, chh = 0.62, gx = 0.12;
  const x0 = (W - (cols * cw + (cols - 1) * gx)) / 2;
  mods.forEach((m, i) => {
    const x = x0 + (i % cols) * (cw + gx), y = 1.95 + Math.floor(i / cols) * (chh + 0.1);
    card(s, x, y, cw, chh, m[2]);
    s.addText(m[0], { x: x + 0.16, y: y + 0.07, w: cw - 0.3, h: 0.25, fontSize: 10.5, fontFace: HEAD, bold: true, color: INK, margin: 0 });
    s.addText(m[1], { x: x + 0.16, y: y + 0.31, w: cw - 0.3, h: 0.28, fontSize: 8, fontFace: BODY, color: MUTED, margin: 0 });
  });
  pageNum(s, 5);
});

// ---- flow slide helper ----
function flowSlide(eyebrow, t, sub, steps, page, note) {
  slide((s) => {
    s.background = { color: BG }; brandBar(s);
    title(s, eyebrow, t, sub);
    const n = steps.length, gap = 0.25;
    const cw = (W - 0.9 - (n - 1) * gap) / n;
    steps.forEach((st, i) => {
      const x = 0.45 + i * (cw + gap), y = 2.25;
      card(s, x, y, cw, 2.0, st.c || TEAL);
      s.addShape(pres.shapes.OVAL, { x: x + 0.2, y: y + 0.18, w: 0.5, h: 0.5, fill: { color: st.c || TEAL }, line: { color: st.c || TEAL } });
      s.addText(String(i + 1), { x: x + 0.2, y: y + 0.18, w: 0.5, h: 0.5, fontSize: 16, fontFace: HEAD, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
      s.addText(st.t, { x: x + 0.18, y: y + 0.78, w: cw - 0.34, h: 0.4, fontSize: 12, fontFace: HEAD, bold: true, color: INK, margin: 0 });
      s.addText(st.d, { x: x + 0.18, y: y + 1.16, w: cw - 0.34, h: 0.75, fontSize: 9, fontFace: BODY, color: MUTED, margin: 0 });
      if (i < n - 1) s.addText("›", { x: x + cw - 0.02, y: y + 0.8, w: gap, h: 0.4, fontSize: 20, fontFace: HEAD, bold: true, color: MUTED, align: "center", margin: 0 });
    });
    if (note) s.addText(note, { x: 0.45, y: 4.5, w: 9.1, h: 0.5, fontSize: 10, fontFace: BODY, italic: true, color: NAVY });
    pageNum(s, page);
  });
}

// =========================================================================
// 6-11. FLOWS
// =========================================================================
flowSlide("FLOW · ACCOUNTING", "Sales cycle → the ledger",
  "Every document posts a balanced double-entry journal; the trial balance always balances.",
  [
    { t: "Quote / Order", d: "Optional pre-sale documents.", c: NAVY },
    { t: "Issue invoice", d: "DR Accounts Receivable; CR Sales + Output VAT; DR COGS / CR Inventory.", c: NAVY },
    { t: "Record receipt", d: "DR Bank; CR Accounts Receivable; FX gain/loss if foreign.", c: NAVY },
    { t: "Reports", d: "Flows straight into P&L, Balance Sheet, AR aging.", c: TEAL },
  ], 6,
  "Purchases mirror this: receive bill (DR Inventory/Input VAT, CR AP) → pay (DR AP, CR Bank).");

flowSlide("FLOW · MULTI-TENANT", "How a request routes to the right books",
  "Each business is an isolated PostgreSQL database; routing is by subdomain or login picker.",
  [
    { t: "Host detected", d: "<slug>-erp.hagai.online resolves the tenant slug.", c: TEAL },
    { t: "Control plane", d: "bizclinik_control DB maps slug → database.", c: TEAL },
    { t: "Active DB set", d: "Context var routes every query to bizclinik_t_<slug>.", c: NAVY },
    { t: "Isolated session", d: "Tenant only ever sees its own data.", c: NAVY },
  ], 7,
  "Default DB = bizclinik · Control = bizclinik_control · Tenant = bizclinik_t_<slug>.");

flowSlide("FLOW · BILLING", "Subscriptions on the provider-agnostic payments layer",
  "PAYMENTS_PROVIDER selects Paystack / Flutterwave / Moniepoint — no code change to switch.",
  [
    { t: "Choose plan", d: "Free activates instantly; paid → checkout.", c: TEAL },
    { t: "Initialize", d: "Provider returns a checkout URL + reference.", c: TEAL },
    { t: "Webhook", d: "Signed callback verified (HMAC / hash).", c: INFO },
    { t: "Activate", d: "Subscription set active for the billing period.", c: SUCCESS },
  ], 8,
  "State in control plane: subscription + billing_charge. Webhooks are signature-verified.");

flowSlide("FLOW · CRM", "Lead to customer, tied to the ledger",
  "Lightweight CRM in front of accounting; a won lead becomes a real Customer.",
  [
    { t: "Capture lead", d: "Name, company, source, owner.", c: INFO },
    { t: "Work pipeline", d: "Deal stages: Lead → Qualified → Proposal → Negotiation.", c: INFO },
    { t: "Convert", d: "Creates a Customer (idempotent) + optional deal.", c: TEAL },
    { t: "Invoice", d: "Customer flows into sales + statements.", c: NAVY },
  ], 9,
  "Follow-up activities bucket into overdue / today / upcoming.");

flowSlide("FLOW · BANK FEED", "Statements into reconciliation",
  "Manual CSV upload or push-in from a bank / aggregator via the API.",
  [
    { t: "Ingest", d: "CSV (GTB/Access/Zenith/FBN/Moniepoint) or JSON lines.", c: INFO },
    { t: "Parse", d: "Lenient header/date/amount normalisation.", c: INFO },
    { t: "Auto-match", d: "Statement lines ↔ GL postings (amount + date).", c: TEAL },
    { t: "Reconcile", d: "Review unmatched, finalise the period.", c: NAVY },
  ], 10,
  "API: POST /api/v1/bank/statements (structured lines or raw CSV).");

flowSlide("FLOW · FIRS E-INVOICE", "Draft e-invoice generation",
  "Builds a FIRS MBS-style payload + QR. Marked DRAFT until transmitted to FIRS.",
  [
    { t: "Pick invoice", d: "Any posted sales invoice.", c: SUCCESS },
    { t: "Build payload", d: "Supplier/customer/lines/tax, sanitised IRN.", c: SUCCESS },
    { t: "QR + JSON", d: "Compact QR; downloadable JSON.", c: TEAL },
    { t: "Submit (future)", d: "On FIRS onboarding: real CSID + QR.", c: WARN },
  ], 11,
  "Today's CSID/QR are placeholders; document_status = DRAFT until FIRS countersigns.");

// =========================================================================
// 12. TECH STACK — APPLICATION
// =========================================================================
slide((s) => {
  s.background = { color: BG }; brandBar(s);
  title(s, "TECH STACK", "Application & libraries");
  const stack = [
    ["Python 3.12", "Runtime"], ["SQLAlchemy 2.0", "ORM + GL primitives"],
    ["PostgreSQL 16", "System of record (DB-per-tenant)"], ["psycopg 3", "Postgres driver"],
    ["Streamlit", "Multi-page web UI"], ["FastAPI + Uvicorn", "REST API + webhooks"],
    ["ReportLab", "Invoice / statement PDFs"], ["Altair", "Dashboard charts"],
    ["pandas / openpyxl", "Data + xlsx import"], ["qrcode", "FIRS e-invoice QR"],
    ["boto3", "R2 (S3) offsite backups"], ["cryptography", "Client-side backup encryption"],
    ["sentry-sdk", "Optional error tracking"], ["pytest", "150+ tests (CI)"],
  ];
  const cols = 4, rows = Math.ceil(stack.length / cols);
  const cw = (W - 0.9 - (cols - 1) * 0.18) / cols, chh = 0.78;
  stack.forEach((it, i) => {
    const x = 0.45 + (i % cols) * (cw + 0.18), y = 2.0 + Math.floor(i / cols) * (chh + 0.18);
    card(s, x, y, cw, chh, NAVY);
    s.addText(it[0], { x: x + 0.15, y: y + 0.12, w: cw - 0.25, h: 0.3, fontSize: 11, fontFace: HEAD, bold: true, color: INK, margin: 0 });
    s.addText(it[1], { x: x + 0.15, y: y + 0.42, w: cw - 0.25, h: 0.3, fontSize: 8.5, fontFace: BODY, color: MUTED, margin: 0 });
  });
  pageNum(s, 12);
});

// =========================================================================
// 13. INFRASTRUCTURE
// =========================================================================
slide((s) => {
  s.background = { color: BG }; brandBar(s);
  title(s, "INFRASTRUCTURE", "Hosting & services");
  kvTable(s, 0.45, 1.95, 5.0, [
    ["Server", "DigitalOcean droplet · 1 vCPU / 2 GB + 2 GB swap"],
    ["OS / region", "Ubuntu 24.04 · London (lon1)"],
    ["Public IP", "165.227.224.154 (SSH only; no public app ports)"],
    ["Ingress", "Cloudflare named tunnel (cloudflared)"],
    ["DNS / zone", "hagai.online (Cloudflare)"],
    ["App hosts", "erp · api · <slug>-erp.hagai.online"],
    ["TLS", "Cloudflare Universal SSL (auto)"],
  ], [1.4, 3.6]);
  s.addText("systemd services & timers", { x: 5.65, y: 1.95, w: 4, h: 0.3, fontSize: 12, fontFace: HEAD, bold: true, color: INK });
  bullets(s, 5.65, 2.35, 3.95, 2.6, [
    "bizclinik-erp  — Streamlit UI (:8501), Restart=always",
    "bizclinik-api  — FastAPI/Uvicorn (:8600)",
    "cloudflared  — public tunnel",
    "bizclinik-backup.timer  — nightly 02:30 UTC",
    "bizclinik-health.timer  — watchdog every 5 min (auto-restart + alert)",
    "PostgreSQL 16  — local service, 127.0.0.1:5432",
  ], { fontSize: 10 });
  pageNum(s, 13);
});

// =========================================================================
// 14. DATABASE & MIGRATION
// =========================================================================
slide((s) => {
  s.background = { color: BG }; brandBar(s);
  title(s, "DATABASE", "PostgreSQL · database-per-tenant",
    "Migrated from SQLite with verified row counts + ledger sums. SQLite files frozen as rollback.");
  kvTable(s, 0.45, 2.0, 5.1, [
    ["Backend switch", "BIZCLINIK_DB_BACKEND = sqlite | postgres"],
    ["Default DB", "bizclinik"],
    ["Control plane", "bizclinik_control (tenants, API keys, billing)"],
    ["Per tenant", "bizclinik_t_<slug>"],
    ["Abstraction", "bizclinik_erp/dbbackend.py (key → URL)"],
    ["Schema migrate", "python -m bizclinik_erp migrate (additive)"],
    ["Data migrate", "python -m bizclinik_erp pg-migrate (verified)"],
  ], [1.6, 3.5]);
  s.addText("Why database-per-tenant", { x: 5.75, y: 2.0, w: 3.8, h: 0.3, fontSize: 12, fontFace: HEAD, bold: true, color: INK });
  bullets(s, 5.75, 2.4, 3.8, 2.2, [
    "Mirrors the original per-tenant SQLite isolation",
    "One tenant cannot read another's data",
    "Postgres handles many concurrent writers (no file lock)",
    "Rollback: set backend=sqlite + restart (pre-cutover state)",
  ], { fontSize: 10 });
  pageNum(s, 14);
});

// =========================================================================
// 15. SECRETS & CREDENTIALS
// =========================================================================
slide((s) => {
  s.background = { color: BG }; brandBar(s);
  title(s, "SECRETS & CREDENTIALS", "Inventory — names & locations (not values)");
  s.addShape(pres.shapes.RECTANGLE, { x: 0.45, y: 1.85, w: 9.1, h: 0.5, fill: { color: "FEF2F2" }, line: { color: DANGER, width: 0.75 } });
  s.addText("⚠  Secret VALUES are never stored in this deck. They live in chmod-600 env files on the server and your password manager. Rotate via the issuing service.",
    { x: 0.6, y: 1.85, w: 8.8, h: 0.5, fontSize: 9.5, fontFace: BODY, color: DANGER, valign: "middle", margin: 0 });
  kvTable(s, 0.45, 2.5, 9.1, [
    ["BIZCLINIK_API_KEY", "REST API auth (default DB) · /opt/bizclinik-erp/.env"],
    ["Per-tenant API keys", "SHA-256 hashed in control plane; plaintext shown once at creation"],
    ["PGPASSWORD (role bizclinik)", "Postgres login · /etc/bizclinik/pg.env (chmod 600)"],
    ["BIZCLINIK_BACKUP_PASSPHRASE", "RECOVERY SECRET — decrypts R2 backups · /etc/bizclinik/backup.env + password manager"],
    ["R2_ACCESS_KEY_ID / SECRET", "Cloudflare R2 (S3) · /etc/bizclinik/backup.env"],
    ["Cloudflare API token", "DNS/zone automation · used ad-hoc, not stored on box"],
    ["Tunnel credentials", "/etc/cloudflared/<tunnel-id>.json"],
    ["Server root (SSH)", "Droplet access · your password manager"],
  ], [3.0, 6.1]);
  pageNum(s, 15);
});

// =========================================================================
// 16. BACKUP PROCESS
// =========================================================================
slide((s) => {
  s.background = { color: BG }; brandBar(s);
  title(s, "BACKUP", "Process & procedures",
    "Encrypted, offsite, nightly — and self-contained (the dump leaves the box already encrypted).");
  const steps = [
    { t: "pg_dump", d: "Each DB (default / control / tenant) → .sql", c: NAVY },
    { t: "Encrypt", d: "Client-side AES (PBKDF2 + Fernet) with the passphrase", c: DANGER },
    { t: "Upload", d: "Push to Cloudflare R2 via S3 API (boto3)", c: WARN },
    { t: "Prune", d: "Keep newest per scope; drop old", c: TEAL },
  ];
  const n = steps.length, cw = (W - 0.9 - (n - 1) * 0.25) / n;
  steps.forEach((st, i) => {
    const x = 0.45 + i * (cw + 0.25), y = 2.0;
    card(s, x, y, cw, 1.3, st.c);
    s.addText(`${i + 1}. ${st.t}`, { x: x + 0.16, y: y + 0.14, w: cw - 0.3, h: 0.3, fontSize: 12, fontFace: HEAD, bold: true, color: INK, margin: 0 });
    s.addText(st.d, { x: x + 0.16, y: y + 0.48, w: cw - 0.3, h: 0.7, fontSize: 9, fontFace: BODY, color: MUTED, margin: 0 });
  });
  kvTable(s, 0.45, 3.55, 5.4, [
    ["Schedule", "Nightly 02:30 UTC (bizclinik-backup.timer)"],
    ["Destination", "R2 bucket bizclinik-backups, per-scope folders"],
    ["Retention", "retain_days 30, min 7 per scope"],
    ["Config", "/etc/bizclinik/backup.env + pg.env"],
  ], [1.5, 3.9]);
  s.addText("Manual run", { x: 6.0, y: 3.55, w: 3.5, h: 0.3, fontSize: 11, fontFace: HEAD, bold: true, color: INK });
  codeBox(s, 6.0, 3.9, 3.55, 1.05, [
    "scripts/backup.py snapshot   # + offsite",
    "scripts/backup.py offsite    # push only",
    "scripts/backup.py list",
  ]);
  pageNum(s, 16);
});

// =========================================================================
// 17. DISASTER RECOVERY
// =========================================================================
slide((s) => {
  s.background = { color: BG }; brandBar(s);
  title(s, "RECOVERY", "Disaster recovery & the recovery secret",
    "If the droplet is lost, the books survive in R2 — provided you have the passphrase.");
  card(s, 0.45, 1.95, 4.5, 3.1, DANGER);
  s.addText("Restore from R2", { x: 0.65, y: 2.05, w: 4, h: 0.3, fontSize: 12, fontFace: HEAD, bold: true, color: INK });
  bullets(s, 0.65, 2.45, 4.2, 2.5, [
    "Provision a fresh droplet + PostgreSQL",
    "Download the encrypted .sql.enc from R2 (S3 API)",
    "Decrypt with BIZCLINIK_BACKUP_PASSPHRASE",
    "psql restore each .sql into its database",
    "Set PG* + backend=postgres; restart services",
    "Re-point Cloudflare tunnel / DNS",
  ], { fontSize: 10 });
  card(s, 5.15, 1.95, 4.4, 3.1, WARN);
  s.addText("The recovery secret", { x: 5.35, y: 2.05, w: 4, h: 0.3, fontSize: 12, fontFace: HEAD, bold: true, color: INK });
  bullets(s, 5.35, 2.45, 4.0, 1.5, [
    "BIZCLINIK_BACKUP_PASSPHRASE is the ONLY key that decrypts the R2 backups",
    "Stored on the box (/etc/bizclinik/backup.env) AND must be kept in your password manager",
    "Lose it → offsite backups are unrecoverable",
  ], { fontSize: 10, color: INK });
  s.addText("Rollback (post-migration): set BIZCLINIK_DB_BACKEND=sqlite and restart — reverts to the frozen pre-cutover SQLite books (loses any writes made after cutover).",
    { x: 5.35, y: 4.0, w: 4.0, h: 1.0, fontSize: 9.5, fontFace: BODY, italic: true, color: NAVY, margin: 0 });
  pageNum(s, 17);
});

// =========================================================================
// 18. MONITORING & API SECURITY
// =========================================================================
slide((s) => {
  s.background = { color: BG }; brandBar(s);
  title(s, "OPERATIONS", "Monitoring, security & API");
  s.addText("Monitoring", { x: 0.45, y: 1.95, w: 3, h: 0.3, fontSize: 12, fontFace: HEAD, bold: true, color: INK });
  bullets(s, 0.45, 2.3, 3.0, 2.4, [
    "Health watchdog every 5 min: checks erp/api/tenant; auto-restarts a failed service + emails alert",
    "GitHub Actions CI on every push",
    "Sentry hook (set SENTRY_DSN to enable)",
    "Restart=always on app services",
  ], { fontSize: 10 });
  s.addText("Security model", { x: 3.65, y: 1.95, w: 3, h: 0.3, fontSize: 12, fontFace: HEAD, bold: true, color: INK });
  bullets(s, 3.65, 2.3, 3.0, 2.4, [
    "No public app ports — Cloudflare tunnel only",
    "Login: per-tenant users + roles; 5-try lockout",
    "REST: per-tenant API keys (SHA-256 hashed)",
    "Webhooks: provider signature verified",
    "Secrets in chmod-600 env files",
  ], { fontSize: 10 });
  s.addText("REST API (key in X-API-Key)", { x: 6.85, y: 1.95, w: 3, h: 0.3, fontSize: 12, fontFace: HEAD, bold: true, color: INK });
  bullets(s, 6.85, 2.3, 2.75, 2.4, [
    "/customers /products /invoices",
    "/reports/* (TB, P&L, BS)",
    "/bank/statements (bank feed)",
    "/crm/* /billing/*",
    "/billing/webhook/{provider}",
  ], { fontSize: 10 });
  pageNum(s, 18);
});

// =========================================================================
// 19. RUNBOOK / REFERENCE
// =========================================================================
slide((s) => {
  s.background = { color: BG }; brandBar(s);
  title(s, "RUNBOOK", "Common operations — quick reference");
  codeBox(s, 0.45, 1.95, 9.1, 3.05, [
    "# Deploy an update",
    "ssh root@165.227.224.154 ; cd /opt/bizclinik-erp",
    "git pull --ff-only && python -m bizclinik_erp migrate",
    "systemctl restart bizclinik-erp bizclinik-api",
    "",
    "# Add a tenant + its free HTTPS subdomain",
    "python -m bizclinik_erp tenant-create <slug> \"<Name>\" --admin-password ***",
    "deploy/linux/add-tenant-subdomain.sh <slug>",
    "",
    "# Backup now / restore",
    "scripts/backup.py snapshot          # pg_dump -> encrypt -> R2",
    "# restore: download .sql.enc -> decrypt(passphrase) -> psql -d <db> -f dump.sql",
    "",
    "# Health / status",
    "systemctl is-active bizclinik-erp bizclinik-api cloudflared postgresql",
  ]);
  pageNum(s, 19);
});

// =========================================================================
// 20. CLOSING
// =========================================================================
slide((s) => {
  s.background = { color: NAVY };
  s.addText("Production-ready.", { x: 0.6, y: 1.7, w: 9, h: 0.8, fontSize: 40, fontFace: HEAD, bold: true, color: "FFFFFF" });
  s.addText("Documented, tested, monitored, and backed up offsite.", { x: 0.62, y: 2.6, w: 9, h: 0.5, fontSize: 15, fontFace: BODY, color: "DBEAFE" });
  const facts = [["TESTS", "150+ (CI green)"], ["DATABASE", "PostgreSQL 16"], ["BACKUPS", "Encrypted → R2 nightly"]];
  facts.forEach((c, i) => {
    const x = 0.6 + i * 3.1;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 3.55, w: 2.9, h: 1.0, fill: { color: NAVY_DARK }, line: { color: TEAL, width: 1.5 } });
    s.addText(c[0], { x: x + 0.2, y: 3.65, w: 2.5, h: 0.3, fontSize: 10, fontFace: HEAD, bold: true, color: TEAL, charSpacing: 3, margin: 0 });
    s.addText(c[1], { x: x + 0.2, y: 3.95, w: 2.5, h: 0.45, fontSize: 14, fontFace: HEAD, bold: true, color: "FFFFFF", margin: 0 });
  });
  footerTeal(s);
});

// ---- render ----
TOTAL = builders.length;
builders.forEach((fn) => fn(pres.addSlide()));
pres.writeFile({ fileName: "C:/Users/User/Downloads/bizclinik-erp/BizClinik_ERP_Technical_Documentation_2026-06-05.pptx" })
  .then((fn) => console.log("wrote", fn, "—", TOTAL, "slides"));
