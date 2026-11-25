#!/usr/bin/env python3
"""G2 progress for both phase-1 slides: Zarr shards done and PNG planes written so far.

Run on a login node (stdlib only):  OUT_ROOT=<test output root> python3 g2_progress.py   (or pass the root as the argument)
Zarr progress comes from the store's progress.json (written by the parent after each durable shard).
PNG progress counts the {z}z.png files under G2's kept PNG tree; the tile total comes from the Zarr store
(same grid, same code), so PNG percentages are only shown once the store exists.
"""
import json
import os
import sys

G2 = os.path.join(os.environ.get("OUT_ROOT") or (sys.argv[1] if len(sys.argv) > 1 else "."), "g2-cropper")
SLIDES = [
    ("TADP", "54490_TADP1_232Q-2-69_L_2024_11_12_15_50_13"),
    ("PAL", "PAL1999_B2_sample100_slide1"),
]


def zarr_progress(slide):
    path = os.path.join(G2, "stores", slide + ".zarr", "progress.json")
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def png_progress(slide, z_planes):
    root = os.path.join(G2, "png", slide)
    if not os.path.isdir(root):
        return None
    planes = tiles = full = 0
    for entry in os.scandir(root):
        if not entry.is_dir():
            continue
        tiles += 1
        k = sum(1 for f in os.scandir(entry.path) if f.name.endswith("z.png"))
        planes += k
        if z_planes and k >= z_planes:
            full += 1
    return tiles, full, planes


def pct(a, b):
    return f"{100.0 * a / b:5.1f}%" if b else "  n/a"


def main():
    for key, slide in SLIDES:
        p = zarr_progress(slide)
        if p is None:
            print(f"{key:4}  Zarr: not started (no progress.json)")
            n = z = None
        else:
            n, z = p.get("n_tiles"), p.get("z_planes")
            done, total = len(p.get("shards_done", [])), p.get("shards_total", 0)
            tiles = min(n or 0, done * p.get("tiles_per_shard", 0))
            state = "COMPLETE" if p.get("complete") else "running/stopped"
            print(f"{key:4}  Zarr: {done}/{total} shards {pct(done, total)}  (~{tiles}/{n} tiles, Z={z})  "
                  f"missing planes: {len(p.get('missing_planes', []))}  [{state}]")
        q = png_progress(slide, z)
        if q is None:
            print(f"{key:4}  PNG : not started (no {G2}/png/{slide})")
        else:
            tiles, full, planes = q
            if n and z:
                print(f"{key:4}  PNG : {full}/{n} tiles with all {z} planes {pct(full, n)}  "
                      f"({planes}/{n * z} plane files {pct(planes, n * z)}, {tiles} tile folders)")
            else:
                print(f"{key:4}  PNG : {tiles} tile folders, {planes} plane files (total unknown until the store exists)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
