"""Render a BizClinik ERP card (PNG + PDF) — brand: dark navy + teal, rounded
panels. Footer attributes the build to HAG_Ai (provider). No public ERP URL.

Presets:
  expanded  — milestone card highlighting recent additions (NEW badges).
  fresh     — clean product introduction: full capability cards (every
              sub-module listed) plus a plans/tiers strip (no prices).

Usage:
  python scripts/build_celebration_card.py [--variant expanded|fresh]
                                           [--name BRAND] [--out BASENAME]
The brand word renders white + " ERP" in teal. --name sets the product brand
at render time without code changes (default BizClinik).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent

W = 1200
MARGIN = 88
GAP = 28

BG_TOP = (10, 14, 26)
BG_BOT = (12, 20, 46)
WHITE = (245, 248, 252)
TEAL = (43, 226, 198)
MUTED = (150, 165, 190)
PARA = (179, 190, 210)
CARD_BG = (19, 26, 44)
CARD_BD = (33, 45, 72)
PLAN_BG = (17, 30, 40)
PLAN_BD = (28, 64, 64)
MAGENTA = (224, 60, 150)
ORANGE = (245, 166, 46)

FONTS = "C:/Windows/Fonts"


def font(name, size):
    return ImageFont.truetype(f"{FONTS}/{name}", size)


f_black = lambda s: font("seguibl.ttf", s)
f_bold = lambda s: font("segoeuib.ttf", s)
f_reg = lambda s: font("segoeui.ttf", s)
f_light = lambda s: font("segoeuil.ttf", s)

# scratch draw for measuring before the real canvas exists
_SCRATCH = ImageDraw.Draw(Image.new("RGB", (W, 10)))


def tw(s, fnt):
    return _SCRATCH.textbbox((0, 0), s, font=fnt)[2]


def wrap(s, fnt, max_w):
    words, lines, cur = s.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if tw(trial, fnt) <= max_w:
            cur = trial
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def spaced(d, xy, s, fnt, fill, tracking=6):
    x, y = xy
    for ch in s:
        d.text((x, y), ch, font=fnt, fill=fill)
        x += tw(ch, fnt) + tracking


def panel(d, x, y, w, h, title, sub_lines, sub_fnt, bg, bd, title_fnt=None):
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=bg,
                        outline=bd, width=2)
    pad = 26
    d.text((x + pad, y + 22), title, font=title_fnt or f_bold(34), fill=TEAL)
    sy = y + 72
    for ln in sub_lines:
        d.text((x + pad, sy), ln, font=sub_fnt, fill=MUTED)
        sy += 29


def render(out_base: Path, *, brand, eyebrow, subtitle, paragraph, cards,
           plans, pill, plans_label, footer_right):
    pad = 26
    cw = (W - 2 * MARGIN - GAP) // 2
    csub = f_reg(22)
    # per-card wrapped sub-lines + heights
    card_lines = [wrap(s, csub, cw - 2 * pad) for _, s, _ in cards]
    card_h = [72 + len(ls) * 29 + 18 for ls in card_lines]

    pw = (W - 2 * MARGIN - 2 * GAP) // 3
    psub = f_reg(21)
    plan_lines = [wrap(s, psub, pw - 2 * pad) for _, s in plans]
    plan_h = max(72 + len(ls) * 27 + 16 for ls in plan_lines)

    para_lines = wrap(paragraph, f_reg(28), W - 2 * MARGIN)

    # ---- vertical layout pass ----
    y = 458 + len(para_lines) * 40 + 26          # cards start
    cards_top = y
    row_tops = []
    for r in range(0, len(cards), 2):
        row_tops.append(y)
        rh = max(card_h[r], card_h[r + 1] if r + 1 < len(cards) else 0)
        y += rh + GAP
    y_plans_label = y - GAP + 18
    y_plans = y_plans_label + 50
    y_after_plans = y_plans + plan_h
    y_pill = y_after_plans + 24
    H = y_pill + 56 + 132

    # ---- draw ----
    img = Image.new("RGB", (W, H), BG_TOP)
    px = img.load()
    for yy in range(H):
        t = yy / max(1, H - 1)
        row = (int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t),
               int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t),
               int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t))
        for xx in range(W):
            px[xx, yy] = row
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W - 380, -180, W + 120, 320], fill=(43, 226, 198, 22))
    gd.ellipse([-200, H - 360, 260, H + 160], fill=(224, 60, 150, 16))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    d = ImageDraw.Draw(img)

    for i, c in enumerate((TEAL, MAGENTA, ORANGE, TEAL)):
        cx = MARGIN + i * 34
        r = 9 if i != 3 else 6
        d.ellipse([cx, 96, cx + r * 2, 96 + r * 2], fill=c)

    spaced(d, (MARGIN, 168), eyebrow, f_bold(22), TEAL, 5)

    t1, t2 = brand + " ", "ERP"
    size = 118
    while size > 70 and tw(t1 + t2, f_black(size)) > W - 2 * MARGIN:
        size -= 4
    tf = f_black(size)
    ty = 206 + (118 - size)
    d.text((MARGIN - 4, ty), t1, font=tf, fill=WHITE)
    d.text((MARGIN - 4 + tw(t1, tf), ty), t2, font=tf, fill=TEAL)

    d.text((MARGIN, 348), subtitle, font=f_light(46), fill=PARA)
    d.rounded_rectangle([MARGIN, 424, MARGIN + 96, 431], radius=3, fill=TEAL)

    yy = 458
    for ln in para_lines:
        d.text((MARGIN, yy), ln, font=f_reg(28), fill=PARA)
        yy += 40

    # capability cards
    for r in range(0, len(cards), 2):
        top = row_tops[r // 2]
        rh = max(card_h[r], card_h[r + 1] if r + 1 < len(cards) else 0)
        for col in (0, 1):
            idx = r + col
            if idx >= len(cards):
                break
            x = MARGIN + col * (cw + GAP)
            panel(d, x, top, cw, rh, cards[idx][0], card_lines[idx], csub,
                  CARD_BG, CARD_BD)

    # plans label + tiers (no prices)
    spaced(d, (MARGIN, y_plans_label), plans_label, f_bold(22), TEAL, 5)
    for i, (name, _) in enumerate(plans):
        x = MARGIN + i * (pw + GAP)
        panel(d, x, y_plans, pw, plan_h, name, plan_lines[i], psub,
              PLAN_BG, PLAN_BD, title_fnt=f_bold(30))

    # live pill
    pf = f_bold(26)
    lw = tw(pill, pf)
    pwid = lw + 56 + 40
    d.rounded_rectangle([MARGIN, y_pill, MARGIN + pwid, y_pill + 56], radius=28,
                        outline=TEAL, width=2)
    d.text((MARGIN + 28, y_pill + 12), pill, font=pf, fill=TEAL)
    ckx, cky = MARGIN + 28 + lw + 18, y_pill + 28
    d.line([(ckx, cky), (ckx + 8, cky + 9)], fill=TEAL, width=4)
    d.line([(ckx + 8, cky + 9), (ckx + 22, cky - 10)], fill=TEAL, width=4)

    fy = H - 96
    d.text((MARGIN, fy), "HAG", font=f_black(46), fill=WHITE)
    hw = tw("HAG", f_black(46))
    d.text((MARGIN + hw, fy), "_Ai", font=f_black(46), fill=TEAL)
    ff = f_reg(22)
    d.text((W - MARGIN - tw(footer_right, ff), fy + 18), footer_right,
           font=ff, fill=MUTED)

    png, pdf = out_base.with_suffix(".png"), out_base.with_suffix(".pdf")
    img.save(png, "PNG")
    img.convert("RGB").save(pdf, "PDF", resolution=150.0)
    print("wrote", png, f"({png.stat().st_size // 1024} KB)  {W}x{H}")
    print("wrote", pdf, f"({pdf.stat().st_size // 1024} KB)")


PRESETS = {
    "expanded": dict(
        eyebrow="HUGE SUCCESS  ·  EXPANDED",
        subtitle="now with HR & subscription plans.",
        paragraph=("A full double-entry accounting platform — multi-business "
                   "and Nigeria-ready — reorganised into a grouped workspace: "
                   "Finance & Accounting, CRM, a complete HR suite, and System. "
                   "Live on PostgreSQL with encrypted off-site backups."),
        cards=[
            ("Grouped workspace", "Finance · CRM · HR · System", "NEW"),
            ("HR suite", "Employees · Recruitment · Leave · Payroll", "NEW"),
            ("PostgreSQL 16", "Database-per-tenant · auto tenant migrations", None),
            ("Encrypted backups", "Nightly · off-site · disaster-ready", None),
        ],
        plans=[("Free", "Core accounting"), ("Starter", "+ premium add-ons"),
               ("Business", "Everything · unlimited")],
        plans_label="PLANS",
        pill="LIVE IN PRODUCTION",
        footer_right="Built and powered by HAG_Ai",
    ),
    "fresh": dict(
        eyebrow="NIGERIA-READY  ·  DOUBLE-ENTRY ERP",
        subtitle="Run your whole business in one place.",
        paragraph=("A complete accounting and business-management platform for "
                   "Nigerian SMEs. Keep proper double-entry books on every "
                   "transaction, manage operations and people, and see the full "
                   "picture in real time — across multiple businesses."),
        cards=[
            ("Finance & Accounting",
             "Sales · Purchases · Inventory · Banking · Bank Reconciliation · "
             "Fixed Assets · Recurring · Currencies · General Ledger · Month-End",
             None),
            ("Tax & compliance",
             "VAT · Graduated PAYE · WHT certificates · FIRS e-invoice", None),
            ("People & HR",
             "Employees · Recruitment · Leave · Payroll", None),
            ("CRM",
             "Leads · Deal pipeline · Follow-ups · Convert to customer", None),
            ("Reports & insight",
             "Dashboard · P&L · Balance Sheet · Trial Balance · Cash Flow · "
             "Budgets · Statements", None),
            ("Secure & multi-tenant",
             "PostgreSQL · Per-tenant isolation · Roles & audit · REST API · "
             "Encrypted backups", None),
        ],
        plans=[
            ("Free", "Core accounting · up to 2 users"),
            ("Starter", "+ Bank rec · Recurring · FIRS e-invoice · up to 5 users"),
            ("Business", "+ Multi-currency · CRM · Budgets · API · unlimited users"),
        ],
        plans_label="PLANS THAT SCALE WITH YOU",
        pill="LIVE IN PRODUCTION",
        footer_right="Built and powered by HAG_Ai",
    ),
}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=list(PRESETS), default="expanded")
    ap.add_argument("--name", default="BizClinik")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = Path(a.out) if a.out else ROOT / f"BizClinik_ERP_Celebration_Card_{a.variant}"
    if not out.is_absolute():
        out = ROOT / out
    render(out, brand=a.name, **PRESETS[a.variant])
