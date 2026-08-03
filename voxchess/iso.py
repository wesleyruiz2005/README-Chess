"""2:1 dimetric projection.

The voxel width must be EVEN: h = w/2 and d = w/2 must be integers so that
shape-rendering="crispEdges" and NEAREST scaling do not break the edges.
That quantizes the available scales to 2, 4, 6, 8, 12, 16...
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Projection:
    w: int = 8                      # voxel width

    def __post_init__(self):
        if self.w % 2:
            raise ValueError(f"voxel width must be even, not {self.w}")

    @property
    def h(self) -> int:             # height of the top rhombus
        return self.w // 2

    @property
    def d(self) -> int:             # vertical on-screen height of the voxel
        return self.w // 2

    def lattice(self, gx: float, gy: float, gz: float) -> tuple[float, float]:
        """Lattice vertex (gx, gy, gz) -> pixel. Origin at (0, 0)."""
        return ((gx - gy) * (self.w / 2), (gx + gy) * (self.h / 2) - gz * self.d)

    # --- voxel faces in lattice coordinates ------------------------------
    def top(self, x, y, z):
        return [self.lattice(x, y, z + 1), self.lattice(x + 1, y, z + 1),
                self.lattice(x + 1, y + 1, z + 1), self.lattice(x, y + 1, z + 1)]

    def left(self, x, y, z):
        return [self.lattice(x, y + 1, z + 1), self.lattice(x + 1, y + 1, z + 1),
                self.lattice(x + 1, y + 1, z), self.lattice(x, y + 1, z)]

    def right(self, x, y, z):
        return [self.lattice(x + 1, y + 1, z + 1), self.lattice(x + 1, y, z + 1),
                self.lattice(x + 1, y, z), self.lattice(x + 1, y + 1, z)]

    def rect(self, kind: str, a, b):
        """Merged (greedy) rectangle -> projected polygon."""
        (x0, y0, z0), (x1, y1, z1) = a, b
        if kind == "t":
            return [self.lattice(x0, y0, z0), self.lattice(x1, y0, z0),
                    self.lattice(x1, y1, z0), self.lattice(x0, y1, z0)]
        if kind == "l":
            return [self.lattice(x0, y0, z1), self.lattice(x1, y0, z1),
                    self.lattice(x1, y0, z0), self.lattice(x0, y0, z0)]
        return [self.lattice(x0, y1, z1), self.lattice(x0, y0, z1),
                self.lattice(x0, y0, z0), self.lattice(x0, y1, z0)]

    def occlusion_rows(self, piece_height: int, square: int) -> float:
        """How many board rows a piece of that height occludes toward the back."""
        return (piece_height * self.d) / (square * self.h / 2)
