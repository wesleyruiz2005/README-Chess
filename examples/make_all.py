#!/usr/bin/env python3
"""Generates every deliverable of the project. Equivalent to the README's
command sequence, but from the API instead of the CLI."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voxchess import (BoardLayout, Effects, MODES, MoveAnim, Palette, Scene,
                      START_FEN, THEMES, animate_move, parse_fen,
                      random_position, render_svg, save_gif, upscale, vox)

OUT = Path(__file__).resolve().parent.parent / "out"
OUT.mkdir(exist_ok=True)
MODELS = vox.load_set(Path(__file__).resolve().parent.parent / "models")
SIZE = max(g.shape[0] for g in MODELS.values())

board = random_position(plies=28, seed=7)
pieces = parse_fen(board.fen())
print("FEN:", board.fen())

# 1 — raster board with effects, one file per theme
raster = BoardLayout(voxel=4, square=14, frame=3, slab=4, piece_size=SIZE)
for theme in THEMES:
    pal = Palette(theme, "12bit")
    scene = Scene(raster, pal, MODELS, "solid", Effects())
    img = upscale(scene.render(pieces), 2)
    img.save(OUT / f"board-{theme}@2x.png")
    print(f"  board-{theme}@2x.png  {img.size}")

# 2 — variant normalized to 8 bits (RGB332)
pal = Palette("acero", "12bit")
scene = Scene(raster, pal, MODELS, "solid", Effects())
scene.render(pieces, quantize="8bit").save(OUT / "board-acero-8bit.png")

# 3 — SVG without effects, maximum resolution
flat = BoardLayout(voxel=16, square=11, frame=0, slab=2, piece_size=SIZE)
svg = render_svg(flat, Palette("acero", "12bit"), MODELS, pieces, "solid")
(OUT / "board-flat.svg").write_text(svg)
print(f"  board-flat.svg  {len(svg)} bytes")

# 4 — knight jump GIF, one file per theme + one at 8 bits
anim = MoveAnim(frames=22, arc=13)
for theme in THEMES:
    scene = Scene(raster, Palette(theme, "12bit"), MODELS, "solid", Effects())
    frames, durs = animate_move(scene, pieces, "e2", "f4", anim=anim)
    n = save_gif(OUT / f"knight-{theme}.gif", frames, durs)
    print(f"  knight-{theme}.gif  {n} colors")

scene = Scene(raster, Palette("acero", "12bit"), MODELS, "solid", Effects())
frames, durs = animate_move(scene, pieces, "e2", "f4", anim=anim, quantize="8bit")
save_gif(OUT / "knight-acero-8bit.gif", frames, durs)

# 5 — the same board in every render mode (white vs rotated black)
start = parse_fen(START_FEN)
for mode in MODES:
    scene = Scene(raster, Palette("acero", "12bit"), MODELS, mode, Effects())
    img = upscale(scene.render(start), 2)
    img.save(OUT / f"mode-{mode}@2x.png")
    print(f"  mode-{mode}@2x.png  {img.size}")

# 6 — several moves from the starting position (origin always occupied)
scene = Scene(raster, Palette("fosforo", "12bit"), MODELS, "solid", Effects())
for name, frm, to in (("knight", "g1", "f3"), ("pawn", "e2", "e4"),
                      ("queen", "d1", "d3"), ("bishop", "f1", "c4")):
    frames, durs = animate_move(scene, start, frm, to, anim=anim)
    n = save_gif(OUT / f"move-{name}-{frm}{to}.gif", frames, durs)
    print(f"  move-{name}-{frm}{to}.gif  {n} colors")

print("done ->", OUT)
