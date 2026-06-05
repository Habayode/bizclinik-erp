// BizClinik ERP — Explainer Deck
// Navy + teal brand. 16:9. Heavy whitespace. Brand bar motif.

const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";  // 10" x 5.625"
pres.author = "HAG_Ai";
pres.company = "HAG_Ai";
pres.title = "BizClinik ERP — Explainer";

// ---- Brand --------------------------------------------------------------
const NAVY      = "1F3864";
const NAVY_DARK = "16284F";
const TEAL      = "0EA5A4";
const INK       = "0F172A";
const MUTED     = "64748B";
const BG        = "F4F6FB";
const SURFACE   = "FFFFFF";
const BORDER    = "E5E7EB";
const SUCCESS   = "16A34A";
const WARN      = "F59E0B";
const DANGER    = "DC2626";
const INFO      = "2563EB";

const HEAD_FONT = "Calibri";
const BODY_FONT = "Calibri Light";

// ---- Layout helpers -----------------------------------------------------
const W = 10, H = 5.625;

// Brand bar at the top of every content slide
function brandBar(slide) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: W, h: 0.45, fill: { color: NAVY }, line: { color: NAVY }
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0.45, w: W, h: 0.05, fill: { color: TEAL }, line: { color: TEAL }
  });
  slide.addText("BizClinik ERP", {
    x: 0.4, y: 0, w: 5, h: 0.45,
    fontSize: 12, fontFace: HEAD_FONT, bold: true, color: "FFFFFF",
    valign: "middle", margin: 0,
  });
  slide.addText("hagai.online", {
    x: W - 2.2, y: 0, w: 1.9, h: 0.45,
    fontSize: 11, fontFace: BODY_FONT, color: "DBEAFE",
    align: "right", valign: "middle", margin: 0,
  });
}

function pageNumber(slide, n, total) {
  slide.addText(`${n} / ${total}`, {
    x: W - 1.0, y: H - 0.4, w: 0.8, h: 0.3,
    fontSize: 9, fontFace: BODY_FONT, color: MUTED, align: "right",
  });
}

function sectionTitle(slide, eyebrow, title, subtitle) {
  slide.addText(eyebrow, {
    x: 0.5, y: 0.75, w: 9, h: 0.3,
    fontSize: 11, fontFace: HEAD_FONT, bold: true, color: TEAL,
    charSpacing: 4,
  });
  slide.addText(title, {
    x: 0.5, y: 1.05, w: 9, h: 0.7,
    fontSize: 30, fontFace: HEAD_FONT, bold: true, color: INK,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.5, y: 1.75, w: 9, h: 0.4,
      fontSize: 13, fontFace: BODY_FONT, color: MUTED,
    });
  }
}

// Coloured rounded "chip" card with icon-letter, label, description
function chipCard(slide, x, y, w, h, glyph, label, desc, color) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: SURFACE }, line: { color: BORDER, width: 0.5 },
    shadow: { type: "outer", color: "1F3864", blur: 8, offset: 2,
              angle: 90, opacity: 0.06 },
  });
  // Accent stripe on left
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 0.08, h, fill: { color: color || NAVY }, line: { color: color || NAVY },
  });
  // Icon disc
  slide.addShape(pres.shapes.OVAL, {
    x: x + 0.25, y: y + 0.22, w: 0.55, h: 0.55,
    fill: { color: (color || NAVY) + "" },
    line: { color: color || NAVY },
  });
  slide.addText(glyph, {
    x: x + 0.25, y: y + 0.22, w: 0.55, h: 0.55,
    fontSize: 18, fontFace: HEAD_FONT, bold: true, color: "FFFFFF",
    align: "center", valign: "middle", margin: 0,
  });
  // Label
  slide.addText(label, {
    x: x + 0.95, y: y + 0.18, w: w - 1.0, h: 0.35,
    fontSize: 14, fontFace: HEAD_FONT, bold: true, color: INK, margin: 0,
  });
  // Description
  slide.addText(desc, {
    x: x + 0.95, y: y + 0.5, w: w - 1.05, h: h - 0.55,
    fontSize: 10.5, fontFace: BODY_FONT, color: MUTED, margin: 0,
  });
}

