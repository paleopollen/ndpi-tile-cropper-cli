"""Read one fixed region of the NDPI through Bio-Formats (same calls as ndpi_tile_cropper_cli.py)
into a raw uint8 memmap (Z, H, W, 3), timing every openBytesXYWH call.

Runs INSIDE the ndpi-tile-cropper:amd64 container (python-bioformats + JVM live there).
Two read patterns are timed:
  chunks : 2048-px chunks at stride 2048 (what a Zarr/HDF5 writer would read)   -> fills the memmap
  tiles  : 2048-px tiles at stride 1792 (what the PNG cropper reads today), read only, not stored
"""
import argparse, json, os, time
import numpy as np
import javabridge, bioformats
import bioformats.formatreader as format_reader
from bioformats import logback

p = argparse.ArgumentParser()
p.add_argument("--ndpi", required=True)
p.add_argument("--out", required=True, help="directory for region_raw.npy and read_timing.json")
p.add_argument("--x0", type=int, required=True); p.add_argument("--y0", type=int, required=True)
p.add_argument("--size", type=int, default=16384, help="region edge in px (multiple of 2048)")
p.add_argument("--tile", type=int, default=2048); p.add_argument("--overlap", type=int, default=256)
p.add_argument("--skip-tiles", action="store_true", help="skip the stride-1792 read pass")
a = p.parse_args()

javabridge.start_vm(class_path=bioformats.JARS, run_headless=True)
try:
    logback.basic_config()   # same as the CLI: silences Bio-Formats DEBUG output
    t0 = time.perf_counter()
    ome = bioformats.OMEXML(xml=bioformats.get_omexml_metadata(a.ndpi))
    Z = ome.image().Pixels.SizeZ
    meta_s = time.perf_counter() - t0
    ImageReader = format_reader.make_image_reader_class()
    reader = ImageReader()
    t0 = time.perf_counter(); reader.setId(a.ndpi); setid_s = time.perf_counter() - t0
    S, T, step = a.size, a.tile, a.tile - a.overlap
    os.makedirs(a.out, exist_ok=True)
    mm = np.lib.format.open_memmap(os.path.join(a.out, "region_raw.npy"), mode="w+",
                                   dtype=np.uint8, shape=(Z, S, S, 3))
    timing = {"z_planes": Z, "region": {"x0": a.x0, "y0": a.y0, "size": S}, "metadata_s": meta_s,
              "setId_s": setid_s, "chunk_reads": [], "tile_reads": []}
    # pass 1: aligned 2048 chunks -> memmap
    n = S // T
    t_pass = time.perf_counter()
    for z in range(Z):
        for j in range(n):
            for i in range(n):
                x, y = a.x0 + i * T, a.y0 + j * T
                t0 = time.perf_counter()
                img = reader.openBytesXYWH(z, x, y, T, T); img.shape = (T, T, 3)
                dt = time.perf_counter() - t0
                mm[z, j*T:(j+1)*T, i*T:(i+1)*T, :] = img
                timing["chunk_reads"].append(dt)
        mm.flush(); print(f"z={z} done, {len(timing['chunk_reads'])} chunk reads", flush=True)
    timing["chunk_pass_wall_s"] = time.perf_counter() - t_pass
    # pass 2: the cropper's own grid (stride 1792) over the same pixels, read only
    if not a.skip_tiles:
        xs = list(range(a.x0, a.x0 + S - T + 1, step)); ys = list(range(a.y0, a.y0 + S - T + 1, step))
        t_pass = time.perf_counter()
        for x in xs:
            for y in ys:
                for z in range(Z):
                    t0 = time.perf_counter()
                    img = reader.openBytesXYWH(z, x, y, T, T)
                    timing["tile_reads"].append(time.perf_counter() - t0)
        timing["tile_pass_wall_s"] = time.perf_counter() - t_pass
        timing["tile_grid"] = {"xs": xs, "ys": ys}
    reader.close()
    with open(os.path.join(a.out, "read_timing.json"), "w") as f:
        json.dump(timing, f)
    cr = timing["chunk_reads"]; print(f"chunk reads: n={len(cr)} mean={sum(cr)/len(cr):.3f}s total={sum(cr):.0f}s")
    if timing["tile_reads"]:
        tr = timing["tile_reads"]; print(f"tile reads: n={len(tr)} mean={sum(tr)/len(tr):.3f}s total={sum(tr):.0f}s")
finally:
    javabridge.kill_vm()
