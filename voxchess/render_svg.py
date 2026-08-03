"""SVG emitter. One <symbol> per (piece, color) and one <use> per occupied square.

No dither: Bayer patterns exist in the raster renderer; here they are omitted
on purpose to keep the file small and the DOM flat.
"""
from __future__ import annotations

from . import grid as G
from . import modes as M
from .board import BoardLayout
from .color import Palette, to_hex

SHORT = {"pawn": "p", "rook": "r", "knight": "n",
         "bishop": "b", "queen": "q", "king": "k"}


def _pts(poly, dx=0, dy=0):
    return " ".join(f"{int(round(x + dx))},{int(round(y + dy))}" for x, y in poly)


def render_svg(layout: BoardLayout, palette: Palette, models: dict, pieces,
               mode: str = "solid", crisp: bool = True) -> str:
    L, P = layout, palette
    max_h = max(g.shape[2] for g in models.values())
    x0, y0, x1, y1 = L.bounds(max_h)
    pad = L.voxel * 2
    vx, vy = int(x0 - pad), int(y0 - pad)
    vw, vh = int(x1 - x0 + 2 * pad), int(y1 - y0 + 2 * pad)

    classes, out = {}, []

    def cls(color):
        key = to_hex(color)
        if key not in classes:
            classes[key] = f"c{len(classes)}"
        return classes[key]

    body = []
    # --- symbols
    defs = []
    counts = {}
    for name, grid in models.items():
        for side in ("l", "d"):
            geo = M.build(G.orient(grid, side), L.proj, P.piece(side), mode, quantize=P.q)
            counts[(name, side)] = len(geo)
            frag = [f'<g id="{SHORT[name]}{side}">']
            for fill, stroke, poly in geo:
                if fill is None:
                    frag.append(f'<polygon class="{cls(stroke)}" fill="none" '
                                f'stroke="{to_hex(stroke)}" points="{_pts(poly)}"/>')
                else:
                    frag.append(f'<polygon class="{cls(fill)}" points="{_pts(poly)}"/>')
            frag.append("</g>")
            defs.append("".join(frag))

    # --- frame
    if L.frame:
        for gx, gy in sorted([(a, b) for b in range(0, L.side, L.frame)
                              for a in range(0, L.side, L.frame)
                              if not (L.frame <= a < L.side - L.frame
                                      and L.frame <= b < L.side - L.frame)], key=sum):
            body.append(_slab(L, P.border, gx, gy, L.frame, cls))

    # --- squares
    for bx, by in sorted([(a, b) for b in range(L.n) for a in range(L.n)], key=sum):
        gx, gy = L.square_origin(bx, by)
        body.append(_slab(L, P.square((bx + by) % 2 == 0), gx, gy, L.square, cls))

    # --- pieces
    for bx, by, name, side in sorted(pieces, key=lambda p: p[0] + p[1]):
        gx, gy = L.piece_origin(bx, by)
        dx, dy = L.proj.lattice(gx, gy, L.slab)
        body.append(f'<use href="#{SHORT[name]}{side}" '
                    f'x="{int(round(dx))}" y="{int(round(dy))}"/>')

    style = "".join(f".{v}{{fill:{k}}}" for k, v in classes.items())
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx} {vy} {vw} {vh}" '
               f'width="{vw}" height="{vh}"'
               + (' shape-rendering="crispEdges"' if crisp else "") + ">")
    out.append(f"<style>{style}.bg{{fill:{to_hex(P.background)}}}</style>")
    out.append(f'<rect class="bg" x="{vx}" y="{vy}" width="{vw}" height="{vh}"/>')
    out.append("<defs>" + "".join(defs) + "</defs>")
    out += body
    out.append("</svg>")
    render_svg.last_counts = counts
    return "\n".join(out)


def _slab(L, triad, gx, gy, size, cls):
    p = L.proj
    top = [p.lattice(gx, gy, 0), p.lattice(gx + size, gy, 0),
           p.lattice(gx + size, gy + size, 0), p.lattice(gx, gy + size, 0)]
    left = [p.lattice(gx, gy + size, 0), p.lattice(gx + size, gy + size, 0),
            p.lattice(gx + size, gy + size, -L.slab), p.lattice(gx, gy + size, -L.slab)]
    right = [p.lattice(gx + size, gy + size, 0), p.lattice(gx + size, gy, 0),
             p.lattice(gx + size, gy, -L.slab), p.lattice(gx + size, gy + size, -L.slab)]
    return (f'<polygon class="{cls(triad[1])}" points="{_pts(left)}"/>'
            f'<polygon class="{cls(triad[2])}" points="{_pts(right)}"/>'
            f'<polygon class="{cls(triad[0])}" points="{_pts(top)}"/>')