// Step pill for sales/purchase cycles
function stepPill(slide, x, y, n, label, descLines) {
  slide.addShape(pres.shapes.OVAL, {
    x, y, w: 0.55, h: 0.55,
    fill: { color: TEAL }, line: { color: TEAL },
  });
  slide.addText(String(n), {
    x, y, w: 0.55, h: 0.55,
    fontSize: 18, fontFace: HEAD_FONT, bold: true, color: "FFFFFF",
    align: "center", valign: "middle", margin: 0,
  });
  slide.addText(label, {
    x: x + 0.7, y: y - 0.02, w: 2.5, h: 0.32,
    fontSize: 13, fontFace: HEAD_FONT, bold: true, color: INK, margin: 0,
  });
  slide.addText(descLines, {
    x: x + 0.7, y: y + 0.3, w: 2.5, h: 1.2,
    fontSize: 9.5, fontFace: BODY_FONT, color: MUTED, margin: 0,
  });
}

const TOTAL = 14;
const slides = [];

// =========================================================================
// 1. TITLE
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: NAVY };
  slides.push(s);

  // Subtle teal accent rectangle bottom-right
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.5, y: H - 0.18, w: 3.5, h: 0.18, fill: { color: TEAL }, line: { color: TEAL },
  });
  // Wordmark
  s.addText("BizClinik", {
    x: 0.6, y: 1.6, w: 9, h: 0.9,
    fontSize: 64, fontFace: HEAD_FONT, bold: true, color: "FFFFFF",
    charSpacing: -2,
  });
  s.addText("ERP", {
    x: 0.6, y: 2.4, w: 9, h: 0.9,
    fontSize: 64, fontFace: HEAD_FONT, bold: true, color: TEAL,
    charSpacing: -2,
  });
  // Tagline
  s.addText("Double-entry accounting for Nigerian SMEs, on the web.", {
    x: 0.6, y: 3.45, w: 9, h: 0.5,
    fontSize: 17, fontFace: BODY_FONT, color: "DBEAFE",
  });
  // Footer
  s.addText("HAG_Ai  ·  erp.hagai.online", {
    x: 0.6, y: H - 0.7, w: 9, h: 0.35,
    fontSize: 11, fontFace: HEAD_FONT, bold: true, color: "BAE6FD", charSpacing: 3,
  });
}

// =========================================================================
// 2. THE PROBLEM
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG };
  slides.push(s);
  brandBar(s);
  sectionTitle(s, "THE PROBLEM",
    "Most SMEs still run on spreadsheets.",
    "The classic BizClinik xlsx gives you forms — but no real ledger underneath.");

  const items = [
    { g: "x", l: "No double-entry ledger",
      d: "Numbers live in cells. Nothing forces debits to equal credits. Reports drift over time.", c: DANGER },
    { g: "x", l: "No live dashboards",
      d: "P&L, balance sheet and cash flow exist only when someone manually refreshes formulas.", c: DANGER },
    { g: "x", l: "Single-user, single-file",
      d: "One person edits at a time. Email the workbook to share. Version conflicts everywhere.", c: DANGER },
    { g: "x", l: "Manual VAT + COGS",
      d: "Output VAT, input VAT, and cost of goods sold are recomputed by hand each month.", c: DANGER },
  ];
  const cardW = 4.3, cardH = 1.1;
  items.forEach((it, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    chipCard(s, 0.5 + col * 4.6, 2.4 + row * 1.3, cardW, cardH, it.g, it.l, it.d, it.c);
  });
  pageNumber(s, 2, TOTAL);
}

// =========================================================================
// 3. THE SOLUTION
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG };
  slides.push(s);
  brandBar(s);
  sectionTitle(s, "THE SOLUTION",
    "A proper ERP, built on a system of record.",
    "SQLite ledger · double-entry GL · multi-page web UI · single password gate.");

  // Three big pillar boxes
  const pillars = [
    { t: "System of record",
      d: "Every invoice, bill, receipt and payment lands in one balanced journal entry. Trial Balance always equals zero.",
      g: "1" },
    { t: "Web, not Excel",
      d: "Multi-page Streamlit UI. Open anywhere. Add a user, share the URL — no file passing.",
      g: "2" },
    { t: "Open data",
      d: "SQLite file you can back up, export, audit. CLI + Python API on the same engine.",
      g: "3" },
  ];
  pillars.forEach((p, i) => {
    const x = 0.5 + i * 3.13;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.3, w: 2.93, h: 2.55,
      fill: { color: SURFACE }, line: { color: BORDER, width: 0.5 },
      shadow: { type: "outer", color: "1F3864", blur: 8, offset: 2,
                angle: 90, opacity: 0.06 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.3, w: 2.93, h: 0.06,
      fill: { color: TEAL }, line: { color: TEAL },
    });
    s.addText(p.g, {
      x: x + 0.3, y: 2.55, w: 0.5, h: 0.5,
      fontSize: 28, fontFace: HEAD_FONT, bold: true, color: TEAL, margin: 0,
    });
    s.addText(p.t, {
      x: x + 0.3, y: 3.15, w: 2.55, h: 0.4,
      fontSize: 17, fontFace: HEAD_FONT, bold: true, color: INK, margin: 0,
    });
    s.addText(p.d, {
      x: x + 0.3, y: 3.6, w: 2.55, h: 1.15,
      fontSize: 11.5, fontFace: BODY_FONT, color: MUTED, margin: 0,
    });
  });
  pageNumber(s, 3, TOTAL);
}

