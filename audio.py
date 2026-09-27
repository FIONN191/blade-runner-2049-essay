#!/usr/bin/env python3
"""Original synth score and sound design for the Blade Runner 2049 essay.

Pure numpy: wavetable saw pads, brass "braams", rain, wind, HUD blips,
music box and bells, all synced to the timeline constants in render.py.
Usage: python3 audio.py OUT.wav
"""
import math
import sys
import wave

import numpy as np

from render import (CHAPTERS, DUR, EXPAND, GLITCH, HOLO_T, HUD_ON, PANEL_STAGGER, PANEL_T0, S_CITY, S_COLOR,
                    S_FARM, S_MEM, S_SNOW, S_TITLE, SPINNERS, TITLE_2049, TYPED, W, h01)

SR = 48000
N = int(SR * DUR)
T = np.arange(N) / SR
rng = np.random.default_rng(2049)


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def noise(*shape):
    return rng.standard_normal(shape)


def filt(x, lo=None, hi=None, order=2, pad=True):
    x = np.asarray(x, float)
    n = x.shape[-1]
    p = min(n, SR // 2) if pad else 0
    if p:
        x = np.concatenate([x, np.zeros(x.shape[:-1] + (p,))], axis=-1)
    f = np.fft.rfftfreq(x.shape[-1], 1 / SR)
    g = np.ones_like(f)
    if hi:
        g /= np.sqrt(1 + (f / hi) ** (2 * order))
    if lo:
        g /= np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** (2 * order))
    return np.fft.irfft(np.fft.rfft(x, axis=-1) * g, n=x.shape[-1], axis=-1)[..., :n]


TL = 4096
_tabs = {}


def saw_tab(f):
    nh = int(max(1, min(200, 9000 / max(f, 1.0))))
    if nh not in _tabs:
        ph = np.arange(TL) / TL
        tab = np.zeros(TL)
        for k in range(1, nh + 1):
            tab += np.sin(2 * np.pi * k * ph) / k
        _tabs[nh] = tab * (2 / np.pi)
    return _tabs[nh]


def osc(freq, n, tab, ph0=0.0):
    inc = (np.full(n, freq) if np.isscalar(freq) else np.asarray(freq)) / SR
    ph = (ph0 + np.cumsum(inc)) % 1.0
    idx = ph * TL
    i0 = idx.astype(np.int64)
    fr = idx - i0
    return tab[i0 % TL] * (1 - fr) + tab[(i0 + 1) % TL] * fr


class Bus:
    def __init__(self):
        self.b = np.zeros((2, N))

    def put(self, sig, t0, gain=1.0, pan=0.0):
        sig = np.asarray(sig, float)
        if sig.ndim == 1:
            a = (np.clip(np.asarray(pan, float), -1, 1) + 1) * np.pi / 4
            sig = np.stack([sig * np.cos(a), sig * np.sin(a)]) * math.sqrt(2)
        i0 = int(round(t0 * SR))
        if i0 < 0:
            sig, i0 = sig[:, -i0:], 0
        n = min(sig.shape[1], N - i0)
        if n > 0:
            self.b[:, i0:i0 + n] += sig[:, :n] * gain

    def norm(self):
        pk = np.abs(self.b).max()
        return self.b / pk if pk > 0 else self.b


def env_ar(n, att, rel_at, rel):
    tt = np.arange(n) / SR
    a = np.clip(tt / att, 0, 1) ** 1.6
    r = np.where(tt < rel_at, 1.0, np.exp(-(tt - rel_at) / max(rel, 1e-3)))
    return a * r


