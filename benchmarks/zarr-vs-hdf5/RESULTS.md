# Zarr vs HDF5 for tile storage (PALYIM stage ①): benchmark results

Run 2026-10-28 on Rashmil's M1 MacBook (8 cores, 16 GB) following `../zarr-benchmark-brief.md`.
Scripts in `scripts/`, raw numbers in `results/*.jsonl` and `results/read_timing.json`.

## Setup

- **Slide:** `PAL1999_B2_sample103_slide1 - 2023-01-11 08.16.52.ndpi` (5.4 GB), 134912 × 90624 px, **9 focal planes**
  (the brief assumed about 21; PAL1999 slides have 9, TADP slides have about 21, so file counts below scale ×2.3 for TADP).
- **Region:** 16384 × 16384 px starting at x=71680, y=43008 (tile columns 40–48, rows 24–32 on the production
  2048/256 grid), chosen as a content-rich window by per-tile pixel-std on the 1/8-scale plane (the std map and thumbnail are kept
  outside the repo). The start is a multiple of both 1792 and 2048, so the **9 × 9 overlapping PNG tiles** (stride 1792)
  and the **8 × 8 storage chunks** (stride 2048) cover exactly the same pixels. Raw size 9 × 16384² × 3 = 7.25 GB.
- **Read side (Bio-Formats):** `scripts/extract_region.py` inside `ndpi-tile-cropper:amd64` (the repo's Dockerfile built
  with `--platform linux/amd64`; python-bioformats 4.0.7, Bio-Formats 6.11.1, JDK 17, Python 3.9), same
  `openBytesXYWH` calls as the cropper, every call timed. Two passes: aligned 2048 chunks (what an array writer
  needs) and the cropper's own 1792-stride grid (what the PNG output costs). Output: `region_raw.npy` memmap.
- **Write side:** `scripts/write_formats.py`, native arm64, Python 3.14.7, zarr 3.4.2, numcodecs 0.17.1, h5py 3.16.0
  (HDF5 2.0.0), hdf5plugin 7.1.0, numpy 2.5.4, Pillow 13.0.0. Each format is written from the memmap; wall time,
  peak RSS (parent and largest child), bytes and file count recorded. The PNG path uses `Image.fromarray(...).save()`
  exactly as the CLI does (zlib level 6), and `png-zip` stores the tree with `ZIP_STORED` like `--zip`.
- **Why two environments:** the JVM only decodes NDPI on x86_64 (no arm64 libturbojpeg in Bio-Formats), so reads run
  under Rosetta emulation and are slow in absolute terms; the encoders run natively. The *read* column is therefore
  pessimistic and the *encode* columns optimistic relative to Delta. Compare formats against each other, not
  against Delta wall clocks.
- **Read benchmarks:** `scripts/read_bench.py`, warm page cache (no `sudo purge`; the 7 GB raw file plus outputs
  exceed what stays cached, but no cold guarantee). Items: 50 random full tile stacks (Z, 2048, 2048, 3); 1000 random
  256 × 256 × Z windows; one full plane.
- **Concurrency:** `ProcessPoolExecutor`, each worker opens the memmap and the store itself; Zarr workers write
  whole chunks (B) or whole shards (C). No locks. HDF5 via h5py has a single writer (no MPI build); 4-worker HDF5
  is reported as not supported.
- **Sharding note:** the brief's shard (Z, 8·2048, 8·2048, 3) is the whole 7.25 GB region in one shard; zarr-python
  encodes a shard in memory and rewrites it whole on any partial write, so a shard must be written by one process in
  one go. For a 21-plane TADP slide that is 17 GB per shard. The benchmark therefore uses shards of 4 × 4 chunks
  (1.8 GB per shard, 4 shards) for C, plus a per-plane variant C-z with shards (1, 8·2048, 8·2048, 3) (0.8 GB per
  shard, 9 shards) which keeps one shard per plane per 8 × 8 block.
- **bioformats2raw:** `openmicroscopy/bioformats2raw:latest` = 0.9.1 (Bio-Formats 7.1.0). It writes **Zarr v2 /
  OME-Zarr 0.4** only (no `--zarr-format` option, no sharding). Run on series 1 (the 1/8-scale pyramid level, 9 ×
  11328 × 16864 × 3) because the full-resolution series would be about 330 GB raw.

## Results

Region: x0=71680 y0=43008 size=16384 px, Z=9; raw 7.25 GB; setId 0.7 s; Bio-Formats read 2048² chunk: n=576 mean 0.171 s median 0.115 s, pass total 99 s of reads (313 s wall including writing the 7.2 GB memmap through the Docker bind mount)
Bio-Formats read on the cropper's 1792-stride grid: n=729 mean 0.130 s, pass total 95 s (= read cost of today's PNG output for this region: 81 tiles)

