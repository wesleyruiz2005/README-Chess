"""Render modes for a voxel model.

Each mode returns a list of (color, polygon) already in draw order.
They work in pixel coordinates relative to the model's lattice origin (0,0,0);
the caller only has to translate them.

  solid     one cube per visible voxel, three tones by orientation.
            Exact painter's order. The correct default mode.
  greedy    coplanar faces merged into rectangles. Far fewer polygons,
            but DESTROYS painter's order: only valid for models without
            self-occlusion (convex) or for flat surfaces.
  flat      solid single-color silhouette. The cheapest; useful as fallback.
  top       tops only. Plan reading, good for debugging profiles.
  layers    each Z level with its own tint. Design view.
  wire      outline of each visible face, no fill.
  ascii     does not draw: returns the text dump (see vox.dump_ascii).
"""
from __future__ import annotations
import numpy as np

from . import grid as G
from .color import to_oklch, clamp_chroma

MODES = ("solid", "greedy", "flat", "top", "layers", "wire")


def _shift(poly, dx, dy):
    return [(x + dx, y + dy) for x, y in poly]


def build(model: np.ndarray, proj, triad, mode: str = "solid", *,
          cull_camera: bool = True, quantize=lambda c: c):
    """-> [(fill, stroke, polygon)]; stroke is None except in 'wire'."""
    if mode == "solid":
        out = []
        for x, y, z, top, left, right in G.painter_order(model, cull_camera):
            if left:
                out.append((triad[1], None, proj.left(x, y, z)))
            if right:
                out.append((triad[2], None, proj.right(x, y, z)))
            if top:
                out.append((triad[0], None, proj.top(x, y, z)))
        return out

    if mode == "greedy":
        order = {"l": 0, "r": 1, "t": 2}
        faces = sorted(G.greedy_faces(model), key=lambda f: order[f[0]])
        return [(triad[order[k]], None, proj.rect(k, a, b)) for k, a, b in faces]

    if mode == "top":
        out = []
        for x, y, z, top, _, _ in G.painter_order(model, cull_camera):
            if top:
                out.append((triad[0], None, proj.top(x, y, z)))
        return out

    if mode == "flat":
        out = []
        for x, y, z, top, left, right in G.painter_order(model, cull_camera):
            for flag, face in ((left, proj.left), (right, proj.right), (top, proj.top)):
                if flag:
                    out.append((triad[1], None, face(x, y, z)))
        return out

    if mode == "layers":
        nz = model.shape[2]
        L, C, h = to_oklch(triad[0])
        tints = [quantize(clamp_chroma(0.35 + 0.55 * (z / max(1, nz - 1)), C, h))
                 for z in range(nz)]
        out = []
        for x, y, z, top, left, right in G.painter_order(model, cull_camera):
            c = tints[z]
            dark = quantize(clamp_chroma(to_oklch(c)[0] * 0.72, C, h))
            if left:
                out.append((dark, None, proj.left(x, y, z)))
            if right:
                out.append((dark, None, proj.right(x, y, z)))
            if top:
                out.append((c, None, proj.top(x, y, z)))
        return out

    if mode == "wire":
        out = []
        for x, y, z, top, left, right in G.painter_order(model, cull_camera):
            for flag, face in ((left, proj.left), (right, proj.right), (top, proj.top)):
                if flag:
                    out.append((None, triad[0], face(x, y, z)))
        return out

    raise ValueError(f"unknown mode: {mode!r}. Available: {MODES}")


def cost(model: np.ndarray, mode: str) -> int:
    """Polygons each mode produces, for budgeting the SVG."""
    if mode == "greedy":
        return G.n_greedy(model)
    if mode == "top":
        return int(G.face_masks(model)["t"].sum())
    return sum(1 for x, y, z, t, l, r in G.painter_order(model)
               for f in (t, l, r) if f)
