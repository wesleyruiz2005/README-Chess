"""Animation of a move and export to GIF."""
from __future__ import annotations
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image

from .board import square_to_board
from .render_png import Scene, upscale


@dataclass
class MoveAnim:
    frames: int = 22
    arc: int = 13              # jump height in voxels
    hold_start: int = 900      # ms
    hold_end: int = 1200       # ms
    frame_ms: int = 55
    easing: str = "smoothstep"  # smoothstep | linear


EASINGS = {
    "linear": lambda t: t,
    "smoothstep": lambda t: t * t * (3 - 2 * t),
}


def animate_move(scene: Scene, pieces, frm: str, to: str, *,
                 anim: MoveAnim = MoveAnim(), quantize: str = "none",
                 scale: int = 1):
    """pieces includes the moving piece; it is located by its origin square."""
    L = scene.L
    bx0, by0 = square_to_board(frm)
    bx1, by1 = square_to_board(to)

    moving = next((p for p in pieces if p[0] == bx0 and p[1] == by0), None)
    if moving is None:
        raise ValueError(f"no piece at {frm}")
    captured = [p for p in pieces if p[0] == bx1 and p[1] == by1]
    rest = [p for p in pieces if p is not moving and p not in captured]
    after = rest + [(bx1, by1, moving[2], moving[3])]

    gx0, gy0 = L.piece_origin(bx0, by0)
    gx1, gy1 = L.piece_origin(bx1, by1)
    ease = EASINGS[anim.easing]

    frames = [scene.render(pieces, quantize=quantize)]
    durations = [anim.hold_start]
    for i in range(1, anim.frames):
        t = i / (anim.frames - 1)
        e = ease(t)
        frames.append(scene.render(
            rest,
            moving=(moving[2], moving[3],
                    round(gx0 + (gx1 - gx0) * e),
                    round(gy0 + (gy1 - gy0) * e),
                    L.slab + round(anim.arc * math.sin(math.pi * t))),
            quantize=quantize))
        durations.append(anim.frame_ms)
    frames.append(scene.render(after, quantize=quantize))
    durations.append(anim.hold_end)

    frames = _align(frames, scene.P.background)
    if scale > 1:
        frames = [upscale(f, scale) for f in frames]
    return frames, durations


def _align(frames, background):
    """All frames on the same canvas, anchored to the bottom and centered."""
    w = max(f.size[0] for f in frames)
    h = max(f.size[1] for f in frames)
    out = []
    for f in frames:
        c = Image.new("RGB", (w, h), background)
        c.paste(f, ((w - f.size[0]) // 2, h - f.size[1]))
        out.append(c)
    return out


def save_gif(path, frames, durations, colors: int = 32):
    """Palette shared by all frames and palette dithering DISABLED:
    dithering here would destroy the pixel art."""
    pal = frames[0].quantize(colors=colors, method=Image.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    q[0].save(path, save_all=True, append_images=q[1:], duration=durations,
              loop=0, optimize=True, disposal=2)
    unique = set()
    for f in frames:
        unique |= set(map(tuple, np.unique(np.array(f).reshape(-1, 3), axis=0)))
    return len(unique)
