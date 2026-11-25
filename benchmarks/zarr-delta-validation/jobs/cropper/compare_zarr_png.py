"""G2: a cropper Zarr tile store against a PNG slide folder: tiles[i, z] == decoded {x}x_{y}y/{z}z.png.

Two modes:

--gate (default; the store and a PNG run of the same code in the same image). Passes only if ALL hold:
  - the store is complete (tile_store.open refuses an incomplete one) and has N >= 1 tiles and Z >= 1 planes;
  - the store's tile set equals the PNG folder set, both ways (no tile only in the store, no {x}x_{y}y folder only
    in the PNG tree), and every folder holds exactly the files 0z.png .. {Z-1}z.png;
  - no plane is missing on either side (store plane_present all True; every PNG file present);
  - every one of the N x Z planes is equal, so planes_equal == N * Z (zero planes compared cannot pass);
  - at least one compared plane has content (not one uniform value), so two blank outputs cannot pass;
  - attrs "palyim" == metadata.json, every key. No key is exempt: both runs use the same code on the same slide,
    PNG mode writes metadata.json once (tile_size, tile_overlap, ome_metadata, total_tile_count) and updates
    processed_tile_count and percent_complete at exit, which for a complete run are N and 100.0, exactly what Zarr
    mode writes at finish. A difference therefore means one run was incomplete or made with other settings.
--report (the store against production tiles made by another image): the same numbers, never fails (exit 0).

The JSON report has a "checks" dict (name -> bool) and "pass". Needs palyim-io[zarr] (run inside our SIF).

Usage: python3 compare_zarr_png.py <store.zarr> <png_slide_dir> <report.json> [processes] [--report]

Memory: each worker reads one plane at a time (tile_stack(i, planes=[z]), 12 MiB) with zarr limited to one thread, so a
worker stays at a few hundred MB whatever Z is. (Reading whole shards, 432-504 MiB each plus zarr's thread pool, with 8
workers went past the 12 GB job limit on PAL on 2026-11-05.) Workers run in a ProcessPoolExecutor: if one is killed
(e.g. by the out-of-memory killer) the comparison stops with an error and exit 2 instead of hanging, which is what
multiprocessing.Pool did. Progress goes to stderr every ~2% of shards.
"""
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from multiprocessing import get_context

import numpy as np
from PIL import Image

from palyim_io import configure_worker, layout, tile_store

_STORE = {}


def _init_worker():
    configure_worker(threads=1)


def _open(store_path):
    if store_path not in _STORE:  # one handle per worker process, reused for every shard it compares
        _STORE[store_path] = tile_store.open(store_path)
    return _STORE[store_path]