// =========================================================================
// 4. MODULE MAP
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG };
  slides.push(s);
  brandBar(s);
  sectionTitle(s, "WHAT'S INSIDE",
    "Ten modules. One ledger.",
    "Each module reads and writes the same general ledger underneath.");

  const mods = [
    ["Sales",          "Quote / Order / Invoice / Receipt",   TEAL],
    ["Purchases",      "PO / Bill / Payment",                 NAVY],
    ["Inventory",      "Weighted-avg cost, stock card",       NAVY],
    ["Banking",        "Transfers, charges, reconcile",       INFO],
    ["Payroll",        "PAYE, pension, payslips",             NAVY],
    ["General Ledger", "Trial balance, journal entry",        NAVY],
    ["Reports",        "P&L, BS, CF, AR/AP aging",            TEAL],
    ["Tax",            "VAT return, WHT position",            WARN],
    ["Settings",       "Company, customers, suppliers",       NAVY],
    ["Data",           "Import xlsx, manage DB",              NAVY],
  ];
  const cols = 5, rows = 2;
  const padX = 0.4, padY = 2.35;
  const cw = (W - padX*2 - (cols-1)*0.2) / cols;
  const ch = 1.25;
  mods.forEach((m, i) => {
    const col = i % cols, row = Math.floor(i / cols);
    const x = padX + col * (cw + 0.2);
    const y = padY + row * (ch + 0.2);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: cw, h: ch,
      fill: { color: SURFACE }, line: { color: BORDER, width: 0.5 },
      shadow: { type: "outer", color: "1F3864", blur: 6, offset: 2,
                angle: 90, opacity: 0.05 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.08, h: ch, fill: { color: m[2] }, line: { color: m[2] },
    });
    s.addText(m[0], {
      x: x + 0.22, y: y + 0.18, w: cw - 0.3, h: 0.35,
      fontSize: 14, fontFace: HEAD_FONT, bold: true, color: INK, margin: 0,
    });
    s.addText(m[1], {
      x: x + 0.22, y: y + 0.55, w: cw - 0.3, h: 0.7,
      fontSize: 9.5, fontFace: BODY_FONT, color: MUTED, margin: 0,
    });
  });
  pageNumber(s, 4, TOTAL);
}

// =========================================================================
// 5. SALES CYCLE
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG };
  slides.push(s);
  brandBar(s);
  sectionTitle(s, "SALES CYCLE",
    "Quote → Order → Invoice → Receipt.",
    "Issuing the invoice auto-posts revenue, VAT, AR, and COGS in one journal entry.");

  const steps = [
    { l: "Quotation",   d: "Customer + line items. No ledger impact." },
    { l: "Sales Order", d: "Convert quote when accepted. Operational only." },
    { l: "Invoice",     d: "Auto-posts DR Receivable · CR Revenue · CR Output VAT · plus DR COGS · CR Inventory at avg cost." },
    { l: "Receipt",     d: "DR Bank · CR Receivable. Marks invoice paid / partial." },
  ];
  steps.forEach((st, i) => {
    const x = 0.5 + i * 2.35;
    stepPill(s, x, 2.6, i + 1, st.l, st.d);
  });
  // Arrows between steps
  for (let i = 0; i < steps.length - 1; i++) {
    const x = 0.5 + i * 2.35 + 0.55 + 1.5;
    s.addShape(pres.shapes.RIGHT_TRIANGLE, {
      x, y: 2.75, w: 0.25, h: 0.25,
      fill: { color: NAVY }, line: { color: NAVY }, rotate: 90,
    });
  }

  // Bottom journal-entry callout
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 4.45, w: 9, h: 0.9,
    fill: { color: NAVY }, line: { color: NAVY },
  });
  s.addText("Trial Balance impact of one invoice", {
    x: 0.75, y: 4.5, w: 4, h: 0.3,
    fontSize: 11, fontFace: HEAD_FONT, bold: true, color: "BAE6FD",
    charSpacing: 2, margin: 0,
  });
  s.addText("DR Accounts Receivable     ·     CR Sales     ·     CR Output VAT     ·     DR COGS     ·     CR Inventory", {
    x: 0.75, y: 4.85, w: 8.5, h: 0.4,
    fontSize: 13, fontFace: HEAD_FONT, color: "FFFFFF", margin: 0,
  });

  pageNumber(s, 5, TOTAL);
}