| Format | files | GB on disk | encode wall 1w (s) | end-to-end est. 1w (s) | peak RSS MB (parent/child) | 4 workers (s) | 8 workers (s) | tile stack (s) | 256² window ×Z (ms) | full plane (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| A PNG tree | 730 | 1.11 | 354 | 449 | 1001/0 | 123 | 83 | 0.461 | 481.6 | 4.8 |
| A-zip PNG + zip | 1 | 1.11 | 397 | 492 | 930/0 | n/a | n/a | – | – | – |
| B Zarr v3 chunked | 65 | 1.35 | 106 | 204 | 1322/0 | 54 | 43 | 0.111 | 92.7 | 2.5 |
| C Zarr v3 sharded 4×4 zstd | 5 | 1.35 | 77 | 175 | 1579/0 | 24 | n/a | 0.069 | 27.7 | 0.9 |
| C-lz4 Zarr v3 sharded 4×4 lz4 | 5 | 2.82 | 78 | 177 | 1924/0 | n/a | n/a | 0.061 | 21.5 | 1.1 |
| C-z Zarr v3 sharded per plane 8×8 | 10 | 1.35 | 44 | 143 | 1515/0 | 27 | 59 | 0.067 | 28.1 | 0.7 |
| D HDF5 blosc-zstd | 1 | 1.35 | 73 | 172 | 1118/1 | n/a | n/a | 0.285 | 108.9 | 0.9 |

end-to-end est. = Bio-Formats read pass (99 s aligned chunks; 95 s on the 1792 grid for PNG) + encode wall (native arm64).

Reading the columns: *encode wall* is the native write of the region from the raw memmap; *end-to-end est.* adds
the Bio-Formats read pass measured in the container (99 s for the 64 aligned chunks × 9 planes; 95 s for the 81
overlapping tiles × 9 that the PNG output needs). *4 / 8 workers* is the encode wall with that many processes;
"n/a" = fewer blocks than workers (C has 4 shards) or not supported (HDF5 single writer). Read columns are warm cache.

**Per-slide extrapolation (file counts are the headline):**

| | PNG tree (today) | PNG + `--zip` | B Zarr chunked | C Zarr sharded 4×4 | C-z Zarr sharded per plane 8×8 | D HDF5 |
|---|---|---|---|---|---|---|
| This PAL slide, 66 × 45 chunks, Z = 9 | 33,750 files + 3,750 dirs | 1 | ~3,000 | 204 | 486 | 1 |
| TADP slide, ~43 × 43 chunks, Z ≈ 21 | ~50,400 + 2,400 dirs | 1 | ~1,850 | 121 | 756 | 1 |
| Bytes vs PNG, same pixels | 1.00 | 1.00 | 1.21 | 1.21 | 1.21 | 1.21 |

Bytes: Blosc-zstd-3 is 21 percent larger than PNG for the same region, but PNG also stores the 256 px overlap
(81 tiles for 64 chunks' worth of pixels), so per stored pixel zstd is about 1.5× PNG. Bytes are not the
constraint on Delta (2.1 TB used of 24 TB); files are.

**Concurrency (item 7):** Zarr B and C needed no locking: each process writes whole chunks or whole shards to its own
files. PNG scales the same way (one process per tile). HDF5 through h5py is a single writer (no MPI build; SWMR is
read-side only), so parallel HDF5 would mean one file per worker and a merge, or MPI-HDF5. The 8-worker C-z run was
slower than 4 workers (59 s vs 27 s): eight 0.8 GB shards in flight plus compression buffers exceeded what this
16 GB laptop could hold alongside Docker; on a Delta node this is not a concern, but shard size × workers is the
memory budget to size.

**bioformats2raw 0.9.1** (Bio-Formats 7.1.0) reads this NDPI (`--series 0`, 4 reader workers) but writes only
Zarr v2 / OME-NGFF 0.4: one file per chunk per plane and no sharding, i.e. the same file count as B, and it cannot
cut a sub-region. Note Bio-Formats numbers the NDPI pyramid as resolutions of series 0 (series 1 is the macro
image, series 2 the map), unlike tifffile. Throughput: see `results/b2r_series0_throughput.txt`. Probe on series 0 (full resolution, 4 workers, stopped after 180 s): first chunk after 10 s, then **6.7 chunk files/s** (2048² × 1 plane each, about 85 MB/s raw), i.e. about 66 min for this 9-plane slide under emulation. The branch cropper manages 1.9 plane-chunks/s on one core, so bioformats2raw's pooled readers are worth about 3.5× here, which supports the "several readers on one NDPI" route for the cropper; but its output would still need re-sharding.


## Recommendation

**Use Zarr v3 with per-plane shards (variant C-z): shape (Z, H, W, 3) uint8, inner chunk (1, 2048, 2048, 3),
shard (1, 16384, 16384, 3), Blosc zstd level 3 with byte shuffle.**

Why this and not the others:
- **Files:** 486 per PAL slide and about 750 per TADP slide instead of 37,500 and 52,800. C (4 × 4 shards over all
  Z) gets to 200, but its shard is Z × 0.2 GB: 1.8 GB here and 4.2 GB for a 21-plane TADP slide, which has to sit in
  one process's memory per write. Per-plane shards stay at 0.8 GB whatever Z is, and give Z × blocks independent
  write units for free. HDF5 wins on file count (1) but loses on everything else below.
- **Write speed:** 44 s to encode the region versus 354 s for PNG (8×); end to end 143 s versus 449 s (3×). This is
  also the answer to the cropper's remaining cost: PNG encode is three quarters of its per-tile time.
- **Read speed:** a tile z-stack in 0.07 s versus 0.46 s from PNGs (7×), a 256 px window across Z in 28 ms versus
  480 ms (17×, because the PNG reader has to decode 9 whole tiles), a full plane in 0.7 s versus 4.8 s. HDF5 reads
  a z-stack in 0.29 s: h5py's per-chunk filter pipeline is slower than zarr's, though full-plane reads match.
- **Parallel writes** with no coordination (whole shards per process); HDF5 would need a single writer.
- **Open format with a viewer path:** OME-NGFF 0.5 (Nov 2024) is Zarr v3 with sharding, so the array can be wrapped
  as OME-Zarr for napari / Neuroglancer / vizarr. Sandeep's "need a viewer for spot checks" is answerable, but which
  viewer versions read sharded v3 today is **not verified here**.
- **Not chosen:** B (chunked, 3,000 files) only halves the problem; lz4 doubles bytes for no speed; `--zip` keeps
  the inode win but is the slowest to write and cannot be read by stage ② without unzipping.

Costs and caveats:
- 21 percent more bytes than PNG for the same pixels (1.5× per stored pixel). If bytes ever matter, JPEG-XL or
  JPEG 2000 lossless through `imagecodecs` as a Zarr codec is the next experiment, not lz4.
- Single slide, single region (content-rich, so compression ratios are conservative for blank slide edges).
- Reads measured warm; cold-cache numbers on Delta's Lustre will differ in absolute terms. The relative order is
  unlikely to change: PNG pays a full-tile decode for every access, the chunked formats do not.
- Reads ran under x86 emulation, encodes natively; compare formats to each other, not to Delta wall clocks.
- zarr-python 3 rewrites a whole shard on any partial write, so a shard must be written by exactly one process in
  one call. The prototype must assign shards, not tiles, to workers.

What the on-disk contract would become (to be written into `pipeline/overview.md` and `tile-cropping.md` before any
PR, per the brief):
- `<out>/<slide>.zarr`: one array `tiles` (or the OME-Zarr `0` level), axes `zyxc`, uint8, level 0 only, chunk
  (1, 2048, 2048, 3), shard (1, 16384, 16384, 3), blosc-zstd-3-shuffle, fill 0.
- `metadata.json` content goes into the array attributes (`tile_size`, `tile_overlap`, `ome_metadata`, progress
  fields) and is also kept as a file next to the store while stage ② still reads it.
- The `{x}x_{y}y` tile key keeps its meaning (top-left px at full resolution): a tile's z-stack is
  `arr[:, y:y+2048, x:x+2048, :]`. The 256 px overlap is no longer stored; readers take a 2048 window at stride 1792.
  The right and bottom strips that today's grid drops are stored, so consumers can choose to use them.
- Resume: a shard either exists or not; progress = shards present / shards expected.

Which module first (open question, Rashmil's item): **tiles (①) first**, because the writer is a regular grid, the
contract is one array, and stage ② has five `*z.png` glob sites to switch to one array read. The inode win there is
37,500 files per PAL slide. **Segments (②) are the bigger win (about 340,000 files per TADP slide) but need their own
layout**, since crops are ragged: pad to a fixed crop size (or a few size classes) into an array (N, Z, h, w, 3) with
a table of (tile key, bbox, segment id), sharded along N. The tile result transfers in the sense that the codec,
sharding and read patterns carry over; the shape does not. Proposal: prototype `--tile_format zarr` in the cropper
(optional, additive), teach stage ② to read it, then design the segment container with what we learn.

