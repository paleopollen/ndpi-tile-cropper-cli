"""Read-side measurements on one written output (brief items 4, 5, 6).
  4: full tile z-stack (Z,2048,2048,3) for N random tiles on the stride-1792 grid
  5: M random 256x256 windows, all Z
  6: one full plane
Page cache is NOT dropped (needs sudo purge); pass --label to record warm/cold.
"""
import argparse, glob, json, os, random, time
import numpy as np

T = 2048; STEP = 1792

class PNGReader:
    def __init__(self, path, meta):
        from PIL import Image; self.Image = Image
        self.path = path; self.x0 = meta["region"]["x0"]; self.y0 = meta["region"]["y0"]; self.Z = meta["ome_metadata"]["z_plane"]
        self.n = (meta["region"]["size"] - T) // STEP + 1
    def tile_dir(self, i, j): return os.path.join(self.path, f"{self.x0+i*STEP}x_{self.y0+j*STEP}y")
    def stack(self, i, j):   # what stage 2 does: glob *z.png, open each
        files = sorted(glob.glob(os.path.join(self.tile_dir(i, j), "*z.png")), key=lambda p: int(os.path.basename(p)[:-5]))
        return np.stack([np.asarray(self.Image.open(f)) for f in files])
    def window(self, y, x, h, w):   # window in region px; falls inside one grid tile by construction
        i = min(x // STEP, self.n - 1); j = min(y // STEP, self.n - 1)
        s = self.stack(i, j); return s[:, y - j*STEP:y - j*STEP + h, x - i*STEP:x - i*STEP + w, :]
    def plane(self, z):   # decode plane z of every tile (overlap discarded by taking the stride area)
        S = (self.n - 1) * STEP + T; out = np.empty((S, S, 3), np.uint8)
        for j in range(self.n):
            for i in range(self.n):
                a = np.asarray(self.Image.open(os.path.join(self.tile_dir(i, j), f"{z}z.png")))
                out[j*STEP:j*STEP+T, i*STEP:i*STEP+T] = a
        return out

class ArrayReader:
    def __init__(self, arr, meta):
        self.a = arr; self.x0 = meta["region"]["x0"]; self.y0 = meta["region"]["y0"]; self.Z = arr.shape[0]
        self.n = (arr.shape[1] - T) // STEP + 1
    def stack(self, i, j): return np.asarray(self.a[:, j*STEP:j*STEP+T, i*STEP:i*STEP+T, :])
    def window(self, y, x, h, w): return np.asarray(self.a[:, y:y+h, x:x+w, :])
    def plane(self, z): return np.asarray(self.a[z])

def open_reader(path):
    if path.endswith(".zarr"):
        import zarr; a = zarr.open_array(path, mode="r"); meta = dict(a.attrs); return ArrayReader(a, meta), meta
    if path.endswith(".h5"):
        import h5py, hdf5plugin; f = h5py.File(path, "r"); ds = f["tiles"]
        meta = {k: (json.loads(v) if isinstance(v, str) and v[:1] in "{[" else v) for k, v in ds.attrs.items()}
        return ArrayReader(ds, meta), meta
    meta = json.load(open(os.path.join(path, "metadata.json"))); return PNGReader(path, meta), meta

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("path"); p.add_argument("--results", required=True); p.add_argument("--label", default="warm")
    p.add_argument("--tiles", type=int, default=50); p.add_argument("--windows", type=int, default=1000); p.add_argument("--seed", type=int, default=0)
    a = p.parse_args(); random.seed(a.seed)
    r, meta = open_reader(a.path); S = (r.n - 1) * STEP + T
    # 4: random tile stacks
    picks = [(random.randrange(r.n), random.randrange(r.n)) for _ in range(a.tiles)]
    t0 = time.perf_counter()
    for i, j in picks: s = r.stack(i, j); assert s.shape == (r.Z, T, T, 3), s.shape
    t_stack = (time.perf_counter() - t0) / a.tiles
    # 5: random 256 windows (kept inside one grid tile so PNG reads one stack)
    wins = []
    for _ in range(a.windows):
        i, j = random.randrange(r.n), random.randrange(r.n)
        wins.append((j*STEP + random.randrange(T - 256), i*STEP + random.randrange(T - 256)))
    t0 = time.perf_counter()
    for y, x in wins: w = r.window(y, x, 256, 256); assert w.shape == (r.Z, 256, 256, 3), w.shape
    t_win = (time.perf_counter() - t0) / a.windows
    # 6: full plane
    t0 = time.perf_counter(); pl = r.plane(r.Z // 2); t_plane = time.perf_counter() - t0; assert pl.shape[:2] == (S, S)
    rec = {"path": a.path, "label": a.label, "tile_stack_s": round(t_stack, 4), "window256_s": round(t_win, 5),
           "plane_s": round(t_plane, 2), "n_tiles": a.tiles, "n_windows": a.windows}
    print(json.dumps(rec)); open(a.results, "a").write(json.dumps(rec) + "\n")
