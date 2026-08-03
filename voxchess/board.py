"""Scene composition: board, frame, positions and shadows."""
from __future__ import annotations
from dataclasses import dataclass, field

import numpy as np

from .iso import Projection

PIECE_LETTER = {"p": "pawn", "r": "rook", "n": "knight",
                "b": "bishop", "q": "queen", "k": "king"}


@dataclass
class BoardLayout:
    voxel: int = 4          # voxel width in px (even)
    square: int = 14        # voxels per square
    n: int = 8
    frame: int = 3          # frame in voxels (0 = no frame)
    slab: int = 4           # slab thickness in voxels
    piece_size: int = 9     # piece footprint, for centering
    proj: Projection = field(init=False)

    def __post_init__(self):
        self.proj = Projection(self.voxel)

    @property
    def side(self) -> int:
        return self.n * self.square + 2 * self.frame

    def square_origin(self, bx: int, by: int) -> tuple[int, int]:
        return self.frame + bx * self.square, self.frame + by * self.square

    def piece_origin(self, bx: int, by: int) -> tuple[int, int]:
        gx, gy = self.square_origin(bx, by)
        pad = (self.square - self.piece_size) // 2
        return gx + pad, gy + pad

    def occlusion_rows(self, piece_height: int) -> float:
        return self.proj.occlusion_rows(piece_height, self.square)

    def bounds(self, max_piece_height: int):
        xs, ys = [], []
        for gx in (0, self.side):
            for gy in (0, self.side):
                for gz in (-self.slab, 0):
                    x, y = self.proj.lattice(gx, gy, gz)
                    xs.append(x)
                    ys.append(y)
        ys.append(self.proj.lattice(0, 0, self.slab + max_piece_height)[1])
        return min(xs), min(ys), max(xs), max(ys)


# ------------------------------------------------------------------ position
def parse_fen(fen: str) -> list[tuple[int, int, str, str]]:
    """FEN -> [(bx, by, name, 'l'|'d')] with white at the front (high by)."""
    rows = fen.split()[0].split("/")
    if len(rows) != 8:
        raise ValueError("invalid FEN: expected 8 rows")
    out = []
    for by, row in enumerate(rows):          # rows[0] is rank 8 = back
        bx = 0
        for ch in row:
            if ch.isdigit():
                bx += int(ch)
                continue
            name = PIECE_LETTER.get(ch.lower())
            if name is None:
                raise ValueError(f"invalid FEN: character {ch!r}")
            out.append((bx, by, name, "l" if ch.isupper() else "d"))
            bx += 1
    return out


START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


def square_to_board(square: str) -> tuple[int, int]:
    """'e2' -> (bx, by)."""
    f = ord(square[0].lower()) - ord("a")
    r = int(square[1])
    return f, 8 - r


def random_position(plies: int = 28, seed: int = 7):
    """Random legal position. Requires python-chess."""
    import chess
    import random
    rng = random.Random(seed)
    board = chess.Board()
    for _ in range(plies):
        moves = list(board.legal_moves)
        if not moves:
            break
        board.push(rng.choice(moves))
    return board
