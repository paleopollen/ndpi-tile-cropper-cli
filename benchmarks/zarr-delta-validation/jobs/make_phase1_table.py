"""Phase-1 PNG vs Zarr table (stages 1 and 2, both slides) from the rsynced Delta results. Stdlib only.

    python3 make_phase1_table.py <results folder copied back with copy-back.rsync-filter>

Stage 1 comes from the cropper's G2 (g2-cropper/<KEY>-<job>/: sizes.txt, timings-{zarr,png}.json,
crop-{zarr,png}.log, verdict.txt), stage 2 from segmentation/full-slide-png-vs-zarr.sbatch
(full-seg/<job>/report.json). The newest job per slide wins. Prints the table and writes it to
<results>/phase1-table.md.
"""
import glob
import json
import os
import re
import sys

STORE_RE = re.compile(r"^store: files (\d+), dirs (\d+), bytes (\d+)")
PNG_RE = re.compile(r"^png \(own run\): files (\d+), dirs (\d+), bytes (\d+)")
SLIDE_RE = re.compile(r"^slide (\w+): .*\((?P<name>[^()]+)\)\s*$", re.M)
ELAPSED_RE = re.compile(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)")


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


def job_id(folder):
    m = re.search(r"(\d+)$", os.path.basename(folder.rstrip("/")))
    return int(m.group(1)) if m else -1


def gnu_wall(path):
    found = ELAPSED_RE.findall(read_text(path))
    if not found:
        return None
    s = 0.0
    for part in found[-1].split(":"):
        s = s * 60 + float(part)
    return s


CROP_SLIDE_RE = re.compile(r"ndpi_tile_cropper_cli\.py - (.+?): Read NDPISlide metadata")
TQDM_RE = re.compile(r"\| *\d+/\d+ \[((?:\d+:)?\d+:\d+)<")
STAMP_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", re.M)


def crop_slide(path):
    """The slide file a crop log read (None if the log never got that far)."""
    m = CROP_SLIDE_RE.search(read_text(path))
    return m.group(1) if m else None


def run_seconds(path):
    """Wall time of one crop run: GNU time if the run ended normally; for a run SLURM killed (time limit, cancel),
    the last tqdm elapsed, else the span of its log timestamps."""
    w = gnu_wall(path)
    if w is not None:
        return w
    text = read_text(path)
    t = TQDM_RE.findall(text)
    if t:
        s = 0.0
        for part in t[-1].split(":"):
            s = s * 60 + float(part)
        return s
    stamps = STAMP_RE.findall(text)
    if len(stamps) >= 2:
        from datetime import datetime
        f = "%Y-%m-%d %H:%M:%S"
        return (datetime.strptime(stamps[-1], f) - datetime.strptime(stamps[0], f)).total_seconds()
    return 0.0


def stage1(results):
    """{key: {"name", "folder", "verdict", "png": {...}, "zarr": {...}}}: sizes and verdict from the newest G2 job
    per slide; wall time summed over every G2 job that cropped the same slide file, because a crop stopped by a
    kill or a time limit resumes in the next job, so only the sum is the crop's cost. Jobs that read another slide
    file under the same key (TADP's first, unreadable slide) are left out."""
    out = {}
    folders = sorted(glob.glob(os.path.join(results, "g2-cropper", "*-*")), key=job_id)
    for folder in folders:
        if not os.path.isfile(os.path.join(folder, "sizes.txt")):
            continue
        key = os.path.basename(folder).split("-")[0]
        m = SLIDE_RE.search(read_text(os.path.join(folder, "env.txt")))
        entry = {"name": m.group("name") if m else key, "folder": folder,
                 "verdict": (read_text(os.path.join(folder, "verdict.txt")).strip().splitlines() or ["n/a"])[-1]}
        for side, regex in (("zarr", STORE_RE), ("png", PNG_RE)):
            d = {"files": None, "dirs": None, "bytes": None}
            for line in read_text(os.path.join(folder, "sizes.txt")).splitlines():
                mm = regex.match(line)
                if mm:
                    d["files"], d["dirs"], d["bytes"] = (int(x) for x in mm.groups())
            t = read_json(os.path.join(folder, "timings-%s.json" % side)) or {}
            slide_file = crop_slide(os.path.join(folder, "crop-%s.log" % side)) or \
                crop_slide(os.path.join(folder, "crop-zarr.log"))
            runs = [f for f in folders if os.path.basename(f).split("-")[0] == key and
                    crop_slide(os.path.join(f, "crop-%s.log" % side)) == slide_file]
            secs = [run_seconds(os.path.join(f, "crop-%s.log" % side)) for f in runs]
            d["wall_seconds"] = sum(secs) if runs else t.get("total_seconds")
            # The newest job's PhaseTimer phases describe only its own (often resumed, near-empty) run; show the
            # per-job wall times that make up the sum instead.
            d["phases"] = {"job %s" % job_id(f): s for f, s in zip(runs, secs)} if runs else \
                {k: v.get("seconds") for k, v in (t.get("phases") or {}).items()}
            d["segments"] = None
            entry[side] = d
        out[key] = entry
    return out


