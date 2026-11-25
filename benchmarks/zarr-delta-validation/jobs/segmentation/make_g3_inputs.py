"""Build G3's inputs: the same 9 tiles as PNG tile folders and as a 9-tile store.

    python3 make_g3_inputs.py --store FULL.zarr --slide NAME --out DIR [--png-slide-dir DIR] [--tiles "x,y x,y ..."]

- The store: palyim_io.testing.subset_tile_store(FULL.zarr, DIR/stores/NAME.zarr, tiles), i.e. pixels, tile_xy,
  plane_present and the slide attrs copied out of the full store that G2 verified.
- The PNG tree DIR/tiles/NAME/: with --png-slide-dir, a copy of those tile folders (G2's PNG run of the slide by
  default, from the same code and image as the store); every copied plane is checked against the store. Without it (no production PNG tiles
  kept for the slide), the planes are written from the store with Pillow (pixel-identical, bytes differ).
- Both sides get the same slide metadata: DIR/tiles/NAME/metadata.json is written from the store's slide attrs
  (the new cropper's metadata.json), so PNG and Zarr outputs can be compared field by field. The metadata.json of
  --png-slide-dir is not used as input; how it differs from the store attrs is reported separately.
- Tiles: --tiles, or the 3 x 3 block of the grid's centre tiles with every plane present.
Runs in our SIF (needs palyim-io with zarr). Prints a JSON summary.
"""
import argparse
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image
from palyim_io import testing, tile_store


def centre_block(store):
    xy = [tuple(int(v) for v in p) for p in store.tile_xy]
    xs, ys = sorted({x for x, _ in xy}), sorted({y for _, y in xy})
    full = store.plane_present.all(axis=1)
    ok = {p for p, f in zip(xy, full) if f}
    for r in range(0, max(len(xs), len(ys))):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                i, j = len(xs) // 2 + dx, len(ys) // 2 + dy
                if 0 <= i <= len(xs) - 3 and 0 <= j <= len(ys) - 3:
                    block = [(xs[i + a], ys[j + b]) for a in range(3) for b in range(3)]
                    if all(p in ok for p in block):
                        return block
    raise SystemExit("no 3 x 3 block with all planes present")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True)
    ap.add_argument("--slide", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--png-slide-dir")
    ap.add_argument("--tiles", help='"x,y x,y ..." tile origins')
    a = ap.parse_args()

    src = tile_store.open(a.store, "r")
    tiles = ([tuple(int(v) for v in t.split(",")) for t in a.tiles.split()] if a.tiles else centre_block(src))
    sub_path = os.path.join(a.out, "stores", a.slide + ".zarr")
    sub = testing.subset_tile_store(a.store, sub_path, tiles, overwrite=True)

    slide_dir = os.path.join(a.out, "tiles", a.slide)
    if os.path.exists(slide_dir):
        shutil.rmtree(slide_dir)
    os.makedirs(slide_dir)
    mismatches = []
    store_md = sub.slide_metadata()
    with open(os.path.join(slide_dir, "metadata.json"), "w") as f:
        json.dump(store_md, f, indent=4)
    production_metadata = None
    if a.png_slide_dir and os.path.isfile(os.path.join(a.png_slide_dir, "metadata.json")):
        with open(os.path.join(a.png_slide_dir, "metadata.json")) as f:
            prod_md = json.load(f)
        keys = sorted(set(prod_md) | set(store_md))
        production_metadata = {
            "path": os.path.join(a.png_slide_dir, "metadata.json"),
            "differences_from_store_attrs": {k: {"production": prod_md.get(k), "store": store_md.get(k)}
                                             for k in keys if prod_md.get(k) != store_md.get(k)},
        }
    for i, (x, y) in enumerate(sub.tile_xy):
        name = "%dx_%dy" % (x, y)
        stack = sub.tile_stack(i)
        present = sub.plane_present[i]
        if a.png_slide_dir:
            shutil.copytree(os.path.join(a.png_slide_dir, name), os.path.join(slide_dir, name))
            for z in range(sub.z_planes):
                p = os.path.join(slide_dir, name, "%dz.png" % z)
                if os.path.exists(p) != bool(present[z]):
                    mismatches.append("%s plane %d: file %s, plane_present %s" % (name, z, os.path.exists(p), present[z]))
                elif os.path.exists(p):
                    with Image.open(p) as im:
                        if not np.array_equal(np.asarray(im.convert("RGB")), stack[z]):
                            mismatches.append("%s plane %d: pixels differ" % (name, z))
        else:
            os.makedirs(os.path.join(slide_dir, name))
            for z in range(sub.z_planes):
                if present[z]:
                    Image.fromarray(stack[z]).save(os.path.join(slide_dir, name, "%dz.png" % z))
    summary = {"tiles": [list(map(int, t)) for t in sub.tile_xy], "z_planes": sub.z_planes,
               "png_source": a.png_slide_dir or "written from the store", "store": sub_path,
               "slide_metadata": "written from the store attrs (both sides)",
               "production_metadata": production_metadata, "mismatches": mismatches}
    print(json.dumps(summary, indent=2))
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
