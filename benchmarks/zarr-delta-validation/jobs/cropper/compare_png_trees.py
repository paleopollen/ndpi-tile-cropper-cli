"""Compare two cropper PNG slide folders: side a and side b.

--gate (default; G1a: base code vs new code, same image). Passes only if ALL hold:
  - each side is complete on its own: it has metadata.json, exactly total_tile_count tile folders, and every folder
    holds exactly 0z.png .. {z_plane-1}z.png (so two equally truncated runs cannot pass);
  - the same tile folders and file lists on both sides, and at least one plane compared;
  - decoded pixels equal for every plane;
  - metadata.json equal, every key (same code path, same slide: no key may vary);
  - at least one plane is not "small" (see blank check), so two blank outputs cannot pass.
  Byte identity is reported, not gated (PNG bytes depend on the zlib/Pillow build; same image here, so expected).
--summary (G1: our run vs existing production tiles made by another image): never fails; tile counts, the
  per-plane pixel equality rate over the planes both sides have, and the tiles that differ or exist on one side only.

Blank check: a plane whose PNG file is under 1% of the raw plane (tile_size^2 x 3 bytes, from metadata.json) is
counted as "small", i.e. likely blank: a uniform 2048 x 2048 RGB plane compresses to a few KiB (about 0.1% of its
12 MiB), content planes to about 1-3 MB (10-25%). Reported per side. The gate's content check is exact: it decodes
side b's 20 largest PNG files and requires at least one that is not a single uniform value (if the largest planes
are blank, all are).
Runs on Python 3.9+ with numpy and Pillow.

Usage: python3 compare_png_trees.py <slide_dir_a> <slide_dir_b> <report.json> [processes] [--summary]
"""
import filecmp
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

import numpy as np
from PIL import Image

SMALL_PNG_FRACTION = 0.01


def listing(root):
    tiles = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    return tiles, {t: sorted(os.listdir(os.path.join(root, t))) for t in tiles}


def completeness(root, tiles, files, meta):
    """Problems that make one side incomplete on its own (empty list if complete)."""
    if meta is None:
        return ["no metadata.json"]
    problems = []
    total = meta.get("total_tile_count")
    z = (meta.get("ome_metadata") or {}).get("z_plane")
    if not isinstance(total, int) or total < 1:
        problems.append("total_tile_count is %r" % (total,))
    elif len(tiles) != total:
        problems.append("%d tile folders, total_tile_count %d" % (len(tiles), total))
    if not isinstance(z, int) or z < 1:
        problems.append("ome_metadata.z_plane is %r" % (z,))
    else:
        expected = sorted("%dz.png" % i for i in range(z))
        bad = [t for t in tiles if files[t] != expected]
        if bad:
            problems.append("%d tile folders without exactly %d planes (first: %s)" % (len(bad), z, bad[:5]))
    if meta.get("percent_complete") != 100.0:
        problems.append("percent_complete is %r" % (meta.get("percent_complete"),))
    return problems


def small_planes(root, tiles, files, meta):
    size = (meta or {}).get("tile_size")
    if not isinstance(size, int) or size < 1:
        return None
    limit = SMALL_PNG_FRACTION * size * size * 3
    return sum(1 for t in tiles for f in files[t] if os.path.getsize(os.path.join(root, t, f)) < limit)


def planes_with_content(root, tiles, files, n=20):
    """How many of the n largest PNG files under root decode to more than one value."""
    paths = [os.path.join(root, t, f) for t in tiles for f in files[t]]
    largest = sorted(paths, key=os.path.getsize, reverse=True)[:n]
    count = 0
    for p in largest:
        a = np.asarray(Image.open(p))
        count += int(a.size > 0 and a.min() != a.max())
    return count