def stage2(results):
    """{slide name: report.json} from the newest full-seg job per slide."""
    out = {}
    for folder in sorted(glob.glob(os.path.join(results, "full-seg", "*")), key=job_id):
        r = read_json(os.path.join(folder, "report.json"))
        if r:
            r["folder"] = folder
            out[r["slide"]] = r
    return out


def fmt_int(v):
    return "n/a" if v is None else "{:,}".format(v)


def fmt_bytes(v):
    if v is None:
        return "n/a"
    for unit, size in (("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)):
        if v >= size:
            return "%.2f %s" % (v / size, unit)
    return "%d B" % v


def fmt_time(s):
    if s is None:
        return "n/a"
    s = int(round(s))
    return "%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


def fmt_phases(phases):
    return ", ".join("%s %s" % (k, fmt_time(v)) for k, v in (phases or {}).items()) or "n/a"


def vs_png(png, zarr):
    parts = []
    if png.get("files") and zarr.get("files"):
        parts.append("files ÷%.0f" % (png["files"] / zarr["files"]))
    if png.get("bytes") and zarr.get("bytes"):
        parts.append("bytes ×%.2f" % (zarr["bytes"] / png["bytes"]))
    if png.get("wall_seconds") and zarr.get("wall_seconds"):
        parts.append("time ×%.2f" % (zarr["wall_seconds"] / png["wall_seconds"]))
    return ", ".join(parts) or "n/a"


def main(argv):
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        print("usage: python3 make_phase1_table.py <results folder>", file=sys.stderr)
        return 2
    results = argv[1]
    s1, s2 = stage1(results), stage2(results)
    keys = {e["name"]: k for k, e in s1.items()}
    slides = [(k, e["name"]) for k, e in sorted(s1.items())]
    slides += [(n, n) for n in sorted(s2) if n not in keys]
    rows, notes = [], []
    for key, name in slides:
        for stage, entry in (("① crop", s1.get(key)), ("② segment", s2.get(name))):
            if not entry:
                rows.append("| %s | %s | n/a | | | | | | | no results |" % (key, stage))
                continue
            for side in ("png", "zarr"):
                d = entry[side]
                rows.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                    key, stage, "PNG" if side == "png" else "Zarr", fmt_int(d.get("files")), fmt_int(d.get("dirs")),
                    fmt_bytes(d.get("bytes")), fmt_time(d.get("wall_seconds")), fmt_phases(d.get("phases")),
                    fmt_int(d.get("segments")) if stage.startswith("②") else "", vs_png(entry["png"], d) if side == "zarr" else ""))
        e1, e2 = s1.get(key), s2.get(name)
        note = "- **%s** `%s`:" % (key, name)
        if e1:
            note += " ① `%s`, %s." % (os.path.relpath(e1["folder"], results), e1["verdict"])
        if e2:
            k = e2.get("segment_key_overlap") or {}
            note += " ② `%s`, segment_key overlap (reported, not gated): both %s, only PNG %s, only Zarr %s." % (
                os.path.relpath(e2["folder"], results), fmt_int(k.get("both")), fmt_int(k.get("only_png")),
                fmt_int(k.get("only_zarr")))
        notes.append(note)
    text = "\n".join([
        "| Slide | Stage | Format | Files | Dirs | Bytes | Wall time | Phases (PhaseTimer) | Segments | Zarr vs PNG |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ] + rows + [""] + notes + [
        "",
        "Files and bytes: ① the tile tree / tile store; ② the output tree plus the CSV (`du -sb`). Wall time: the "
        "CLI process (GNU time). ① sums every G2 job that cropped the slide (a crop stopped by a kill or a time "
        "limit resumes in the next job; a run SLURM cancelled counts up to its last progress line), and the "
        "Phases column lists those jobs. Both ① sides write to Taiga. ② PNG is G1's run, ② Zarr reads ①'s Zarr "
        "store.",
    ]) + "\n"
    with open(os.path.join(results, "phase1-table.md"), "w") as f:
        f.write(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
