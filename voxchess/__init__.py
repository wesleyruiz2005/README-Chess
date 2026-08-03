"""voxchess — isometric voxel chess for READMEs: PNG, SVG and GIF."""
__version__ = "1.0.0"

from .board import BoardLayout, parse_fen, random_position, START_FEN
from .color import Palette, THEMES, QUANTIZERS
from .iso import Projection
from .modes import MODES, build, cost
from .render_png import Effects, Scene, upscale
from .render_svg import render_svg
from .animate import MoveAnim, animate_move, save_gif
from . import vox, grid

__all__ = ["BoardLayout", "parse_fen", "random_position", "START_FEN",
           "Palette", "THEMES", "QUANTIZERS", "Projection", "MODES", "build",
           "cost", "Effects", "Scene", "upscale", "render_svg", "MoveAnim",
           "animate_move", "save_gif", "vox", "grid"]
