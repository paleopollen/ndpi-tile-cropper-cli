"""Copy a slide's metadata.json and n of its tile folders into a new tiles root, for G0/G1a.

    python3 pick_tiles.py --src <tiles_root>/<slide> --dst <new_root> --n N [--prod-metadata <seg_root>/<slide>/metadata.json]

Which tiles: if the production metadata.json exists and lists segments, the n tiles with the most production
segments (ties in tile order); if fewer than n tiles have segments, or there is no production metadata, the rest
are the tiles nearest the centre of the grid. The first tiles in x-major order are the blank left edge of a
slide, so they are never the default. Prints a JSON summary (tiles and their production segment counts).
Stdlib only.
"""
import argparse
import json
import os
import re
import shutil
import sys

TILE_RE = re.compile(r"^(\d+)x_(\d+)y$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--prod-metadata")
    ap.add_argument("--name", help="slide folder name in --dst (default: the source folder's name)")
    a = ap.parse_args()

    tiles = {}
    for d in os.listdir(a.src):
        m = TILE_RE.match(d)
        if m and os.path.isdir(os.path.join(a.src, d)):
            tiles[d] = (int(m.group(1)), int(m.group(2)))
    order = sorted(tiles, key=lambda t: tiles[t])
    counts = {}
    if a.prod_metadata and os.path.isfile(a.prod_metadata):
        with open(a.prod_metadata) as f:
            md = json.load(f)
        for s in (md.get("segmentation") or {}).get("segments") or []:
            k = "%sx_%sy" % (s.get("tileX"), s.get("tileY"))
            counts[k] = counts.get(k, 0) + 1
    chosen = [t for t in sorted((t for t in order if counts.get(t)), key=lambda t: -counts[t])][:a.n]
    if len(chosen) < a.n:
        xs = sorted({x for x, _ in tiles.values()})
        ys = sorted({y for _, y in tiles.values()})
        cx, cy = (len(xs) - 1) / 2.0, (len(ys) - 1) / 2.0
        xi = {x: i for i, x in enumerate(xs)}
        yi = {y: i for i, y in enumerate(ys)}
        rest = sorted((t for t in order if t not in chosen),
                      key=lambda t: ((xi[tiles[t][0]] - cx) ** 2 + (yi[tiles[t][1]] - cy) ** 2, tiles[t]))
        chosen += rest[:a.n - len(chosen)]
    name = a.name or os.path.basename(os.path.normpath(a.src))
    dst = os.path.join(a.dst, name)
    os.makedirs(dst, exist_ok=True)
    shutil.copy2(os.path.join(a.src, "metadata.json"), dst)
    for t in chosen:
        shutil.copytree(os.path.join(a.src, t), os.path.join(dst, t))
    print(json.dumps({"slide": name, "tiles": sorted(chosen, key=lambda t: tiles[t]),
                      "production_segments_on_these_tiles": sum(counts.get(t, 0) for t in chosen),
                      "production_metadata": a.prod_metadata if counts else None,
                      "selection": "production segment counts" if counts else "grid centre"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