# ------------------------------------------------------------------ pad
CHORDS = [
    (0.3, 9.4, [38, 45], 0.8),
    (9.0, 17.4, [38, 50, 53, 57], 0.7),
    (17.0, 21.4, [38, 50, 53, 57, 62], 0.7),
    (21.0, 25.4, [46, 53, 57, 62], 0.7),
    (25.0, 28.9, [43, 50, 55, 58], 0.7),
    (28.5, 32.3, [45, 52, 57, 61, 64], 0.7),
    (32.0, 46.4, [38, 45, 50], 0.55),
    (46.0, 51.0, [41, 53, 57, 60], 0.6),
    (50.5, 56.0, [48, 55, 60, 64], 0.6),
    (55.6, 64.4, [38, 45, 50, 58], 0.75),
    (64.0, 68.0, [46, 53, 57, 62], 0.6),
    (67.5, 71.5, [45, 53, 57, 60], 0.6),
    (71.0, 75.0, [43, 53, 58, 62], 0.6),
    (74.5, 78.6, [45, 52, 55, 61], 0.6),
    (78.0, 84.5, [38, 50, 53, 57, 64], 0.6),
    (84.0, 89.0, [38, 50, 57, 64], 0.55),
]
pad = Bus()
for (a, b, notes, amp) in CHORDS:
    rel = 2.2
    n = int((b - a + rel) * SR)
    tt = np.arange(n) / SR
    e = env_ar(n, 1.4, b - a, rel / 3)
    for m in notes:
        f = mtof(m)
        vib = 1 + 0.0016 * np.sin(2 * np.pi * 4.6 * tt + rng.uniform(0, 6.28)) * np.clip(tt / 2.5, 0, 1)
        tab = saw_tab(f * 1.01)
        l = osc(f * vib * 2 ** (-7 / 1200), n, tab, rng.random()) + 0.7 * osc(f * vib, n, tab, rng.random())
        r = osc(f * vib * 2 ** (7 / 1200), n, tab, rng.random()) + 0.7 * osc(f * vib * 2 ** (2 / 1200), n, tab,
                                                                             rng.random())
        g = amp / math.sqrt(len(notes)) * (1.3 if m <= 45 else 1.0)
        pad.put(np.stack([l, r]) * e * g, a)
bright = np.interp(T, [0, 9, 10, 17, 18, 32, 33, 46, 47, 56, 57, 64, 65, 78, 79, 90],
                   [0.05, 0.05, 0.3, 0.3, 0.6, 0.6, 0.12, 0.12, 0.5, 0.5, 0.75, 0.75, 0.35, 0.35, 0.4, 0.4])
pad.b = filt(pad.b, hi=700, pad=False) * (1 - bright) + filt(pad.b, hi=2600, pad=False) * bright
# faint minor-second shimmer over the farm
for m, pn in [(74, -0.4), (75, 0.4)]:
    n = int(14.0 * SR)
    tt = np.arange(n) / SR
    s = np.sin(2 * np.pi * mtof(m) * tt) * env_ar(n, 3.0, 11.5, 0.8) * (0.8 + 0.2 * np.sin(tt * 0.9 + m))
    pad.put(s * 0.05, S_FARM + 0.3, pan=pn)

# ------------------------------------------------------------------ sub drone
sub = Bus()
for (a, b) in [(0.5, 9.3), (32.2, 46.2), (55.8, 64.2), (78.4, 89.0)]:
    n = int((b - a) * SR)
    tt = np.arange(n) / SR
    e = np.clip(tt / 2.0, 0, 1) * np.clip((b - a - tt) / 1.5, 0, 1)
    sub.put((np.sin(2 * np.pi * mtof(26) * tt) + 0.5 * np.sin(2 * np.pi * mtof(38) * tt)) * e, a)

# ------------------------------------------------------------------ rain / rumble / wind
rain = Bus()
r = filt(noise(2, N), lo=400, hi=6500, order=1, pad=False)
r /= r.std()
imp = np.zeros((2, N))
k = int(DUR * 70)
imp[0, rng.integers(0, N, k)] = rng.uniform(0.3, 1, k)
imp[1, rng.integers(0, N, k)] = rng.uniform(0.3, 1, k)
patter = filt(imp, lo=1800, hi=6000, order=2, pad=False)
patter /= patter.std() + 1e-9
renv = np.interp(T, [0, 2, 9, 10, 16.6, 17.4, 31.7, 32.05, 90], [0, .5, .5, .22, .22, .8, .8, 0, 0])
rain.put((r + 0.35 * patter) * renv, 0)

rumble = Bus()
br_ = np.cumsum(noise(2, N), axis=1)
br_ = filt(br_, lo=25, hi=140, order=2, pad=False)
rumble.put(br_ * np.interp(T, [0, 16.8, 18, 31.5, 32.1, 90], [0, 0, 1, 1, 0, 0]), 0)

