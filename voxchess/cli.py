"""Command line interface.

  python -m voxchess board   --theme acero --out board.png
  python -m voxchess board   --format svg --mode greedy --out board.svg
  python -m voxchess animate --from e2 --to f4 --theme fosforo --out jump.gif
  python -m voxchess sheet   --mode layers --out modes.png
  python -m voxchess inspect --model models/king.vox
  python -m voxchess convert --model models/rook.vox --to txt
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from . import vox
from .animate import MoveAnim, animate_move, save_gif
from .board import BoardLayout, START_FEN, parse_fen, random_position
from .color import Palette, THEMES, QUANTIZERS
from .grid import metrics
from .modes import MODES, cost
from .render_png import Effects, Scene, upscale
from .render_svg import render_svg

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODELS = ROOT / "models"


def common(p):
    p.add_argument("--models", default=str(DEFAULT_MODELS), help="models directory")
    p.add_argument("--theme", default="acero", choices=list(THEMES))
    p.add_argument("--quantize", default="12bit", choices=list(QUANTIZERS),
                   help="palette color normalization")
    p.add_argument("--post-quantize", default="none", choices=list(QUANTIZERS),
                   help="normalization applied to the final image (e.g. 8bit = RGB332)")
    p.add_argument("--mode", default="solid", choices=list(MODES))
    p.add_argument("--voxel", type=int, default=4, help="voxel width in px (even)")
    p.add_argument("--square", type=int, default=14, help="voxels per square")
    p.add_argument("--frame", type=int, default=3)
    p.add_argument("--slab", type=int, default=4)
    p.add_argument("--scale", type=int, default=1, help="integer NEAREST scaling")
    p.add_argument("--no-shadows", action="store_true")
    p.add_argument("--no-grain", action="store_true")


def make(args):
    models = vox.load_set(args.models)
    layout = BoardLayout(voxel=args.voxel, square=args.square,
                         frame=args.frame, slab=args.slab,
                         piece_size=max(g.shape[0] for g in models.values()))
    palette = Palette(args.theme, args.quantize)
    fx = Effects(shadows=not args.no_shadows, grain=not args.no_grain)
    return models, layout, palette, Scene(layout, palette, models, args.mode, fx)


def positions(args, models):
    if getattr(args, "random", False):
        board = random_position(args.plies, args.seed)
        print("FEN:", board.fen(), file=sys.stderr)
        return parse_fen(board.fen())
    return parse_fen(args.fen)


# ------------------------------------------------------------------ commands
def cmd_board(args):
    models, layout, palette, scene = make(args)
    pieces = positions(args, models)
    if args.format == "svg":
        svg = render_svg(layout, palette, models, pieces, args.mode)
        Path(args.out).write_text(svg)
        print(f"{args.out}  {len(svg)} bytes  "
              f"{sum(render_svg.last_counts.values())} polygons in <defs>")
    else:
        img = upscale(scene.render(pieces, quantize=args.post_quantize), args.scale)
        img.save(args.out)
        print(f"{args.out}  {img.size[0]}x{img.size[1]}")
    print("occlusion:", round(layout.occlusion_rows(
        max(g.shape[2] for g in models.values())), 2), "rows")
    for k, v in palette.contrast_report().items():
        print(f"  contrast {k:32s} {v}")


def cmd_animate(args):
    models, layout, palette, scene = make(args)
    pieces = positions(args, models)
    anim = MoveAnim(frames=args.frames, arc=args.arc, frame_ms=args.frame_ms,
                    hold_start=args.hold_start, hold_end=args.hold_end,
                    easing=args.easing)
    frames, durs = animate_move(scene, pieces, args.frm, args.to, anim=anim,
                                quantize=args.post_quantize, scale=args.scale)
    n = save_gif(args.out, frames, durs, colors=args.colors)
    print(f"{args.out}  {len(frames)} frames  {frames[0].size[0]}x{frames[0].size[1]}  "
          f"{n} colors  {Path(args.out).stat().st_size} bytes")


def cmd_sheet(args):
    """A sheet with the same model in every render mode."""
    from PIL import Image, ImageDraw, ImageFont
    from .iso import Projection
    from . import modes as M
    models = vox.load_set(args.models)
    palette = Palette(args.theme, args.quantize)
    proj = Projection(args.voxel)
    names = list(models)
    cells = []
    for mode in MODES:
        for name in names:
            geo = M.build(models[name], proj, palette.piece("l"), mode,
                          quantize=palette.q)
            xs = [p[0] for _, _, poly in geo for p in poly]
            ys = [p[1] for _, _, poly in geo for p in poly]
            cells.append((mode, name, geo, min(xs), min(ys), max(xs), max(ys)))
    cw = int(max(c[5] - c[3] for c in cells)) + 16
    ch = int(max(c[6] - c[4] for c in cells)) + 16
    img = Image.new("RGB", (cw * len(names) + 120, (ch + 26) * len(MODES) + 20),
                    palette.background)
    dr = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    for i, (mode, name, geo, mnx, mny, *_ ) in enumerate(cells):
        r, c = divmod(i, len(names))
        ox = 120 + c * cw - mnx + 8
        oy = 20 + r * (ch + 26) - mny + 8
        for fill, stroke, poly in geo:
            dr.polygon([(x + ox, y + oy) for x, y in poly], fill=fill, outline=stroke)
        if c == 0:
            dr.text((8, 20 + r * (ch + 26) + ch // 2), mode, font=font, fill="#EEEEEE")
    img = upscale(img, args.scale)
    img.save(args.out)
    print(f"{args.out}  {img.size[0]}x{img.size[1]}")
    print(f"{'mode':10s} " + " ".join(f"{n[:6]:>7s}" for n in names))
    for mode in MODES:
        print(f"{mode:10s} " + " ".join(f"{cost(models[n], mode):7d}" for n in names))


def cmd_inspect(args):
    grid, _ = vox.load_vox(args.model)
    print(json.dumps(metrics(grid), indent=2))


def cmd_convert(args):
    grid, _ = vox.load_vox(args.model)
    stem = Path(args.model).with_suffix("")
    if args.to == "txt":
        out = stem.with_suffix(".txt")
        out.write_text(vox.dump_ascii(grid))
    elif args.to == "json":
        out = stem.with_suffix(".json")
        out.write_text(json.dumps(vox.to_rle(grid), separators=(",", ":")))
    else:
        raise SystemExit("--to must be txt or json")
    print(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="voxchess", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("board", help="render a position")
    common(b)
    b.add_argument("--fen", default=START_FEN)
    b.add_argument("--random", action="store_true")
    b.add_argument("--plies", type=int, default=28)
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--format", default="png", choices=["png", "svg"])
    b.add_argument("--out", default="board.png")
    b.set_defaults(func=cmd_board)

    a = sub.add_parser("animate", help="animate a move and export a GIF")
    common(a)
    a.add_argument("--fen", default=START_FEN)
    a.add_argument("--random", action="store_true")
    a.add_argument("--plies", type=int, default=28)
    a.add_argument("--seed", type=int, default=7)
    a.add_argument("--from", dest="frm", required=True)
    a.add_argument("--to", dest="to", required=True)
    a.add_argument("--frames", type=int, default=22)
    a.add_argument("--arc", type=int, default=13)
    a.add_argument("--frame-ms", type=int, default=55)
    a.add_argument("--hold-start", type=int, default=900)
    a.add_argument("--hold-end", type=int, default=1200)
    a.add_argument("--easing", default="smoothstep", choices=["smoothstep", "linear"])
    a.add_argument("--colors", type=int, default=32)
    a.add_argument("--out", default="move.gif")
    a.set_defaults(func=cmd_animate)

    s = sub.add_parser("sheet", help="comparison sheet of render modes")
    common(s)
    s.add_argument("--out", default="modes.png")
    s.set_defaults(func=cmd_sheet)

    i = sub.add_parser("inspect", help="metrics of a model")
    i.add_argument("--model", required=True)
    i.set_defaults(func=cmd_inspect)

    c = sub.add_parser("convert", help="convert a .vox to txt or json")
    c.add_argument("--model", required=True)
    c.add_argument("--to", required=True, choices=["txt", "json"])
    c.set_defaults(func=cmd_convert)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
