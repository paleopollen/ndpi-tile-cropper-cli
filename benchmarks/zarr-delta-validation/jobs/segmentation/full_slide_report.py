"""PNG vs Zarr report for one slide's full-slide segmentation runs (full-slide-png-vs-zarr.sbatch).

    python3 full_slide_report.py --slide NAME --png <G1 output dir> --zarr <this job's output dir> [--g0 <G0 root>]

Reads, from each side's folder: sizes.txt ("tree: files N, dirs N, bytes N" and "csv: bytes N"), the CLI log
(new.log / zarr.log: the PhaseTimer line "[<slide>] timings: total=...s; <phase>=...s (n=...), ..." and GNU time's
"Elapsed (wall clock) time"), the slide metadata.json (segment count) and exit-codes.txt; from the Zarr side also
overlap.json (compare_outputs.py summary-vs-production, a = the PNG run). Writes report.md and report.json into the
Zarr side's folder and prints one summary line. Stdlib only. Never gates: missing inputs show as "n/a".
"""
import argparse
import glob
import json
import os
import re

TIMINGS_RE = re.compile(r"\[(?P<slide>[^\]]+)\] timings: total=(?P<total>[0-9.]+)s; (?P<rest>.*)$")
PHASE_RE = re.compile(r"(\w+)=([0-9.]+)s \(n=(\d+)\)")
ELAPSED_RE = re.compile(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)")
TREE_RE = re.compile(r"^tree: files (\d+), dirs (\d+), bytes (\d+)")
CSV_RE = re.compile(r"^csv: bytes (\d+)")


