"""Write the extracted region (region_raw.npy, uint8 (Z,S,S,3)) in each candidate format and
measure wall time, peak RSS, bytes on disk and file count.  Runs natively (uv env).

formats:
  png        one dir per tile (stride 1792, 2048 px), one PNG per plane  (= today's cropper output)
  png-zip    the png tree stored into one uncompressed zip (= cropper --zip), tree removed
  zarr-b     Zarr v3, chunks (Z,T,T,3), Blosc zstd-3 shuffle                [brief: B]
  zarr-c     Zarr v3 sharded, shard (Z,4T,4T,3), inner chunk (1,T,T,3), zstd [brief: C, 4x4 shard]
  zarr-c-lz4 same as zarr-c with Blosc lz4
  zarr-c-z   Zarr v3 sharded per plane: shard (1,8T,8T,3), inner (1,T,T,3), zstd
  hdf5       one dataset (Z,S,S,3), chunks (1,T,T,3), Blosc zstd-3 via hdf5plugin [brief: D]
"""
import argparse, json, os, resource, shutil, sys, time, zipfile
from concurrent.futures import ProcessPoolExecutor
import numpy as np

T = 2048; STEP = 1792
RAW = None  # memmap, opened per process

def _open(raw):
    global RAW
    if RAW is None:
        RAW = np.load(raw, mmap_mode="r")
    return RAW

def tree_stats(path):
    n = 0; b = 0
    if os.path.isfile(path):
        return 1, os.path.getsize(path)
    for root, dirs, files in os.walk(path):
        for f in files:
            n += 1; b += os.path.getsize(os.path.join(root, f))
    return n, b

# ---------- PNG ----------
def png_tile(args):
    raw, out, x0, y0, i, j = args
    from PIL import Image
    a = _open(raw); Z = a.shape[0]
    d = os.path.join(out, f"{x0 + i*STEP}x_{y0 + j*STEP}y"); os.makedirs(d, exist_ok=True)
    for z in range(Z):
        Image.fromarray(np.ascontiguousarray(a[z, j*STEP:j*STEP+T, i*STEP:i*STEP+T, :])).save(os.path.join(d, f"{z}z.png"))
    return 1

def write_png(raw, out, x0, y0, workers, meta):
    a = _open(raw); S = a.shape[1]; n = (S - T) // STEP + 1
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "metadata.json"), "w") as f: json.dump(meta, f, indent=4)
    tasks = [(raw, out, x0, y0, i, j) for i in range(n) for j in range(n)]
    if workers == 1:
        for t in tasks: png_tile(t)
    else:
        with ProcessPoolExecutor(workers) as ex: list(ex.map(png_tile, tasks, chunksize=4))
    return {"tiles": n*n, "grid": f"{n}x{n} @ stride {STEP}"}

def write_png_zip(raw, out, x0, y0, workers, meta):
    tree = out + "_tree"
    t0 = time.perf_counter(); info = write_png(raw, tree, x0, y0, workers, meta); t_png = time.perf_counter() - t0
    t0 = time.perf_counter()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as zf:   # as zip_tiles() in the CLI
        for root, dirs, files in os.walk(tree):
            for f in files: zf.write(os.path.join(root, f), os.path.relpath(os.path.join(root, f), tree))
    shutil.rmtree(tree)
    info.update({"png_s": t_png, "zip_s": time.perf_counter() - t0}); return info

# ---------- Zarr ----------
def zarr_codec(cname):
    from zarr.codecs import BloscCodec
    return BloscCodec(cname=cname, clevel=3, shuffle="shuffle")

def zarr_create(out, shape, chunks, shards, cname, meta):
    import zarr
    arr = zarr.create_array(store=out, shape=shape, chunks=chunks, shards=shards, dtype="uint8",
                            compressors=zarr_codec(cname), zarr_format=3, fill_value=0,
                            dimension_names=("z", "y", "x", "c"), overwrite=True)
    arr.attrs.update(meta); return arr

def zarr_block(args):
    raw, out, z0, z1, y0, y1, x0, x1 = args
    import zarr
    a = _open(raw); arr = zarr.open_array(out, mode="r+")
    arr[z0:z1, y0:y1, x0:x1, :] = a[z0:z1, y0:y1, x0:x1, :]
    return 1

