// BizClinik ERP — Explainer deck. Built fresh, one cohesive piece. pptxgenjs, 16:9.
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "HAG_Ai"; pres.company = "HAG_Ai"; pres.title = "BizClinik ERP — Explainer";

const NAVY = "1F3864", NAVY_DARK = "16284F", TEAL = "0EA5A4", INK = "0F172A",
      MUTED = "64748B", BG = "F4F6FB", SURFACE = "FFFFFF", BORDER = "E5E7EB",
      SUCCESS = "16A34A", WARN = "F59E0B", INFO = "2563EB", DANGER = "DC2626";
const HEAD = "Calibri", BODY = "Calibri Light";
const W = 10, H = 5.625;

const builders = [];
const slide = (fn) => builders.push(fn);
let TOTAL = 0;

function bar(s) {
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: W, h: 0.4, fill: { color: NAVY }, line: { color: NAVY } });
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0.4, w: W, h: 0.045, fill: { color: TEAL }, line: { color: TEAL } });
  s.addText("BizClinik ERP", { x: 0.35, y: 0, w: 5, h: 0.4, fontSize: 11, fontFace: HEAD, bold: true, color: "FFFFFF", valign: "middle", margin: 0 });
  s.addText("erp.hagai.online", { x: W - 2.2, y: 0, w: 1.9, h: 0.4, fontSize: 10, fontFace: BODY, color: "DBEAFE", align: "right", valign: "middle", margin: 0 });
}
function pageNum(s, n) { s.addText(`${n} / ${TOTAL}`, { x: W - 1.0, y: H - 0.35, w: 0.8, h: 0.28, fontSize: 8.5, fontFace: BODY, color: MUTED, align: "right" }); }
function head(s, eyebrow, t, sub) {
  s.addText(eyebrow, { x: 0.5, y: 0.7, w: 9, h: 0.3, fontSize: 11, fontFace: HEAD, bold: true, color: TEAL, charSpacing: 4 });
  s.addText(t, { x: 0.5, y: 1.0, w: 9, h: 0.7, fontSize: 28, fontFace: HEAD, bold: true, color: INK });
  if (sub) s.addText(sub, { x: 0.5, y: 1.68, w: 9, h: 0.4, fontSize: 13, fontFace: BODY, color: MUTED });
}
function card(s, x, y, w, h, accent) {
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: SURFACE }, line: { color: BORDER, width: 0.5 },
    shadow: { type: "outer", color: "1F3864", blur: 7, offset: 2, angle: 90, opacity: 0.06 } });
  s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.07, h, fill: { color: accent || NAVY }, line: { color: accent || NAVY } });
}
function chip(s, x, y, w, h, glyph, label, desc, accent) {
  card(s, x, y, w, h, accent);
  s.addShape(pres.shapes.OVAL, { x: x + 0.24, y: y + 0.22, w: 0.55, h: 0.55, fill: { color: accent || NAVY }, line: { color: accent || NAVY } });
  s.addText(glyph, { x: x + 0.24, y: y + 0.22, w: 0.55, h: 0.55, fontSize: 17, fontFace: HEAD, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
  s.addText(label, { x: x + 0.92, y: y + 0.18, w: w - 1.05, h: 0.34, fontSize: 14, fontFace: HEAD, bold: true, color: INK, margin: 0 });
  s.addText(desc, { x: x + 0.92, y: y + 0.5, w: w - 1.05, h: h - 0.55, fontSize: 10, fontFace: BODY, color: MUTED, margin: 0 });
}

// 1. TITLE
slide((s) => {
  s.background = { color: NAVY };
  s.addShape(pres.shapes.RECTANGLE, { x: 6.4, y: H - 0.18, w: 3.6, h: 0.18, fill: { color: TEAL }, line: { color: TEAL } });
  s.addText("BizClinik", { x: 0.6, y: 1.55, w: 9, h: 0.95, fontSize: 62, fontFace: HEAD, bold: true, color: "FFFFFF", charSpacing: -2 });
  s.addText("ERP", { x: 0.6, y: 2.42, w: 9, h: 0.95, fontSize: 62, fontFace: HEAD, bold: true, color: TEAL, charSpacing: -2 });
  s.addText("Real accounting software for Nigerian businesses — on the web.", { x: 0.62, y: 3.5, w: 9, h: 0.5, fontSize: 17, fontFace: BODY, color: "DBEAFE" });
  s.addText("HAG_Ai  ·  erp.hagai.online", { x: 0.62, y: H - 0.7, w: 9, h: 0.35, fontSize: 11, fontFace: HEAD, bold: true, color: "BAE6FD", charSpacing: 3 });
});

// 2. THE PROBLEM
slide((s) => {
  s.background = { color: BG }; bar(s);
  head(s, "THE PROBLEM", "Your books live in too many places.",
    "Spreadsheets, a notebook, WhatsApp receipts, the bank app — and nothing agrees.");
  const pains = [
    ["✕", "Spreadsheets break", "One wrong cell and the numbers stop adding up.", DANGER],
    ["✕", "No single truth", "Sales here, expenses there, cash somewhere else.", DANGER],
    ["✕", "Tax is guesswork", "VAT, PAYE and WHT worked out by hand, late.", WARN],
    ["✕", "Can't trust the total", "\"How much did we actually make?\" — nobody's sure.", WARN],
  ];
  const cols = 2, cw = 4.5, ch = 0.95, gx = 0.3;
  const x0 = (W - (cols * cw + gx)) / 2;
  pains.forEach((p, i) => {
    const x = x0 + (i % cols) * (cw + gx), y = 2.2 + Math.floor(i / cols) * (ch + 0.25);
    chip(s, x, y, cw, ch, p[0], p[1], p[2], p[3]);
  });
  pageNum(s, 2);
});

// 3. THE SOLUTION
slide((s) => {
  s.background = { color: BG }; bar(s);
  head(s, "THE SOLUTION", "One platform that keeps your books right.",
    "BizClinik ERP runs your whole business on a proper double-entry ledger — automatically.");
  const x = 1.0, y = 2.15;
  card(s, x, y, 8.0, 2.5, TEAL);
  s.addText("Every sale, purchase, payment and payroll run posts to the ledger by itself.\nYou get accurate books, real reports, and Nigerian tax handled — without an accountant babysitting a spreadsheet.",
    { x: x + 0.35, y: y + 0.3, w: 7.3, h: 1.0, fontSize: 14, fontFace: BODY, color: INK, margin: 0 });
  const tags = ["Invoices", "Expenses", "Inventory", "Payroll", "Bank", "Tax", "Reports"];
  tags.forEach((t, i) => {
    const tx = x + 0.35 + (i % 4) * 1.85, ty = y + 1.45 + Math.floor(i / 4) * 0.5;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: tx, y: ty, w: 1.65, h: 0.38, fill: { color: "E6FFFA" }, line: { color: TEAL, width: 0.75 }, rectRadius: 0.08 });
    s.addText(t, { x: tx, y: ty, w: 1.65, h: 0.38, fontSize: 10.5, fontFace: HEAD, bold: true, color: NAVY, align: "center", valign: "middle", margin: 0 });
  });
  pageNum(s, 3);
});