// =========================================================================
// 6. PURCHASE CYCLE
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG };
  slides.push(s);
  brandBar(s);
  sectionTitle(s, "PURCHASE CYCLE",
    "PO → Bill → Payment.",
    "Receiving a bill capitalises inventory or expenses it, and updates weighted-avg cost.");

  const steps = [
    { l: "Purchase Order", d: "Supplier + items. Operational only." },
    { l: "Bill",           d: "Stockable lines: DR Inventory · DR Input VAT · CR Payable. Non-stock: DR expense account." },
    { l: "Stock movement", d: "Auto-update qty on hand + recompute avg cost: ((qty × avg) + (new × rate)) ÷ total." },
    { l: "Payment",        d: "DR Payable · CR Bank. Marks bill paid / partial." },
  ];
  steps.forEach((st, i) => {
    const x = 0.5 + i * 2.35;
    stepPill(s, x, 2.6, i + 1, st.l, st.d);
  });
  for (let i = 0; i < steps.length - 1; i++) {
    const x = 0.5 + i * 2.35 + 0.55 + 1.5;
    s.addShape(pres.shapes.RIGHT_TRIANGLE, {
      x, y: 2.75, w: 0.25, h: 0.25,
      fill: { color: NAVY }, line: { color: NAVY }, rotate: 90,
    });
  }

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 4.45, w: 9, h: 0.9,
    fill: { color: NAVY }, line: { color: NAVY },
  });
  s.addText("Trial Balance impact of one bill", {
    x: 0.75, y: 4.5, w: 4, h: 0.3,
    fontSize: 11, fontFace: HEAD_FONT, bold: true, color: "BAE6FD",
    charSpacing: 2, margin: 0,
  });
  s.addText("DR Inventory  ·  DR Input VAT     ·     CR Accounts Payable     ·     stock card + avg cost updated", {
    x: 0.75, y: 4.85, w: 8.5, h: 0.4,
    fontSize: 13, fontFace: HEAD_FONT, color: "FFFFFF", margin: 0,
  });

  pageNumber(s, 6, TOTAL);
}

// =========================================================================
// 7. FIRST-PRINCIPLES ACCOUNTING
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG };
  slides.push(s);
  brandBar(s);
  sectionTitle(s, "WHY THIS MATTERS",
    "Every report comes from the ledger.",
    "Reports are derived, not typed. The numbers can't drift.");

  // Equation panel
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 2.4, w: 4.2, h: 2.6,
    fill: { color: NAVY }, line: { color: NAVY },
  });
  s.addText("Assets", {
    x: 0.5, y: 2.7, w: 4.2, h: 0.5,
    fontSize: 28, fontFace: HEAD_FONT, bold: true, color: "FFFFFF",
    align: "center", margin: 0,
  });
  s.addText("=", {
    x: 0.5, y: 3.2, w: 4.2, h: 0.4,
    fontSize: 22, fontFace: HEAD_FONT, color: TEAL,
    align: "center", margin: 0,
  });
  s.addText("Liabilities  +  Equity", {
    x: 0.5, y: 3.6, w: 4.2, h: 0.5,
    fontSize: 24, fontFace: HEAD_FONT, bold: true, color: "FFFFFF",
    align: "center", margin: 0,
  });
  s.addText("Enforced at every JE post.", {
    x: 0.5, y: 4.3, w: 4.2, h: 0.4,
    fontSize: 12, fontFace: BODY_FONT, color: "BAE6FD",
    align: "center", margin: 0,
  });

  // Right column — three short statements
  const points = [
    { h: "DR = CR at post time", d: "Refuse the entry if it doesn't balance. No bad data enters the books." },
    { h: "Reports derive from the GL", d: "P&L, Balance Sheet, Cash Flow read posted journal lines — never spreadsheet cells." },
    { h: "Audit-friendly", d: "Every transaction has an entry no. Drill from any report cell to its source documents." },
  ];
  points.forEach((p, i) => {
    const y = 2.4 + i * 0.88;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 5.05, y, w: 0.05, h: 0.8, fill: { color: TEAL }, line: { color: TEAL },
    });
    s.addText(p.h, {
      x: 5.25, y, w: 4.5, h: 0.32,
      fontSize: 14, fontFace: HEAD_FONT, bold: true, color: INK, margin: 0,
    });
    s.addText(p.d, {
      x: 5.25, y: y + 0.3, w: 4.5, h: 0.55,
      fontSize: 11, fontFace: BODY_FONT, color: MUTED, margin: 0,
    });
  });
  pageNumber(s, 7, TOTAL);
}