def read_text(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def parse_sizes(path):
    out = {"files": None, "dirs": None, "bytes": None, "tree_files": None, "tree_bytes": None, "csv_bytes": None}
    for line in read_text(path).splitlines():
        m = TREE_RE.match(line)
        if m:
            out["tree_files"], out["dirs"], out["tree_bytes"] = (int(x) for x in m.groups())
        m = CSV_RE.match(line)
        if m:
            out["csv_bytes"] = int(m.group(1))
    if out["tree_files"] is not None:
        has_csv = bool(out["csv_bytes"])
        out["files"] = out["tree_files"] + (1 if has_csv else 0)
        out["bytes"] = out["tree_bytes"] + (out["csv_bytes"] or 0)
    return out


def hms_to_seconds(text):
    parts = [float(p) for p in text.split(":")]
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def parse_log(path, slide):
    """{'total': s, 'phases': {name: s}, 'wall': s} from the last timings line of `slide` and GNU time."""
    total, phases, wall = None, {}, None
    for line in read_text(path).splitlines():
        m = TIMINGS_RE.search(line)
        if m and m.group("slide") == slide:
            total = float(m.group("total"))
            phases = {name: float(s) for name, s, _n in PHASE_RE.findall(m.group("rest"))}
        m = ELAPSED_RE.search(line)
        if m:
            wall = hms_to_seconds(m.group(1))
    return {"wall_seconds": wall, "total_seconds": total, "phases": phases}


def segment_count(path):
    md = read_json(path)
    seg = (md or {}).get("segmentation")
    segs = seg.get("segments") if isinstance(seg, dict) else None
    return len(segs) if isinstance(segs, list) else None


def exit_code(path, label):
    m = re.search(r"^%s exit (\d+)" % label, read_text(path), re.M)
    return int(m.group(1)) if m else None


def newest_g0_line(root):
    if not root:
        return None
    found = [p for p in glob.glob(os.path.join(root, "*", "result.txt")) if read_text(p).strip()]
    if not found:
        return None
    newest = max(found, key=os.path.getmtime)
    slide = "slide unknown"
    for line in read_text(os.path.join(os.path.dirname(newest), "env.txt")).splitlines():
        if line.startswith("slide:"):
            slide = "slide " + line.split()[1]  # G0 runs on whichever slide it was submitted with
            break
    return "%s, %s (%s)" % (read_text(newest).strip().splitlines()[-1], slide, newest)


def fmt_int(v):
    return "n/a" if v is None else "{:,}".format(v)


def fmt_bytes(v):
    if v is None:
        return "n/a"
    for unit, size in (("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)):
        if v >= size:
            return "%.2f %s (%s B)" % (v / size, unit, "{:,}".format(v))
    return "%d B" % v


def fmt_time(s):
    if s is None:
        return "n/a"
    s = int(round(s))
    return "%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--slide", required=True)
    ap.add_argument("--png", required=True, help="G1's output folder (the PNG side)")
    ap.add_argument("--zarr", required=True, help="this job's output folder (the Zarr side)")
    ap.add_argument("--g0", help="G0's output root, to quote its newest result")
    a = ap.parse_args()

    sides = {}
    for side, folder, log, md, label in (
            ("png", a.png, "new.log", os.path.join(a.png, "new-metadata.json"), "new"),
            ("zarr", a.zarr, "zarr.log", os.path.join(a.zarr, "zarr", a.slide, "metadata.json"), "zarr")):
        d = parse_sizes(os.path.join(folder, "sizes.txt"))
        d.update(parse_log(os.path.join(folder, log), a.slide))
        d["segments"] = segment_count(md)
        d["exit"] = exit_code(os.path.join(folder, "exit-codes.txt"), label)
        d["folder"] = folder
        sides[side] = d

    overlap = read_json(os.path.join(a.zarr, "overlap.json")) or {}
    entry = (overlap.get("slides") or {}).get(a.slide) or {}
    keys = entry.get("segment_key_overlap") or {}
    csv_rows = [r.get("rows") for r in overlap.get("csv") or []] + [None, None]
    sides["png"]["csv_rows"], sides["zarr"]["csv_rows"] = csv_rows[0], csv_rows[1]
    report = {
        "schema": "palyim.phase1.full-slide-seg", "version": 1, "slide": a.slide, "stage": 2,
        "png": sides["png"], "zarr": sides["zarr"],
        "segment_key_overlap": {"both": keys.get("both"), "only_png": keys.get("only_production"),
                                "only_zarr": keys.get("only_new"), "jaccard": keys.get("jaccard")},
        "tiles_with_different_counts": entry.get("tiles_with_different_counts"),
        "png_tile_provenance": read_text(os.path.join(a.png, "tile-provenance.txt")).strip() or None,
        "g0": newest_g0_line(a.g0),
    }
    with open(os.path.join(a.zarr, "report.json"), "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    p, z = sides["png"], sides["zarr"]
    rows = [
        ("Files (output tree + CSV)", fmt_int(p["files"]), fmt_int(z["files"])),
        ("Directories", fmt_int(p["dirs"]), fmt_int(z["dirs"])),
        ("Bytes (output tree + CSV)", fmt_bytes(p["bytes"]), fmt_bytes(z["bytes"])),
        ("Wall time, CLI (GNU time)", fmt_time(p["wall_seconds"]), fmt_time(z["wall_seconds"])),
        ("Wall time, PhaseTimer total", fmt_time(p["total_seconds"]), fmt_time(z["total_seconds"])),
    ]
    for name in list(p["phases"]) + [n for n in z["phases"] if n not in p["phases"]]:
        rows.append(("phase `%s`" % name, fmt_time(p["phases"].get(name)), fmt_time(z["phases"].get(name))))
    rows += [
        ("Segments (slide metadata.json)", fmt_int(p["segments"]), fmt_int(z["segments"])),
        ("CSV rows", fmt_int(p["csv_rows"]), fmt_int(z["csv_rows"])),
        ("CLI exit code", fmt_int(p["exit"]), fmt_int(z["exit"])),
    ]
    k = report["segment_key_overlap"]
    lines = [
        "# Stage 2, full slide, PNG vs Zarr: %s" % a.slide, "",
        "PNG: G1 run `%s`. Zarr: this run `%s`." % (a.png, a.zarr), "",
        "| | PNG | Zarr |", "|---|---|---|",
    ] + ["| %s | %s | %s |" % r for r in rows] + [
        "",
        "**segment_key overlap** (reported, not gated): both %s, only PNG %s, only Zarr %s, tiles with different "
        "counts %s." % (fmt_int(k["both"]), fmt_int(k["only_png"]), fmt_int(k["only_zarr"]),
                        fmt_int(report["tiles_with_different_counts"])),
        "",
        "- G0 (GPU repeatability, two runs on a tile subset): %s" % (report["g0"] or "no G0 result found"),
        "- PNG side (G1) %s. Zarr side tiles: G2's tile store." % (report["png_tile_provenance"] or "tiles: n/a"),
        "- PNG sizes were measured in node-local scratch before G1's cleanup; Zarr sizes on Taiga. Bytes are "
        "`du -sb` (apparent size, directories included) plus the CSV.",
        "- Phases are each mode's own PhaseTimer phases; a phase one mode does not have shows n/a.",
    ]
    with open(os.path.join(a.zarr, "report.md"), "w") as f:
        f.write("\n".join(lines) + "\n")

    ratio = ("%.0fx fewer" % (p["files"] / z["files"])) if p["files"] and z["files"] else "n/a"
    print("REPORTED (not gated)  %s: files PNG %s / Zarr %s (%s), bytes PNG %s / Zarr %s, wall PNG %s / Zarr %s, "
          "segments PNG %s / Zarr %s, keys both %s / only PNG %s / only Zarr %s"
          % (a.slide, fmt_int(p["files"]), fmt_int(z["files"]), ratio, fmt_int(p["bytes"]), fmt_int(z["bytes"]),
             fmt_time(p["wall_seconds"]), fmt_time(z["wall_seconds"]), fmt_int(p["segments"]),
             fmt_int(z["segments"]), fmt_int(k["both"]), fmt_int(k["only_png"]), fmt_int(k["only_zarr"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
