"""Sound for V1: VO placement, a procedural TEMP score, synthesized sound
design, ducking, loudness. Everything is generated deterministically (seeded)
from the timeline in edl.py, so a re-cut re-flows the sound automatically.

Outputs (media/02_AUDIO/):
  VO/placed/VO_<id>.wav      processed VO lines (tempo, EQ, comp), one per event
  MUSIC/IAM_v01_TEMP_SCORE.wav   procedural placeholder score (replace with licensed music)
  SFX/IAM_v01_SFX.wav            full sound-design stem
  MIX/IAM_v01_VO_STEM.wav        VO stem
  MIX/IAM_v01_MIX.wav            final review mix, -16 LUFS integrated, <= -1 dBTP

The temp score is NOT a finished music choice. It exists so the cut can be
judged with the intended arc (silence -> motif -> pulse -> expansion -> open
harmony -> rhythmic system -> strip -> silence). Swap in a licensed track.
"""
import json
import os
import subprocess
import sys

import numpy as np
from scipy import signal
from scipy.io import wavfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edl  # noqa: E402

SR = 48000
ROOT = edl.ROOT
A_DIR = os.path.join(ROOT, "media", "02_AUDIO")
BUILD = os.path.join(ROOT, "build", "audio")
RNG = np.random.default_rng(1971)


# ----------------------------------------------------------------------------- dsp helpers
def db(x):
    return 10 ** (x / 20.0)


def n_(t):
    return int(round(t * SR))


def tvec(dur):
    return np.arange(n_(dur)) / SR


def sos(kind, f, order=2):
    if kind == "bp":
        return signal.butter(order, [f[0] / (SR / 2), f[1] / (SR / 2)], "bandpass", output="sos")
    return signal.butter(order, f / (SR / 2), {"lp": "lowpass", "hp": "highpass"}[kind], output="sos")


def filt(x, kind, f, order=2):
    return signal.sosfilt(sos(kind, f, order), x, axis=0)


def white(n):
    return RNG.standard_normal(n)