def compare_shard(job):
    store_path, png_dir, shard = job
    store = _open(store_path)
    start, stop = store.shard_range(shard)
    present = store.plane_present
    xy = store.tile_xy
    out = {"planes_equal": 0, "planes_with_content": 0, "mismatches": [], "png_missing": [], "store_missing": [],
           "tile_dirs_missing": [], "unexpected_files": []}
    expected_files = {"%dz.png" % z for z in range(store.z_planes)}
    for j, i in enumerate(range(start, stop)):
        x, y = int(xy[i][0]), int(xy[i][1])
        tdir = os.path.join(png_dir, layout.tile_name(x, y))
        if not os.path.isdir(tdir):
            out["tile_dirs_missing"].append(i)
            continue
        extra = sorted(set(os.listdir(tdir)) - expected_files)
        if extra:
            out["unexpected_files"].append({"tile": i, "files": extra[:10]})
        for z in range(store.z_planes):
            if not present[i, z]:
                out["store_missing"].append([i, z])
                continue
            png = os.path.join(tdir, "%dz.png" % z)
            if not os.path.exists(png):
                out["png_missing"].append([i, z])
                continue
            a = np.asarray(Image.open(png))
            plane = store.tile_stack(i, planes=[z])[0]
            if a.shape == plane.shape and np.array_equal(a, plane):
                out["planes_equal"] += 1
                if plane.min() != plane.max():
                    out["planes_with_content"] += 1
            else:
                out["mismatches"].append({"tile": i, "x": x, "y": y, "z": z, "png_shape": list(a.shape)})
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    report_only = "--report" in sys.argv[1:]
    store_path, png_dir, report = args[0:3]
    processes = int(args[3]) if len(args) > 3 else 4
    store = tile_store.open(store_path)  # raises IncompleteStoreError for an incomplete store
    jobs = [(store_path, png_dir, s) for s in range(store.shards_total)]
    results = []
    if jobs:
        t0, step, done = time.time(), max(1, len(jobs) // 50), 0
        try:
            with ProcessPoolExecutor(processes, mp_context=get_context("spawn"), initializer=_init_worker) as ex:
                futures = [ex.submit(compare_shard, j) for j in jobs]
                for fut in as_completed(futures):
                    results.append(fut.result())
                    done += 1
                    if done % step == 0 or done == len(jobs):
                        print("progress: %d/%d shards compared (%.0f s)" % (done, len(jobs), time.time() - t0),
                              file=sys.stderr, flush=True)
        except BrokenProcessPool as e:
            print("ERROR: a comparison worker died (%s); likely out of memory. Fewer processes or more --mem." % e,
                  file=sys.stderr, flush=True)
            print("VERDICT %s: FAIL (comparison incomplete: worker died)" % ("report" if report_only else "gate"))
            sys.exit(2)
    store_tiles = {layout.tile_name(int(x), int(y)) for x, y in store.tile_xy}
    png_tiles = {d for d in os.listdir(png_dir) if os.path.isdir(os.path.join(png_dir, d))}
    meta_path = os.path.join(png_dir, "metadata.json")
    png_meta = json.load(open(meta_path)) if os.path.exists(meta_path) else None
    attrs = store.slide_metadata()
    agg = {k: [v for r in results for v in r[k]]
           for k in ("mismatches", "png_missing", "store_missing", "tile_dirs_missing", "unexpected_files")}
    n, z = store.n_tiles, store.z_planes
    planes_equal = sum(r["planes_equal"] for r in results)
    with_content = sum(r["planes_with_content"] for r in results)
    attr_diff = sorted(k for k in set(attrs) | set(png_meta or {}) if attrs.get(k) != (png_meta or {}).get(k))
    summary = {
        "mode": "report" if report_only else "gate",
        "store": store_path, "png_dir": png_dir,
        "n_tiles": n, "z_planes": z, "tile_size": store.tile_size, "planes_expected": n * z,
        "planes_equal": planes_equal,
        "planes_with_content": with_content,
        "planes_mismatched": len(agg["mismatches"]),
        "png_planes_missing": len(agg["png_missing"]),
        "store_planes_missing": len(agg["store_missing"]),
        "store_tiles_without_png_folder": len(agg["tile_dirs_missing"]),
        "png_folders_not_in_store": sorted(png_tiles - store_tiles),
        "png_folders_with_unexpected_files": len(agg["unexpected_files"]),
        "plane_equality_rate": (planes_equal / (n * z)) if n * z else None,
        "attrs_keys_differing_from_metadata_json": attr_diff,
        "attrs_palyim": attrs, "png_metadata_json": png_meta,
        "store_timings": store.timings(),
    }
    checks = {
        "store_has_tiles_and_planes": n >= 1 and z >= 1,
        "every_plane_equal": n * z > 0 and planes_equal == n * z,
        "no_mismatches": not agg["mismatches"],
        "no_store_planes_missing": not agg["store_missing"],
        "no_png_planes_missing": not agg["png_missing"],
        "every_store_tile_has_png_folder": not agg["tile_dirs_missing"],
        "every_png_folder_in_store": not (png_tiles - store_tiles),
        "png_folders_hold_only_plane_files": not agg["unexpected_files"],
        "some_planes_have_content": with_content > 0,
        "metadata_json_present": png_meta is not None,
        "attrs_equal_metadata_json": png_meta is not None and attrs == png_meta,
    }
    summary["checks"] = checks
    summary["pass"] = all(checks.values())
    with open(report, "w") as f:
        json.dump({"summary": summary, "details": {k: v[:1000] for k, v in agg.items()}}, f, indent=2)
    shown = {k: v for k, v in summary.items() if k not in ("attrs_palyim", "png_metadata_json", "store_timings")}
    shown["png_folders_not_in_store"] = shown["png_folders_not_in_store"][:20]
    print(json.dumps(shown, indent=2))
    print("VERDICT %s: %s" % (summary["mode"], "PASS" if summary["pass"] else
                              "FAIL (%s)" % ", ".join(k for k, v in checks.items() if not v)))
    sys.exit(0 if summary["pass"] or report_only else 1)


if __name__ == "__main__":
    main()