def write_zarr(raw, out, x0, y0, workers, meta, variant, cs=4, czs=8):
    a = _open(raw); Z, S = a.shape[0], a.shape[1]
    assert S % (cs*T) == 0 and S % (czs*T) == 0, f"region {S} not a multiple of shard edges {cs*T}/{czs*T}"
    shape = (Z, S, S, 3)
    if variant == "zarr-b":
        chunks, shards, cname = (Z, T, T, 3), None, "zstd"
        blocks = [(raw, out, 0, Z, j*T, (j+1)*T, i*T, (i+1)*T) for j in range(S//T) for i in range(S//T)]
    elif variant in ("zarr-c", "zarr-c-lz4"):
        chunks, shards, cname = (1, T, T, 3), (Z, cs*T, cs*T, 3), ("lz4" if variant.endswith("lz4") else "zstd")
        blocks = [(raw, out, 0, Z, j*cs*T, (j+1)*cs*T, i*cs*T, (i+1)*cs*T) for j in range(S//(cs*T)) for i in range(S//(cs*T))]
    elif variant == "zarr-c-z":
        chunks, shards, cname = (1, T, T, 3), (1, czs*T, czs*T, 3), "zstd"
        blocks = [(raw, out, z, z+1, j*czs*T, (j+1)*czs*T, i*czs*T, (i+1)*czs*T) for z in range(Z) for j in range(S//(czs*T)) for i in range(S//(czs*T))]
    else: raise ValueError(variant)
    zarr_create(out, shape, chunks, shards, cname, meta)
    if workers == 1:
        for b in blocks: zarr_block(b)
    else:
        with ProcessPoolExecutor(workers) as ex: list(ex.map(zarr_block, blocks))
    return {"chunks": chunks, "shards": shards, "codec": f"blosc-{cname}-3-shuffle", "blocks": len(blocks)}

# ---------- HDF5 ----------
def write_hdf5(raw, out, x0, y0, workers, meta):
    import h5py, hdf5plugin
    a = _open(raw); Z, S = a.shape[0], a.shape[1]
    if workers != 1:
        return {"skipped": "h5py without MPI/SWMR has a single writer; parallel writers not supported"}
    with h5py.File(out, "w") as f:
        ds = f.create_dataset("tiles", shape=(Z, S, S, 3), dtype="uint8", chunks=(1, T, T, 3),
                              **hdf5plugin.Blosc(cname="zstd", clevel=3, shuffle=hdf5plugin.Blosc.SHUFFLE))
        for k, v in meta.items(): ds.attrs[k] = json.dumps(v) if isinstance(v, (dict, list)) else v
        for z in range(Z):
            for j in range(S//T):
                for i in range(S//T):
                    ds[z, j*T:(j+1)*T, i*T:(i+1)*T, :] = a[z, j*T:(j+1)*T, i*T:(i+1)*T, :]
    return {"chunks": (1, T, T, 3), "codec": "blosc-zstd-3-shuffle"}

WRITERS = {"png": write_png, "png-zip": write_png_zip, "hdf5": write_hdf5}

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--raw", required=True); p.add_argument("--outdir", required=True)
    p.add_argument("--format", required=True, choices=["png", "png-zip", "zarr-b", "zarr-c", "zarr-c-lz4", "zarr-c-z", "hdf5"])
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--x0", type=int, required=True); p.add_argument("--y0", type=int, required=True)
    p.add_argument("--results", required=True, help="jsonl file to append to")
    p.add_argument("--keep", action="store_true", help="keep the output (default: delete after measuring)")
    p.add_argument("--c-shard", type=int, default=4, help="zarr-c shard edge in chunks")
    p.add_argument("--cz-shard", type=int, default=8, help="zarr-c-z shard edge in chunks")
    a = p.parse_args()
    raw = _open(a.raw); Z, S = raw.shape[0], raw.shape[1]
    meta = {"tile_size": T, "tile_overlap": T - STEP, "region": {"x0": a.x0, "y0": a.y0, "size": S},
            "ome_metadata": {"width": 134912, "height": 90624, "z_plane": Z, "calibration": 0.22507314877335133, "calibration_unit": "µm"},
            "axes": "zyxc", "storage_grid": T, "source": "PAL1999_B2_sample103_slide1"}
    ext = {"png": "", "png-zip": ".zip", "hdf5": ".h5"}.get(a.format, ".zarr")
    out = os.path.join(a.outdir, f"{a.format}_w{a.workers}{ext}")
    if os.path.exists(out): shutil.rmtree(out) if os.path.isdir(out) else os.remove(out)
    os.makedirs(a.outdir, exist_ok=True)
    t0 = time.perf_counter()
    if a.format.startswith("zarr"): info = write_zarr(a.raw, out, a.x0, a.y0, a.workers, meta, a.format, a.c_shard, a.cz_shard)
    else: info = WRITERS[a.format](a.raw, out, a.x0, a.y0, a.workers, meta)
    wall = time.perf_counter() - t0
    rss_self = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss; rss_child = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    if sys.platform == "darwin": rss_self /= 1e6; rss_child /= 1e6     # bytes -> MB
    else: rss_self /= 1e3; rss_child /= 1e3                            # kB -> MB
    nfiles, nbytes = tree_stats(out) if "skipped" not in info else (0, 0)
    rec = {"format": a.format, "workers": a.workers, "wall_s": round(wall, 2), "files": nfiles, "bytes": nbytes,
           "GB": round(nbytes/1e9, 3), "peak_rss_parent_MB": round(rss_self), "peak_rss_max_child_MB": round(rss_child),
           "raw_GB": round(Z*S*S*3/1e9, 3), "out": out, "info": info}
    print(json.dumps(rec))
    with open(a.results, "a") as f: f.write(json.dumps(rec) + "\n")
    if not a.keep and "skipped" not in info:
        shutil.rmtree(out) if os.path.isdir(out) else os.remove(out)