def colored(n, power):
    """1/f^power noise (power 1 = pink, 2 = brown), unit RMS."""
    w = np.fft.rfft(white(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = f[1]
    x = np.fft.irfft(w / f ** (power / 2), n)
    return x / (np.sqrt(np.mean(x ** 2)) + 1e-12)


def norm_rms(x, level_db):
    r = np.sqrt(np.mean(x ** 2)) + 1e-12
    return x * db(level_db) / r


def norm_peak(x, level_db):
    p = np.max(np.abs(x)) + 1e-12
    return x * db(level_db) / p


def env_ar(n, a, r, sustain=None):
    """Attack/release envelope over n samples (a, r in seconds)."""
    e = np.ones(n)
    na, nr = min(n, n_(a)), min(n, n_(r))
    if na:
        e[:na] = np.linspace(0, 1, na) ** 1.5
    if nr:
        e[n - nr:] *= np.linspace(1, 0, nr) ** 1.5
    return e


def expdecay(n, tau):
    return np.exp(-np.arange(n) / (tau * SR))


def smooth_rand(dur, rate, depth=1.0):
    """Slow random modulation (0..1-ish) at roughly `rate` Hz."""
    n = n_(dur)
    k = max(4, int(dur * rate) + 4)
    pts = RNG.random(k)
    x = np.interp(np.linspace(0, k - 3, n), np.arange(k), pts)
    return 1 - depth + depth * x


def pan(x, p):
    """Equal-power pan, p in [-1, 1]. Returns (n, 2)."""
    a = (p + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], axis=1)


def stereo(x, width=0.0):
    if x.ndim == 2:
        return x
    if width <= 0:
        return np.stack([x, x], axis=1) * 0.7071
    d = n_(0.011 * width)
    y = np.concatenate([np.zeros(d), x[:-d]]) if d else x
    return np.stack([x, y], axis=1) * 0.7071


def make_ir(rt, predelay=0.02, lp=6500, seed=7, early=True):
    rng = np.random.default_rng(seed)
    n = n_(rt * 1.2)
    t = np.arange(n) / SR
    decay = np.exp(-6.9 * t / rt)
    ir = rng.standard_normal((n, 2)) * decay[:, None]
    ir = signal.sosfilt(sos("lp", lp), ir, axis=0)
    ir = signal.sosfilt(sos("hp", 120), ir, axis=0)
    if early:
        for k in range(8):
            d = n_(0.004 + 0.009 * k + rng.random() * 0.004)
            if d < n:
                ir[d, :] += (0.6 / (k + 1)) * np.array([rng.choice([-1, 1]), rng.choice([-1, 1])])
    pd = n_(predelay)
    ir = np.concatenate([np.zeros((pd, 2)), ir])
    return ir / np.sqrt(np.sum(ir ** 2))


def reverb(x, ir, wet):
    x = stereo(x)
    y = np.stack([signal.fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], axis=1)
    return x * (1 - wet) + y * wet * 1.6


class Track:
    def __init__(self, dur):
        self.buf = np.zeros((n_(dur) + SR, 2))

    def add(self, t, x, gain_db=0.0, p=0.0):
        if x.ndim == 1:
            x = pan(x, p)
        i = n_(t)
        if i < 0:
            x = x[-i:]
            i = 0
        j = min(len(self.buf), i + len(x))
        self.buf[i:j] += x[: j - i] * db(gain_db)

    def region_gain(self, t0, t1, gain_db, fade=0.05):
        """Multiply a time region by a gain with short ramps."""
        g = np.ones(len(self.buf))
        a, b, f = n_(t0), n_(t1), n_(fade)
        g[a:b] = db(gain_db)
        ramp = np.linspace(1, db(gain_db), f)
        g[max(0, a - f):a] = ramp[: a - max(0, a - f)]
        g[b:b + f] = ramp[::-1][: len(g[b:b + f])]
        self.buf *= g[:, None]


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"])}


def m(name):
    """'D3' -> midi."""
    pc, octv = name[:-1], int(name[-1])
    return 12 * (octv + 1) + NOTE[pc]


# ----------------------------------------------------------------------------- instruments
def saw(f, t, detune_cents=0.0, phase=0.0):
    ff = f * 2 ** (detune_cents / 1200)
    return 2 * ((ff * t + phase) % 1.0) - 1


def pad_note(freq, dur, attack=2.2, release=2.5, cutoff=900, voices=5, spread=9, wobble=True):
    """Low-strings-ish pad: detuned saw stack, lowpassed, slow attack, tape wow."""
    t = tvec(dur + release)
    wow = 1 + (0.0009 * np.sin(2 * np.pi * 0.31 * t) if wobble else 0)
    x = np.zeros_like(t)
    for v in range(voices):
        c = (v - (voices - 1) / 2) * (spread / max(1, voices - 1)) * 2
        x += saw(freq * wow, t, c, RNG.random())
    x = filt(x / voices, "lp", cutoff, 2)
    x = filt(x, "lp", cutoff * 1.6, 2)
    e = env_ar(len(t), attack, release)
    return x * e


def string_note(freq, dur, attack=1.4, release=2.0, cutoff=2400):
    t = tvec(dur + release)
    vib = 1 + 0.0022 * np.sin(2 * np.pi * 5.1 * t) * np.clip(t / 1.2, 0, 1)
    x = sum(saw(freq * vib, t, c, RNG.random()) for c in (-6, 0, 6)) / 3
    x = filt(x, "lp", cutoff, 2)
    x = filt(x, "hp", 180, 1)
    return x * env_ar(len(t), attack, release)


def felt_piano(freq, dur=4.5, vel=1.0):
    """Felt piano: inharmonic partials, per-partial decay, soft hammer."""
    t = tvec(dur)
    B = 0.00035
    x = np.zeros_like(t)
    for k in range(1, 10):
        fk = k * freq * np.sqrt(1 + B * k * k)
        if fk > 9000:
            break
        amp = (1.0 / k ** 1.35) * (0.85 if k % 2 == 0 else 1.0)
        tau = 2.6 / (1 + 0.55 * (k - 1)) * (220 / max(freq, 110)) ** 0.35
        x += amp * np.sin(2 * np.pi * fk * t + RNG.random()) * np.exp(-t / tau)
    a = n_(0.006)
    x[:a] *= np.linspace(0, 1, a)
    ham = filt(white(n_(0.025)), "lp", 1800) * expdecay(n_(0.025), 0.006) * 0.25
    x[: len(ham)] += ham
    x = filt(x, "lp", 3200 * (0.6 + 0.4 * vel), 2)
    return x * vel


def kick(vel=1.0):
    n = n_(0.45)
    t = np.arange(n) / SR
    f = 44 + 70 * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-t / 0.16)
    x += filt(white(n), "lp", 900) * np.exp(-t / 0.008) * 0.25
    return filt(x, "lp", 2200) * vel


def tick(vel=1.0, bright=6000):
    n = n_(0.06)
    x = filt(white(n), "hp", bright, 2) * expdecay(n, 0.012)
    return x * vel


def pluck(freq, vel=1.0, cutoff=1300, length=0.22):
    """Analog-ish arp pluck: square wave through a decaying lowpass."""
    t = tvec(length + 0.05)
    x = np.sign(np.sin(2 * np.pi * freq * t)) * 0.6 + saw(freq, t) * 0.4
    x = filt(x, "lp", cutoff, 2)
    return x * np.exp(-t / (length * 0.45)) * vel


def sub(freq, dur, attack=3.0, release=3.0):
    t = tvec(dur + release)
    x = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * 2 * freq * t)
    x = np.tanh(1.4 * x) / np.tanh(1.4)
    return x * env_ar(len(t), attack, release)


# ----------------------------------------------------------------------------- score
def chord(names):
    return [mtof(m(n)) for n in names]