wind = Bus()
wn = filt(noise(2, N), lo=90, hi=650, order=2, pad=False)
lfo = np.interp(T, np.arange(int(DUR / 0.7) + 2) * 0.7, rng.random(int(DUR / 0.7) + 2))
lfo = filt(lfo, hi=1.5, pad=False)
wh = filt(noise(2, N), lo=650, hi=1100, order=3, pad=False) * np.clip(lfo - 0.45, 0, None) * 2.5
wenv = np.interp(T, [0, 32, 33, 45.5, 46.5, 55, 56.5, 63.8, 64.2, 78, 79.5, 88, 90],
                 [0, 0, .55, .55, .1, .1, .65, .65, 0, 0, .35, .35, 0])
wind.put((wn / wn.std() * (0.5 + 0.8 * lfo) + wh / (wh.std() + 1e-9) * 0.25) * wenv, 0)

# ------------------------------------------------------------------ braams + hits
braam = Bus()


def make_braam(dur=5.5, root=38):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    bend = 2 ** ((35 / 1200) * np.exp(-tt / 0.12))
    sig = np.zeros(n)
    for m, a in [(root - 12, 1.0), (root, 0.8), (root + 7, 0.5), (root + 12, 0.35)]:
        f = mtof(m)
        tab = saw_tab(f)
        for det in (-8, 0, 8):
            sig += a * osc(f * bend * 2 ** (det / 1200), n, tab, rng.random())
    e = np.exp(-tt / 0.7) * (1 - np.exp(-tt / 0.03))
    y = filt(sig, hi=260) * (1 - e) + filt(sig, hi=2300) * e
    y = np.tanh(y * ((1 - np.exp(-tt / 0.04)) * np.exp(-tt / 1.9)) * 1.4)
    fs = 34 + 24 * np.exp(-tt / 0.15)
    y += 0.9 * np.sin(2 * np.pi * np.cumsum(fs) / SR) * np.exp(-tt / 1.4) * (1 - np.exp(-tt / 0.01))
    return np.stack([y, np.roll(y, 240)])


braam.put(make_braam(6.0, 38), TITLE_2049 - 0.02, 0.8)
braam.put(make_braam(7.5, 36), EXPAND[0] + 0.45, 1.0)

hits = Bus()


def subhit(dur=1.8):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    f = 36 + 40 * np.exp(-tt / 0.1)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt / 0.5) * (1 - np.exp(-tt / 0.004))


def riser(dur):
    n = int(dur * SR)
    u = np.arange(n) / n
    s = filt(noise(n), hi=700) * (1 - u) + filt(noise(n), lo=1500, hi=9000) * u
    return s / np.abs(s).max() * u ** 3


for (a, b, num, title) in CHAPTERS:
    hits.put(subhit(), a, 0.9)
    hits.put(riser(1.1), a - 1.1, 0.25)
hits.put(riser(1.9), 7.0, 0.35)                 # eye zoom into the pupil

# ------------------------------------------------------------------ fx (UI, whooshes, neon, glitches)
fx = Bus()


def click():
    n = int(0.02 * SR)
    tt = np.arange(n) / SR
    return filt(noise(n) * np.exp(-tt / 0.0025), lo=1800, hi=9000, order=1)


def beep(f, dur=0.07):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    return np.sin(2 * np.pi * f * tt) * np.clip(tt / 0.004, 0, 1) * np.clip((dur - tt) / 0.02, 0, 1)


def whoosh(dur, lo=250, hi=3500):
    n = int(dur * SR)
    u = np.arange(n) / n
    s = filt(noise(n), lo=lo, hi=hi)
    return s / np.abs(s).max() * np.sin(np.pi * u) ** 2


def buzz(dur, f=100):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    return filt(osc(f, n, saw_tab(f)), hi=1500) * np.exp(-tt / (dur / 3))


for (t0, text, cps) in TYPED:
    for i, ch in enumerate(text):
        if ch not in ' .':
            fx.put(click(), t0 + (i + 1) / cps, 0.10 * rng.uniform(0.6, 1.0), pan=rng.uniform(-0.3, 0.3))
fx.put(beep(1320, 0.05), HUD_ON, 0.14)
fx.put(beep(1760, 0.05), HUD_ON + 0.08, 0.10)
for (t0, text, cps) in TYPED[2:6]:
    fx.put(beep(1320), t0, 0.08, pan=0.4)
