"""Color system: OKLCH, per-material luminance bands, themes, retro
quantization and Bayer dithering.

Core rule: luminance is fixed by face ORIENTATION and material BAND; hue only
disambiguates. This way the volume reads the same across all themes and
contrast is measurable, not aesthetic.
"""
from __future__ import annotations
import math

import numpy as np

# ------------------------------------------------------------ sRGB <-> OKLCH
def _s2l(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _l2s(c: float) -> float:
    v = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
    return max(0.0, min(1.0, v)) * 255.0


def to_oklch(rgb) -> tuple[float, float, float]:
    r, g, b = (_s2l(float(v)) for v in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, math.hypot(a, bb), math.atan2(bb, a)


def to_rgb(L: float, C: float, h: float) -> tuple[float, float, float]:
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (_l2s(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
            _l2s(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
            _l2s(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s))


def in_gamut(L: float, C: float, h: float) -> bool:
    return all(0 <= v <= 255 for v in to_rgb(L, C, h))


def clamp_chroma(L: float, C: float, h: float, steps: int = 20):
    lo, hi = 0.0, C
    for _ in range(steps):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if in_gamut(L, mid, h) else (lo, mid)
    return to_rgb(L, lo, h)


# ------------------------------------------------------------- quantization
def quantize_none(c):
    return tuple(int(round(max(0, min(255, v)))) for v in c)


def quantize_12bit(c):
    """4 bits per channel (Amiga OCS). Every channel a multiple of 0x11."""
    return tuple(int(round(max(0, min(255, v)) / 17.0)) * 17 for v in c)


def quantize_8bit(c):
    """RGB332: 3 bits R, 3 G, 2 B. Bit-replication reconstruction."""
    r, g, b = (int(round(max(0, min(255, v)))) for v in c)
    r, g, b = r >> 5, g >> 5, b >> 6
    return ((r << 5) | (r << 2) | (r >> 1),
            (g << 5) | (g << 2) | (g >> 1),
            (b << 6) | (b << 4) | (b << 2) | b)


QUANTIZERS = {"none": quantize_none, "12bit": quantize_12bit, "8bit": quantize_8bit}


def quantize_image(img, mode: str):
    """Applies quantization to a whole PIL image (vectorized)."""
    if mode == "none":
        return img
    a = np.array(img).astype(np.uint16)
    out = np.empty_like(a, dtype=np.uint8)
    if mode == "12bit":
        out[:] = np.clip(np.round(a / 17.0), 0, 15).astype(np.uint8) * 17
    elif mode == "8bit":
        r, g, b = a[..., 0] >> 5, a[..., 1] >> 5, a[..., 2] >> 6
        out[..., 0] = (r << 5) | (r << 2) | (r >> 1)
        out[..., 1] = (g << 5) | (g << 2) | (g >> 1)
        out[..., 2] = (b << 6) | (b << 4) | (b << 2) | b
    else:
        raise ValueError(f"unknown quantization: {mode}")
    from PIL import Image
    return Image.fromarray(out)


# -------------------------------------------------------------------- themes
hexa = lambda s: tuple(int(s.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
to_hex = lambda c: "#%02X%02X%02X" % tuple(int(v) for v in c)

#: luminance (top, left, right) per material.
#: The bands do not overlap: piece_light > square_light > square_dark > piece_dark.
BANDS = {
    "square_light": (0.76, 0.64, 0.56),
    "square_dark":  (0.56, 0.46, 0.40),
    "piece_light":  (0.91, 0.75, 0.63),
    "piece_dark":   (0.40, 0.30, 0.24),
    "border":       (0.46, 0.38, 0.32),
}

THEMES = {
    "acero": dict(square_light="#AABBCC", square_dark="#667788",
                  piece_light="#EEEECC", piece_dark="#553344",
                  border="#445566", shadow="#334455", background="#223344"),
    "ambar": dict(square_light="#DDBB88", square_dark="#AA7755",
                  piece_light="#EEDDCC", piece_dark="#443355",
                  border="#775533", shadow="#664433", background="#332222"),
    "fosforo": dict(square_light="#99BB88", square_dark="#558855",
                    piece_light="#DDFFCC", piece_dark="#224433",
                    border="#336644", shadow="#224433", background="#112211"),
    "magenta": dict(square_light="#CCAABB", square_dark="#886677",
                    piece_light="#FFEEDD", piece_dark="#334466",
                    border="#664455", shadow="#443355", background="#221133"),
}


class Palette:
    """Resolved and quantized face triads for a theme."""

    def __init__(self, theme="acero", quantize="12bit", bands=None):
        spec = THEMES[theme] if isinstance(theme, str) else dict(theme)
        self.name = theme if isinstance(theme, str) else "custom"
        self.quantize = quantize
        self.q = QUANTIZERS[quantize]
        bands = bands or BANDS
        for key, band in bands.items():
            setattr(self, key, self._triad(spec[key], band))
        self.shadow = self.q(hexa(spec["shadow"]))
        self.background = self.q(hexa(spec["background"]))

    def _triad(self, base_hex, band):
        L, C, h = to_oklch(hexa(base_hex))
        return [self.q(clamp_chroma(l, C, h)) for l in band]

    def piece(self, side: str):
        return self.piece_light if side == "l" else self.piece_dark

    def square(self, light: bool):
        return self.square_light if light else self.square_dark

    def grain(self, triad, factor: float = 0.955):
        L, C, h = to_oklch(triad[0])
        return self.q(clamp_chroma(L * factor, C, h))

    def contrast_report(self) -> dict:
        Lo = lambda c: to_oklch(c)[0]
        pairs = {
            "light piece / light square":   (self.piece_light[0], self.square_light[0]),
            "light piece / dark square":  (self.piece_light[0], self.square_dark[0]),
            "dark piece / light square":  (self.piece_dark[0], self.square_light[0]),
            "dark piece / dark square": (self.piece_dark[0], self.square_dark[0]),
            "light piece / dark piece":    (self.piece_light[0], self.piece_dark[0]),
            "light square / dark square": (self.square_light[0], self.square_dark[0]),
        }
        return {k: round(abs(Lo(a) - Lo(b)), 3) for k, (a, b) in pairs.items()}


# -------------------------------------------------------------------- dither
BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]])


def bayer(x: int, y: int, density: float) -> bool:
    """Anchored to the image's global grid, not the object: this keeps the
    pattern aligned as in a real framebuffer (equivalent to patternUnits
    userSpaceOnUse in SVG)."""
    return density > (BAYER4[y % 4][x % 4] + 0.5) / 16.0