def build_score(tl, K):
    """K: dict of key times from the timeline."""
    dur = edl.DURATION
    padt = Track(dur)
    keys = Track(dur)    # piano, strings
    rhythm = Track(dur)  # kick, ticks, arp
    low = Track(dur)

    def pad(t0, t1, names, gain=-22, cutoff=900, attack=2.2, release=2.5, voices=5):
        for i, f in enumerate(chord(names)):
            p = (i / max(1, len(names) - 1) - 0.5) * 0.9
            padt.add(t0, pad_note(f, t1 - t0, attack, release, cutoff, voices), gain - 2 * (len(names) > 4), p)

    # IDENTITY — almost silence, motif enters at S05 (~10s)
    pad(K["motif"] - 0.6, K["problem"] + 0.4, ["D3", "A3", "F4"], gain=-27, cutoff=700, attack=3.5)
    motif = [(0.0, "A4", 0.9), (1.18, "F4", 0.75), (2.36, "E4", 0.7), (3.9, "D4", 0.8),
             (5.9, "A3", 0.55)]
    for dt, nm, v in motif:
        keys.add(K["motif"] + 0.25 + dt, felt_piano(mtof(m(nm)), 5.0, v), -15, 0.12)
    # "I am the asset" — low D under it
    keys.add(K["asset"] - 0.05, felt_piano(mtof(m("D2")), 6.0, 0.9), -16, -0.1)
    keys.add(K["asset"] - 0.05, felt_piano(mtof(m("D3")), 6.0, 0.6), -18, 0.1)
    low.add(K["asset"] - 0.3, sub(mtof(m("D1")), 2.0, 0.4, 2.5), -24)

    # PROBLEM — pulse begins
    beat = 60 / 84
    P, B = K["problem"], K["billboard_off"]
    prog = [["D3", "F3", "A3"], ["Bb2", "F3", "D4"], ["G2", "D3", "Bb3"], ["A2", "E3", "A3"]]
    t, i = P, 0
    while t < B - 0.5:
        t1 = min(t + 4 * beat, B)
        pad(t, t1 + 0.6, prog[i % 4], gain=-24, cutoff=1100, attack=0.9, release=0.9)
        t, i = t1, i + 1
    k = 0
    t = P
    while t < B - 0.05:
        rhythm.add(t, kick(0.9 if k % 4 == 0 else 0.6), -19)
        if t > P + 2 * beat:
            rhythm.add(t + beat / 2, tick(0.6), -33, 0.35)
        if k % 2 == 1:
            low.add(t, sub(mtof(m("D1")), beat * 0.8, 0.02, 0.3), -27)
        t += beat
        k += 1
    # strobe-pop accents on the "A campaign / A deal / A fee" beats
    for key in ("vo09a", "vo09b", "vo09c"):
        rhythm.add(K[key] - 0.02, kick(1.0), -17)
    # collapse: low sustain only through the black
    low.add(K["black"] - 0.2, sub(mtof(m("D1")), K["trust"] - K["black"], 1.2, 1.2), -31)
    keys.add(K["trust_vo"] - 0.05, felt_piano(mtof(m("D4")), 6.0, 0.75), -16, -0.1)
    keys.add(K["trust_vo"] + 0.02, felt_piano(mtof(m("A4")), 6.0, 0.5), -20, 0.15)

    # INVERSION — low-frequency expansion, wider, steel
    I, D = K["inversion"], K["demand"]
    low.add(I - 0.2, sub(mtof(m("D1")), D - I, 2.5, 2.0), -21)
    inv = [["D2", "A2", "E3", "F3", "C4"], ["Bb1", "F2", "A2", "D3", "E3"]]
    t, i = I, 0
    while t < D:
        t1 = min(t + 8 * beat, D + 0.2)
        pad(t, t1 + 0.5, inv[i % 2], gain=-22, cutoff=1000 + 120 * i, attack=1.6, release=1.5, voices=6)
        t, i = t1, i + 1
    t, k = I, 0
    while t < D - 0.1:
        rhythm.add(t, kick(0.7 if k % 2 == 0 else 0.45), -20)
        rhythm.add(t + beat / 2, tick(0.45, 4500), -35, -0.3)
        for s16 in (0, 0.5):
            f = mtof(m("D2")) if (k + int(s16 * 2)) % 4 else mtof(m("A1"))
            rhythm.add(t + s16 * beat, pluck(f, 0.6, 500, 0.3), -24, 0.0)
        t += beat
        k += 1
    # DEMAND card: breath — pad + sub hold only (pulse already stops at D)
    pad(D - 0.1, K["iam"] + 0.4, ["D2", "A2", "E3"], gain=-25, cutoff=700, attack=0.4, release=1.2)

    # IAM — harmony opens, more resolved
    A, M = K["iam"], K["machine"]
    seg = (M - A) / 5
    iam = [["Bb1", "F2", "A2", "C3", "D3"], ["A1", "F2", "C3", "F3", "A3"], ["G1", "D2", "F2", "Bb2", "A3"],
           ["C2", "G2", "E3", "G3", "C4"], ["D2", "A2", "E3", "F3", "A3"]]
    for i, ch in enumerate(iam):
        pad(A + i * seg, A + (i + 1) * seg + 0.6, ch, gain=-21, cutoff=1500, attack=1.2, release=1.4, voices=6)
        low.add(A + i * seg, sub(mtof(m(ch[0])) * (2 if mtof(m(ch[0])) < 40 else 1), seg, 0.8, 1.0), -27)
    for i, (nm, ln) in enumerate([("A4", 1.0), ("C5", 1.0), ("D5", 1.0), ("E5", 1.0), ("F5", 1.0)]):
        keys.add(A + i * seg + 0.2, string_note(mtof(m(nm)), seg * ln), -27, 0.25)
    t, k = A, 0
    while t < M - 0.1:
        if k % 2 == 0:
            rhythm.add(t, kick(0.55), -21)
        if k % 4 == 3:
            rhythm.add(t + beat / 2, tick(0.4, 5000), -36, 0.3)
        t += beat
        k += 1
    keys.add(K["builds"] - 0.03, felt_piano(mtof(m("D3")), 5.0, 0.9), -15, 0.0)
    keys.add(K["builds"] - 0.03, felt_piano(mtof(m("A3")), 5.0, 0.7), -18, 0.1)

    # MACHINE — rhythmic system develops (16th arp + full pulse)
    C = K["close"]
    mach = [(["D3", "F3", "A3", "C4"], "D2"), (["Bb2", "D3", "F3", "A3"], "Bb1"),
            (["F3", "A3", "C4", "E4"], "F2"), (["C3", "E3", "G3", "C4"], "C2")]
    t, k = M, 0
    while t < C - 0.05:
        ci = (k // 4) % 4
        notes, root = mach[ci]
        if k % 4 == 0:
            pad(t, t + 4 * beat + 0.4, notes[:3], gain=-25, cutoff=1300, attack=0.4, release=0.6)
            low.add(t, sub(mtof(m(root)) * (2 if mtof(m(root)) < 40 else 1), 4 * beat, 0.05, 0.4), -25)
        prog_open = min(1.0, (t - M) / (C - M))
        for s in range(4):
            nt = notes[(s + k) % 4]
            f = mtof(m(nt)) * (2 if s == 2 else 1)
            rhythm.add(t + s * beat / 4, pluck(f, 0.55 + 0.25 * (s == 0), 900 + 1500 * prog_open, 0.18),
                       -25, -0.45 if s % 2 else 0.45)
        rhythm.add(t, kick(0.85 if k % 2 == 0 else 0.6), -18)
        rhythm.add(t + beat / 2, tick(0.6), -31, 0.3)
        for s in (1, 3):
            rhythm.add(t + s * beat / 4, tick(0.25, 8000), -38, -0.3)
        t += beat
        k += 1

    # CLOSE — strip down, motif returns, release to silence before the logo
    E = K["end"]
    pad(C - 0.2, K["stage"] + 1.2, ["D3", "A3", "E4", "F4"], gain=-26, cutoff=800, attack=1.0, release=2.2)
    for dt, nm, v in [(0.35, "A4", 0.75), (1.6, "F4", 0.6), (2.85, "E4", 0.6)]:
        keys.add(C + dt, felt_piano(mtof(m(nm)), 5.0, v), -16, 0.1)
    keys.add(K["owner"] - 0.04, felt_piano(mtof(m("D4")), 5.0, 0.8), -15, 0.0)
    keys.add(K["owner"] - 0.04, felt_piano(mtof(m("D3")), 5.0, 0.6), -18, -0.1)

    ir_hall = make_ir(3.4, 0.03, 6000, seed=11)
    ir_room = make_ir(1.4, 0.015, 7000, seed=12)
    mus = (reverb(padt.buf, ir_hall, 0.35)
           + reverb(keys.buf, ir_hall, 0.45)
           + reverb(rhythm.buf, ir_room, 0.18)
           + low.buf)
    # analog texture: faint tape hiss while music plays
    hiss = stereo(filt(colored(len(mus), 1), "bp", (2000, 12000)), 1.0) * db(-66)
    mus += hiss
    # arc automation: silence at top, collapse on the billboard, release before logo
    t = np.arange(len(mus)) / SR
    g = np.ones(len(mus))
    g *= np.clip((t - (K["motif"] - 1.0)) / 1.5, 0, 1) * 0.92 + 0.08 * (t > K["asset"] - 1)
    off = (t > K["billboard_off"]) & (t < K["trust_vo"] - 0.3)
    g[off] *= 0.55
    rel = np.clip((K["end"] - 0.35 - t) / 2.6, 0, 1)
    g *= rel
    g[t >= K["end"]] = 0
    return mus * g[:, None]


# ----------------------------------------------------------------------------- sfx
def bp_noise(dur, lo, hi, color=1):
    return filt(colored(n_(dur), color), "bp", (lo, hi))


def fx_roomtone(dur):
    return stereo(filt(filt(colored(n_(dur), 1.2), "lp", 1400), "hp", 70), 1.5)


def fx_hum(dur, f0=50.0):
    t = tvec(dur)
    x = sum((1 / k) * np.sin(2 * np.pi * f0 * k * t + k) for k in (1, 2, 3, 4, 6))
    return x * smooth_rand(dur, 0.7, 0.25)


def fx_crowd(dur, excite=0.0):
    base = bp_noise(dur, 180, 2200, 1.2) * smooth_rand(dur, 0.4, 0.35)
    babble = np.zeros(n_(dur))
    for _ in range(int(dur * 25)):
        L = n_(0.15 + RNG.random() * 0.4)
        st = RNG.integers(0, max(1, len(babble) - L))
        fc = 350 + RNG.random() * 1800
        b = filt(white(L), "bp", (fc * 0.8, fc * 1.25)) * np.hanning(L)
        babble[st:st + L] += b * (0.5 + RNG.random())
    x = base + norm_rms(babble, 0) * 0.35 + excite * bp_noise(dur, 900, 5000, 0.8) * 0.3
    return stereo(x, 2.0)


def fx_breath(dur=0.9, inhale=True):
    n = n_(dur)
    x = filt(white(n), "bp", (500, 2400))
    e = np.sin(np.linspace(0, np.pi, n)) ** (1.5 if inhale else 0.8)
    return x * e


def fx_clink():
    n = n_(0.5)
    t = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f * t) * np.exp(-t / d) * a
            for f, d, a in [(2310, 0.11, 1), (3470, 0.08, 0.8), (4890, 0.05, 0.6), (6120, 0.04, 0.45), (7650, 0.03, 0.3)])
    x[: n_(0.004)] += filt(white(n_(0.004)), "hp", 3000)
    return x


