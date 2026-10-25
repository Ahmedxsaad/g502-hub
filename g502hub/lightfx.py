"""Color maths for the live lighting effects: screen sampling, audio, waves.

Colors are (r, g, b) floats in 0..1; `to_rgb8` converts for the mouse.
"""

import colorsys
from math import cos, pi

import numpy as np

# Screen areas as (x, y, w, h) fractions of the screen
AREAS = {
    "screen": (0.0, 0.0, 1.0, 1.0),
    "center": (0.2, 0.15, 0.6, 0.7),
    "left": (0.0, 0.0, 0.33, 1.0),
    "right": (0.67, 0.0, 0.33, 1.0),
    "top": (0.0, 0.0, 1.0, 0.33),
    "bottom": (0.0, 0.67, 1.0, 0.33),
}
AREA_LABELS = {"screen": "Whole screen", "center": "Center (video)", "left": "Left edge",
               "right": "Right edge", "top": "Top edge", "bottom": "Bottom edge"}

OFF = (0.0, 0.0, 0.0)


def region(frame, area):
    """The pixels of one screen area of an (h, w, 3) uint8 frame, as an (n, 3) float array."""
    h, w = frame.shape[:2]
    x, y, aw, ah = AREAS[area]
    x0, y0 = int(x * w), int(y * h)
    x1, y1 = max(int((x + aw) * w), x0 + 1), max(int((y + ah) * h), y0 + 1)
    return frame[y0:y1, x0:x1].reshape(-1, 3).astype(np.float32) / 255


def sample(frame, area="screen", vivid=True):
    """The color an area of the screen 'looks like'.

    Average is the plain mean. Vivid weights saturated, bright pixels so a
    film's colored light wins over dark or grey surroundings, while the
    brightness still follows the scene so dark scenes stay dim.
    """
    px = region(frame, area)
    if not vivid:
        return tuple(float(c) for c in px.mean(0))
    mx, mn = px.max(1), px.min(1)
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    weight = sat ** 2 * mx ** 2 + 1e-4
    color = (px * weight[:, None]).sum(0) / weight.sum()
    peak = float(color.max())
    if peak < 1e-4:
        return OFF
    scene = float(np.sqrt((mx ** 2).mean()))  # bright highlights count more than black bars
    level = min(1.0, 0.15 + scene * 1.6)
    return tuple(float(c) / peak * level for c in color)


def _hues(px):
    """Hue 0..1, saturation and value of an (n, 3) float array."""
    mx, mn = px.max(1), px.min(1)
    c = mx - mn
    r, g, b = px.T
    h = np.zeros_like(mx)
    m = c > 1e-6
    rm = m & (mx == r)
    gm = m & (mx == g) & ~rm
    bm = m & ~rm & ~gm
    h[rm] = ((g - b)[rm] / c[rm]) % 6
    h[gm] = (b - r)[gm] / c[gm] + 2
    h[bm] = (r - g)[bm] / c[bm] + 4
    return h / 6, np.where(mx > 0, c / np.maximum(mx, 1e-6), 0), mx


def palette(frame, n=2, bins=36):
    """The n most prominent vivid colors of an image, in distinct hues, at full brightness.

    For cover-art lighting. Grey art gives white; fewer distinct hues than n repeat the first.
    """
    px = frame.reshape(-1, 3).astype(np.float32) / 255
    hue, sat, val = _hues(px)
    weight = sat ** 2 * val
    if weight.sum() < 1e-3 * len(px):
        return [(1.0, 1.0, 1.0)] * n
    idx = np.minimum((hue * bins).astype(int), bins - 1)
    hist = np.bincount(idx, weights=weight, minlength=bins)
    hist = hist + 0.5 * (np.roll(hist, 1) + np.roll(hist, -1))  # circular smoothing
    out = []
    for _ in range(n):
        peak = int(np.argmax(hist))
        if hist[peak] <= 0:
            break
        near = np.abs((idx - peak + bins // 2) % bins - bins // 2) <= 1
        w = weight * near
        color = (px * w[:, None]).sum(0) / max(float(w.sum()), 1e-6)
        out.append(tuple(float(c) / max(float(color.max()), 1e-6) for c in color))
        for d in range(-3, 4):  # keep the next color a clearly different hue
            hist[(peak + d) % bins] = 0
    return (out + [out[0]] * n)[:n] if out else [(1.0, 1.0, 1.0)] * n


def adjust(rgb, saturation=1.0, brightness=1.0):
    """Scale saturation and brightness (both multipliers, results clipped to 0..1)."""
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    return colorsys.hsv_to_rgb(h, min(1.0, s * saturation), min(1.0, v * brightness))


def smooth(previous, target, response):
    """Move `previous` toward `target`; response 1 = jump, near 0 = very smooth."""
    if previous is None:
        return target
    return tuple(p + (t - p) * response for p, t in zip(previous, target))


def wave(t, period_s, zone, saturation=1.0, brightness=1.0, reverse=False):
    """A hue wave travelling from the DPI lights (zone 0) to the logo (zone 1)."""
    lag = 0.18 * (1 - zone if reverse else zone)
    return colorsys.hsv_to_rgb((t / max(period_s, 0.1) - lag) % 1.0, saturation, brightness)


def scale(rgb, amount):
    return tuple(c * amount for c in rgb)


def breathe(rgb, t, period_s):
    """Fade a color in and out, never quite to black."""
    phase = (1 - cos(2 * pi * t / max(period_s, 0.1))) / 2
    return scale(rgb, 0.06 + 0.94 * phase)


def audio_pulse(levels, rgb, sensitivity=1.0):
    """Both zones in one color, brightness kicking with the bass."""
    if levels is None:
        return {0: OFF, 1: OFF}
    amount = min(1.0, max(levels.bass, levels.level * 0.6) * sensitivity) ** 1.6
    return {0: scale(rgb, min(1.0, amount * 1.1)), 1: scale(rgb, amount)}


def audio_spectrum(levels, sensitivity=1.0):
    """Logo follows the bass, DPI lights the treble; hue moves with the sound's pitch."""
    if levels is None:
        return {0: OFF, 1: OFF}
    hue = 0.66 - 0.66 * levels.centroid  # low = blue, high = red
    bass = min(1.0, levels.bass * sensitivity) ** 1.5
    treble = min(1.0, max(levels.treble, levels.mid * 0.7) * sensitivity) ** 1.5
    return {0: colorsys.hsv_to_rgb((hue + 0.12) % 1.0, 1.0, treble),
            1: colorsys.hsv_to_rgb(hue % 1.0, 1.0, bass)}


class BeatRainbow:
    """The hue jumps around the color wheel on every beat; brightness follows loudness."""

    def __init__(self):
        self.hue = 0.0

    def __call__(self, levels, sensitivity=1.0):
        if levels is None:
            return {0: OFF, 1: OFF}
        if levels.beat:
            self.hue = (self.hue + 0.17) % 1.0
        amount = min(1.0, max(levels.bass, levels.level) * sensitivity) ** 1.3
        return {0: colorsys.hsv_to_rgb((self.hue + 0.5) % 1.0, 1.0, amount),
                1: colorsys.hsv_to_rgb(self.hue, 1.0, amount)}


def to_rgb8(rgb):
    return tuple(int(min(max(c, 0.0), 1.0) * 255 + 0.5) for c in rgb)


def hex_to_rgb(text):
    text = text.lstrip("#")
    return tuple(int(text[i:i + 2], 16) / 255 for i in (0, 2, 4))
