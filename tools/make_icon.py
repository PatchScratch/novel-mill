#!/usr/bin/env python3
"""Generate the Novel Mill app icon: a pencil-sketch Japanese stone mill (ishiusu).

Draws light graphite strokes on the dark PatchScratch badge so the icon
matches the shared design language (Translation-Aggregator palette).
Design coordinates are in a 1024 grid; primitives scale them up to the
4x render canvas, which is downscaled with Lanczos for clean edges.

Usage:  py -3 tools/make_icon.py
Writes: assets/novel-mill-1024.png, novel-mill.png (512), novel-mill-256.png, novel-mill.ico
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

S = 4096  # render size
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# Translation-Aggregator dark palette tokens.
BG = (43, 43, 43, 255)        # window
BORDER = (85, 85, 85, 255)    # border
INK = (220, 228, 238, 255)    # text  — main pencil stroke
INK_SOFT = (150, 158, 170, 255)  # secondary stroke
GHOST = (110, 116, 130, 110)  # construction-line pass

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
rnd = random.Random(7)

U = S / 1024  # design grid -> canvas scale

# Composition transform: scale about the mill's center and nudge down so the
# sketch sits optically centered on the badge (it reads top-heavy otherwise).
OFF_Y = 64
SCALE = 1.06
PV = (512, 470)


def T(x, y):
    return ((x - PV[0]) * SCALE + PV[0], (y - PV[1]) * SCALE + PV[1] + OFF_Y)


def jline(p1, p2, color, w, jitter=5, passes=2):
    """Pencil stroke: a couple of slightly offset passes. Points in 1024 grid."""
    p1 = T(*p1)
    p2 = T(*p2)
    p1 = (p1[0] * U, p1[1] * U)
    p2 = (p2[0] * U, p2[1] * U)
    j = jitter * U
    for _ in range(passes):
        a = (p1[0] + rnd.uniform(-j, j), p1[1] + rnd.uniform(-j, j))
        b = (p2[0] + rnd.uniform(-j, j), p2[1] + rnd.uniform(-j, j))
        d.line([a, b], fill=color, width=w, joint="curve")


def jellipse(cx, cy, rx, ry, color, w, a0=0, a1=360, jitter=4, passes=2):
    """Sketchy ellipse or arc. Angles clockwise from 3 o'clock (PIL convention)."""
    cx, cy = T(cx, cy)
    rx, ry = rx * SCALE, ry * SCALE
    cx, cy, rx, ry = cx * U, cy * U, rx * U, ry * U
    j = jitter * U
    for _ in range(passes):
        ox, oy = rnd.uniform(-j, j), rnd.uniform(-j, j)
        box = [cx - rx + ox, cy - ry + oy, cx + rx + ox, cy + ry + oy]
        d.arc(box, a0, a1, fill=color, width=w)


def hatch(cx, cy, uw, uh, angle_deg, gap, color, w, seed, density=1.0):
    """Short parallel pencil strokes filling a patch centered on cx,cy (1024 grid)."""
    r = random.Random(seed)
    cx, cy = T(cx, cy)
    uw, uh, gap = uw * SCALE, uh * SCALE, gap * SCALE
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -math.sin(a), math.cos(a)
    n = max(2, int(uh / gap))
    for i in range(n):
        t = -uh / 2 + i * gap + r.uniform(-gap * 0.3, gap * 0.3)
        L = uw * (0.45 + 0.55 * r.random()) * density
        mx = (cx + vx * t + r.uniform(-2, 2)) * U
        my = (cy + vy * t + r.uniform(-2, 2)) * U
        p1 = (mx - ux * L / 2 * U, my - uy * L / 2 * U)
        p2 = (mx + ux * L / 2 * U, my + uy * L / 2 * U)
        d.line([p1, p2], fill=color, width=w)


def dot(cx, cy, rr, fill=None, outline=None, w=0):
    cx, cy = T(cx, cy)
    rr2 = rr * SCALE * U
    x, y = cx * U, cy * U
    d.ellipse([x - rr2, y - rr2, x + rr2, y + rr2], fill=fill, outline=outline, width=w)


# ---- badge ----
m = int(S * 0.03)
d.rounded_rectangle([m, m, S - m, S - m], radius=int(S * 0.21), fill=BG, outline=BORDER, width=int(S * 0.008))

W_MAIN = int(14 * U)   # main stroke width
W_THIN = int(9 * U)
W_HATCH = int(7 * U)
CX = 512