def fx_click():
    n = n_(0.03)
    t = np.arange(n) / SR
    return filt(white(n), "hp", 1500) * np.exp(-t / 0.0025) + 0.4 * np.sin(2 * np.pi * 1400 * t) * np.exp(-t / 0.004)


def fx_rustle(dur, lo=900, hi=6000):
    x = filt(white(n_(dur)), "bp", (lo, hi))
    g = smooth_rand(dur, 22, 0.9) ** 3
    return x * g * env_ar(n_(dur), 0.08, 0.15)


def fx_step(hard=False, vel=1.0):
    n = n_(0.25)
    t = np.arange(n) / SR
    thump = np.sin(2 * np.pi * (70 + 40 * np.exp(-t / 0.02)) * t) * np.exp(-t / 0.05)
    heel = filt(white(n), "bp", (300, 3500 if hard else 1800)) * np.exp(-t / (0.012 if hard else 0.02))
    return (thump * 0.8 + heel * (1.2 if hard else 0.7)) * vel


def fx_steps(dur, period, hard=False, jitter=0.05, vel=1.0):
    out = np.zeros(n_(dur) + n_(0.3))
    t = 0.05
    k = 0
    while t < dur:
        s = fx_step(hard, vel * (0.8 + 0.3 * RNG.random()) * (1.0 if k % 2 else 0.85))
        i = n_(t)
        out[i:i + len(s)] += s
        t += period * (1 + jitter * (RNG.random() - 0.5))
        k += 1
    return out[: n_(dur)]


