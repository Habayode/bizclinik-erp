"""Render a BizClinik ERP card (PNG + PDF) — brand: dark navy + teal, rounded
panels. Footer attributes the build to HAG_Ai (provider). No public ERP URL.

Two presets:
  expanded  — milestone card highlighting recent additions (NEW badges).
  fresh     — clean product introduction, full capabilities, no new/old framing.

Usage:
  python scripts/build_celebration_card.py [--variant expanded|fresh]
                                           [--name BRAND] [--out BASENAME]
The brand word is rendered white + " ERP" in teal. --name lets you set the
product brand at render time without changing any code (defaults to BizClinik).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent

W, H = 1200, 1660
MARGIN = 88

BG_TOP = (10, 14, 26)
BG_BOT = (12, 20, 46)
WHITE = (245, 248, 252)
TEAL = (43, 226, 198)
MUTED = (150, 165, 190)
PARA = (179, 190, 210)
CARD_BG = (19, 26, 44)
CARD_BD = (33, 45, 72)
MAGENTA = (224, 60, 150)
ORANGE = (245, 166, 46)

FONTS = "C:/Windows/Fonts"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(f"{FONTS}/{name}", size)


f_black = lambda s: font("seguibl.ttf", s)
f_bold = lambda s: font("segoeuib.ttf", s)
f_reg = lambda s: font("segoeui.ttf", s)
f_light = lambda s: font("segoeuil.ttf", s)


def vgradient(w, h, top, bot):
    base = Image.new("RGB", (w, h), top)
    px = base.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px_row = (int(top[0] + (bot[0] - top[0]) * t),
                  int(top[1] + (bot[1] - top[1]) * t),
                  int(top[2] + (bot[2] - top[2]) * t))
        for x in range(w):
            px[x, y] = px_row
    return base


def tw(d, s, fnt):
    return d.textbbox((0, 0), s, font=fnt)[2]


def spaced(d, xy, s, fnt, fill, tracking=6):
    x, y = xy
    for ch in s:
        d.text((x, y), ch, font=fnt, fill=fill)
        x += tw(d, ch, fnt) + tracking
    return x


def wrap(d, s, fnt, max_w):
    words, lines, cur = s.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if tw(d, trial, fnt) <= max_w:
            cur = trial
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def card(d, x, y, w, h, title, sub, badge=None):
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=CARD_BG,
                        outline=CARD_BD, width=2)
    pad = 26
    d.text((x + pad, y + 24), title, font=f_bold(34), fill=TEAL)
    if badge:
        bx = x + pad + tw(d, title, f_bold(34)) + 16
        bw = tw(d, badge, f_bold(18)) + 24
        d.rounded_rectangle([bx, y + 30, bx + bw, y + 58], radius=14,
                            fill=(20, 60, 54))
        d.text((bx + 12, y + 33), badge, font=f_bold(18), fill=TEAL)
    sy = y + 74
    for ln in wrap(d, sub, f_reg(23), w - 2 * pad):
        d.text((x + pad, sy), ln, font=f_reg(23), fill=MUTED)
        sy += 30


def render(out_base: Path, *, brand, eyebrow, subtitle, paragraph, cards,
           pill, footer_right):
    img = vgradient(W, H, BG_TOP, BG_BOT)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W - 380, -180, W + 120, 320], fill=(43, 226, 198, 22))
    gd.ellipse([-200, H - 360, 260, H + 160], fill=(224, 60, 150, 16))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    d = ImageDraw.Draw(img)

    y = 96
    for i, c in enumerate((TEAL, MAGENTA, ORANGE, TEAL)):
        cx = MARGIN + i * 34
        r = 9 if i != 3 else 6
        d.ellipse([cx, y, cx + r * 2, y + r * 2], fill=c)

    spaced(d, (MARGIN, 168), eyebrow, f_bold(22), TEAL, 5)

    # title (auto-fit to width)
    t1, t2 = brand + " ", "ERP"
    size = 118
    while size > 70:
        tf = f_black(size)
        if tw(d, t1 + t2, tf) <= W - 2 * MARGIN:
            break
        size -= 4
    tf = f_black(size)
    ty = 206 + (118 - size)  # keep baseline roughly stable
    d.text((MARGIN - 4, ty), t1, font=tf, fill=WHITE)
    d.text((MARGIN - 4 + tw(d, t1, tf), ty), t2, font=tf, fill=TEAL)

    d.text((MARGIN, 348), subtitle, font=f_light(46), fill=PARA)
    d.rounded_rectangle([MARGIN, 424, MARGIN + 96, 431], radius=3, fill=TEAL)

    y = 458
    for ln in wrap(d, paragraph, f_reg(28), W - 2 * MARGIN):
        d.text((MARGIN, y), ln, font=f_reg(28), fill=PARA)
        y += 40

    gap = 28
    cw = (W - 2 * MARGIN - gap) // 2
    ch = 150
    y0 = y + 26
    for i, (t, s, b) in enumerate(cards):
        col, row = i % 2, i // 2
        card(d, MARGIN + col * (cw + gap), y0 + row * (ch + gap), cw, ch, t, s, b)

    rows = (len(cards) + 1) // 2
    py = y0 + rows * (ch + gap) + 8
    pf = f_bold(26)
    lw = tw(d, pill, pf)
    pw = lw + 56 + 40
    d.rounded_rectangle([MARGIN, py, MARGIN + pw, py + 56], radius=28,
                        outline=TEAL, width=2)
    d.text((MARGIN + 28, py + 12), pill, font=pf, fill=TEAL)
    ckx, cky = MARGIN + 28 + lw + 18, py + 28
    d.line([(ckx, cky), (ckx + 8, cky + 9)], fill=TEAL, width=4)
    d.line([(ckx + 8, cky + 9), (ckx + 22, cky - 10)], fill=TEAL, width=4)

    fy = H - 96
    d.text((MARGIN, fy), "HAG", font=f_black(46), fill=WHITE)
    hw = tw(d, "HAG", f_black(46))
    d.text((MARGIN + hw, fy), "_Ai", font=f_black(46), fill=TEAL)
    ff = f_reg(22)
    d.text((W - MARGIN - tw(d, footer_right, ff), fy + 18), footer_right,
           font=ff, fill=MUTED)

    png, pdf = out_base.with_suffix(".png"), out_base.with_suffix(".pdf")
    img.save(png, "PNG")
    img.convert("RGB").save(pdf, "PDF", resolution=150.0)
    print("wrote", png, f"({png.stat().st_size // 1024} KB)")
    print("wrote", pdf, f"({pdf.stat().st_size // 1024} KB)")


PRESETS = {
    "expanded": dict(
        eyebrow="HUGE SUCCESS  ·  EXPANDED",
        subtitle="now with HR & subscription plans.",
        paragraph=("A full double-entry accounting platform — multi-business "
                   "and Nigeria-ready — reorganised into a grouped workspace: "
                   "Finance & Accounting, CRM, a complete HR suite, and System. "
                   "Plan-based access (Free · Starter · Business) gates premium "
                   "features per tenant. Live on PostgreSQL with encrypted "
                   "off-site backups."),
        cards=[
            ("Grouped workspace", "Finance · CRM · HR · System", None),
            ("HR suite", "Employees · Recruitment · Leave · Payroll", "NEW"),
            ("Plan tiers", "Free · Starter · Business · feature-gated", "NEW"),
            ("169 tests", "Green on CI · books always balance", None),
            ("PostgreSQL 16", "Database-per-tenant · auto tenant migrations", None),
            ("Encrypted backups", "Nightly · off-site · disaster-ready", None),
        ],
        pill="LIVE IN PRODUCTION",
        footer_right="Built & operated by HAG_Ai for BizClinik  ·  Lagos · 2026",
    ),
    "fresh": dict(
        eyebrow="NIGERIA-READY  ·  DOUBLE-ENTRY ERP",
        subtitle="Run your whole business in one place.",
        paragraph=("A complete accounting and business-management platform for "
                   "Nigerian SMEs. Keep proper double-entry books on every "
                   "transaction, manage operations and people, and see the full "
                   "picture in real time — across multiple businesses, on plans "
                   "that scale with you."),
        cards=[
            ("Finance & Accounting", "Sales · purchases · inventory · banking · GL", None),
            ("Tax & compliance", "VAT · graduated PAYE · WHT · FIRS e-invoice", None),
            ("People & HR", "Employees · recruitment · leave · payroll", None),
            ("CRM", "Leads · pipeline · follow-ups", None),
            ("Reports & insight", "P&L · balance sheet · budgets · statements", None),
            ("Secure & multi-tenant", "PostgreSQL · per-tenant · encrypted backups", None),
        ],
        pill="LIVE IN PRODUCTION",
        footer_right="Built & operated by HAG_Ai  ·  Lagos · 2026",
    ),
}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=list(PRESETS), default="expanded")
    ap.add_argument("--name", default="BizClinik", help="Product brand word")
    ap.add_argument("--out", default=None, help="Output basename (no extension)")
    a = ap.parse_args()
    preset = PRESETS[a.variant]
    out = Path(a.out) if a.out else ROOT / f"BizClinik_ERP_Celebration_Card_{a.variant}"
    if not out.is_absolute():
        out = ROOT / out
    render(out, brand=a.name, **preset)