// =========================================================================
// 8. IMPORT FROM BIZCLINIK XLSX
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG };
  slides.push(s);
  brandBar(s);
  sectionTitle(s, "ZERO-FRICTION MIGRATION",
    "Drop in your existing BizClinik workbook.",
    "Customers, suppliers, products and every historical row get posted as proper journal entries.");

  // Flow diagram: xlsx -> arrow -> SQLite
  // Left box (xlsx)
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 2.6, w: 2.7, h: 2.0,
    fill: { color: SURFACE }, line: { color: BORDER, width: 0.5 },
    shadow: { type: "outer", color: "1F3864", blur: 8, offset: 2, angle: 90, opacity: 0.06 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 2.6, w: 2.7, h: 0.06, fill: { color: SUCCESS }, line: { color: SUCCESS },
  });
  s.addText("Legacy xlsx", {
    x: 0.85, y: 2.8, w: 2.4, h: 0.35,
    fontSize: 14, fontFace: HEAD_FONT, bold: true, color: INK, margin: 0,
  });
  s.addText(
    "Company Details\nInventory List\nSupplier Module\nCustomer Module\nOperating Module\nChart of Accounts",
    { x: 0.85, y: 3.15, w: 2.4, h: 1.4,
      fontSize: 11, fontFace: BODY_FONT, color: MUTED, margin: 0, valign: "top" }
  );

  // Arrow
  s.addShape(pres.shapes.RIGHT_TRIANGLE, {
    x: 3.7, y: 3.45, w: 0.5, h: 0.4,
    fill: { color: TEAL }, line: { color: TEAL }, rotate: 90,
  });
  s.addText("Importer", {
    x: 3.45, y: 3.0, w: 1.0, h: 0.35,
    fontSize: 11, fontFace: HEAD_FONT, bold: true, color: TEAL,
    align: "center", charSpacing: 3, margin: 0,
  });
  s.addText("python -m bizclinik_erp\nimport-bizclinik file.xlsx", {
    x: 3.25, y: 3.95, w: 1.45, h: 0.5,
    fontSize: 8.5, fontFace: "Consolas", color: MUTED,
    align: "center", margin: 0,
  });

  // Right box (ERP)
  s.addShape(pres.shapes.RECTANGLE, {
    x: 4.7, y: 2.6, w: 4.8, h: 2.0,
    fill: { color: NAVY }, line: { color: NAVY },
  });
  s.addText("BizClinik ERP — live ledger", {
    x: 4.95, y: 2.8, w: 4.4, h: 0.35,
    fontSize: 14, fontFace: HEAD_FONT, bold: true, color: "FFFFFF", margin: 0,
  });
  s.addText(
    "Master records: customers, suppliers, products\nBalanced journal entries per row\nInventory at weighted-avg cost\nTrial Balance balances\nP&L, Balance Sheet, Cash Flow available immediately",
    { x: 4.95, y: 3.15, w: 4.4, h: 1.4,
      fontSize: 11, fontFace: BODY_FONT, color: "DBEAFE", margin: 0, valign: "top" }
  );

  pageNumber(s, 8, TOTAL);
}