# ---- wooden feeding funnel (ogi), flared upward ----
FTOP, FRX, FRY = 300, 150, 42      # top rim
FBOT, FBRX = 398, 58               # outlet into the stone
jellipse(CX, FTOP, FRX, FRY, INK, W_MAIN)
jellipse(CX, FTOP, FRX, FRY, GHOST, W_THIN, jitter=9, passes=1)
jline((CX - FRX, FTOP), (CX - FBRX, FBOT), INK, W_MAIN)
jline((CX + FRX, FTOP), (CX + FBRX, FBOT), INK, W_MAIN)
for frac in (-0.55, 0.0, 0.55):    # plank seams
    jline((CX + FRX * frac * 0.9, FTOP + 15), (CX + FBRX * frac * 0.45, FBOT - 10), INK_SOFT, W_THIN)

# ---- upper stone (kama): truncated cone ----
UTOP, UTRX, UTRY = 402, 170, 47
UBOT, UBRX, UBRY = 502, 198, 55
jellipse(CX, UTOP, UTRX, UTRY, INK, W_MAIN, a0=10, a1=170)   # front rim arc (funnel behind)
jline((CX - UTRX, UTOP), (CX - UBRX, UBOT), INK, W_MAIN)
jline((CX + UTRX, UTOP), (CX + UBRX, UBOT), INK, W_MAIN)
jellipse(CX, UBOT, UBRX, UBRY, INK, W_MAIN, a0=0, a1=180)    # front bottom arc
hatch(CX - 98, 456, 130, 58, -38, 16, INK_SOFT, W_HATCH, seed=11)
hatch(CX + 120, 434, 90, 44, -38, 16, INK_SOFT, W_HATCH, seed=12, density=0.7)

# ---- lower stone (jishi): broad base cone ----
LTOP, LTRX, LTRY = 504, 216, 59
LBOT, LBRX, LBRY = 622, 270, 71
jellipse(CX, LTOP, LTRX, LTRY, INK, W_MAIN, a0=0, a1=180)    # rim peeking under the kama
jline((CX - LTRX, LTOP), (CX - LBRX, LBOT), INK, W_MAIN)
jline((CX + LTRX, LTOP), (CX + LBRX, LBOT), INK, W_MAIN)
jellipse(CX, LBOT, LBRX, LBRY, INK, W_MAIN, a0=0, a1=180)    # front foot arc
jellipse(CX, LBOT, LBRX, LBRY, GHOST, W_THIN, jitter=10, passes=1)
hatch(CX - 170, 564, 150, 64, -38, 17, INK_SOFT, W_HATCH, seed=21)
hatch(CX + 180, 548, 110, 54, -38, 17, INK_SOFT, W_HATCH, seed=22, density=0.7)
hatch(CX, 652, 330, 38, -12, 18, GHOST, W_HATCH, seed=23, density=0.5)  # ground shadow

# grind seam: flour escaping between the stones
jellipse(CX, LTOP, 202, 54, INK_SOFT, W_THIN, a0=25, a1=155)

# ---- handle (ote) + pivot post (tategi), up-right ----
hx, hy = CX + 174, 442      # socket in the upper stone
tx, ty = 856, 320            # hand end of the pole
px, py = 856, 560            # post foot
jline((hx, hy), (tx, ty), INK, W_MAIN)
jline((tx, ty), (px, py), INK, W_MAIN)
jellipse(px, py, 34, 12, INK, W_THIN, a0=0, a1=180)
jellipse(px, py, 34, 12, INK_SOFT, W_THIN, a0=180, a1=360)
hatch(px + 26, 470, 58, 118, -80, 15, INK_SOFT, W_HATCH, seed=31, density=0.6)
hatch((hx + tx) / 2 + 18, (hy + ty) / 2 + 6, 128, 24, -100, 14, INK_SOFT, W_HATCH, seed=32, density=0.6)

# ---- a little ground flour at the front-left ----
jellipse(388, 640, 58, 16, INK_SOFT, W_THIN, a0=0, a1=180)
for i in range(14):
    dot(388 + rnd.uniform(-52, 52), 640 + rnd.uniform(2, 16), rnd.uniform(2.4, 4.2), fill=INK_SOFT)

# grains falling into the funnel
dot(588, 240, 4.6, outline=INK, w=W_THIN)
dot(614, 260, 4.6, outline=INK, w=W_THIN)

# ---- render sizes ----
ASSETS.mkdir(exist_ok=True)
big = img.resize((1024, 1024), Image.LANCZOS)
big.save(ASSETS / "novel-mill-1024.png")
p512 = big.resize((512, 512), Image.LANCZOS)
p512.save(ASSETS / "novel-mill.png")
p256 = p512.resize((256, 256), Image.LANCZOS)
p256.save(ASSETS / "novel-mill-256.png")
p256.save(
    ASSETS / "novel-mill.ico",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
print("wrote", ", ".join(p.name for p in sorted(ASSETS.iterdir())))
