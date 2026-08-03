"""Geometric operations on voxel grids.

Key fact governing the whole module: in a 2:1 dimetric projection voxel
(x+1, y+1, z+1) projects EXACTLY onto (x, y, z). Two things follow from it:

  * camera culling  -> a voxel whose diagonal neighbour is occupied is invisible
  * painter's order  -> sorting by (x+y+z) ascending is exact, not a heuristic
"""
from __future__ import annotations
import numpy as np

# visible face directions from the fixed camera
TOP, LEFT, RIGHT = "t", "l", "r"
FACE_AXIS = {TOP: 2, LEFT: 1, RIGHT: 0}


def neighbour(grid: np.ndarray, axis: int) -> np.ndarray:
    """Grid shifted by -1 on 'axis', with the border marked as empty."""
    shifted = np.roll(grid, -1, axis=axis)
    idx = [slice(None)] * 3
    idx[axis] = -1
    shifted[tuple(idx)] = False
    return shifted


def face_masks(grid: np.ndarray) -> dict[str, np.ndarray]:
    """Faces not hidden by an immediate neighbour."""
    return {k: grid & ~neighbour(grid, ax) for k, ax in FACE_AXIS.items()}


def n_faces(grid: np.ndarray) -> int:
    return sum(int(m.sum()) for m in face_masks(grid).values())


def camera_visible(grid: np.ndarray) -> np.ndarray:
    """Voxels not exactly covered by their diagonal neighbour (x+1,y+1,z+1)."""
    covered = np.zeros_like(grid)
    covered[:-1, :-1, :-1] = grid[1:, 1:, 1:]
    return grid & ~covered


def painter_order(grid: np.ndarray, cull_camera: bool = True):
    """Yields (x, y, z, top, left, right) in exact painter's order."""
    src = camera_visible(grid) if cull_camera else grid
    nx, ny, nz = grid.shape

    def occ(a, b, c):
        return 0 <= a < nx and 0 <= b < ny and 0 <= c < nz and grid[a, b, c]

    coords = np.argwhere(src)
    for x, y, z in sorted(map(tuple, coords), key=sum):
        top, left, right = not occ(x, y, z + 1), not occ(x, y + 1, z), not occ(x + 1, y, z)
        if top or left or right:
            yield int(x), int(y), int(z), top, left, right


# ------------------------------------------------------------ greedy meshing
def _rects(mask: np.ndarray):
    """Merges a boolean plane into maximal rectangles -> (i0, j0, i1, j1)."""
    m = mask.copy()
    h_, w_ = m.shape
    for i in range(h_):
        j = 0
        while j < w_:
            if not m[i, j]:
                j += 1
                continue
            w = 0
            while j + w < w_ and m[i, j + w]:
                w += 1
            h = 1
            while i + h < h_ and m[i + h, j:j + w].all():
                h += 1
            m[i:i + h, j:j + w] = False
            yield i, j, i + h, j + w
            j += w


def greedy_faces(grid: np.ndarray):
    """Merged faces -> (kind, (x0,y0,z0), (x1,y1,z1)) in lattice coordinates.

    WARNING: merging destroys painter's order. Only safe for surfaces without
    self-occlusion (e.g. the flat board). For pieces use painter_order().
    """
    nx, ny, nz = grid.shape
    masks = face_masks(grid)
    for z in range(nz):
        for x0, y0, x1, y1 in _rects(masks[TOP][:, :, z]):
            yield TOP, (x0, y0, z + 1), (x1, y1, z + 1)
    for y in range(ny):
        for x0, z0, x1, z1 in _rects(masks[LEFT][:, y, :]):
            yield LEFT, (x0, y + 1, z0), (x1, y + 1, z1)
    for x in range(nx):
        for y0, z0, y1, z1 in _rects(masks[RIGHT][x, :, :]):
            yield RIGHT, (x + 1, y0, z0), (x + 1, y1, z1)


def n_greedy(grid: np.ndarray) -> int:
    return sum(1 for _ in greedy_faces(grid))


# ----------------------------------------------------------------- utilities
def orient(grid: np.ndarray, side: str) -> np.ndarray:
    """Black pieces ('d') rotated 180 around Z so they face the other side.
    A 180 Z rotation = flip X and Y; Z untouched, footprint and grounded unchanged."""
    return grid[::-1, ::-1, :] if side == "d" else grid


def trim(grid: np.ndarray) -> np.ndarray:
    nz = np.nonzero(grid)
    if len(nz[0]) == 0:
        return grid
    return grid[nz[0].min():nz[0].max() + 1,
                nz[1].min():nz[1].max() + 1,
                nz[2].min():nz[2].max() + 1].copy()


def decimate(grid: np.ndarray, fxy: int = 2, fz: int | None = None,
             threshold: float = 0.5) -> np.ndarray:
    """Majority vote. A separate fz lets you flatten in Z to reduce occlusion."""
    fz = fz or fxy
    f = (fxy, fxy, fz)
    pad = [(-grid.shape[i]) % f[i] for i in range(3)]
    p = np.pad(grid, [(0, pad[i]) for i in range(3)])
    b = p.reshape(p.shape[0] // f[0], f[0],
                  p.shape[1] // f[1], f[1],
                  p.shape[2] // f[2], f[2])
    return b.mean(axis=(1, 3, 5)) >= threshold


def levels(grid: np.ndarray) -> list[int]:
    """Thickness of each level: runs of identical Z layers."""
    out, prev = [], None
    for z in range(grid.shape[2]):
        cur = grid[:, :, z].tobytes()
        if cur == prev:
            out[-1] += 1
        else:
            out.append(1)
            prev = cur
    return out


def metrics(grid: np.ndarray) -> dict:
    from scipy import ndimage
    _, components = ndimage.label(grid)
    return dict(dims=[int(v) for v in grid.shape],
                voxels=int(grid.sum()),
                faces=n_faces(grid),
                greedy=n_greedy(grid),
                camera_visible=int(camera_visible(grid).sum()),
                levels=levels(grid),
                grounded=bool(grid[:, :, 0].any()),
                components=int(components))