// =========================================================================
// 9. REPORTS
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG };
  slides.push(s);
  brandBar(s);
  sectionTitle(s, "FINANCIAL REPORTS",
    "Statements you can hand to your accountant.",
    "Date-filter any report. Drill into a number to see the supporting transactions.");

  const reps = [
    ["P&L",            "Revenue, direct costs, gross profit, opex, net profit — by period."],
    ["Balance Sheet",  "A = L + E, with current-year earnings auto-computed from the ledger."],
    ["Cash Flow",      "Indirect method: net profit + working-capital changes + investing + financing."],
    ["AR Aging",       "Open invoices by customer, bucketed 0-30 / 31-60 / 61-90 / 90+."],
    ["AP Aging",       "Open bills by supplier, same buckets — see who you owe and when."],
    ["VAT Return",     "Output VAT − Input VAT for any period. WHT receivable + payable too."],
  ];
  const cw = 4.4, ch = 0.95;
  reps.forEach((r, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.5 + col * 4.6, y = 2.35 + row * 1.05;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: cw, h: ch,
      fill: { color: SURFACE }, line: { color: BORDER, width: 0.5 },
      shadow: { type: "outer", color: "1F3864", blur: 6, offset: 2, angle: 90, opacity: 0.05 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.06, h: ch, fill: { color: TEAL }, line: { color: TEAL },
    });
    s.addText(r[0], {
      x: x + 0.2, y: y + 0.12, w: cw - 0.3, h: 0.3,
      fontSize: 14, fontFace: HEAD_FONT, bold: true, color: INK, margin: 0,
    });
    s.addText(r[1], {
      x: x + 0.2, y: y + 0.42, w: cw - 0.3, h: 0.5,
      fontSize: 10.5, fontFace: BODY_FONT, color: MUTED, margin: 0,
    });
  });
  pageNumber(s, 9, TOTAL);
}

// =========================================================================
// 10. HOSTING & ACCESS
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG };
  slides.push(s);
  brandBar(s);
  sectionTitle(s, "HOSTING & ACCESS",
    "One URL. One password. Anywhere.",
    "Streamlit on a Windows VPS, fronted by a Cloudflare named tunnel.");

  // Diagram: User -> Cloudflare -> Tunnel -> VPS/Streamlit
  const boxes = [
    { l: "Your browser",      d: "Any device.\nNo install.",          c: TEAL  },
    { l: "Cloudflare edge",   d: "TLS, DDoS,\nDNS proxy.",            c: WARN  },
    { l: "Named tunnel",      d: "Outbound-only.\nNo open ports.",     c: NAVY  },
    { l: "Streamlit + SQLite",d: "VPS in Lagos.\nPassword-gated.",     c: NAVY  },
  ];
  const bw = 1.95, bh = 1.6;
  boxes.forEach((b, i) => {
    const x = 0.5 + i * 2.4;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.6, w: bw, h: bh,
      fill: { color: SURFACE }, line: { color: BORDER, width: 0.5 },
      shadow: { type: "outer", color: "1F3864", blur: 8, offset: 2, angle: 90, opacity: 0.06 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.6, w: bw, h: 0.06, fill: { color: b.c }, line: { color: b.c },
    });
    s.addText(b.l, {
      x: x + 0.15, y: 2.78, w: bw - 0.3, h: 0.4,
      fontSize: 13, fontFace: HEAD_FONT, bold: true, color: INK, margin: 0,
    });
    s.addText(b.d, {
      x: x + 0.15, y: 3.22, w: bw - 0.3, h: 0.9,
      fontSize: 10.5, fontFace: BODY_FONT, color: MUTED, margin: 0, valign: "top",
    });
    if (i < boxes.length - 1) {
      s.addShape(pres.shapes.RIGHT_TRIANGLE, {
        x: x + bw + 0.05, y: 3.25, w: 0.3, h: 0.3,
        fill: { color: NAVY }, line: { color: NAVY }, rotate: 90,
      });
    }
  });

  // URL & lock
  s.addText("https://erp.hagai.online", {
    x: 0.5, y: 4.6, w: 9, h: 0.4,
    fontSize: 18, fontFace: "Consolas", bold: true, color: NAVY, align: "center",
  });
  s.addText("Password gate at the door · session-based · auto-locked after 5 wrong attempts", {
    x: 0.5, y: 5.0, w: 9, h: 0.3,
    fontSize: 11, fontFace: BODY_FONT, color: MUTED, align: "center",
  });

  pageNumber(s, 10, TOTAL);
}