def fx_strobe_charge(dur=0.6):
    t = tvec(dur)
    f = 1800 + 4200 * (t / dur) ** 1.5
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * (t / dur) ** 2


def fx_strobe_pop():
    n = n_(0.35)
    t = np.arange(n) / SR
    crack = filt(white(n), "hp", 900) * np.exp(-t / 0.012)
    body = np.sin(2 * np.pi * 95 * t) * np.exp(-t / 0.06) * 0.6
    return crack + body


def fx_shutter():
    out = np.zeros(n_(0.18))
    for d, a in [(0.0, 1.0), (0.055, 0.75)]:
        n = n_(0.025)
        c = filt(white(n), "bp", (1800, 9000)) * expdecay(n, 0.004) * a
        i = n_(d)
        out[i:i + n] += c
    whir = filt(white(len(out)), "bp", (500, 1500)) * np.hanning(len(out)) * 0.12
    return out + whir


def fx_paper(dur, density=18):
    out = np.zeros(n_(dur))
    for _ in range(int(dur * density)):
        L = n_(0.01 + RNG.random() * 0.05)
        st = RNG.integers(0, max(1, len(out) - L))
        out[st:st + L] += filt(white(L), "bp", (1500, 9000)) * np.hanning(L) * RNG.random()
    out += filt(white(len(out)), "bp", (800, 4000)) * smooth_rand(dur, 6, 0.9) * 0.15
    return out * env_ar(len(out), 0.05, 0.1)


def fx_pen(dur):
    x = filt(white(n_(dur)), "bp", (2200, 7000))
    strokes = np.clip(np.sin(2 * np.pi * np.cumsum(5 + 4 * smooth_rand(dur, 2)) / SR), 0, 1) ** 0.7
    return x * strokes * smooth_rand(dur, 9, 0.6) * env_ar(n_(dur), 0.05, 0.1)


def fx_elec_hum(dur, f0=60):
    t = tvec(dur)
    buzz = filt(saw(f0, t), "lp", 1400) * 0.6 + np.sin(2 * np.pi * f0 * 2 * t) * 0.4
    crackle = np.zeros(len(t))
    for _ in range(int(dur * 6)):
        i = RNG.integers(0, len(t) - 400)
        crackle[i:i + 300] += filt(white(300), "hp", 2500) * np.hanning(300) * RNG.random()
    return buzz * smooth_rand(dur, 3, 0.15) + crackle * 0.3


def fx_power_down(dur=0.9):
    t = tvec(dur)
    f = 60 * np.exp(-t / 0.25) + 12
    hum = filt(saw(1, np.cumsum(f) / SR), "lp", 900) * np.exp(-t / 0.35)
    n = n_(0.25)
    tt = np.arange(n) / SR
    thunk = np.sin(2 * np.pi * 55 * tt) * np.exp(-tt / 0.06) + filt(white(n), "bp", (400, 3000)) * np.exp(-tt / 0.01) * 0.5
    out = hum * 0.8
    i = n_(dur * 0.55)
    out[i:i + n] += thunk[: len(out) - i]
    return out


def fx_machinery(dur, period=0.95):
    rumble = filt(colored(n_(dur), 2), "lp", 260) * smooth_rand(dur, 0.5, 0.2)
    rattle = filt(white(n_(dur)), "bp", (350, 1600)) * (0.6 + 0.4 * np.sin(2 * np.pi * 11.3 * tvec(dur))) * 0.35
    thunks = np.zeros(n_(dur))
    t = 0.2
    while t < dur - 0.3:
        n = n_(0.2)
        tt = np.arange(n) / SR
        th = np.sin(2 * np.pi * 85 * tt) * np.exp(-tt / 0.04) + filt(white(n), "bp", (500, 2500)) * np.exp(-tt / 0.01) * 0.4
        i = n_(t)
        thunks[i:i + n] += th * (0.7 + 0.3 * RNG.random())
        t += period
    servo = np.zeros(n_(dur))
    for _ in range(max(1, int(dur / 1.6))):
        L = n_(0.5 + RNG.random() * 0.4)
        st = RNG.integers(0, max(1, len(servo) - L))
        tt = np.arange(L) / SR
        f = 650 + 380 * np.sin(np.pi * tt / tt[-1])
        ph = 2 * np.pi * np.cumsum(f) / SR
        servo[st:st + L] += (np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph)) * np.hanning(L) * 0.25
    return stereo(rumble * 0.3 + rattle * 1.4 + thunks * 1.1 + servo * 1.8, 1.5)


