"""Build the results table (markdown) from write_results.jsonl, read_results.jsonl and read_timing.json."""
import json, os, sys, statistics as st
R = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
W = [json.loads(l) for l in open(os.path.join(R, "write_results.jsonl"))]
RD = [json.loads(l) for l in open(os.path.join(R, "read_results.jsonl"))] if os.path.exists(os.path.join(R, "read_results.jsonl")) else []
tm = json.load(open(os.path.join(R, "read_timing.json")))
cr, tr = tm["chunk_reads"], tm.get("tile_reads", [])
Z = tm["z_planes"]; S = tm["region"]["size"]
print(f"Region: x0={tm['region']['x0']} y0={tm['region']['y0']} size={S} px, Z={Z}; raw {Z*S*S*3/1e9:.2f} GB; "
      f"setId {tm['setId_s']:.1f} s; Bio-Formats read 2048² chunk: n={len(cr)} mean {st.mean(cr):.3f} s median {st.median(cr):.3f} s, "
      f"pass total {tm['chunk_pass_wall_s']:.0f} s")
if tr: print(f"Bio-Formats read on the cropper's 1792-stride grid: n={len(tr)} mean {st.mean(tr):.3f} s, pass total {tm['tile_pass_wall_s']:.0f} s "
             f"(= read cost of today's PNG output for this region: {len(tr)//Z} tiles)")
print()
names = {"png": "A PNG tree", "png-zip": "A-zip PNG + zip", "zarr-b": "B Zarr v3 chunked", "zarr-c": "C Zarr v3 sharded 4×4 zstd",
         "zarr-c-lz4": "C-lz4 Zarr v3 sharded 4×4 lz4", "zarr-c-z": "C-z Zarr v3 sharded per plane 8×8", "hdf5": "D HDF5 blosc-zstd"}
def w(fmt, n):
    for r in W:
        if r["format"] == fmt and r["workers"] == n: return r
def rd(fmt, label="warm"):
    for r in RD:
        if r["label"] == label and os.path.basename(r["path"]).startswith(fmt + "_w1"): return r
read_s = st.mean(cr) * len(cr)   # aligned-chunk read of the region (what B/C/D need)
read_png_s = st.mean(tr) * len(tr) if tr else None
print("| Format | files | GB on disk | encode wall 1w (s) | end-to-end est. 1w (s) | peak RSS MB (parent/child) | 4 workers (s) | 8 workers (s) | tile stack (s) | 256² window ×Z (ms) | full plane (s) |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for fmt, name in names.items():
    r1 = w(fmt, 1)
    if not r1: continue
    r4, r8, rr = w(fmt, 4), w(fmt, 8), rd(fmt)
    rs = read_png_s if fmt.startswith("png") and read_png_s else read_s
    def c(r): return "n/a" if not r or "skipped" in r["info"] else f"{r['wall_s']:.0f}"
    e2e = f"{rs + r1['wall_s']:.0f}"
    rcols = f"{rr['tile_stack_s']:.3f} | {rr['window256_s']*1e3:.1f} | {rr['plane_s']:.1f}" if rr else "– | – | –"
    print(f"| {name} | {r1['files']} | {r1['GB']:.2f} | {r1['wall_s']:.0f} | {e2e} | {r1['peak_rss_parent_MB']}/{r1['peak_rss_max_child_MB']} | {c(r4)} | {c(r8)} | {rcols} |")
print(f"\nend-to-end est. = Bio-Formats read pass ({read_s:.0f} s aligned chunks; {read_png_s:.0f} s on the 1792 grid for PNG) + encode wall (native arm64)." if read_png_s else "")