// =========================================================================
// 11. TECH STACK
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG };
  slides.push(s);
  brandBar(s);
  sectionTitle(s, "UNDER THE HOOD",
    "Boring tech. On purpose.",
    "Mature, well-documented libraries — the boring stuff stays boring.");

  const stack = [
    ["Python 3.12",          "Language runtime"],
    ["SQLAlchemy 2.0",       "ORM + GL primitives"],
    ["SQLite (WAL)",         "System of record"],
    ["Streamlit",            "Web UI framework"],
    ["Altair (Vega-Lite)",   "Charts on dashboards"],
    ["ReportLab",            "PDF invoice export"],
    ["openpyxl",             "BizClinik xlsx import"],
    ["Cloudflare Tunnel",    "Public access, zero open ports"],
  ];
  const cols = 4, rows = 2;
  const padX = 0.4, padY = 2.5;
  const cw = (W - padX*2 - (cols-1)*0.2) / cols;
  const ch = 1.0;
  stack.forEach((it, i) => {
    const col = i % cols, row = Math.floor(i / cols);
    const x = padX + col * (cw + 0.2), y = padY + row * (ch + 0.25);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: cw, h: ch,
      fill: { color: SURFACE }, line: { color: BORDER, width: 0.5 },
      shadow: { type: "outer", color: "1F3864", blur: 6, offset: 2, angle: 90, opacity: 0.05 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.06, h: ch, fill: { color: NAVY }, line: { color: NAVY },
    });
    s.addText(it[0], {
      x: x + 0.18, y: y + 0.16, w: cw - 0.3, h: 0.35,
      fontSize: 13, fontFace: HEAD_FONT, bold: true, color: INK, margin: 0,
    });
    s.addText(it[1], {
      x: x + 0.18, y: y + 0.5, w: cw - 0.3, h: 0.45,
      fontSize: 10, fontFace: BODY_FONT, color: MUTED, margin: 0,
    });
  });
  pageNumber(s, 11, TOTAL);
}

// =========================================================================
// 12. WHAT IT REPLACES
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG };
  slides.push(s);
  brandBar(s);
  sectionTitle(s, "REPLACES",
    "From patched-up spreadsheet to a real ledger.",
    "Side-by-side: what your business runs on today vs what BizClinik ERP gives you.");

  // Two-column table — Before vs After
  const rows = [
    ["Patched-up Excel workbooks", "Live web ERP, one URL"],
    ["Paper invoices, manual VAT", "Auto-VAT invoices + PDF export"],
    ["Separate Word quotations",   "Quote → SO → Invoice pipeline"],
    ["Hand-typed P&L each month",  "P&L on tap, any period"],
    ["Stock card in another file", "Inventory with weighted-avg cost"],
    ["Books that never balance",   "Trial Balance always = 0"],
  ];
  const colW = 4.3, colH = 0.5;
  const x1 = 0.5, x2 = 5.2;
  const y0 = 2.4;
  // Headers
  s.addShape(pres.shapes.RECTANGLE, { x: x1, y: y0, w: colW, h: 0.5,
    fill: { color: DANGER }, line: { color: DANGER } });
  s.addText("BEFORE", { x: x1, y: y0, w: colW, h: 0.5,
    fontSize: 12, fontFace: HEAD_FONT, bold: true, color: "FFFFFF",
    align: "center", valign: "middle", charSpacing: 4, margin: 0 });
  s.addShape(pres.shapes.RECTANGLE, { x: x2, y: y0, w: colW, h: 0.5,
    fill: { color: SUCCESS }, line: { color: SUCCESS } });
  s.addText("AFTER", { x: x2, y: y0, w: colW, h: 0.5,
    fontSize: 12, fontFace: HEAD_FONT, bold: true, color: "FFFFFF",
    align: "center", valign: "middle", charSpacing: 4, margin: 0 });
  rows.forEach((r, i) => {
    const y = y0 + 0.55 + i * 0.42;
    s.addShape(pres.shapes.RECTANGLE, { x: x1, y, w: colW, h: 0.38,
      fill: { color: SURFACE }, line: { color: BORDER, width: 0.5 } });
    s.addShape(pres.shapes.RECTANGLE, { x: x2, y, w: colW, h: 0.38,
      fill: { color: SURFACE }, line: { color: BORDER, width: 0.5 } });
    s.addText(r[0], { x: x1 + 0.2, y, w: colW - 0.3, h: 0.38,
      fontSize: 11, fontFace: BODY_FONT, color: INK, valign: "middle", margin: 0 });
    s.addText(r[1], { x: x2 + 0.2, y, w: colW - 0.3, h: 0.38,
      fontSize: 11, fontFace: HEAD_FONT, bold: true, color: NAVY, valign: "middle", margin: 0 });
  });

  pageNumber(s, 12, TOTAL);
}