def fx_glass_room(dur):
    air = filt(colored(n_(dur), 1), "bp", (3500, 11000)) * 0.4
    hvac = filt(colored(n_(dur), 2), "lp", 220)
    return stereo(air + hvac, 1.2)


def fx_creak(dur=0.6):
    t = tvec(dur)
    f = 190 + 60 * smooth_rand(dur, 9)
    x = saw(1, np.cumsum(f) / SR)
    x = filt(x, "bp", (300, 1600)) * (smooth_rand(dur, 30, 0.9) ** 2)
    return x * np.sin(np.linspace(0, np.pi, len(t)))


def fx_knock(vel=1.0, mat="wood"):
    n = n_(0.25)
    t = np.arange(n) / SR
    modes = [(820, 0.05), (1630, 0.03), (2580, 0.02)] if mat == "wood" else [(1450, 0.18), (3100, 0.1), (4900, 0.06)]
    x = sum(np.sin(2 * np.pi * f * t) * np.exp(-t / d) for f, d in modes)
    x += filt(white(n), "bp", (600, 5000)) * np.exp(-t / 0.004) * 0.6
    return x * vel


def fx_roar(dur):
    x = bp_noise(dur, 250, 4200, 1.0) * smooth_rand(dur, 1.2, 0.4)
    swell = np.linspace(0.45, 1.0, n_(dur)) ** 1.5
    return stereo(x * swell, 3.0)