def compare_tile(job):
    a_dir, b_dir, tile, names = job
    out = {"tile": tile, "planes": len(names), "bytes_equal": 0, "pixels_equal": 0, "mismatches": []}
    for name in names:
        fa, fb = os.path.join(a_dir, tile, name), os.path.join(b_dir, tile, name)
        if filecmp.cmp(fa, fb, shallow=False):
            out["bytes_equal"] += 1
            out["pixels_equal"] += 1
            continue
        a, b = np.asarray(Image.open(fa)), np.asarray(Image.open(fb))
        if a.shape == b.shape and a.dtype == b.dtype and np.array_equal(a, b):
            out["pixels_equal"] += 1
        else:
            diff = int(np.abs(a.astype(np.int16) - b.astype(np.int16)).max()) if a.shape == b.shape else None
            out["mismatches"].append({"plane": name, "shape_a": list(a.shape), "shape_b": list(b.shape),
                                      "max_abs_diff": diff})
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    summary_only = "--summary" in sys.argv[1:]
    a_dir, b_dir, report = args[0:3]
    processes = int(args[3]) if len(args) > 3 else 4
    tiles_a, files_a = listing(a_dir)
    tiles_b, files_b = listing(b_dir)
    common = sorted(set(tiles_a) & set(tiles_b))
    file_list_diffs = [t for t in common if files_a[t] != files_b[t]]
    jobs = [(a_dir, b_dir, t, sorted(set(files_a[t]) & set(files_b[t]))) for t in common]
    results = []
    if jobs:
        # ProcessPoolExecutor, not multiprocessing.Pool: a killed worker raises here instead of hanging the job.
        t0, step, done = time.time(), max(1, len(jobs) // 50), 0
        try:
            with ProcessPoolExecutor(processes) as ex:
                for r in ex.map(compare_tile, jobs, chunksize=8):
                    results.append(r)
                    done += 1
                    if done % step == 0 or done == len(jobs):
                        print("progress: %d/%d tiles compared (%.0f s)" % (done, len(jobs), time.time() - t0),
                              file=sys.stderr, flush=True)
        except BrokenProcessPool as e:
            print("ERROR: a comparison worker died (%s); likely out of memory." % e, file=sys.stderr, flush=True)
            print("VERDICT %s: FAIL (comparison incomplete: worker died)" % ("summary" if summary_only else "gate"))
            sys.exit(2)
    meta = {}
    for side, d in (("a", a_dir), ("b", b_dir)):
        p = os.path.join(d, "metadata.json")
        meta[side] = json.load(open(p)) if os.path.exists(p) else None
    planes = sum(r["planes"] for r in results)
    small_a = small_planes(a_dir, tiles_a, files_a, meta["a"])
    small_b = small_planes(b_dir, tiles_b, files_b, meta["b"])
    content_b = planes_with_content(b_dir, tiles_b, files_b)
    summary = {
        "mode": "summary" if summary_only else "gate",
        "a": a_dir, "b": b_dir,
        "tiles_a": len(tiles_a), "tiles_b": len(tiles_b),
        "incomplete_a": completeness(a_dir, tiles_a, files_a, meta["a"]),
        "incomplete_b": completeness(b_dir, tiles_b, files_b, meta["b"]),
        "tiles_only_in_a": sorted(set(tiles_a) - set(tiles_b)),
        "tiles_only_in_b": sorted(set(tiles_b) - set(tiles_a)),
        "tiles_with_different_file_lists": file_list_diffs,
        "planes_compared": planes,
        "planes_bytes_equal": sum(r["bytes_equal"] for r in results),
        "planes_pixels_equal": sum(r["pixels_equal"] for r in results),
        "small_planes_a": small_a, "small_planes_b": small_b,
        "largest_planes_b_with_content": content_b,
        "metadata_equal": meta["a"] == meta["b"],
        "metadata_a": meta["a"], "metadata_b": meta["b"],
    }
    summary["plane_pixel_equality_rate"] = (summary["planes_pixels_equal"] / planes) if planes else None
    summary["tiles_differing"] = sorted({r["tile"] for r in results if r["mismatches"]} | set(file_list_diffs)
                                        | set(summary["tiles_only_in_a"]) | set(summary["tiles_only_in_b"]))
    checks = {
        "a_complete": not summary["incomplete_a"],
        "b_complete": not summary["incomplete_b"],
        "same_tiles": tiles_a == tiles_b,
        "same_file_lists": not file_list_diffs,
        "some_planes_compared": planes > 0,
        "every_plane_pixel_equal": planes > 0 and summary["planes_pixels_equal"] == planes,
        "metadata_equal": meta["a"] is not None and summary["metadata_equal"],
        "some_planes_have_content": content_b > 0,
    }
    summary["checks"] = checks
    summary["pass"] = all(checks.values())
    mismatches = [dict(m, tile=r["tile"]) for r in results for m in r["mismatches"]]
    with open(report, "w") as f:
        json.dump({"summary": summary, "mismatches": mismatches[:1000]}, f, indent=2)
    print(json.dumps({k: (v[:50] if isinstance(v, list) else v) for k, v in summary.items()
                      if not k.startswith("metadata_")}, indent=2))
    verdict = "PASS" if summary["pass"] else "FAIL (%s)" % ", ".join(k for k, v in checks.items() if not v)
    print("VERDICT %s: %s" % (summary["mode"], "REPORTED ONLY, " + verdict if summary_only else verdict))
    sys.exit(0 if summary["pass"] or summary_only else 1)


if __name__ == "__main__":
    main()