// =========================================================================
// 13. ROADMAP
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: BG };
  slides.push(s);
  brandBar(s);
  sectionTitle(s, "ROADMAP",
    "What's next.",
    "Live today on a single tenant. Targeted features below are scoped to land in the next two quarters.");

  const items = [
    { q: "Q3 2026", t: "Multi-tenant",       d: "Per-business workspaces with isolated SQLite files." },
    { q: "Q3 2026", t: "Mobile templates",   d: "Responsive layouts for phone-first data entry on the go." },
    { q: "Q4 2026", t: "Bank reconciliation",d: "Auto-match Moniepoint / GTB statement lines to GL postings." },
    { q: "Q4 2026", t: "FIRS e-invoice",     d: "Export the JSON the FIRS portal expects, straight from the invoice screen." },
  ];
  items.forEach((it, i) => {
    const x = 0.5 + i * 2.35;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.6, w: 2.15, h: 2.3,
      fill: { color: SURFACE }, line: { color: BORDER, width: 0.5 },
      shadow: { type: "outer", color: "1F3864", blur: 6, offset: 2, angle: 90, opacity: 0.05 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.6, w: 2.15, h: 0.06, fill: { color: TEAL }, line: { color: TEAL },
    });
    s.addText(it.q, {
      x: x + 0.2, y: 2.78, w: 1.85, h: 0.3,
      fontSize: 10, fontFace: HEAD_FONT, bold: true, color: TEAL,
      charSpacing: 3, margin: 0,
    });
    s.addText(it.t, {
      x: x + 0.2, y: 3.05, w: 1.85, h: 0.5,
      fontSize: 15, fontFace: HEAD_FONT, bold: true, color: INK, margin: 0,
    });
    s.addText(it.d, {
      x: x + 0.2, y: 3.55, w: 1.85, h: 1.25,
      fontSize: 10.5, fontFace: BODY_FONT, color: MUTED, margin: 0,
    });
  });
  pageNumber(s, 13, TOTAL);
}

// =========================================================================
// 14. CLOSING
// =========================================================================
{
  const s = pres.addSlide();
  s.background = { color: NAVY };
  slides.push(s);

  // Big tagline
  s.addText("Run your business", {
    x: 0.6, y: 1.5, w: 9, h: 0.75,
    fontSize: 48, fontFace: HEAD_FONT, bold: true, color: "FFFFFF",
    charSpacing: -1,
  });
  s.addText("on a real ledger.", {
    x: 0.6, y: 2.3, w: 9, h: 0.75,
    fontSize: 48, fontFace: HEAD_FONT, bold: true, color: TEAL,
    charSpacing: -1,
  });

  // CTA boxes
  const ctas = [
    { l: "Try it",       v: "erp.hagai.online" },
    { l: "Talk to us",   v: "hello@hagai.online" },
    { l: "About",        v: "hagai.online" },
  ];
  ctas.forEach((c, i) => {
    const x = 0.6 + i * 3.1;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 3.7, w: 2.9, h: 1.0,
      fill: { color: NAVY }, line: { color: TEAL, width: 1.5 },
    });
    s.addText(c.l, {
      x: x + 0.2, y: 3.78, w: 2.5, h: 0.3,
      fontSize: 10, fontFace: HEAD_FONT, bold: true, color: TEAL,
      charSpacing: 4, margin: 0,
    });
    s.addText(c.v, {
      x: x + 0.2, y: 4.1, w: 2.5, h: 0.4,
      fontSize: 14, fontFace: HEAD_FONT, bold: true, color: "FFFFFF", margin: 0,
    });
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: H - 0.15, w: W, h: 0.15, fill: { color: TEAL }, line: { color: TEAL },
  });
}

// ---- Write ---------------------------------------------------------------
pres.writeFile({ fileName: "C:/Users/User/Downloads/bizclinik-erp/BizClinik_ERP_Explainer.pptx" })
    .then((fn) => console.log("wrote", fn));