fx.put(beep(880, 0.12), TYPED[6][0] + len(TYPED[6][1]) / TYPED[6][2], 0.2, pan=0.4)
fx.put(beep(880, 0.12), TYPED[6][0] + len(TYPED[6][1]) / TYPED[6][2] + 0.2, 0.2, pan=0.4)
for i in range(12):                                             # neon title letters igniting
    on = S_TITLE + 0.7 + 1.3 * h01(i, 11)
    fx.put(click(), on, 0.18, pan=(i - 6) / 8)
    fx.put(buzz(0.22), on, 0.05, pan=(i - 6) / 8)
for (a, b, num, title) in CHAPTERS:                             # chapter letters
    for i in range(len(title)):
        fx.put(click(), a + 0.25 + 0.7 * h01(i, 17, len(title)), 0.05, pan=(i / len(title) - 0.5))
for i in range(4):                                              # palette panels
    fx.put(whoosh(0.8, 300, 3000), PANEL_T0 + i * PANEL_STAGGER - 0.2, 0.28, pan=-0.6 + 0.4 * i)
fx.put(riser(1.3), EXPAND[0] - 0.85, 0.4)
for idx, (t0, t1, p0, p1, sc) in enumerate(SPINNERS):         # flying cars
    dur = t1 - t0
    n = int(dur * SR)
    u = np.arange(n) / n
    x = p0[0] + (p1[0] - p0[0]) * u
    near = np.exp(-((x - W / 2) / 700) ** 2)
    dop = 1 + 0.06 * -np.tanh((u - 0.5) * 6) * np.sign(p1[0] - p0[0]) * np.sign(W / 2 - p0[0])
    hum = filt(osc(58 * dop, n, saw_tab(58)), hi=450)
    s = (filt(noise(n), lo=200, hi=2200) * 0.6 + hum * 0.8) * near
    fx.put(s / (np.abs(s).max() + 1e-9), t0, [0.15, 0.45, 0.8][idx], pan=np.clip((x - W / 2) / (W / 2), -1, 1) * 0.9)
for (a, dur, st) in GLITCH:                                     # memory glitches
    n = int(dur * SR)
    hold = int(rng.integers(12, 90))
    v = rng.uniform(-1, 1, n // hold + 1).repeat(hold)[:n]
    gate = (np.floor(np.arange(n) / (0.028 * SR)) % 2 == 0)
    tt = np.arange(n) / SR
    fx.put(v * gate * st + 0.4 * np.sin(2 * np.pi * 60 * tt), a, 0.22, pan=rng.uniform(-0.5, 0.5))
n = int(0.6 * SR)                                               # hologram shift sweep
tt = np.arange(n) / SR
fx.put(np.sin(2 * np.pi * np.cumsum(1800 * np.exp(-tt / 0.15) + 120) / SR) * np.exp(-tt / 0.25), HOLO_T, 0.2)

# ------------------------------------------------------------------ heartbeat, fire
heart = Bus()


def thump(f0=64, f1=40, dec=0.09):
    n = int(0.4 * SR)
    tt = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-tt / 0.04)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt / dec) * (1 - np.exp(-tt / 0.002))


tb = S_FARM + 0.8
while tb < S_FARM + 13.4:
    g = min(1.0, (tb - S_FARM) / 3.0) * min(1.0, (S_FARM + 13.6 - tb) / 2.0)
    heart.put(thump(), tb, g)
    heart.put(thump(58, 38, 0.08), tb + 0.26, 0.7 * g)
    tb += 60 / 58

fire = Bus()
fn = filt(noise(2, N), lo=30, hi=220, order=2, pad=False)
flick = 0.8 + 0.2 * np.sin(T * 13) * np.sin(T * 3.1)
fenv = np.interp(T, [0, S_MEM, S_MEM + 1.5, S_MEM + 8.9, S_MEM + 9.6, 90], [0, 0, 1, 1, 0.3, 0.3])
fenv *= np.interp(T, [0, S_MEM + 13.2, S_MEM + 14.0, 90], [1, 1, 0, 0])
imp = np.zeros((2, N))
kk = int(14 * 18)
pos = rng.integers(int((S_MEM + 1) * SR), int((S_MEM + 13.5) * SR), (2, kk))
imp[0, pos[0]] = rng.uniform(0.2, 1, kk) ** 2
imp[1, pos[1]] = rng.uniform(0.2, 1, kk) ** 2
crackle = filt(imp, lo=900, hi=5000, order=2, pad=False)
fire.put((fn / fn.std() * flick + crackle / (crackle.std() + 1e-9) * 0.9) * fenv, 0)