def build_sfx(tl, K):
    """Levels are absolute targets (pre-loudness-normalisation, where a VO line
    sits around -21 dBFS RMS per channel): amb() sets an element's RMS, spot()
    its peak, so generators don't need calibrated output."""
    dur = edl.DURATION
    tr = Track(dur)
    room_ir = make_ir(0.45, 0.008, 8000, seed=21)
    hall_ir = make_ir(2.6, 0.04, 5000, seed=22)
    shots = tl.shots
    S = lambda i: shots[i]["start"]  # noqa: E731
    E = lambda i: shots[i]["end"]    # noqa: E731

    def amb(t, x, rms_db, p=0.0, ir=None, wet=0.0):
        x = norm_rms(stereo(x) if x.ndim == 2 else pan(x, p), rms_db)
        if ir is not None:
            x = reverb(x, ir, wet)
        tr.add(t, x)

    def spot(t, x, peak_db, p=0.0, ir=None, wet=0.0):
        x = pan(x, p) if x.ndim == 1 else x
        if ir is not None:
            x = reverb(x, ir, wet)
        tr.add(t, norm_peak(x, peak_db))

    # global room tone (dropped to near silence on the black, gone on the logo)
    amb(0.0, fx_roomtone(K["end"]), -62)

    # IDENTITY — backstage: hum, distant PA, crowd behind the wall, breath, jewelry
    P = K["problem"]
    amb(0.0, stereo(fx_hum(P + 0.1, 50)), -56)
    pa = bp_noise(P, 250, 1800, 1.2) * smooth_rand(P, 0.25, 0.6)
    amb(0.0, pa, -52, ir=hall_ir, wet=0.7)
    spot(0.08, fx_breath(0.95), -30)
    spot(1.3, fx_rustle(0.7), -38, -0.2)
    crowd_len = P + 0.25
    crowd = fx_crowd(crowd_len)
    ramp = np.clip((tvec(crowd_len) - (S(5) - 2.0)) / 2.5, 0, 1) * 0.82 + 0.18
    ramp *= np.clip((P + 0.25 - tvec(crowd_len)) / 0.3, 0, 1)
    amb(0.0, reverb(crowd, hall_ir, 0.5) * ramp[:, None], -44)
    s4 = S(1)
    spot(s4 + 0.02, fx_rustle(0.45, 1200, 7000), -36, 0.2)
    for dt, g in [(0.22, -27), (0.62, -30), (1.15, -28)]:
        spot(s4 + dt, fx_clink(), g, 0.15, room_ir, 0.2)
    spot(s4 + 1.55, fx_click(), -26, 0.3)
    amb(S(4), fx_steps(E(4) - S(4), 0.56), -46, ir=room_ir, wet=0.35)
    spot(S(4) + 0.9, fx_rustle(0.5, 300, 2500), -38, -0.3)  # cable / clothing
    amb(S(5), fx_roar(E(5) - S(5) + 0.3), -46, ir=hall_ir, wet=0.6)

    # PROBLEM — commercial machine: strobe, shutter, paper, pen, the billboard dies
    spot(P - 0.62, fx_strobe_charge(0.6), -38, 0.4)
    spot(P, fx_strobe_pop(), -14, 0.2, room_ir, 0.3)
    for dt, p in [(0.55, 0.3), (1.2, -0.2), (1.9, 0.25)]:
        spot(P + dt, fx_shutter(), -22, p, room_ir, 0.25)
    amb(S(7) + 0.05, fx_paper(0.9), -40, -0.1, room_ir, 0.25)
    spot(S(7) + 1.2, fx_rustle(0.35, 2000, 8000), -34, 0.1)
    spot(S(8) - 0.01, fx_strobe_pop(), -15, 0.25, room_ir, 0.3)
    spot(S(8) + 0.12, fx_shutter(), -21, -0.2, room_ir, 0.25)
    spot(S(9) + 0.02, fx_click(), -22, 0.2)            # pen cap
    amb(S(9) + 0.15, fx_pen(0.55), -40, 0.2)
    bb = E(10) - S(10)
    amb(S(10), stereo(fx_elec_hum(bb - 0.4) * env_ar(n_(bb - 0.4), 0.3, 0.05)), -42)
    spot(E(10) - 0.95, stereo(fx_power_down(1.0)), -16)
    tr.region_gain(K["black"], K["trust"], -14, 0.08)    # sound collapses on the black

    # INVERSION — machinery, conveyor, servo, glass room
    amb(S(13), fx_machinery(E(13) - S(13) + 0.15), -40, ir=hall_ir, wet=0.35)
    amb(S(14), fx_glass_room(E(14) - S(14)), -52)
    amb(S(14) + 0.6, fx_machinery(2.6, 1.3), -47, ir=room_ir, wet=0.3)
    spot(S(15) + 0.4, fx_rustle(0.5, 400, 3000), -40, -0.1)
    amb(S(16), fx_machinery(E(16) - S(16), 0.85), -40, ir=hall_ir, wet=0.35)

    # IAM — controlled, clean: room presence, chair, paper, prototype handling
    amb(S(18), fx_glass_room(E(18) - S(18)), -50)
    spot(S(18) + 0.65, fx_creak(0.6), -32, -0.3, room_ir, 0.3)
    amb(S(19), stereo(filt(colored(n_(E(19) - S(19)), 2), "lp", 300)), -54)   # distant city
    amb(S(20) + 1.3, fx_paper(0.6, 10), -42, 0.2, room_ir, 0.3)
    for dt, g, mat in [(0.6, -25, "wood"), (1.9, -28, "ceramic"), (3.4, -26, "wood")]:
        spot(S(21) + dt, fx_knock(1.0, mat), g, 0.1, room_ir, 0.3)
    amb(S(21) + 4.2, fx_paper(0.5, 12), -42, -0.1, room_ir, 0.3)

    # MACHINE — pen, handling, operations hall, heels
    amb(S(22) + 0.15, fx_pen(E(22) - S(22) - 0.4), -40, -0.15, room_ir, 0.2)
    spot(S(23) + 0.5, fx_knock(0.9, "wood"), -27, 0.15, room_ir, 0.3)
    amb(S(24), fx_machinery(E(24) - S(24) + 0.2, 0.75), -41, ir=hall_ir, wet=0.4)
    spot(S(24) + 0.1, fx_steps(E(24) - S(24) - 0.2, 0.5, hard=True, vel=0.8), -24, ir=hall_ir, wet=0.3)
    amb(S(25), stereo(filt(colored(n_(E(25) - S(25)), 2), "lp", 300)), -56)

    # CLOSE — remove almost everything; footsteps, crowd, breath, stage energy
    spot(S(26) + 0.1, fx_breath(0.8, False), -34)
    st = S(27)
    sd = K["end"] - st
    spot(st, fx_steps(sd, 0.6, hard=True, vel=1.0), -18, ir=hall_ir, wet=0.4)
    amb(st - 0.6, fx_roar(sd + 0.6), -36, ir=hall_ir, wet=0.55)
    amb(st, stereo(fx_hum(sd, 50) * 0.6 + bp_noise(sd, 3000, 9000) * 0.2), -50)

    out = tr.buf
    t = np.arange(len(out)) / SR
    out[t >= K["end"]] = 0  # hard silence on the logo
    cut = n_(K["end"])
    f = n_(0.02)
    out[cut - f:cut] *= np.linspace(1, 0, f)[:, None]
    return out


# ----------------------------------------------------------------------------- vo
def process_vo(tl):
    vdir = os.path.join(A_DIR, "VO", "placed")
    os.makedirs(vdir, exist_ok=True)
    track = Track(edl.DURATION)
    placed = []
    for v in tl.vo:
        take, a, b, text = edl.VO[v["id"]]
        src = os.path.join(edl.VO_DIR, take + ".wav")
        a0 = max(0.0, a - edl.VO_PRE)
        b0 = b + edl.VO_POST
        out = os.path.join(vdir, f"VO_{v['id']}.wav")
        af = (f"atrim=start={a0:.3f}:end={b0:.3f},asetpts=PTS-STARTPTS,pan=mono|c0=0.5*c0+0.5*c1,"
              f"rubberband=tempo={edl.VO_TEMPO}:pitchq=quality:smoothing=on,"
              "highpass=f=75,equalizer=f=220:t=q:w=1.2:g=1.5,equalizer=f=3500:t=q:w=1.5:g=1.0,"
              "acompressor=threshold=-22dB:ratio=2.5:attack=8:release=150:makeup=1,"
              "afade=t=in:d=0.02,areverse,afade=t=in:d=0.07,areverse")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", af, "-ar", str(SR), "-c:a", "pcm_s24le", out],
                       check=True)
        sr, x = wavfile.read(out)
        x = x.astype(np.float64) / 2 ** 31 if x.dtype == np.int32 else x.astype(np.float64) / 32768
        # level each line on its loud part so quiet takes don't sink
        frame = n_(0.05)
        r = np.array([np.sqrt(np.mean(x[i:i + frame] ** 2)) for i in range(0, len(x) - frame, frame)])
        active = r[r > r.max() * 0.25]
        g = db(-17.5) / (np.sqrt(np.mean(active ** 2)) + 1e-9)
        x = np.clip(x * g, -0.95, 0.95)
        at = v["start"] - (a - a0) / edl.VO_TEMPO
        track.add(at, pan(x, 0.0) * np.sqrt(2) * 0.7071 * 1.0, 0.0)
        placed.append(dict(id=v["id"], file=os.path.relpath(out, ROOT), at=round(at, 4), text=text,
                           dur=round(len(x) / SR, 4)))
    with open(os.path.join(A_DIR, "VO", "placed", "vo_placement.json"), "w") as fh:
        json.dump(placed, fh, indent=1)
    return track.buf


