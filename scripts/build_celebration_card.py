"""Render the BizClinik ERP celebration card (PNG + PDF).

Brand: dark navy canvas, bright teal accent, rounded panels. Footer attributes
the build to HAG_Ai (provider) for BizClinik (client). No public ERP URL.

Usage:
    python scripts/build_celebration_card.py [out_basename]
Outputs <out_basename>.png and <out_basename>.pdf next to the repo root.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_BASE = ROOT / (sys.argv[1] if len(sys.argv) > 1
                   else "BizClinik_ERP_Celebration_Card_v3")

W, H = 1200, 1660
MARGIN = 88

# ---- palette ---------------------------------------------------------------
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


f_black = lambda s: font("seguibl.ttf", s)      # heavy
f_bold = lambda s: font("segoeuib.ttf", s)
f_semi = lambda s: font("segoeuisl.ttf", s)     # semilight
f_reg = lambda s: font("segoeui.ttf", s)
f_light = lambda s: font("segoeuil.ttf", s)


def vgradient(w: int, h: int, top, bot) -> Image.Image:
    base = Image.new("RGB", (w, h), top)
    px = base.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return base


def text_w(d: ImageDraw.ImageDraw, s: str, fnt) -> int:
    return d.textbbox((0, 0), s, font=fnt)[2]


def spaced(d, xy, s, fnt, fill, tracking=6):
    x, y = xy
    for ch in s:
        d.text((x, y), ch, font=fnt, fill=fill)
        x += text_w(d, ch, fnt) + tracking
    return x


def wrap(d, s, fnt, max_w):
    words, lines, cur = s.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if text_w(d, trial, fnt) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def card(d, x, y, w, h, title, sub, badge=None):
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=CARD_BG,
                        outline=CARD_BD, width=2)
    pad = 26
    d.text((x + pad, y + 24), title, font=f_bold(34), fill=TEAL)
    if badge:
        bx = x + pad + text_w(d, title, f_bold(34)) + 16
        bw = text_w(d, badge, f_bold(18)) + 24
        d.rounded_rectangle([bx, y + 30, bx + bw, y + 58], radius=14,
                            fill=(20, 60, 54))
        d.text((bx + 12, y + 33), badge, font=f_bold(18), fill=TEAL)
    # subtitle (wrap to card width)
    sy = y + 74
    for ln in wrap(d, sub, f_reg(23), w - 2 * pad):
        d.text((x + pad, sy), ln, font=f_reg(23), fill=MUTED)
        sy += 30


def build():
    img = vgradient(W, H, BG_TOP, BG_BOT)
    d = ImageDraw.Draw(img)

    # subtle corner glows
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W - 380, -180, W + 120, 320], fill=(43, 226, 198, 22))
    gd.ellipse([-200, H - 360, 260, H + 160], fill=(224, 60, 150, 16))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    d = ImageDraw.Draw(img)

    y = 96
    # accent dots row
    for i, c in enumerate((TEAL, MAGENTA, ORANGE, TEAL)):
        cx = MARGIN + i * 34
        r = 9 if i != 3 else 6
        d.ellipse([cx, y, cx + r * 2, y + r * 2], fill=c)

    # eyebrow
    y = 168
    spaced(d, (MARGIN, y), "HUGE SUCCESS  ·  EXPANDED", f_bold(22), TEAL, 5)

    # title
    y = 206
    t1, t2 = "BizClinik ", "ERP"
    tf = f_black(118)
    d.text((MARGIN - 4, y), t1, font=tf, fill=WHITE)
    d.text((MARGIN - 4 + text_w(d, t1, tf), y), t2, font=tf, fill=TEAL)

    # subtitle line
    y = 348
    d.text((MARGIN, y), "now with HR & subscription plans.",
           font=f_light(46), fill=PARA)

    # teal underline
    y = 424
    d.rounded_rectangle([MARGIN, y, MARGIN + 96, y + 7], radius=3, fill=TEAL)

    # paragraph
    y = 458
    para = ("A full double-entry accounting platform — multi-business and "
            "Nigeria-ready — reorganised into a grouped workspace: Finance & "
            "Accounting, CRM, a complete HR suite, and System. Plan-based access "
            "(Free · Starter · Business) gates premium features per tenant. Live "
            "on PostgreSQL with encrypted off-site backups.")
    for ln in wrap(d, para, f_reg(28), W - 2 * MARGIN):
        d.text((MARGIN, y), ln, font=f_reg(28), fill=PARA)
        y += 40

    # stat cards — 3 rows x 2
    cards = [
        ("Grouped workspace", "Finance · CRM · HR · System", None),
        ("HR suite", "Employees · Recruitment · Leave · Payroll", "NEW"),
        ("Plan tiers", "Free · Starter · Business · feature-gated", "NEW"),
        ("169 tests", "Green on CI · books always balance", None),
        ("PostgreSQL 16", "Database-per-tenant · auto tenant migrations", None),
        ("Encrypted backups", "Nightly · off-site · disaster-ready", None),
    ]
    gap = 28
    cw = (W - 2 * MARGIN - gap) // 2
    ch = 150
    y0 = y + 26
    for i, (t, s, b) in enumerate(cards):
        col, row = i % 2, i // 2
        cx = MARGIN + col * (cw + gap)
        cy = y0 + row * (ch + gap)
        card(d, cx, cy, cw, ch, t, s, badge=b)

    # live pill (checkmark drawn as strokes — avoids font glyph gaps)
    py = y0 + 3 * (ch + gap) + 8
    label = "LIVE IN PRODUCTION"
    pf = f_bold(26)
    lw = text_w(d, label, pf)
    pw = lw + 56 + 40
    d.rounded_rectangle([MARGIN, py, MARGIN + pw, py + 56], radius=28,
                        outline=TEAL, width=2)
    d.text((MARGIN + 28, py + 12), label, font=pf, fill=TEAL)
    ckx, cky = MARGIN + 28 + lw + 18, py + 28
    d.line([(ckx, cky), (ckx + 8, cky + 9)], fill=TEAL, width=4)
    d.line([(ckx + 8, cky + 9), (ckx + 22, cky - 10)], fill=TEAL, width=4)

    # footer
    fy = H - 96
    d.text((MARGIN, fy), "HAG", font=f_black(46), fill=WHITE)
    hw = text_w(d, "HAG", f_black(46))
    d.text((MARGIN + hw, fy), "_Ai", font=f_black(46), fill=TEAL)

    foot = "Built & operated by HAG_Ai for BizClinik  ·  Lagos · 2026"
    ff = f_reg(22)
    d.text((W - MARGIN - text_w(d, foot, ff), fy + 18), foot, font=ff, fill=MUTED)

    png = OUT_BASE.with_suffix(".png")
    pdf = OUT_BASE.with_suffix(".pdf")
    img.save(png, "PNG")
    img.convert("RGB").save(pdf, "PDF", resolution=150.0)
    print("wrote", png, f"({png.stat().st_size // 1024} KB)")
    print("wrote", pdf, f"({pdf.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