# ------------------------------------------------------------------ music box + bells
mbox = Bus()


def bell(freq, dur, partials):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    s = sum(a * np.sin(2 * np.pi * freq * rr * tt + rng.uniform(0, 6.28)) * np.exp(-tt / d) for rr, a, d in partials)
    return s * (1 - np.exp(-tt / 0.003))


MB = [(1, 1.0, 0.9), (2.0, 0.3, 0.45), (5.4, 0.12, 0.15)]
melody = [74, 69, 65, 69, 76, 69, 65, 69, 77, 76, 74, 72, 69, None, 74]
for i, m in enumerate(melody):
    if m is None:
        continue
    tn = S_MEM + 2.9 + i * 0.5
    warp = 0.985 if tn > HOLO_T else 1.0
    mbox.put(bell(mtof(m + 12) * warp, 2.5, MB), tn, 0.8 + 0.2 * (i % 2), pan=0.25 * math.sin(i))

bells = Bus()
BL = [(1, 1.0, 3.2), (2.0, 0.35, 1.8), (3.0, 0.18, 1.0), (4.16, 0.12, 0.6), (5.43, 0.06, 0.4)]
for i, (tn, m) in enumerate([(S_SNOW + 1.4, 69), (S_SNOW + 2.6, 74), (S_SNOW + 3.8, 76), (S_SNOW + 5.0, 77),
                             (S_SNOW + 6.6, 76), (S_SNOW + 7.8, 74), (S_SNOW + 9.2, 69), (S_SNOW + 9.2, 62)]):
    bells.put(bell(mtof(m), 5.0, BL), tn, 0.9, pan=0.3 * math.sin(i * 1.7))

# ------------------------------------------------------------------ mix
MIX = [  # bus, gain, reverb send
    (pad, 0.30, 0.35), (sub, 0.22, 0.0), (rain, 0.20, 0.05), (rumble, 0.20, 0.0), (wind, 0.20, 0.1),
    (braam, 0.95, 0.3), (hits, 0.65, 0.2), (fx, 0.40, 0.25), (heart, 0.55, 0.1), (fire, 0.22, 0.1),
    (mbox, 0.20, 0.55), (bells, 0.30, 0.6),
]
dry = np.zeros((2, N))
send = np.zeros((2, N))
for bus, g, s in MIX:
    b = bus.norm() * g
    dry += b
    send += b * s
irn = int(3.4 * SR)
itt = np.arange(irn) / SR
ir = filt(noise(2, irn) * np.exp(-itt / 0.6), hi=5500, order=1)
ramp = int(0.02 * SR)
ir[:, :ramp] *= np.linspace(0, 1, ramp)
ir /= np.sqrt((ir ** 2).sum(axis=1, keepdims=True))
nf = 1 << (N + irn - 1).bit_length()
wet = np.fft.irfft(np.fft.rfft(send, nf) * np.fft.rfft(ir, nf), nf)[:, :N]
out = filt(dry + wet * 0.9, lo=22, order=2, pad=False)
out /= np.abs(out).max()
out = np.tanh(out * 1.6) / np.tanh(1.6) * 0.89
out *= np.clip(T / 0.05, 0, 1) * np.clip((DUR - T) / 1.5, 0, 1)

for name, (a, b) in [('eye', (0, 9)), ('title', (9, 17)), ('city', (17, 32)), ('farm', (32, 46)),
                     ('color', (46, 64)), ('memory', (64, 78)), ('snow', (78, 90))]:
    seg = out[:, int(a * SR):int(b * SR)]
    print('%-7s rms %5.1f dBFS  peak %5.1f dBFS' % (name, 20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-9),
                                                  20 * np.log10(np.abs(seg).max() + 1e-9)))
pcm = (np.clip(out, -1, 1).T * 32767).astype('<i2')
with wave.open(sys.argv[1], 'wb') as wf:
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(SR)
    wf.writeframes(pcm.tobytes())
print('wrote', sys.argv[1])
