"""Reading and writing voxel models in four formats.

  .vox   MagicaVoxel 150 (SIZE / XYZI / RGBA)   -> editable in MagicaVoxel, Goxel
  .txt   ASCII by layers                        -> hand-editable, git-legible diff
  .json  per-column RLE                          -> format to version
  .npz   numpy compressed                        -> runtime load format
"""
from __future__ import annotations
import json
import struct
from pathlib import Path

import numpy as np

DEFAULT_PALETTE = [(0xBF, 0x9B, 0x73), (0x54, 0x3A, 0x2B)]


# --------------------------------------------------------------------- .vox
def _chunk(cid: bytes, content: bytes = b"", children: bytes = b"") -> bytes:
    return cid + struct.pack("<II", len(content), len(children)) + content + children


def load_vox(path) -> tuple[np.ndarray, list]:
    data = Path(path).read_bytes()
    if data[:4] != b"VOX ":
        raise ValueError(f"{path}: not a .vox file")
    size, voxels, palette = None, [], []

    def walk(buf: bytes) -> None:
        nonlocal size, voxels, palette
        off = 0
        while off < len(buf):
            cid = buf[off:off + 4]
            csize, chsize = struct.unpack("<II", buf[off + 4:off + 12])
            content = buf[off + 12:off + 12 + csize]
            children = buf[off + 12 + csize:off + 12 + csize + chsize]
            if cid == b"SIZE":
                size = struct.unpack("<iii", content)
            elif cid == b"XYZI":
                n = struct.unpack("<I", content[:4])[0]
                voxels = [struct.unpack("<BBBB", content[4 + i * 4:8 + i * 4])
                          for i in range(n)]
            elif cid == b"RGBA":
                palette = [struct.unpack("<BBBB", content[i * 4:i * 4 + 4])
                           for i in range(256)]
            if chsize:
                walk(children)
            off += 12 + csize + chsize

    walk(data[8:])
    grid = np.zeros(size, bool)
    for x, y, z, _ in voxels:
        grid[x, y, z] = True
    return grid, (palette or [(*c, 255) for c in DEFAULT_PALETTE])


def save_vox(path, grid: np.ndarray, palette=None) -> None:
    palette = palette or DEFAULT_PALETTE
    nx, ny, nz = grid.shape
    if max(grid.shape) > 256:
        raise ValueError("MagicaVoxel is limited to 256 voxels per axis")
    xs, ys, zs = np.nonzero(grid)
    body = struct.pack("<I", len(xs)) + b"".join(
        struct.pack("<BBBB", int(x), int(y), int(z), 1) for x, y, z in zip(xs, ys, zs))
    raw = bytearray()
    for i in range(256):
        c = palette[i] if i < len(palette) else (0, 0, 0, 255)
        raw += struct.pack("<BBBB", c[0], c[1], c[2], c[3] if len(c) > 3 else 255)
    main = _chunk(b"MAIN", b"",
                  _chunk(b"SIZE", struct.pack("<iii", nx, ny, nz))
                  + _chunk(b"XYZI", body)
                  + _chunk(b"RGBA", bytes(raw)))
    Path(path).write_bytes(b"VOX " + struct.pack("<i", 150) + main)


# ---------------------------------------------------------------- ASCII .txt
def dump_ascii(grid: np.ndarray) -> str:
    nx, ny, nz = grid.shape
    out = [f"; grid {nx}x{ny}x{nz}   z=0 is the BASE",
           "; '#' filled, '.' empty, ';' comment",
           f"size {nx} {ny} {nz}"]
    for z in range(nz):
        out += ["", f"; --- z={z}  area={int(grid[:, :, z].sum())}", f"z {z}"]
        for y in range(ny):
            out.append("".join("#" if grid[x, y, z] else "." for x in range(nx)))
    return "\n".join(out) + "\n"


def build_ascii(text: str) -> np.ndarray:
    grid, nx, z, row = None, None, None, 0
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith("size "):
            nx, ny, nz = map(int, s.split()[1:4])
            grid = np.zeros((nx, ny, nz), bool)
        elif s.startswith("z "):
            z, row = int(s.split()[1]), 0
        else:
            if grid is None or z is None:
                raise ValueError('missing "size" or "z" before the rows')
            if len(s) != nx:
                raise ValueError(f"z={z} row {row}: {len(s)} columns, expected {nx}")
            for x, ch in enumerate(s):
                if ch == "#":
                    grid[x, row, z] = True
                elif ch != ".":
                    raise ValueError(f"z={z} row {row}: invalid character {ch!r}")
            row += 1
    if grid is None:
        raise ValueError("empty file")
    return grid


# ------------------------------------------------------------------ RLE json
def to_rle(grid: np.ndarray, voxel_unit: float = 0.2) -> dict:
    nx, ny, nz = grid.shape
    cols = {}
    for x in range(nx):
        for y in range(ny):
            col = grid[x, y]
            if not col.any():
                continue
            runs, z = [], 0
            while z < nz:
                if col[z]:
                    z0 = z
                    while z < nz and col[z]:
                        z += 1
                    runs.append([z0, z - z0])
                else:
                    z += 1
            cols[f"{x},{y}"] = runs
    return {"dims": [int(v) for v in grid.shape], "voxel_unit": voxel_unit,
            "columns": cols}


def from_rle(data: dict) -> np.ndarray:
    grid = np.zeros(data["dims"], bool)
    for key, runs in data["columns"].items():
        x, y = map(int, key.split(","))
        for z0, length in runs:
            grid[x, y, z0:z0 + length] = True
    return grid


# ------------------------------------------------------------------ set
PIECES = ("pawn", "rook", "knight", "bishop", "queen", "king")


def load_set(directory) -> dict[str, np.ndarray]:
    """Loads the six pieces from a directory; accepts .vox, .txt or .json."""
    directory = Path(directory)
    out = {}
    for name in PIECES:
        for ext, fn in ((".vox", lambda p: load_vox(p)[0]),
                        (".txt", lambda p: build_ascii(p.read_text())),
                        (".json", lambda p: from_rle(json.loads(p.read_text())))):
            path = directory / f"{name}{ext}"
            if path.exists():
                out[name] = fn(path)
                break
        else:
            raise FileNotFoundError(f"cannot find {name}.(vox|txt|json) in {directory}")
    return out


def save_set(directory, models: dict[str, np.ndarray], formats=("vox", "txt", "json")) -> None:
    directory = Path(directory)
    for fmt in formats:
        (directory / fmt).mkdir(parents=True, exist_ok=True)
    for name, grid in models.items():
        if "vox" in formats:
            save_vox(directory / "vox" / f"{name}.vox", grid)
        if "txt" in formats:
            (directory / "txt" / f"{name}.txt").write_text(dump_ascii(grid))
        if "json" in formats:
            (directory / "json" / f"{name}.json").write_text(
                json.dumps(to_rle(grid), separators=(",", ":")))
    np.savez_compressed(directory / "pieces.npz", **models)
