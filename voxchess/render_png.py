"""Raster renderer (PIL). Optional dither effects."""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from . import grid as G
from . import modes as M
from .board import BoardLayout
from .color import Palette, bayer, quantize_image


@dataclass
class Effects:
    shadows: bool = True        # dithered shadow under each piece
    grain: bool = True          # dithered grain on the squares
    shadow_density: float = 0.55
    grain_density: float = 0.09


NO_EFFECTS = Effects(shadows=False, grain=False)


class Scene:
    def __init__(self, layout: BoardLayout, palette: Palette, models: dict,
                 mode: str = "solid", effects: Effects = Effects()):
        self.L, self.P, self.models = layout, palette, models
        self.mode, self.fx = mode, effects
        self.max_h = max(g.shape[2] for g in models.values())
        self._cache: dict[tuple[str, str], list] = {}

    # ------------------------------------------------------------ internal
    def _geometry(self, name: str, side: str):
        key = (name, side)
        if key not in self._cache:
            self._cache[key] = M.build(G.orient(self.models[name], side),
                                       self.L.proj, self.P.piece(side), self.mode,
                                       quantize=self.P.q)
        return self._cache[key]

    def _canvas(self):
        x0, y0, x1, y1 = self.L.bounds(self.max_h)
        pad = self.L.voxel * 3
        w, h = int(x1 - x0 + 2 * pad), int(y1 - y0 + 2 * pad)
        img = Image.new("RGB", (w, h), self.P.background)
        return img, (-x0 + pad, -y0 + pad)

    def _cube(self, dr, cx, cy, triad, w, h, d):
        T = (cx, cy); R = (cx + w / 2, cy + h / 2)
        B = (cx, cy + h); L = (cx - w / 2, cy + h / 2)
        dr.polygon([L, B, (B[0], B[1] + d), (L[0], L[1] + d)], fill=triad[1])
        dr.polygon([B, R, (R[0], R[1] + d), (B[0], B[1] + d)], fill=triad[2])
        dr.polygon([T, R, B, L], fill=triad[0])

    def _dither(self, img, poly, ca, cb, density):
        mask = Image.new("1", img.size, 0)
        ImageDraw.Draw(mask).polygon(poly, fill=1)
        px, mk = img.load(), mask.load()
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        for y in range(max(0, int(min(ys))), min(img.size[1], int(max(ys)) + 1)):
            for x in range(max(0, int(min(xs))), min(img.size[0], int(max(xs)) + 1)):
                if mk[x, y]:
                    px[x, y] = ca if bayer(x, y, density) else cb

    def _shadow(self, img, gx, gy, bx, by, lift=0.0):
        L, P = self.L, self.P
        half = L.piece_size / 2
        cx, cy = L.proj.lattice(gx + half, gy + half, 0)
        cx += self.off[0]; cy += self.off[1]
        pal = P.square((bx + by) % 2 == 0)
        k = 1.0 - 0.45 * lift
        rx = (L.piece_size * L.voxel / 2 + 3) * k
        ry = (L.piece_size * L.proj.h / 2 + 2) * k
        self._dither(img, [(cx, cy - ry), (cx + rx, cy), (cx, cy + ry), (cx - rx, cy)],
                     P.shadow, pal[0], self.fx.shadow_density - 0.30 * lift)

    # -------------------------------------------------------------- public
    def render(self, pieces, moving=None, quantize: str = "none") -> Image.Image:
        """pieces: [(bx, by, name, side)]
        moving:  (name, side, gx, gy, gz) in lattice coordinates, for animation."""
        L, P = self.L, self.P
        img, self.off = self._canvas()
        dr = ImageDraw.Draw(img)
        ox, oy = self.off

        # frame
        if L.frame:
            cells = [(gx, gy) for gy in range(0, L.side, L.frame)
                     for gx in range(0, L.side, L.frame)
                     if not (L.frame <= gx < L.side - L.frame
                             and L.frame <= gy < L.side - L.frame)]
            for gx, gy in sorted(cells, key=sum):
                cx, cy = L.proj.lattice(gx, gy, 0)
                self._cube(dr, cx + ox, cy + oy, P.border,
                           L.frame * L.voxel, L.frame * L.proj.h, L.slab * L.proj.d)

        # squares
        for bx, by in sorted([(a, b) for b in range(L.n) for a in range(L.n)], key=sum):
            gx, gy = L.square_origin(bx, by)
            cx, cy = L.proj.lattice(gx, gy, 0)
            cx += ox; cy += oy
            pal = P.square((bx + by) % 2 == 0)
            self._cube(dr, cx, cy, pal, L.square * L.voxel,
                       L.square * L.proj.h, L.slab * L.proj.d)
            if self.fx.grain:
                w2, h2 = L.square * L.voxel / 2, L.square * L.proj.h
                self._dither(img, [(cx, cy), (cx + w2, cy + h2 / 2),
                                   (cx, cy + h2), (cx - w2, cy + h2 / 2)],
                             P.grain(pal), pal[0], self.fx.grain_density)

        # shadows
        if self.fx.shadows:
            for bx, by, *_ in pieces:
                self._shadow(img, *L.piece_origin(bx, by), bx, by)
            if moving:
                _, _, gx, gy, gz = moving
                lift = min(1.0, max(0.0, (gz - L.slab) / 12.0))
                bx = int((gx - L.frame) / L.square); by = int((gy - L.frame) / L.square)
                self._shadow(img, gx, gy, bx, by, lift=lift)

        # pieces, painter's order by square
        items = [(bx + by, (bx, by, name, side)) for bx, by, name, side in pieces]
        if moving:
            name, side, gx, gy, gz = moving
            items.append(((gx + gy) / L.square, ("move", name, side, gx, gy, gz)))
        for _, item in sorted(items, key=lambda t: t[0]):
            if item[0] == "move":
                _, name, side, gx, gy, gz = item
                base = gz
            else:
                bx, by, name, side = item
                gx, gy = L.piece_origin(bx, by)
                base = L.slab
            dx, dy = L.proj.lattice(gx, gy, base)
            for fill, stroke, poly in self._geometry(name, side):
                pts = [(x + dx + ox, y + dy + oy) for x, y in poly]
                dr.polygon(pts, fill=fill, outline=stroke)

        img = self._crop(img)
        return quantize_image(img, quantize) if quantize != "none" else img

    def _crop(self, img):
        a = np.array(img)
        nb = np.any(a != np.array(self.P.background), axis=-1)
        ys, xs = np.nonzero(nb)
        if len(xs) == 0:
            return img
        pad = 8
        return img.crop((max(0, xs.min() - pad), max(0, ys.min() - pad),
                         min(img.size[0], xs.max() + pad + 1),
                         min(img.size[1], ys.max() + pad + 1)))


def upscale(img, factor: int):
    """INTEGER scaling with NEAREST. Any other factor ruins the pixel art."""
    if factor == 1:
        return img
    return img.resize((img.size[0] * factor, img.size[1] * factor), Image.NEAREST)