# ----------------------------------------------------------------------------- mix
def duck(vo, music, depth_db=-5.0):
    lvl = np.sqrt(signal.sosfilt(sos("lp", 8), (vo ** 2).mean(axis=1)).clip(0))
    on = np.clip((20 * np.log10(lvl + 1e-9) + 48) / 18, 0, 1)
    # asymmetric smoothing: 60ms attack, 450ms release
    out = np.zeros_like(on)
    aa, rr = np.exp(-1 / (0.06 * SR)), np.exp(-1 / (0.45 * SR))
    prev = 0.0
    for i in range(0, len(on), 48):
        x = on[i]
        prev = aa * prev + (1 - aa) * x if x > prev else rr * prev + (1 - rr) * x
        out[i:i + 48] = prev
    return music * db(depth_db * out)[:, None]


def write(path, x):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    y = np.clip(x, -1, 1)
    wavfile.write(path, SR, (y * (2 ** 31 - 1)).astype(np.int32))


def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "loudnorm=I=-16:TP=-1:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    js = r.stderr[r.stderr.rfind("{"):]
    d = json.loads(js)
    return float(d["input_i"]), float(d["input_tp"])


def keytimes(tl):
    sh = tl.shots
    vo = {v["id"]: v for v in tl.vo}
    sec = dict((name, t) for t, name in tl.sections)
    K = dict(
        motif=sh[4]["start"],
        asset=vo["07a"]["start"],
        problem=sec["THE PROBLEM"],
        vo09a=vo["09a"]["start"], vo09b=vo["09b"]["start"], vo09c=vo["09c"]["start"],
        billboard_off=sh[10]["end"] - 0.45,
        black=sh[11]["start"],
        trust=sh[12]["start"],
        trust_vo=vo["12"]["start"],
        inversion=sec["THE INVERSION"],
        demand=sh[17]["start"],
        iam=sec["INTRODUCE IAM"],
        builds=vo["21b"]["start"],
        machine=sec["THE MACHINE"],
        close=sec["CLOSE"],
        owner=vo["27"]["start"],
        stage=sh[27]["start"],
        end=tl.end_card,
    )
    return K


def main():
    tl = edl.build()
    K = keytimes(tl)
    os.makedirs(BUILD, exist_ok=True)
    print("  VO ...")
    vo = process_vo(tl)
    print("  score ...")
    music = build_score(tl, K)
    print("  sfx ...")
    sfx = build_sfx(tl, K)
    n = min(len(vo), len(music), len(sfx), n_(edl.DURATION))
    vo, music, sfx = vo[:n], music[:n], sfx[:n]
    # stem balance (pre-loudness): music sits under VO, sfx as designed
    music = music * db(0.0)
    music_d = duck(vo, music, -4.5)
    mix = vo + music_d + sfx
    tmp = os.path.join(BUILD, "mix_pre.wav")
    write(tmp, mix * 0.5)
    li, tp = loudness(tmp)
    li += 6.02
    tp += 6.02
    gain = -16.0 - li
    print(f"  pre-norm: {li:.1f} LUFS, TP {tp:.1f} dBTP -> gain {gain:+.1f} dB")
    g = db(gain)
    vo, music_d, sfx, mix = vo * g, music_d * g, sfx * g, mix * g
    write(os.path.join(A_DIR, "MUSIC", "IAM_v01_TEMP_SCORE.wav"), music_d)
    write(os.path.join(A_DIR, "SFX", "IAM_v01_SFX.wav"), sfx)
    write(os.path.join(A_DIR, "MIX", "IAM_v01_VO_STEM.wav"), vo)
    raw = os.path.join(BUILD, "mix_gained.wav")
    wavfile.write(raw, SR, mix.astype(np.float32))  # float: no clipping before the limiter
    final = os.path.join(A_DIR, "MIX", "IAM_v01_MIX.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af",
                    "aresample=192000,alimiter=limit=0.8:attack=2:release=80:level=false,aresample=48000",
                    "-c:a", "pcm_s24le", "-ar", str(SR), final],
                   check=True)
    li, tp = loudness(final)
    print(f"  final mix: {li:.1f} LUFS integrated, {tp:.1f} dBTP")


if __name__ == "__main__":
    main()
