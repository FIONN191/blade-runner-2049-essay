#!/usr/bin/env python3
"""Blade Runner 2049 - a 90-second motion-graphics video essay.

Every frame is generated procedurally with numpy + Pillow: no film footage,
stills or actor likenesses. Usage:
    python3 render.py still 3.0,12.5,...  OUTDIR     # preview PNGs
    python3 render.py worker I N OUTDIR              # render chunk I of N to mp4
"""
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 24
DUR = 90.0
NF = int(round(DUR * FPS))
BAR = 138                                  # 2.39:1 letterbox
AY0, AY1 = BAR, H - BAR


def _ffmpeg():
    if os.environ.get('FFMPEG'):
        return os.environ['FFMPEG']
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return 'ffmpeg'


FFMPEG = _ffmpeg()

# ------------------------------------------------------------------ timeline
S_EYE, S_TITLE, S_CITY, S_FARM, S_COLOR, S_MEM, S_SNOW = 0.0, 9.0, 17.0, 32.0, 46.0, 64.0, 78.0
TITLE_2049 = S_TITLE + 2.6

CHAPTERS = [
    (S_CITY + 0.3, S_CITY + 2.9, 'I', 'THIRTY YEARS LATER'),
    (S_FARM + 0.3, S_FARM + 2.9, 'II', 'THE MIRACLE'),
    (S_COLOR + 0.2, S_COLOR + 2.5, 'III', 'A WORLD IN FOUR COLORS'),
    (S_MEM + 0.2, S_MEM + 2.4, 'IV', 'MORE HUMAN'),
]
CARDS = [
    (S_CITY + 3.1, S_CITY + 8.9,
     "In 1982, Ridley Scott's Blade Runner asked what separates people from the machines they build."),
    (S_CITY + 9.1, S_CITY + 14.6,
     "In 2017, Denis Villeneuve returned to that world, thirty years further into its future."),
    (S_FARM + 3.1, S_FARM + 8.6,
     "K, a replicant blade runner who hunts his own kind, finds a box buried beneath a dead tree."),
    (S_FARM + 8.8, S_FARM + 13.6,
     "Inside is proof that a replicant once gave birth: a miracle that could start a war."),
    (S_COLOR + 3.3, S_COLOR + 9.1,
     "Cinematographer Roger Deakins gives each world one dominant color, and a mood to match."),
    (S_COLOR + 10.9, S_COLOR + 17.3,
     "The film earned Deakins his first Oscar, on his fourteenth nomination."),
    (S_MEM + 2.9, S_MEM + 8.4,
     "K's memories might be implants. His love might be a product. Even his hope is borrowed."),
    (S_MEM + 8.6, S_MEM + 13.5,
     "He isn't the chosen one. He chooses anyway, and that's the most human thing in the film."),
]
# (global start, text, chars per second)
TYPED = [
    (S_EYE + 3.4, 'LOS ANGELES  //  2049', 20),
    (S_EYE + 4.3, 'LAPD  //  KD6-3.7', 20),
    (S_FARM + 4.3, 'SUBSURFACE SCAN', 32),
    (S_FARM + 4.9, 'DEPTH ........ 1.8 M', 32),
    (S_FARM + 5.5, 'OBJECT ....... SEALED BOX', 32),
    (S_FARM + 6.3, 'REMAINS ...... FEMALE', 32),
    (S_FARM + 7.1, 'SERIAL ....... N7FAA52318', 32),
]
HUD_ON = S_FARM + 4.0
# memory glitch bursts: (global start, duration, strength)
GLITCH = [(S_MEM + 2.4, 0.28, 1.0), (S_MEM + 4.9, 0.16, 0.5), (S_MEM + 7.3, 0.2, 0.6),
          (S_MEM + 8.9, 0.34, 1.0), (S_MEM + 10.8, 0.14, 0.5), (S_MEM + 12.4, 0.2, 0.7)]
HOLO_T = S_MEM + 8.9
# flying vehicles: (t0, t1, start, end, scale)
SPINNERS = [
    (S_CITY + 0.3, S_CITY + 11.0, (-60, 330), (1980, 300), 0.5),
    (S_CITY + 4.0, S_CITY + 9.2, (2000, 420), (-100, 520), 1.0),
    (S_CITY + 10.0, S_CITY + 12.8, (-120, 235), (2040, 350), 1.6),
]
PANEL_T0, PANEL_STAGGER = S_COLOR + 2.5, 0.18
EXPAND = (S_COLOR + 9.4, S_COLOR + 10.6)
PW, PH, PY = 388, 530, 190
PANEL_X = [160 + i * (PW + 16) for i in range(4)]
PANELS = [('FARMLAND', '#8F9191'), ('LOS ANGELES', '#0F4C5C'), ('LAS VEGAS', '#E07A2E'), ('SNOW', '#DEE5EB')]

# ------------------------------------------------------------------ helpers
AVENIR = '/System/Library/Fonts/Avenir Next.ttc'
MENLO = '/System/Library/Fonts/Menlo.ttc'
GOTHIC = '/System/Library/Fonts/AppleSDGothicNeo.ttc'
HIRA = '/System/Library/Fonts/Hiragino Sans GB.ttc'
_fonts = {}


def F(path, size, idx=0):
    k = (path, size, idx)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(path, size, index=idx)
    return _fonts[k]


def AV(size, w='reg'):
    return F(AVENIR, size, {'ul': 10, 'reg': 7, 'med': 5, 'demi': 2, 'bold': 0}[w])


def MONO(size):
    return F(MENLO, size, 0)


def C(*v):
    return np.array(v, np.float32)


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ss(a, b, x):
    t = clamp((x - a) / (b - a))
    return t * t * (3 - 2 * t)


def sstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def eout(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def eio(x):
    x = clamp(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def h01(*a):
    x = 0x9E3779B9
    for v in a:
        x = ((x ^ (int(v) & 0xFFFFFFFF)) * 0x85EBCA6B) & 0xFFFFFFFF
        x ^= x >> 13
        x = (x * 0xC2B2AE35) & 0xFFFFFFFF
        x ^= x >> 16
    return x / 4294967296.0


def fbm(h, w, cell, seed, oct=4, gain=0.5):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(oct):
        c = cell / 2 ** o
        g = rng.random((max(2, int(h / c) + 2), max(2, int(w / c) + 2)), dtype=np.float32)
        out += np.asarray(Image.fromarray(g).resize((w, h), Image.BICUBIC), np.float32) * amp
        tot += amp
        amp *= gain
    out /= tot
    return np.clip(0.5 + (out - out.mean()) / (out.std() + 1e-6) * 0.2, 0, 1).astype(np.float32)


_G = {}


def grid():
    if 'x' not in _G:
        ys, xs = np.mgrid[0:H, 0:W]
        _G['x'], _G['y'] = xs.astype(np.float32), ys.astype(np.float32)
    return _G['x'], _G['y']


def Lnp(im):
    return np.asarray(im, np.float32) * (1 / 255)


def blurL(im, r, down=4):
    s = im.resize((W // down, H // down), Image.BILINEAR).filter(ImageFilter.GaussianBlur(r / down))
    return Lnp(s.resize((W, H), Image.BILINEAR))


def over(img, m, color, a=1.0):
    if a <= 0.001:
        return
    mm = (m * a)[..., None]
    img *= 1 - mm
    img += mm * np.asarray(color, np.float32)


def addc(img, m, color, a=1.0):
    if a <= 0.001:
        return
    img += m[..., None] * (np.asarray(color, np.float32) * a)


def blit(img, tex, x, y, alpha=1.0):
    h_, w_ = tex.shape[:2]
    x1, y1, x2, y2 = max(0, x), max(0, y), min(W, x + w_), min(H, y + h_)
    if x2 <= x1 or y2 <= y1 or alpha <= 0.001:
        return
    sub = tex[y1 - y:y2 - y, x1 - x:x2 - x]
    if alpha >= 0.999:
        img[y1:y2, x1:x2] = sub
    else:
        img[y1:y2, x1:x2] = img[y1:y2, x1:x2] * (1 - alpha) + sub * alpha


def tw(text, font, tr):
    return sum(font.getlength(c) for c in text) + tr * max(0, len(text) - 1)


def dtext(d, x, y, text, font, tr=0, fill=255, fills=None, align='l'):
    if align == 'c':
        x -= tw(text, font, tr) / 2
    elif align == 'r':
        x -= tw(text, font, tr)
    for i, c in enumerate(text):
        f = fills[i] if fills is not None else fill
        if f > 0 and c != ' ':
            d.text((x, y), c, font=font, fill=int(f), anchor='ls')
        x += font.getlength(c) + tr
    return x


def wrap(text, font, maxw):
    lines, cur = [], ''
    for wd in text.split():
        tst = (cur + ' ' + wd).strip()
        if font.getlength(tst) <= maxw:
            cur = tst
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


_fog = {}


def fog_frame(lt, speed, seed):
    if seed not in _fog:
        _fog[seed] = Image.fromarray(fbm(540, 2400, 170, seed, oct=5))
    x0 = (lt * speed * 0.5) % 1400
    return np.asarray(_fog[seed].resize((W, H), Image.BILINEAR, box=(x0, 0, x0 + 960, 540)), np.float32)


def typed(d, t, fi, t0, text, cps, x, y, font, tr=1, fill=235, align='l'):
    if t < t0 or fill <= 0:
        return
    n = min(len(text), int((t - t0) * cps))
    if align == 'r':
        x -= tw(text, font, tr)
    end = dtext(d, x, y, text[:n], font, tr, fill=fill)
    if (t - t0) - len(text) / cps < 0.9 and (fi // 5) % 2 == 0:
        d.rectangle([end + 3, y - font.size * 0.78, end + 3 + font.size * 0.55, y + 2], fill=int(fill))


# ------------------------------------------------------------------ overlays
def scrim():
    if 'scrim' not in _G:
        x, y = grid()
        _G['scrim'] = (sstep(600, 880, y) * (1 - sstep(700, 1500, x)) * 0.85).astype(np.float32)
    return _G['scrim']


def chapter(img, t, fi):
    for (a, b, num, title) in CHAPTERS:
        if a <= t <= b:
            break
    else:
        return
    lt = t - a
    fo = 1 - ss(b - 0.45, b, t)
    img *= 1 - 0.6 * ss(a, a + 0.3, t) * fo
    L = Image.new('L', (W, H))
    d = ImageDraw.Draw(L)
    cy = 548
    dtext(d, W / 2, cy - 78, num, MONO(22), 6, fill=235 * ss(a + 0.05, a + 0.4, t), align='c')
    ln = eout((lt - 0.1) / 0.9) * 170
    if ln > 1:
        d.line([(W / 2 - 40 - ln, cy - 86), (W / 2 - 40, cy - 86)], fill=150, width=1)
        d.line([(W / 2 + 40, cy - 86), (W / 2 + 40 + ln, cy - 86)], fill=150, width=1)
    fills = []
    for i, c in enumerate(title):
        on = 0.25 + 0.7 * h01(i, 17, len(title))
        fills.append(0 if lt < on else (255 if h01(i, fi, 3) > 0.5 else 60) if lt < on + 0.3 else 255)
    dtext(d, W / 2, cy + 10, title, AV(58, 'reg'), 22, fills=fills, align='c')
    addc(img, blurL(L, 16), (1.0, 0.62, 0.3), 0.35 * fo)
    over(img, Lnp(L), (0.95, 0.94, 0.9), fo)


def card(img, t):
    for (a, b, text) in CARDS:
        if a <= t <= b:
            break
    else:
        return
    font, lh = AV(38, 'reg'), 54
    lines = wrap(text, font, 1000)
    base0 = 900 - lh * (len(lines) - 1)
    fo = 1 - ss(b - 0.5, b, t)
    lt = t - a
    img *= (1 - scrim() * (0.6 * ss(a, a + 0.4, t) * fo))[..., None]
    L = Image.new('L', (W, H))
    d = ImageDraw.Draw(L)
    k = 0
    for li, line in enumerate(lines):
        x = 160
        for wd in line.split(' '):
            p = (lt - 0.055 * k) / 0.45
            al = eout(p) * fo
            if al > 0.003:
                d.text((x, base0 + li * lh + (1 - eout(p)) * 12), wd, font=font, fill=int(255 * al), anchor='ls')
            x += font.getlength(wd + ' ')
            k += 1
    over(img, Lnp(L), (0.94, 0.93, 0.9))
    y0 = int(base0 - 34)
    bh = int(eout(lt / 0.6) * (lh * (len(lines) - 1) + 44))
    if bh > 0:
        img[y0:y0 + bh, 128:131] = img[y0:y0 + bh, 128:131] * (1 - fo) + C(1.0, 0.62, 0.25) * fo


# ------------------------------------------------------------------ 1. eye
NT, NR = 1440, 320
_eye = {}


def eye_assets():
    if not _eye:
        x, y = grid()
        X, Y = x - W / 2, y - H / 2 + 10
        rng = np.random.default_rng(7)
        fib = np.asarray(Image.fromarray(rng.random((NT, 36), dtype=np.float32)).resize((NR, NT), Image.BICUBIC))
        g2 = np.asarray(Image.fromarray(rng.random((NT, 10), dtype=np.float32)).resize((NR, NT), Image.BICUBIC))
        fib2 = sum(np.roll(g2, k, axis=0) for k in range(-3, 4)) / 7
        th = np.linspace(-np.pi, np.pi, NT, endpoint=False)[:, None]
        r = np.linspace(0, 1, NR)[None, :]
        crypt = (0.5 + 0.25 * np.sin(9 * th + 7 * r) * np.sin(14 * th - 5 * r + 1.3)
                 + 0.25 * np.sin(23 * th + 11 * r + 0.4) * np.sin(5 * th + 2.1))
        T = 0.5 * fib + 0.35 * fib2 + 0.35 * crypt
        T = (T - T.min()) / (T.max() - T.min())
        _eye.update(X=X, Y=Y, D=np.sqrt(X * X + Y * Y), TH=np.arctan2(Y, X).astype(np.float32),
                    T=T.astype(np.float32))
    return _eye


def scene_eye(lt, fi, t):
    E = eye_assets()
    z = 1.0 + 0.16 * eio((lt - 1.0) / 6.0)
    if lt > 6.9:
        z *= math.exp(2.8 * ((lt - 6.9) / 1.7) ** 2)
    R = 300.0 * z
    rn = E['D'] * (1.0 / R)
    ti = ((E['TH'] + (np.pi + lt * 0.015)) * (NT / (2 * np.pi))).astype(np.int32) % NT
    ri = np.minimum((rn * (NR - 1)).astype(np.int32), NR - 1)
    fib = E['T'][ti, ri]
    p = 0.33 - 0.08 * ss(2.4, 3.8, lt)
    w = sstep(0.30, 0.78, rn)[..., None]
    inner, outer = C(0.95, 0.58, 0.22), C(0.20, 0.50, 0.58)
    col = inner + (outer - inner) * w
    ring = 1 - 0.88 * sstep(0.80, 0.99, rn)
    coll = 0.4 * np.exp(-((rn - 0.42) / 0.05) ** 2)
    iris = col * ((0.16 + 1.1 * fib * fib) * ring + coll)[..., None]
    inside = 1 - sstep(0.985, 1.03, rn)
    m = (sstep(p - 0.012, p + 0.014, rn) * inside)[..., None]
    scl = np.clip(np.exp(-(rn - 1.0) * 1.6), 0, 1) * 0.30
    eye = iris * m + (C(0.80, 0.82, 0.86) * (scl * (1 - inside))[..., None])
    u, v = E['X'] / R, E['Y'] / R
    q = np.clip(1 - (u / 2.5) ** 2, 0, None)
    up, lo = -0.93 * q, 1.02 * q
    openm = sstep(up, up + 0.06, v) * (1 - sstep(lo - 0.06, lo, v))
    shade = 0.30 + 0.70 * sstep(up, up + 0.6, v)
    lf = 0.55 + 0.6 * sstep(-2.0, 2.0, -(0.75 * u + 0.65 * v))
    eye *= (shade * lf)[..., None]
    rr = np.sqrt((u / 3.4) ** 2 + (v / 2.0) ** 2)
    skin = C(0.075, 0.052, 0.045) * (np.exp(-rr * 1.6) * (0.5 + 0.8 * lf))[..., None]
    om = openm[..., None]
    img = eye * om + skin * (1 - om)
    cl = np.exp(-(np.abs((u + 0.30) / 0.10) ** 4 + np.abs((v + 0.30) / 0.075) ** 4))
    cl2 = np.exp(-(((u - 0.40) / 0.05) ** 2 + ((v - 0.22) / 0.02) ** 2))
    img += (openm * cl)[..., None] * C(1.2, 1.2, 1.25) + (openm * cl2)[..., None] * C(0.72, 0.2, 0.6)
    img *= ss(0.6, 2.8, lt) * (1 - ss(7.8, 8.9, lt))
    # HUD
    fo = 1 - ss(6.7, 7.5, lt)
    L = Image.new('L', (W, H))
    d = ImageDraw.Draw(L)
    typed(d, t, fi, TYPED[0][0], TYPED[0][1], TYPED[0][2], 160, 880, MONO(24), 3, fill=220 * fo)
    typed(d, t, fi, TYPED[1][0], TYPED[1][1], TYPED[1][2], 1760, 202, MONO(20), 3, fill=190 * fo, align='r')
    over(img, Lnp(L), (0.75, 0.92, 0.98))
    return img.astype(np.float32)


# ------------------------------------------------------------------ 2. title
def scene_title(lt, fi, t):
    x, y = grid()
    if 'tbg' not in _G:
        tt = np.clip((y - AY0) / (AY1 - AY0), 0, 1)[..., None]
        _G['tbg'] = (C(0.012, 0.03, 0.04) * (1 - tt) + C(0.05, 0.028, 0.015) * tt).astype(np.float32)
        _G['tfw'] = sstep(300, 950, y).astype(np.float32)
    img = _G['tbg'] + (fog_frame(lt, 26, 2) * _G['tfw'])[..., None] * C(0.20, 0.10, 0.04)
    fo = 1 - ss(7.2, 8.0, lt)
    L1 = Image.new('L', (W, H))
    d1 = ImageDraw.Draw(L1)
    t1 = 'BLADE RUNNER'
    fills = []
    for i, c in enumerate(t1):
        on = 0.7 + 1.3 * h01(i, 11)
        fills.append(0 if lt < on else (255 if h01(i, fi, 5) > 0.45 else 40) if lt < on + 0.4 else 255)
    dtext(d1, W / 2, 470, t1, AV(80, 'reg'), 40, fills=fills, align='c')
    L2 = Image.new('L', (W, H))
    d2 = ImageDraw.Draw(L2)
    t2 = '2049'
    l2 = TITLE_2049 - S_TITLE
    fills = []
    for i in range(4):
        on = l2 - 0.35 + 0.3 * h01(i, 23)
        fills.append(0 if lt < on else (255 if h01(i, fi, 9) > 0.5 else 0) if lt < l2 else 255)
    dtext(d2, W / 2, 705, t2, AV(200, 'ul'), 56, fills=fills, align='c')
    burst = math.exp(-(lt - l2) / 0.5) if lt > l2 else 0.0
    m1, m2 = Lnp(L1), Lnp(L2)
    addc(img, blurL(L1, 18), (0.25, 0.35, 0.45), 0.6 * fo)
    over(img, m1, (0.94, 0.95, 0.96), fo)
    addc(img, blurL(L2, 34), (1.0, 0.45, 0.12), (1.0 + 1.8 * burst) * fo)
    over(img, m2, (1.0, 0.82, 0.58), fo)
    if burst > 0.01:
        dx = np.abs(x - W / 2)
        streak = np.exp(-((y - 632) / 2.2) ** 2) * np.exp(-dx / 750) * 1.5 + \
            np.exp(-((y - 632) / 16) ** 2) * np.exp(-dx / 420) * 0.35
        addc(img, streak, (0.55, 0.75, 1.0), burst * fo)
    L3 = Image.new('L', (W, H))
    dtext(ImageDraw.Draw(L3), W / 2, 800, 'A  VIDEO  ESSAY', MONO(20), 10,
          fill=255 * ss(3.6, 4.5, lt) * fo, align='c')
    over(img, Lnp(L3), (0.7, 0.76, 0.8))
    img *= ss(0.0, 0.5, lt)
    return img


# ------------------------------------------------------------------ 3. city
_city = {}
WL = W + 900


def sign_sprite(text, font, color, vertical):
    pad = 70
    if vertical:
        sz = font.size
        w_, h_ = int(max(font.getlength(c) for c in text)) + 4, int(len(text) * sz * 1.08)
    else:
        w_, h_ = int(font.getlength(text)) + 4, int(font.size * 1.2)
    im = Image.new('L', (w_ + 2 * pad, h_ + 2 * pad))
    d = ImageDraw.Draw(im)
    if vertical:
        for i, c in enumerate(text):
            d.text((pad + w_ / 2, pad + i * sz * 1.08), c, font=font, fill=255, anchor='mt')
    else:
        d.text((pad, pad), text, font=font, fill=255, anchor='lt')
    core = Lnp(im)
    g1 = Lnp(im.filter(ImageFilter.GaussianBlur(6)))
    g2 = Lnp(im.filter(ImageFilter.GaussianBlur(28)))
    spr = core[..., None] * (color * 0.55 + 0.6) + g1[..., None] * color * 1.3 + g2[..., None] * color * 1.0
    return spr.astype(np.float32), w_, h_, pad


def city():
    if _city:
        return _city
    rng = np.random.default_rng(21)
    x, y = grid()
    tt = np.clip((y - AY0) / (AY1 - AY0), 0, 1)[..., None]
    sky = C(0.012, 0.03, 0.045) * (1 - tt) + C(0.06, 0.11, 0.14) * tt
    sky += np.exp(-((y - 860) / 200) ** 2)[..., None] * C(0.30, 0.10, 0.22) * 0.8
    sky += np.exp(-((y - 900) / 90) ** 2)[..., None] * C(0.35, 0.18, 0.10) * 0.5
    _city['sky'] = sky.astype(np.float32)
    _city['hazew'] = sstep(250, 900, y).astype(np.float32)
    specs = [(C(0.075, 0.12, 0.15), 240, 560, 50, 170, 0.10, 0.45),
             (C(0.03, 0.05, 0.065), 180, 640, 90, 260, 0.16, 0.8),
             (C(0.006, 0.010, 0.014), 100, 780, 140, 420, 0.03, 0.7)]
    winc = [C(1.0, 0.72, 0.42), C(0.55, 0.85, 1.0), C(1.0, 0.45, 0.75), C(0.9, 0.9, 0.8)]
    signdefs = [
        (0, 760, 'HOTEL', AV(24, 'demi'), C(1.0, 0.35, 0.3), False, 0.25),
        (1, 430, '사랑', F(GOTHIC, 58, 6), C(1.0, 0.22, 0.62), True, 0.15),
        (1, 1480, '雨', F(HIRA, 96, 2), C(0.30, 0.90, 1.0), False, 0.0),
        (1, 2330, '未来', F(HIRA, 60, 2), C(1.0, 0.62, 0.22), True, 0.5),
        (2, 180, '기억', F(GOTHIC, 86, 6), C(0.3, 1.0, 0.85), True, 0.08),
        (2, 1950, '夢', F(HIRA, 120, 2), C(1.0, 0.3, 0.45), False, 0.3),
    ]

    def c8(c, a=255):
        return tuple(int(max(0.0, min(1.0, float(v))) * 255) for v in c) + (a,)

    layers, signs, blinks = [], [], []
    for li, (col, hmin, hmax, wmin, wmax, pwin, wint) in enumerate(specs):
        im = Image.new('RGBA', (WL, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if li == 0:
            zx, bw_, tw_, ztop, tiers = 1350, 1100, 170, 250, 6
            for k in range(tiers):
                y0 = AY1 - (AY1 - ztop) * k / tiers
                y1 = AY1 - (AY1 - ztop) * (k + 1) / tiers
                w0 = bw_ + (tw_ - bw_) * k / tiers
                w1 = bw_ + (tw_ - bw_) * (k + 0.85) / tiers
                d.polygon([(zx - w0 / 2, y0 + 2), (zx + w0 / 2, y0 + 2), (zx + w1 / 2, y1), (zx - w1 / 2, y1)],
                          fill=c8(col * 1.15))
                for lx in np.arange(zx - w1 / 2 + 6, zx + w1 / 2 - 6, 14):
                    d.rectangle([lx, y1 + 3, lx + 3, y1 + 5], fill=c8(C(1.0, 0.7, 0.4) * 0.55))
            blinks.append((0, zx, ztop - 4))
        x0 = -30
        while x0 < WL:
            bw = int(rng.integers(wmin, wmax))
            bh = int(rng.integers(hmin, hmax))
            if li == 2 and 600 < (x0 % 1500) < 1100:
                bh = int(bh * 0.35)
            top = AY1 - bh
            cc = col * (0.8 + 0.4 * rng.random())
            d.rectangle([x0, top, x0 + bw, H], fill=c8(cc))
            top2 = top
            if rng.random() < 0.45:
                sw = int(bw * rng.uniform(0.3, 0.7))
                sh = int(rng.integers(15, 80))
                sx = x0 + int(rng.integers(0, max(1, bw - sw)))
                d.rectangle([sx, top - sh, sx + sw, top], fill=c8(cc))
                top2 = top - sh
            if rng.random() < 0.35:
                ax = x0 + int(rng.integers(4, max(5, bw - 4)))
                ah = int(rng.integers(30, 130))
                d.line([(ax, top2), (ax, top2 - ah)], fill=c8(cc), width=2 if li < 2 else 3)
                blinks.append((li, ax, top2 - ah))
            ws = (7, 11) if li == 0 else (10, 15) if li == 1 else (14, 20)
            wsz = (2, 3) if li == 0 else (4, 5) if li == 1 else (6, 8)
            for wy in range(top + 12, AY1 - 6, ws[1]):
                rowp = pwin * (0.3 + 1.4 * rng.random())
                for wx in range(x0 + 6, x0 + bw - 8, ws[0]):
                    if rng.random() < rowp:
                        wc = winc[int(rng.choice(4, p=[0.5, 0.3, 0.08, 0.12]))] * (wint * (0.4 + 0.6 * rng.random()))
                        d.rectangle([wx, wy, wx + wsz[0], wy + wsz[1]], fill=c8(wc))
            x0 += bw + int(rng.integers(-15, 30))
        a = np.asarray(im, np.float32)[..., 3] / 255
        has = (a > 0.5).any(axis=0)
        top = np.where(has, np.argmax(a > 0.5, axis=0), H)
        for si, (sl, sx, text, font, color, vert, flk) in enumerate(signdefs):
            if sl != li:
                continue
            spr, w_, h_, pad = sign_sprite(text, font, color, vert)
            best = None
            for cx in sorted(range(max(20, sx - 500), min(WL - w_ - 40, sx + 500), 10), key=lambda v: abs(v - sx)):
                cy = int(top[cx - 20:cx + w_ + 20].max()) + 40
                if cy + h_ < AY1 - 90:
                    best = (cx, cy)
                    break
            if best is None:
                continue
            sx, sy = best
            d.rectangle([sx - 14, sy - 14, sx + w_ + 14, sy + h_ + 14], fill=c8(col * 1.6 + color * 0.04))
            signs.append((li, sx, sy, spr, pad, flk, si))
        arr = np.asarray(im, np.float32) / 255
        a = arr[..., 3].copy()
        layers.append(((arr[..., :3] * a[..., None]).astype(np.float32), a.astype(np.float32)))
    _city.update(layers=layers, signs=signs, blinks=blinks)
    return _city


def add_signs(img, li, xoff, fi):
    for (sl, sx, sy, spr, pad, flk, idx) in _city['signs']:
        if sl != li:
            continue
        X0, Y0 = int(round(sx - xoff)) - pad, sy - pad
        h_, w_ = spr.shape[:2]
        x1, y1, x2, y2 = max(0, X0), max(0, Y0), min(W, X0 + w_), min(H, Y0 + h_)
        if x2 <= x1 or y2 <= y1:
            continue
        f = 1.0
        if flk > 0 and h01(idx, fi // 2) < flk * 0.3:
            f = 0.15 + 0.3 * h01(idx, fi)
        img[y1:y2, x1:x2] += spr[y1 - Y0:y2 - Y0, x1 - X0:x2 - X0] * f


_rain = {}


def rain(img, t, n, seed, spd, ln, width, slant, bright, col):
    if seed not in _rain:
        rng = np.random.default_rng(seed)
        _rain[seed] = (rng.uniform(-300, W + 100, n), rng.uniform(0, H, n), rng.uniform(*spd, n),
                       rng.uniform(*ln, n), rng.uniform(0.3, 1.0, n))
    x0, y0, sp, le, br = _rain[seed]
    Y = (y0 + sp * t) % (H + 120) - 60
    X = x0 + slant * Y
    im = Image.new('L', (W, H))
    d = ImageDraw.Draw(im)
    for i in range(n):
        d.line([(X[i], Y[i]), (X[i] + slant * le[i], Y[i] + le[i])], fill=int(br[i] * bright * 255), width=width)
    addc(img, Lnp(im), col)


def spinners(img, t, fi):
    gl = Image.new('RGB', (W // 4, H // 4))
    dg = ImageDraw.Draw(gl)
    core = Image.new('L', (W, H))
    dc = ImageDraw.Draw(core)
    any_ = False
    for i, (t0, t1, p0, p1, s) in enumerate(SPINNERS):
        if not (t0 <= t <= t1):
            continue
        any_ = True
        u = (t - t0) / (t1 - t0)
        px = p0[0] + (p1[0] - p0[0]) * u
        py = p0[1] + (p1[1] - p0[1]) * u + 6 * math.sin(t * 1.3 + i)
        dx = 1 if p1[0] > p0[0] else -1
        if i == 1:
            dg.polygon([(px / 4, py / 4), ((px - 150) / 4, AY1 / 4), ((px + 150) / 4, AY1 / 4)], fill=(26, 34, 42))
        hx, tx = px + dx * 14 * s, px - dx * 14 * s
        dc.ellipse([hx - 2.4 * s, py - 1.6 * s, hx + 2.4 * s, py + 1.6 * s], fill=255)
        dg.ellipse([(hx - 12 * s) / 4, (py - 7 * s) / 4, (hx + 12 * s) / 4, (py + 7 * s) / 4], fill=(190, 215, 255))
        if (fi // 5 + i) % 3 == 0:
            dc.ellipse([tx - 1.8 * s, py - 1.8 * s, tx + 1.8 * s, py + 1.8 * s], fill=200)
            dg.ellipse([(tx - 9 * s) / 4, (py - 9 * s) / 4, (tx + 9 * s) / 4, (py + 9 * s) / 4], fill=(255, 40, 30))
    if not any_:
        return
    g = gl.filter(ImageFilter.GaussianBlur(2.5)).resize((W, H), Image.BILINEAR)
    img += np.asarray(g, np.float32) * (1.4 / 255)
    addc(img, Lnp(core), (1.0, 1.0, 1.0))


def scene_city(lt, fi, t):
    Cc = city()
    img = Cc['sky'].copy()
    offs = [12 * lt, 28 * lt, 58 * lt]
    for li in range(3):
        rgb, a = Cc['layers'][li]
        xo = offs[li]
        i, f = int(xo), xo - int(xo)
        aa = a[:, i:i + W] * (1 - f) + a[:, i + 1:i + 1 + W] * f
        img *= (1 - aa)[..., None]
        img += rgb[:, i:i + W] * (1 - f) + rgb[:, i + 1:i + 1 + W] * f
        add_signs(img, li, xo, fi)
        if li == 0:
            img += (fog_frame(lt, 16, 3) * Cc['hazew'])[..., None] * C(0.08, 0.13, 0.16)
        elif li == 1:
            spinners(img, t, fi)
            img += (fog_frame(lt, 34, 5) * Cc['hazew'])[..., None] * C(0.04, 0.07, 0.09)
    near_a = Cc['layers'][2][1]
    ni = int(offs[2])
    for k, (li, bx, by) in enumerate(Cc['blinks']):
        sx = int(bx - offs[li])
        if 0 <= sx < W and 0 <= by < H and near_a[by, sx + ni] < 0.5 and (fi // 12 + k) % 4 == 0:
            y1, y2, x1, x2 = max(0, by - 3), min(H, by + 4), max(0, sx - 3), min(W, sx + 4)
            img[y1:y2, x1:x2] += C(0.9, 0.12, 0.08)
    rain(img, lt, 1300, 101, (1300, 2100), (18, 42), 1, 0.12, 0.5, (0.55, 0.68, 0.78))
    rain(img, lt, 140, 102, (2200, 2800), (60, 110), 2, 0.12, 0.35, (0.6, 0.7, 0.8))
    img *= ss(0.0, 0.8, lt) * (1 - ss(14.4, 15.0, lt))
    chapter(img, t, fi)
    card(img, t)
    return img


# ------------------------------------------------------------------ 4. farm
_farm = {}


def draw_tree(d, x, y, ang, ln, wd, depth, rng, S):
    if depth == 0 or ln < 3:
        return
    pts = [(x * S, y * S)]
    a = ang
    for _ in range(3):
        a += rng.normal(0, 0.16)
        x += math.cos(a) * ln / 3
        y += math.sin(a) * ln / 3
        pts.append((x * S, y * S))
    w_ = max(1, int(wd * S))
    d.line(pts, fill=255, width=w_, joint='curve')
    for (px, py) in pts:
        r = w_ / 2
        d.ellipse([px - r, py - r, px + r, py + r], fill=255)
    nb = 2 if rng.random() < 0.7 else 3
    for i in range(nb):
        na = a + (i - (nb - 1) / 2) * rng.uniform(0.45, 0.8) + rng.normal(0, 0.15)
        draw_tree(d, x, y, na, ln * rng.uniform(0.62, 0.78), wd * 0.64, depth - 1, rng, S)


def tree_mask(cw, ch, bx, by, ln, wd, depth, seed):
    S = 2
    im = Image.new('L', (cw * S, ch * S))
    d = ImageDraw.Draw(im)
    rng = np.random.default_rng(seed)
    d.polygon([((bx - wd * 1.3) * S, (by + 4) * S), ((bx + wd * 1.3) * S, (by + 4) * S),
               ((bx + wd * 0.45) * S, (by - ln * 0.3) * S), ((bx - wd * 0.45) * S, (by - ln * 0.3) * S)], fill=255)
    draw_tree(d, bx, by, -math.pi / 2 + 0.05, ln, wd, depth, rng, S)
    return Lnp(im.resize((cw, ch), Image.LANCZOS))


FCW, FCH, FHZ = 2400, 1350, 760
FP, FPF = (1560.0, 900.0), (1248.0, 720.0)


def farm_assets():
    if _farm:
        return _farm
    ys, xs = np.mgrid[0:FCH, 0:FCW].astype(np.float32)
    tsky = np.clip(ys / FHZ, 0, 1)[..., None]
    sky = C(0.56, 0.58, 0.60) * (1 - tsky) + C(0.80, 0.80, 0.79) * tsky
    tg = np.clip((ys - FHZ) / (FCH - FHZ), 0, 1)[..., None]
    gr = (C(0.52, 0.52, 0.50) * (1 - tg) + C(0.24, 0.24, 0.23) * tg) * \
        (0.85 + 0.3 * fbm(FCH, FCW, 90, 8, oct=4))[..., None]
    img = np.where((ys < FHZ)[..., None], sky, gr)
    rows = Image.new('L', (FCW, FCH))
    d = ImageDraw.Draw(rows)
    vp = (700, FHZ)
    for k in range(-40, 60):
        d.line([vp, (vp[0] + k * 260, FCH)], fill=255, width=2)
    yk = FHZ + 6.0
    while yk < FCH:
        d.line([(0, yk), (FCW, yk)], fill=160, width=1)
        yk = FHZ + (yk - FHZ) * 1.32
    att = np.clip(1 - np.exp(-(ys - FHZ) / 150), 0, 1)
    img += (Lnp(rows) * att * 0.09)[..., None]
    hz = Image.new('L', (FCW, FCH))
    d = ImageDraw.Draw(hz)
    rng = np.random.default_rng(12)
    xx = 0
    while xx < FCW:
        wdt = int(rng.integers(20, 140))
        hgt = int(rng.integers(4, 18))
        if rng.random() < 0.6:
            d.rectangle([xx, FHZ - hgt, xx + wdt, FHZ + 2], fill=255)
        xx += wdt + int(rng.integers(10, 120))
    over(img, Lnp(hz), (0.60, 0.61, 0.61), 0.7)
    house = Image.new('L', (FCW, FCH))
    d = ImageDraw.Draw(house)
    d.rectangle([1010, 862, 1150, 922], fill=255)
    d.polygon([(996, 866), (1080, 818), (1164, 866)], fill=255)
    over(img, Lnp(house), (0.30, 0.30, 0.30))
    img[878:892, 1040:1052] = C(0.72, 0.62, 0.46)
    img += (C(0.83, 0.83, 0.82) - img) * (0.65 * np.exp(-((ys - FHZ) / 45) ** 2))[..., None]
    tm = tree_mask(FCW, FCH, 1560, 935, 150, 30, 9, 3)
    over(img, tm, (0.19, 0.19, 0.19))
    fd = np.sqrt((xs - 1594) ** 2 + (ys - 929) ** 2)
    img += (np.exp(-(fd / 4.0) ** 2) * 0.9)[..., None] * C(1.0, 1.0, 0.95) + \
        (np.exp(-(fd / 14.0) ** 2) * 0.12)[..., None] * C(1.0, 1.0, 1.0)
    _farm['im'] = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    x, y = grid()
    _farm['mistw'] = (0.35 + 0.65 * np.exp(-((y - 610) / 260) ** 2)).astype(np.float32)
    return _farm


def zoom_frame(im, P, Pf, s):
    box = (P[0] - Pf[0] / s, P[1] - Pf[1] / s, P[0] + (W - Pf[0]) / s, P[1] + (H - Pf[1]) / s)
    return np.asarray(im.resize((W, H), Image.BILINEAR, box=box), np.float32) * (1 / 255)


def scene_farm(lt, fi, t):
    A = farm_assets()
    s = 0.8 * (1 + 0.12 * eio(lt / 14))
    img = zoom_frame(A['im'], FP, FPF, s)
    fg = fog_frame(lt, 30, 4)
    img += (C(0.84, 0.84, 0.83) - img) * (fg * 0.42 * A['mistw'])[..., None]
    img *= ss(0.0, 0.8, lt) * (1 - ss(13.4, 14.0, lt))
    # HUD
    if HUD_ON <= t <= S_FARM + 10.0:
        fo = 1 - ss(S_FARM + 9.4, S_FARM + 9.9, t)
        L = Image.new('L', (W, H))
        d = ImageDraw.Draw(L)
        bx = FPF[0] + (1560 - FP[0]) * s
        by = FPF[1] + (948 - FP[1]) * s
        e = eout((t - HUD_ON) / 0.35)
        hw, hh = 130 * e, 64 * e
        cl = 22
        for sx in (-1, 1):
            for sy in (-1, 1):
                cx, cy = bx + sx * hw, by + sy * hh
                d.line([(cx, cy), (cx - sx * cl, cy)], fill=int(230 * fo), width=2)
                d.line([(cx, cy), (cx, cy - sy * cl)], fill=int(230 * fo), width=2)
        if e > 0.99:
            sy_ = by - hh + (2 * hh) * (((t - HUD_ON) / 1.3) % 1.0)
            d.line([(bx - hw + 6, sy_), (bx + hw - 6, sy_)], fill=int(120 * fo), width=1)
            d.line([(bx - 8, by), (bx + 8, by)], fill=int(160 * fo), width=1)
            d.line([(bx, by - 8), (bx, by + 8)], fill=int(160 * fo), width=1)
        for k in range(2, 7):
            t0, text, cps = TYPED[k]
            if k < 6:
                typed(d, t, fi, t0, text, cps, 1410, 704 + (k - 2) * 27, MONO(19), 1, fill=225 * fo)
        m = Lnp(L)
        addc(img, blurL(L, 8), (0.3, 0.8, 1.0), 0.5)
        over(img, m, (0.72, 0.94, 1.0))
        L2 = Image.new('L', (W, H))
        t0, text, cps = TYPED[6]
        blink = 1.0 if t < t0 + len(text) / cps + 0.2 else (0.55 + 0.45 * ((fi // 6) % 2))
        typed(ImageDraw.Draw(L2), t, fi, t0, text, cps, 1410, 704 + 4 * 27, MONO(19), 1, fill=255 * fo * blink)
        addc(img, blurL(L2, 8), (1.0, 0.5, 0.1), 0.8)
        over(img, Lnp(L2), (1.0, 0.72, 0.38))
    chapter(img, t, fi)
    card(img, t)
    return img


# ------------------------------------------------------------------ 5. colors + Las Vegas
_col = {}
VCW, VCH, VHZ = 2400, 1350, 900
VP, VPF = (1200.0, 700.0), (960.0, 560.0)


def vegas_assets():
    if 'vegas' in _col:
        return _col['vegas']
    ys, xs = np.mgrid[0:VCH, 0:VCW].astype(np.float32)
    tt = (np.clip(ys / VHZ, 0, 1) ** 1.3)[..., None]
    skyref = C(0.36, 0.14, 0.035) * (1 - tt) + C(0.98, 0.64, 0.30) * tt
    g = np.clip((ys - VHZ) / (VCH - VHZ), 0, 1)[..., None]
    ground = C(0.78, 0.44, 0.17) * (1 - g) + C(0.25, 0.10, 0.03) * g
    img = np.where((ys >= VHZ)[..., None], ground, skyref)
    dd = np.sqrt((xs - 1580) ** 2 + (ys - 470) ** 2)
    img += np.exp(-(dd / 90) ** 2)[..., None] * C(1.0, 0.90, 0.70) * 0.5 + \
        np.exp(-dd / 480)[..., None] * C(1.0, 0.55, 0.22) * 0.30
    img *= (0.9 + 0.2 * fbm(VCH, VCW, 120, 51, oct=4))[..., None]
    rng = np.random.default_rng(77)

    def layer(draw_fn, silcol, haze):
        im = Image.new('L', (VCW * 2, VCH * 2))
        draw_fn(ImageDraw.Draw(im), 2)
        m = Lnp(im.resize((VCW, VCH), Image.LANCZOS))
        col = silcol * (1 - haze) + skyref * haze
        return m, col

    def far(d, S):
        xx = -20
        while xx < VCW:
            w_ = int(rng.integers(30, 180))
            h_ = int(rng.integers(60, 300))
            lean = int(rng.integers(-30, 30)) if rng.random() < 0.3 else 0
            if rng.random() < 0.7:
                d.polygon([(xx * S, (VHZ + 10) * S), ((xx + w_) * S, (VHZ + 10) * S),
                           ((xx + w_ + lean) * S, (VHZ - h_) * S), ((xx + lean) * S, (VHZ - h_) * S)], fill=255)
            xx += w_ + int(rng.integers(20, 160))

    def mid(d, S):
        P = lambda pts: d.polygon([(a * S, b * S) for a, b in pts], fill=255)
        P([(520, VHZ + 30), (575, 300), (700, 318), (690, VHZ + 30)])
        d.rectangle([1165 * S, 330 * S, 1185 * S, (VHZ + 20) * S], fill=255)
        d.ellipse([1115 * S, 285 * S, 1235 * S, 345 * S], fill=255)
        d.rectangle([1172 * S, 180 * S, 1178 * S, 290 * S], fill=255)
        d.rectangle([1830 * S, 480 * S, 1890 * S, (VHZ + 20) * S], fill=255)
        d.rectangle([2080 * S, 520 * S, 2140 * S, (VHZ + 20) * S], fill=255)
        P([(1820, 470), (2010, 448), (2000, 500), (1820, 522)])
        d.ellipse([160 * S, 700 * S, 560 * S, 1060 * S], fill=255)

    def near(d, S):
        for _ in range(26):
            cx, cy = rng.uniform(0, VCW), rng.uniform(1160, 1400)
            rx, ry = rng.uniform(30, 160), rng.uniform(12, 50)
            d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=255)
        d.ellipse([1442 * S, 954 * S, 1458 * S, 970 * S], fill=255)
        d.polygon([(1441 * S, 972 * S), (1459 * S, 972 * S), (1467 * S, 1032 * S), (1433 * S, 1032 * S)], fill=255)
        d.line([(1444 * S, 1030 * S), (1442 * S, 1062 * S)], fill=255, width=5 * S)
        d.line([(1456 * S, 1030 * S), (1459 * S, 1062 * S)], fill=255, width=5 * S)

    for fn, sc, hz in [(far, C(0.55, 0.26, 0.08), 0.62), (mid, C(0.30, 0.12, 0.03), 0.38),
                       (near, C(0.09, 0.04, 0.012), 0.0)]:
        m, col = layer(fn, sc, hz)
        img = img * (1 - m[..., None]) + col * m[..., None]
    img += (C(0.95, 0.62, 0.32) - img) * (0.5 * np.exp(-((ys - VHZ) / 70) ** 2))[..., None]
    v = {'im': Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))}
    r = np.random.default_rng(88)
    n = 420
    v['dust'] = (r.uniform(0, W, n), r.uniform(AY0, AY1, n), r.uniform(8, 40, n), r.uniform(0, 6.28, n),
                 r.uniform(0.6, 2.4, n), r.uniform(0.3, 1.0, n))
    x, y = grid()
    v['fogw'] = (0.3 + 0.7 * sstep(300, 900, y)).astype(np.float32)
    _col['vegas'] = v
    return v


def vegas_frame(t, fi):
    v = vegas_assets()
    lt = t - EXPAND[0]
    img = zoom_frame(v['im'], VP, VPF, 0.8 * (1 + 0.07 * eio(lt / 8.6)))
    img += (fog_frame(t - S_COLOR, 30, 7) * v['fogw'])[..., None] * C(0.30, 0.15, 0.04)
    x0, y0, sp, ph, sz, br = v['dust']
    X = (x0 + sp * (t - S_COLOR) + 15 * np.sin((t - S_COLOR) * 0.7 + ph)) % W
    Y = AY0 + (y0 - AY0 + 6 * (t - S_COLOR) + 10 * np.cos((t - S_COLOR) * 0.5 + ph)) % (AY1 - AY0)
    im = Image.new('L', (W, H))
    d = ImageDraw.Draw(im)
    for i in range(len(X)):
        r = sz[i]
        d.ellipse([X[i] - r, Y[i] - r, X[i] + r, Y[i] + r], fill=int(br[i] * 200))
    addc(img, Lnp(im), (1.0, 0.82, 0.58), 0.45)
    return img


def panel_textures():
    if 'panels' in _col:
        return _col['panels']
    w, h = PW, PH
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    n = fbm(h, w, 60, 41, oct=4)
    hz = 330
    tsky = np.clip(ys / hz, 0, 1)[..., None]
    tg = np.clip((ys - hz) / (h - hz), 0, 1)[..., None]
    farm = np.where((ys < hz)[..., None], C(0.58, 0.60, 0.61) * (1 - tsky) + C(0.80, 0.80, 0.79) * tsky,
                    C(0.50, 0.50, 0.48) * (1 - tg) + C(0.28, 0.28, 0.27) * tg)
    farm *= (0.92 + 0.16 * n)[..., None]
    farm += (C(0.83, 0.83, 0.82) - farm) * (0.6 * np.exp(-((ys - hz) / 30) ** 2))[..., None]
    over(farm, tree_mask(w, h, 262, hz + 58, 62, 11, 8, 5), (0.2, 0.2, 0.2))

    tt = (ys / h)[..., None]
    la = C(0.015, 0.045, 0.06) * (1 - tt) + C(0.05, 0.12, 0.15) * tt
    la += np.exp(-(h - ys) / 140)[..., None] * C(0.40, 0.08, 0.30)
    im = Image.new('RGB', (w, h))
    d = ImageDraw.Draw(im)
    rng = np.random.default_rng(9)
    xx = -10
    while xx < w:
        bw = int(rng.integers(40, 110))
        d.rectangle([xx, int(rng.integers(120, 330)), xx + bw, h], fill=(4, 8, 11))
        xx += bw + int(rng.integers(-5, 10))
    strips = Image.new('RGB', (w, h))
    ds = ImageDraw.Draw(strips)
    for (sx, sy, sh, c) in [(60, 200, 150, (255, 50, 160)), (180, 160, 90, (70, 230, 255)),
                            (300, 240, 120, (255, 150, 50)), (240, 380, 60, (255, 60, 90))]:
        ds.rectangle([sx, sy, sx + 6, sy + sh], fill=c)
    bld = np.asarray(im, np.float32) / 255
    mask = (bld.sum(axis=2) > 0)[..., None]
    la = np.where(mask, bld, la)
    sa = np.asarray(strips, np.float32) / 255
    sg = np.asarray(strips.filter(ImageFilter.GaussianBlur(14)), np.float32) / 255
    la += sa * 1.1 + sg * 2.2

    snow = C(0.78, 0.83, 0.88) * (1 - tt) + C(0.93, 0.95, 0.97) * tt
    snow *= (0.95 + 0.1 * n)[..., None]
    yy, k = 420, 0
    while yy < h:
        th, rh = 4 + k * 2, 7 + k * 3
        snow[yy + th:yy + th + rh] *= 0.55
        yy += th + rh
        k += 1
    _col['panels'] = [farm.astype(np.float32), la.astype(np.float32), None, snow.astype(np.float32)]
    return _col['panels']


def panel_live(i, tex, t):
    if i not in (1, 3):
        return tex
    out = tex.copy()
    im = Image.new('L', (PW, PH))
    d = ImageDraw.Draw(im)
    rng = np.random.default_rng(300 + i)
    n = 90 if i == 1 else 110
    x0, y0, sp = rng.uniform(0, PW, n), rng.uniform(0, PH, n), rng.uniform(0.6, 1.0, n)
    lt = t - S_COLOR
    for k in range(n):
        if i == 1:
            y = (y0[k] + sp[k] * 1500 * lt) % (PH + 40) - 20
            x = x0[k] + 0.1 * y
            d.line([(x, y), (x + 3, y + 26)], fill=int(90 * sp[k]), width=1)
        else:
            y = (y0[k] + sp[k] * 55 * lt) % PH
            x = (x0[k] + 12 * math.sin(lt * 1.3 + k)) % PW
            r = 1.0 + 1.5 * sp[k]
            d.ellipse([x - r, y - r, x + r, y + r], fill=255 if i == 3 else 0)
    m = np.asarray(im, np.float32)[..., None] / 255
    if i == 1:
        out += m * C(0.6, 0.72, 0.8)
    else:
        out = out * (1 - m) + m * C(1.0, 1.0, 1.0)
    return out


def scene_colors(lt, fi, t):
    x, y = grid()
    img = np.zeros((H, W, 3), np.float32) + C(0.018, 0.02, 0.024)
    tex = panel_textures()
    e = eio((t - EXPAND[0]) / (EXPAND[1] - EXPAND[0]))
    need_v = t >= PANEL_T0 + 2 * PANEL_STAGGER
    vf = vegas_frame(t, fi) if need_v else None
    if e >= 1.0:
        img = vf
    else:
        for i in range(4):
            rev = eout((t - (PANEL_T0 + i * PANEL_STAGGER)) / 0.9)
            if rev <= 0:
                continue
            off = int(round((1 - rev) * PH))
            if i == 2:
                rx = PANEL_X[2] + (0 - PANEL_X[2]) * e
                ry = PY + (AY0 - PY) * e
                rw = PW + (W - PW) * e
                rh = PH + (AY1 - AY0 - PH) * e
                x1, y1, x2, y2 = int(rx), int(ry), int(rx + rw), int(ry + rh)
                ys1 = y1 + off
                if y2 > ys1:
                    img[ys1:y2, x1:x2] = vf[y1:y2 - off, x1:x2]
            else:
                shift = int((-560 if i < 2 else 560) * e)
                t_ = panel_live(i, tex[i], t)
                if PH - off > 0:
                    blit(img, t_[:PH - off], PANEL_X[i] + shift, PY + off, alpha=1 - e)
        L = Image.new('L', (W, H))
        d = ImageDraw.Draw(L)
        sw = np.zeros((H, W), np.float32)
        swc = np.zeros((H, W, 3), np.float32)
        lfo = 1 - ss(EXPAND[0] - 0.4, EXPAND[0], t)
        for i, (name, hx) in enumerate(PANELS):
            a = ss(PANEL_T0 + i * PANEL_STAGGER + 0.6, PANEL_T0 + i * PANEL_STAGGER + 1.1, t) * lfo
            if a <= 0:
                continue
            px = PANEL_X[i]
            dtext(d, px, PY + PH + 38, name, AV(19, 'demi'), 5, fill=240 * a)
            dtext(d, px + 22, PY + PH + 66, hx, MONO(16), 2, fill=170 * a)
            rgb = C(*[int(hx[k:k + 2], 16) / 255 for k in (1, 3, 5)])
            sw[PY + PH + 53:PY + PH + 66, px:px + 13] = a
            swc[PY + PH + 53:PY + PH + 66, px:px + 13] = rgb
        over(img, Lnp(L), (0.92, 0.92, 0.9))
        img = img * (1 - sw[..., None]) + swc * sw[..., None]
    img *= ss(0.0, 0.4, lt) * (1 - ss(17.3, 18.0, lt))
    chapter(img, t, fi)
    card(img, t)
    return img


# ------------------------------------------------------------------ 6. memory
_mem = {}
HORSE_XY = (635, 175)


def mem_assets():
    if _mem:
        return _mem
    x, y = grid()
    bg = np.zeros((H, W, 3), np.float32) + C(0.03, 0.014, 0.008)
    bg += np.exp(-(AY1 - y) / 230)[..., None] * C(0.60, 0.20, 0.05)
    bg += np.exp(-(((x - 960) / 520) ** 2 + ((y - 470) / 360) ** 2))[..., None] * C(0.22, 0.09, 0.03)
    _mem['bg'] = bg.astype(np.float32)
    scan = np.ones(H, np.float32)
    scan[::3] = 0.84
    _mem['scan'] = scan[:, None, None]
    S, sc = 2, 1.25
    w, h = 650, 500
    im = Image.new('L', (w * S, h * S))
    d = ImageDraw.Draw(im)
    k = S * sc

    def P(pts):
        d.polygon([(a * k, b * k) for a, b in pts], fill=255)

    d.ellipse([100 * k, 128 * k, 345 * k, 218 * k], fill=255)
    P([(285, 150), (318, 72), (352, 52), (378, 62), (360, 132), (335, 195)])
    P([(345, 58), (385, 46), (440, 86), (452, 108), (440, 122), (400, 110), (366, 122)])
    P([(350, 62), (356, 26), (370, 56)])
    P([(362, 56), (372, 30), (382, 54)])
    for (xa, lean) in [(118, -6), (160, 4), (270, -4), (308, 8)]:
        P([(xa, 185), (xa + 26, 185), (xa + 22 + lean, 340), (xa + 4 + lean, 340)])
    P([(108, 150), (78, 168), (62, 250), (76, 256), (94, 190), (118, 172)])
    for j in range(5):
        P([(296 + j * 10, 124 - j * 15), (288 + j * 10, 104 - j * 15), (309 + j * 10, 111 - j * 15)])
    A = Lnp(im.resize((w, h), Image.LANCZOS))
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    gy = ys + 14 * fbm(h, w, 90, 61, oct=3)
    tex = 0.86 + 0.14 * (0.5 + 0.5 * np.sin(gy * 0.08))
    lit = 0.45 + 0.55 * (ys / h) ** 1.2 + 0.25 * (xs / w)
    base = C(0.92, 0.55, 0.26) * tex[..., None] * lit[..., None]
    sh = np.zeros_like(A)
    sh[:-4, :-3] = A[4:, 3:]
    edge = np.clip(A - sh, 0, 1)
    edge = Lnp(Image.fromarray((edge * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5)))
    rgb = base * A[..., None] + edge[..., None] * C(1.0, 0.6, 0.25) * 0.55
    _mem['horse'] = (rgb.astype(np.float32), A.astype(np.float32))
    r = np.random.default_rng(33)
    n = 170
    _mem['emb'] = (r.uniform(300, 1620, n), r.uniform(0, 820, n), r.uniform(40, 110, n),
                   r.uniform(0, 6.28, n), r.uniform(1.0, 3.2, n), r.uniform(0.4, 1.0, n))
    return _mem


def glitch_strength(t, fi):
    g = 0.0
    for (a, dur, s) in GLITCH:
        if a <= t < a + dur:
            g = max(g, s)
    if h01(fi, 91) < 0.035:
        g = max(g, 0.25)
    return g


def scene_memory(lt, fi, t):
    M = mem_assets()
    flick = 0.9 + 0.06 * math.sin(lt * 13) + 0.04 * math.sin(lt * 29 + 1) + 0.03 * math.sin(lt * 47 + 2)
    img = M['bg'] * flick
    ma = ss(2.35, 2.9, lt)
    rgb, A = M['horse']
    hx, hy = HORSE_XY[0], HORSE_XY[1] + int(round(4 * math.sin(lt * 0.9)))
    if ma > 0:
        h_, w_ = A.shape
        sub = img[hy:hy + h_, hx:hx + w_]
        aa = (A * ma)[..., None]
        img[hy:hy + h_, hx:hx + w_] = sub * (1 - aa) + rgb * (0.8 + 0.2 * flick) * ma
    x0, y0, sp, ph, sz, br = M['emb']
    Y = AY1 - ((y0 + sp * lt) % 820)
    X = x0 + 25 * np.sin(lt * 0.9 + ph)
    im = Image.new('L', (W, H))
    d = ImageDraw.Draw(im)
    for i in range(len(X)):
        r = sz[i]
        b = br[i] * (0.6 + 0.4 * math.sin(lt * 7 + ph[i] * 3)) * clamp((Y[i] - AY0) / 500)
        d.ellipse([X[i] - r, Y[i] - r, X[i] + r, Y[i] + r], fill=int(255 * b))
    addc(img, Lnp(im), (1.0, 0.55, 0.2), 1.1)
    addc(img, blurL(im, 10), (1.0, 0.45, 0.12), 1.4)
    if lt > 3.6:
        L = Image.new('L', (W, H))
        fl = 255 if lt > 4.1 or h01(fi, 44) > 0.5 else 0
        dtext(ImageDraw.Draw(L), W / 2, 752, '6.10.21', MONO(40), 12, fill=fl * ma, align='c')
        addc(img, blurL(L, 12), (1.0, 0.5, 0.15), 0.9)
        over(img, Lnp(L), (1.0, 0.74, 0.42))
    img *= 0.3 + 0.7 * ma
    hv = ss(HOLO_T, HOLO_T + 0.5, t)
    if hv > 0:
        x, y = grid()
        Yl = img[..., 0] * 0.3 + img[..., 1] * 0.59 + img[..., 2] * 0.11
        band = (0.5 + 0.5 * np.sin(y * 0.004 + lt * 0.9))[..., None]
        hol = (C(1.0, 0.3, 0.85) * (1 - band) + C(0.3, 0.85, 1.0) * band) * (Yl * 1.9)[..., None]
        hol *= (0.82 + 0.18 * np.sin(y * 1.1 - lt * 40))[..., None]
        img = img * (1 - 0.9 * hv) + hol * (0.9 * hv)
    img *= M['scan']
    pix = ss(S_MEM + 11.6, S_MEM + 13.4, t)
    if pix > 0:
        b = 1 + int(pix * 40)
        im8 = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
        img = np.asarray(im8.resize((W // b, H // b), Image.NEAREST).resize((W, H), Image.NEAREST),
                         np.float32) / 255
    g = glitch_strength(t, fi) if lt > 2.3 else 0.0
    if g > 0:
        rng = np.random.default_rng(fi * 7 + 3)
        for _ in range(int(2 + g * 6)):
            y0_ = int(rng.integers(AY0, AY1 - 10))
            hh = int(rng.integers(4, 40))
            img[y0_:y0_ + hh] = np.roll(img[y0_:y0_ + hh], int(rng.normal(0, 60 * g)), axis=1)
        s = int(3 + 10 * g)
        img[..., 0] = np.roll(img[..., 0], s, axis=1)
        img[..., 2] = np.roll(img[..., 2], -s, axis=1)
        img *= 1 + 0.25 * g * (h01(fi, 5) - 0.3)
    img *= 1 - ss(13.3, 14.0, lt)
    chapter(img, t, fi)
    card(img, t)
    return img


# ------------------------------------------------------------------ 7. snow
_snow = {}


def snow_assets():
    if _snow:
        return _snow
    x, y = grid()
    tt = np.clip((y - AY0) / (AY1 - AY0), 0, 1)[..., None]
    bg = C(0.05, 0.07, 0.10) * (1 - tt) + C(0.15, 0.18, 0.22) * tt
    bg += np.exp(-(((x - 420) / 600) ** 2 + ((y - 250) / 380) ** 2))[..., None] * C(0.18, 0.20, 0.24)
    n = fbm(H, W, 40, 12, oct=3)
    xr = x[0]
    side = y >= 735
    bg = np.where(side[..., None], C(0.09, 0.11, 0.14) * (0.75 + 0.5 * n)[..., None], bg)
    yy, k = 735, 0
    while yy < AY1:
        tr, rh = int(5 + k * 2.0), int(9 + k * 3.2)
        for (y0, y1, col) in [(yy, yy + tr, C(0.42, 0.47, 0.54) * (0.72 + 0.03 * k)),
                              (yy + tr, yy + tr + rh, C(0.06, 0.075, 0.10))]:
            y1 = min(y1, H)
            if y1 <= y0:
                continue
            yc = np.arange(y0, y1, dtype=np.float32)
            hw = 380 + np.clip((yc - 735) / (AY1 - 735), 0, 1) ** 1.3 * 1150
            inside = (np.abs(xr[None, :] - 960) < hw[:, None])[..., None]
            bg[y0:y1] = np.where(inside, col * (0.85 + 0.3 * n[y0:y1])[..., None], bg[y0:y1])
        yy += tr + rh
        k += 1
    bg += (C(0.20, 0.23, 0.27) - bg) * (0.5 * np.exp(-((y - 735) / 60) ** 2))[..., None]
    _snow['bg'] = bg.astype(np.float32)
    r = np.random.default_rng(55)
    lay = []
    for (cnt, rad, spd, sway, b) in [(900, (0.8, 1.3), (25, 45), 10, 0.5), (340, (1.6, 2.6), (55, 90), 20, 0.8),
                                     (55, (5, 9), (110, 170), 34, 0.45)]:
        lay.append((r.uniform(0, W, cnt), r.uniform(0, H, cnt), r.uniform(*spd, cnt), r.uniform(*rad, cnt),
                    r.uniform(0, 6.28, cnt), r.uniform(0.5, 1.2, cnt), sway, b))
    _snow['flakes'] = lay
    return _snow


def scene_snow(lt, fi, t):
    S = snow_assets()
    img = S['bg'].copy()
    im = Image.new('L', (W, H))
    d = ImageDraw.Draw(im)
    bok = Image.new('L', (W // 4, H // 4))
    db = ImageDraw.Draw(bok)
    for li, (x0, y0, sp, rad, ph, fr, sway, b) in enumerate(S['flakes']):
        Y = (y0 + sp * lt) % (AY1 - AY0 + 40) + AY0 - 20
        X = (x0 + sway * np.sin(lt * fr + ph) + 8 * lt) % W
        for i in range(len(X)):
            r = rad[i]
            if li < 2:
                d.ellipse([X[i] - r, Y[i] - r, X[i] + r, Y[i] + r], fill=int(255 * b))
            else:
                db.ellipse([(X[i] - r) / 4, (Y[i] - r) / 4, (X[i] + r) / 4, (Y[i] + r) / 4], fill=int(255 * b))
    addc(img, Lnp(im), (0.9, 0.93, 0.97))
    bk = bok.filter(ImageFilter.GaussianBlur(1.2)).resize((W, H), Image.BILINEAR)
    addc(img, Lnp(bk), (0.85, 0.9, 0.95))
    tfo = 1 - ss(9.6, 10.8, lt)
    L = Image.new('L', (W, H))
    d = ImageDraw.Draw(L)
    dtext(d, W / 2, 420, 'BLADE RUNNER 2049', AV(56, 'reg'), 28, fill=255 * ss(0.8, 2.2, lt) * tfo, align='c')
    for k, line in enumerate(['DIRECTED BY DENIS VILLENEUVE', 'CINEMATOGRAPHY BY ROGER DEAKINS',
                              'MUSIC BY HANS ZIMMER & BENJAMIN WALLFISCH']):
        a = ss(3.0 + 0.6 * k, 3.8 + 0.6 * k, lt) * tfo
        dtext(d, W / 2, 500 + 36 * k, line, AV(21, 'med'), 7, fill=215 * a, align='c')
    a2 = ss(6.2, 7.0, lt) * tfo
    wl = eout((lt - 6.0) / 0.8) * 60
    if wl > 0.5:
        d.line([(W / 2 - wl, 614), (W / 2 + wl, 614)], fill=int(200 * tfo), width=1)
    L2 = Image.new('L', (W, H))
    d2 = ImageDraw.Draw(L2)
    dtext(d2, W / 2, 660, 'TWO ACADEMY AWARDS', AV(22, 'demi'), 8, fill=255 * a2, align='c')
    dtext(d2, W / 2, 694, 'CINEMATOGRAPHY  ·  VISUAL EFFECTS', MONO(17), 4, fill=200 * a2, align='c')
    mL, mL2 = Lnp(L), Lnp(L2)
    shadow = blurL(Image.fromarray((np.clip(mL + mL2, 0, 1) * 255).astype(np.uint8)), 14)
    over(img, shadow, (0, 0, 0), 0.5)
    over(img, mL, (0.93, 0.95, 0.97))
    addc(img, blurL(L2, 10), (1.0, 0.55, 0.2), 0.4)
    over(img, mL2, (1.0, 0.74, 0.45))
    img *= ss(0.0, 0.8, lt) * (1 - ss(10.6, 11.8, lt))
    return img


# ------------------------------------------------------------------ assembly
SCENES = [  # start, end, fn, bloom threshold, bloom amount
    (S_EYE, S_TITLE, scene_eye, 0.55, 0.5),
    (S_TITLE, S_CITY, scene_title, 0.45, 0.6),
    (S_CITY, S_FARM, scene_city, 0.42, 0.7),
    (S_FARM, S_COLOR, scene_farm, 0.95, 0.2),
    (S_COLOR, S_MEM, scene_colors, 0.82, 0.45),
    (S_MEM, S_SNOW, scene_memory, 0.5, 0.6),
    (S_SNOW, DUR + 1, scene_snow, 0.75, 0.35),
]
_fin = {}


def finish(img, fi, thr, amt):
    if not _fin:
        x, y = grid()
        u, v = (x - W / 2) / (W / 2), (y - H / 2) / (H / 2)
        _fin['vig'] = np.clip(1 - 0.38 * np.clip(u * u * 0.8 + v * v * 1.2 - 0.15, 0, None), 0, 1)[..., None]
        rng = np.random.default_rng(99)
        _fin['grain'] = [rng.standard_normal((H, W), dtype=np.float32)[..., None] for _ in range(6)]
    img = np.ascontiguousarray(img, dtype=np.float32)
    if amt > 0:
        b = np.clip((img - thr) * 1.6, 0, 1)
        bi = Image.fromarray((b * 255).astype(np.uint8))
        s = bi.resize((W // 8, H // 8), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3.5))
        img += np.asarray(s.resize((W, H), Image.BILINEAR), np.float32) * (amt / 255)
    img *= _fin['vig']
    np.maximum(img, 0, out=img)
    k = 0.82
    img = np.minimum(img, k) + (1 - k) * (1 - np.exp(-np.maximum(img - k, 0) / (1 - k)))
    img += _fin['grain'][fi % 6] * 0.026
    img[:AY0] = 0
    img[AY1:] = 0
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def render_frame(fi):
    t = fi / FPS
    for (a, b, fn, thr, amt) in SCENES:
        if a <= t < b:
            return finish(fn(t - a, fi, t), fi, thr, amt)
    return np.zeros((H, W, 3), np.uint8)


def main():
    mode = sys.argv[1]
    if mode == 'still':
        out = sys.argv[3]
        os.makedirs(out, exist_ok=True)
        for s in sys.argv[2].split(','):
            fi = int(round(float(s) * FPS))
            Image.fromarray(render_frame(fi)).save(os.path.join(out, 'f_%06.2f.png' % float(s)))
            print('still', s, flush=True)
    elif mode == 'worker':
        i, n, out = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
        a, b = NF * i // n, NF * (i + 1) // n
        cmd = [FFMPEG, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (W, H),
               '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '17',
               '-pix_fmt', 'yuv420p', '-g', '48', os.path.join(out, 'seg_%02d.mp4' % i)]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for fi in range(a, b):
            p.stdin.write(render_frame(fi).tobytes())
            if (fi - a) % 24 == 0:
                print('worker %d: %d/%d' % (i, fi - a, b - a), flush=True)
        p.stdin.close()
        p.wait()
        print('worker %d done' % i, flush=True)


if __name__ == '__main__':
    main()