// 4. A REAL LEDGER
slide((s) => {
  s.background = { color: BG }; bar(s);
  head(s, "WHY IT'S DIFFERENT", "A real ledger — not a spreadsheet.",
    "Double-entry means every transaction balances. The books are always trustworthy.");
  s.addShape(pres.shapes.RECTANGLE, { x: 1.0, y: 2.5, w: 3.6, h: 0.7, fill: { color: NAVY }, line: { color: NAVY } });
  s.addText("Assets", { x: 1.0, y: 2.5, w: 3.6, h: 0.7, fontSize: 18, fontFace: HEAD, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
  s.addText("=", { x: 4.6, y: 2.5, w: 0.8, h: 0.7, fontSize: 24, fontFace: HEAD, bold: true, color: MUTED, align: "center", valign: "middle", margin: 0 });
  s.addShape(pres.shapes.RECTANGLE, { x: 5.4, y: 2.5, w: 3.6, h: 0.7, fill: { color: TEAL }, line: { color: TEAL } });
  s.addText("Liabilities  +  Equity", { x: 5.4, y: 2.5, w: 3.6, h: 0.7, fontSize: 16, fontFace: HEAD, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
  s.addText("Enforced on every entry — plus a full audit trail of who did what, and period locks so closed months can't silently change.",
    { x: 1.0, y: 3.6, w: 8.0, h: 0.7, fontSize: 13, fontFace: BODY, italic: true, color: NAVY, align: "center" });
  pageNum(s, 4);
});

// 5. CAPABILITIES
slide((s) => {
  s.background = { color: BG }; bar(s);
  head(s, "WHAT YOU GET", "Everything your business runs on.");
  const caps = [
    ["₦", "Invoicing & sales", "Quotes, invoices, receipts, customer statements.", NAVY],
    ["⇄", "Purchases & expenses", "Bills, payments, supplier tracking.", NAVY],
    ["▦", "Inventory", "Stock levels, average cost, automatic COGS.", NAVY],
    ["👥", "Payroll", "Nigerian graduated PAYE, payslips.", SUCCESS],
    ["🏦", "Banking", "Import statements, auto-match, reconcile.", INFO],
    ["%", "Tax", "VAT, withholding tax, FIRS e-invoice drafts.", SUCCESS],
    ["📊", "Reports", "P&L, Balance Sheet, Cash Flow, agings.", NAVY],
    ["🔁", "Automation", "Recurring invoices, month-end close.", TEAL],
    ["🤝", "CRM", "Leads, pipeline, follow-ups → customers.", INFO],
  ];
  const cols = 3, cw = 3.05, ch = 0.92, gx = 0.12;
  const x0 = (W - (cols * cw + (cols - 1) * gx)) / 2;
  caps.forEach((c, i) => {
    const x = x0 + (i % cols) * (cw + gx), y = 1.95 + Math.floor(i / cols) * (ch + 0.14);
    chip(s, x, y, cw, ch, c[0], c[1], c[2], c[3]);
  });
  pageNum(s, 5);
});

// 6. HOW IT WORKS (flow)
slide((s) => {
  s.background = { color: BG }; bar(s);
  head(s, "HOW IT WORKS", "Do the work once. The books update themselves.",
    "Example: raising one invoice.");
  const steps = [
    ["Create invoice", "Pick a customer, add items. Done."],
    ["Books update", "Sales, VAT, receivables and stock all post automatically."],
    ["Get paid", "Record the payment; the bank and customer balance update."],
    ["See the truth", "It's already in your P&L, balance sheet and aging."],
  ];
  const n = steps.length, gap = 0.25, cw = (W - 1.0 - (n - 1) * gap) / n;
  steps.forEach((st, i) => {
    const x = 0.5 + i * (cw + gap), y = 2.3;
    card(s, x, y, cw, 1.9, TEAL);
    s.addShape(pres.shapes.OVAL, { x: x + 0.2, y: y + 0.2, w: 0.5, h: 0.5, fill: { color: TEAL }, line: { color: TEAL } });
    s.addText(String(i + 1), { x: x + 0.2, y: y + 0.2, w: 0.5, h: 0.5, fontSize: 16, fontFace: HEAD, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
    s.addText(st[0], { x: x + 0.18, y: y + 0.8, w: cw - 0.34, h: 0.4, fontSize: 12.5, fontFace: HEAD, bold: true, color: INK, margin: 0 });
    s.addText(st[1], { x: x + 0.18, y: y + 1.18, w: cw - 0.34, h: 0.65, fontSize: 9.5, fontFace: BODY, color: MUTED, margin: 0 });
  });
  pageNum(s, 6);
});

// 7. BUILT FOR NIGERIA
slide((s) => {
  s.background = { color: BG }; bar(s);
  head(s, "MADE FOR NIGERIA", "Local rules, handled out of the box.",
    "Not a foreign tool bent to fit — built for how Nigerian SMEs actually operate.");
  const items = [
    ["Graduated PAYE", "Correct banded pay-as-you-earn, not a flat guess.", SUCCESS],
    ["VAT & WHT", "7.5% VAT and withholding tax, with WHT certificates.", SUCCESS],
    ["FIRS e-invoice", "Generates the FIRS-style e-invoice + QR (MBS-ready).", SUCCESS],
    ["Naira-first", "₦ functional currency, with foreign-currency support.", TEAL],
    ["Local banks", "Imports GTB, Access, Zenith, FBN, Moniepoint statements.", INFO],
    ["Built locally", "By HAG_Ai, for Nigerian businesses.", NAVY],
  ];
  const cols = 3, cw = 3.05, ch = 1.25, gx = 0.12;
  const x0 = (W - (cols * cw + (cols - 1) * gx)) / 2;
  items.forEach((it, i) => {
    const x = x0 + (i % cols) * (cw + gx), y = 2.15 + Math.floor(i / cols) * (ch + 0.18);
    card(s, x, y, cw, ch, it[2]);
    s.addText(it[0], { x: x + 0.18, y: y + 0.14, w: cw - 0.3, h: 0.35, fontSize: 13, fontFace: HEAD, bold: true, color: INK, margin: 0 });
    s.addText(it[1], { x: x + 0.18, y: y + 0.5, w: cw - 0.3, h: 0.65, fontSize: 9.5, fontFace: BODY, color: MUTED, margin: 0 });
  });
  pageNum(s, 7);
});

// 8. MULTI-BUSINESS
slide((s) => {
  s.background = { color: BG }; bar(s);
  head(s, "FOR ONE BUSINESS — OR MANY", "Run every business from one login.",
    "Each business gets its own private books and its own web address.");
  const items = [
    ["🔒", "Fully separate", "Each business is an isolated database — no mixing.", NAVY],
    ["🌐", "Own subdomain", "yourbusiness.erp.hagai.online lands on its own books.", TEAL],
    ["🎨", "Own branding", "Per-business invoice logo, colour and details.", INFO],
    ["👤", "Users & roles", "Give staff the right access per business.", SUCCESS],
  ];
  const cols = 2, cw = 4.4, ch = 1.0, gx = 0.3;
  const x0 = (W - (cols * cw + gx)) / 2;
  items.forEach((it, i) => {
    const x = x0 + (i % cols) * (cw + gx), y = 2.2 + Math.floor(i / cols) * (ch + 0.25);
    chip(s, x, y, cw, ch, it[0], it[1], it[2], it[3]);
  });
  pageNum(s, 8);
});

// 9. GET PAID + GROW
slide((s) => {
  s.background = { color: BG }; bar(s);
  head(s, "GET PAID & GROW", "Collect payments and win more customers.",
    "Subscriptions and a built-in CRM, connected to your books.");
  card(s, 0.7, 2.2, 4.2, 2.4, TEAL);
  s.addText("Online payments", { x: 0.95, y: 2.35, w: 3.7, h: 0.35, fontSize: 14, fontFace: HEAD, bold: true, color: INK });
  s.addText("Accept payments via Paystack, Flutterwave or Moniepoint — switch provider any time, no rebuild. Subscriptions activate automatically on payment.",
    { x: 0.95, y: 2.75, w: 3.7, h: 1.6, fontSize: 11.5, fontFace: BODY, color: MUTED, margin: 0 });
  card(s, 5.1, 2.2, 4.2, 2.4, INFO);
  s.addText("Built-in CRM", { x: 5.35, y: 2.35, w: 3.7, h: 0.35, fontSize: 14, fontFace: HEAD, bold: true, color: INK });
  s.addText("Track leads, move deals through a pipeline, and set follow-up reminders. Win a deal and it becomes a customer you can invoice — in one click.",
    { x: 5.35, y: 2.75, w: 3.7, h: 1.6, fontSize: 11.5, fontFace: BODY, color: MUTED, margin: 0 });
  pageNum(s, 9);
});

// 10. SAFE BY DESIGN
slide((s) => {
  s.background = { color: BG }; bar(s);
  head(s, "SAFE BY DESIGN", "Your data is protected — and recoverable.",
    "The boring, essential stuff, done properly.");
  const items = [
    ["Audit trail", "Every change is recorded: who, what, when.", NAVY],
    ["Roles & access", "Staff see only what they should.", NAVY],
    ["Encrypted backups", "Nightly, encrypted, stored safely off-site.", DANGER],
    ["Secure access", "No open ports; traffic over an encrypted tunnel.", INFO],
    ["Always-on", "Auto-restart + health checks keep it running.", SUCCESS],
    ["Real database", "PostgreSQL — handles many users at once.", TEAL],
  ];
  const cols = 3, cw = 3.05, ch = 1.2, gx = 0.12;
  const x0 = (W - (cols * cw + (cols - 1) * gx)) / 2;
  items.forEach((it, i) => {
    const x = x0 + (i % cols) * (cw + gx), y = 2.15 + Math.floor(i / cols) * (ch + 0.18);
    card(s, x, y, cw, ch, it[2]);
    s.addText(it[0], { x: x + 0.18, y: y + 0.14, w: cw - 0.3, h: 0.35, fontSize: 13, fontFace: HEAD, bold: true, color: INK, margin: 0 });
    s.addText(it[1], { x: x + 0.18, y: y + 0.5, w: cw - 0.3, h: 0.6, fontSize: 9.5, fontFace: BODY, color: MUTED, margin: 0 });
  });
  pageNum(s, 10);
});

// 11. ANYWHERE
slide((s) => {
  s.background = { color: BG }; bar(s);
  head(s, "ANYWHERE, ANY DEVICE", "Nothing to install. Just open the link.",
    "Works on a laptop in the office and a phone on the move.");
  const items = [
    ["🌍", "On the web", "Open erp.hagai.online in any browser — no setup.", NAVY],
    ["📱", "Mobile-friendly", "Responsive layout for phone-first data entry.", TEAL],
    ["⚡", "Always current", "Updates roll out centrally; you're always on the latest.", INFO],
    ["🔌", "Connects out", "REST API + webhooks to plug into other tools.", SUCCESS],
  ];
  const cols = 2, cw = 4.4, ch = 1.0, gx = 0.3;
  const x0 = (W - (cols * cw + gx)) / 2;
  items.forEach((it, i) => {
    const x = x0 + (i % cols) * (cw + gx), y = 2.2 + Math.floor(i / cols) * (ch + 0.25);
    chip(s, x, y, cw, ch, it[0], it[1], it[2], it[3]);
  });
  pageNum(s, 11);
});

// 12. PLANS
slide((s) => {
  s.background = { color: BG }; bar(s);
  head(s, "PLANS", "Start free. Grow when you're ready.");
  const plans = [
    ["Free", "₦0", ["1 business", "Up to 2 users", "Core accounting"], NAVY],
    ["Starter", "₦15,000/mo", ["Up to 5 users", "Invoicing + bank rec", "FIRS e-invoice drafts"], TEAL],
    ["Business", "₦45,000/mo", ["Unlimited users", "Multi-currency", "API + priority support"], INFO],
  ];
  const cw = 2.9, gx = 0.25, x0 = (W - (3 * cw + 2 * gx)) / 2;
  plans.forEach((p, i) => {
    const x = x0 + i * (cw + gx), y = 2.1, h = 2.7;
    card(s, x, y, cw, h, p[3]);
    s.addText(p[0], { x: x + 0.2, y: y + 0.18, w: cw - 0.35, h: 0.4, fontSize: 16, fontFace: HEAD, bold: true, color: INK, margin: 0 });
    s.addText(p[1], { x: x + 0.2, y: y + 0.58, w: cw - 0.35, h: 0.45, fontSize: 18, fontFace: HEAD, bold: true, color: p[3], margin: 0 });
    s.addText(p[2].map(t => ({ text: t, options: { bullet: { code: "2022" }, color: MUTED, fontSize: 11, fontFace: BODY, paraSpaceAfter: 6 } })),
      { x: x + 0.2, y: y + 1.15, w: cw - 0.35, h: 1.4, valign: "top", margin: 0 });
  });
  s.addText("Indicative pricing — set to your market.", { x: 0.5, y: 5.0, w: 9, h: 0.3, fontSize: 9.5, fontFace: BODY, italic: true, color: MUTED, align: "center" });
  pageNum(s, 12);
});

// 13. CTA
slide((s) => {
  s.background = { color: NAVY };
  s.addText("Run your business", { x: 0.6, y: 1.5, w: 9, h: 0.8, fontSize: 40, fontFace: HEAD, bold: true, color: "FFFFFF" });
  s.addText("on books you can trust.", { x: 0.6, y: 2.35, w: 9, h: 0.8, fontSize: 40, fontFace: HEAD, bold: true, color: TEAL });
  s.addText("Open it in your browser and start today — no installation, no spreadsheets.", { x: 0.62, y: 3.35, w: 9, h: 0.5, fontSize: 14, fontFace: BODY, color: "DBEAFE" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 4.05, w: 4.2, h: 0.8, fill: { color: TEAL }, line: { color: TEAL }, rectRadius: 0.1 });
  s.addText("erp.hagai.online", { x: 0.6, y: 4.05, w: 4.2, h: 0.8, fontSize: 18, fontFace: HEAD, bold: true, color: NAVY_DARK, align: "center", valign: "middle", margin: 0 });
  s.addText("HAG_Ai", { x: 5.2, y: 4.05, w: 4, h: 0.8, fontSize: 13, fontFace: HEAD, bold: true, color: "BAE6FD", valign: "middle", charSpacing: 3 });
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: H - 0.12, w: W, h: 0.12, fill: { color: TEAL }, line: { color: TEAL } });
});

TOTAL = builders.length;
builders.forEach((fn) => fn(pres.addSlide()));
pres.writeFile({ fileName: "C:/Users/User/Downloads/bizclinik-erp/BizClinik_ERP_Explainer_Fresh.pptx" })
  .then((fn) => console.log("wrote", fn, "—", TOTAL, "slides"));
