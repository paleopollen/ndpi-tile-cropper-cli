# Brief: Zarr vs HDF5 benchmark for tile storage (PALYIM stage ①)

Written 2026-10-28 by Rashmil's Claude session for the agent running the benchmark.
Read `palyim-ctx/CLAUDE.md` first, then `palyim-ctx/pipeline/tile-cropping.md` and
`palyim-ctx/infrastructure/storage.md`. The code is the source of truth; docs drift.

## Goal

Decide whether the pipeline should write tiles to a chunked container (Zarr, HDF5) instead of
loose PNGs, and with which layout. The driver is inodes, not bytes: `/work/hdd/bdar` on Delta is
over its file quota (soft 43.35 M, hard 47.685 M, used 44.83 M on 2026-10-22). Plane counts differ
by dataset: TADP slides have 21 focal planes, PAL1999 slides 9 or 10. A TADP slide is about
2,300 tiles × 21 planes = about 48,000 PNGs from tiling alone and about 340,000 crop files after
segmentation; a PAL slide is about 21,000 and 145,000. The local test slide is PAL, so read Z
from the file (`ome_metadata.z_plane`) and expect 9 or 10. PAL has 470+ slides.

Deliverable: a results table plus a one-page recommendation, brought to the Monday dev weekly
with Sandeep. Do not change any module repo without being asked; a prototype lives in a branch
and goes through a PR.

## What exists today (verified in code, 2026-10-28)

- `ndpi-tile-cropper-cli/src/ndpi_tile_cropper_cli.py` reads series 0 through Bio-Formats
  (`openBytesXYWH(z, x, y, w, h)`) and writes `<out>/<slide>/{x}x_{y}y/{z}z.png`, RGB uint8,
  plus `<out>/<slide>/metadata.json`. Branch `87-improve-tile-cropping-performance` (PR #24)
  is the version that cropped PAL1999; use it.
- Production parameters come from `palyim-snakemake-workflow/config/config.yaml`:
  `tile_size: 2048`, `tile_overlap: 256`. CLI defaults are 1024 / 0; do not benchmark those.
- Grid is `np.arange(0, W - size, size - overlap)`; the right and bottom edges are dropped.
  Match that grid so the comparison is like for like.
- `--zip` writes one uncompressed zip per slide and deletes the directory. It is the current
  inode workaround and belongs in the comparison as a baseline.
- Stage ② (`post-processing-cli-sam-2/src/post_processor.py`) finds tiles with
  `glob("<slide>/<tile>/*z.png")` and `filename.endswith("z.png")` in several places
  (around lines 118, 262, 660, 1091, 1141). That is the read side any new format must serve.

## Test input

Local slide, already on disk (5.8 GB):
`~/Documents/palyim/ndpi-tile-cropper-cli/data/PAL1999_B2_sample103_slide1 - 2023-01-11 08.16.52.ndpi`

Run everything locally in Docker on this Mac first (Sandeep's instruction, 2026-10-26). Delta
`/work` currently accepts no new files. If a full slide is too slow locally, crop a fixed
sub-region (for example the first 8 × 8 tiles at 2048 / 256, all Z) and use the same region for
every format. Record which region was used.

## Formats to compare

| ID | Format | Layout | Expected files per slide |
|---|---|---|---|
| A | PNG (today) | one dir per tile, one PNG per plane | about 21,000 (PAL, Z = 9); 48,000 on TADP |
| A-zip | PNG + `--zip` | one uncompressed zip | 1 |
| B | Zarr v2 or v3 | whole-slide array (Z, Y, X, 3), chunk (Z, 2048, 2048, 3) | about 2,300 (independent of Z) |
| C | Zarr v3 sharded | same array; shard (Z, 8·2048, 8·2048, 3), inner chunk (1, 2048, 2048, 3) | about 40 (independent of Z) |
| D | HDF5 | one dataset (Z, Y, X, 3), chunk (1, 2048, 2048, 3), Blosc via `hdf5plugin` | 1 |

Notes on B, C, D:
- Store the slide as one array, not one array per tile. The 256 px overlap then costs nothing
  on disk; readers take a window of 2048 at stride 1792. Today the overlap inflates bytes by
  about 30 percent (2048² / 1792²).
- Chunks must align to the storage grid (stride 2048, not 1792) so each write is a whole chunk
  with no read-modify-write.
- For C, one process must own and write a whole shard. Sharding needs `zarr>=3` (zarr-python 3,
  released 2025-01) or `tensorstore`. Zarr v2 cannot shard, so skip a v2 variant of C.
- Codec for B, C, D: Blosc, Zstd level 3, byte shuffle. Also run one variant of C with Blosc
  LZ4 to see the speed/size trade. Optional stretch: lossless JPEG 2000 or JPEG XL through
  `imagecodecs` if PNG wins on bytes by a wide margin.
- Also try `bioformats2raw` (Glencoe) on the NDPI straight to OME-Zarr. If it works it could
  replace the cropper's Bio-Formats loop. Check its version for Zarr v3 / sharding support
  before relying on it; record the version.

## Measurements (same slide or region for every row)

Write side:
1. Wall time to produce the output from the NDPI, end to end. Report the Bio-Formats read time
   separately if you can (time the `openBytesXYWH` calls), so encode cost is visible.
2. Bytes on disk (`du -s`), and file count (`find <out> -type f | wc -l`). The file count is
   the headline number.
3. Peak RSS of the writer.

Read side (cold cache where possible; on macOS run `sudo purge` or just use a region bigger
than RAM; say which you did):
4. Time to read one full tile stack (all Z for one tile, 2048 × 2048 × 3) as a numpy array,
   averaged over 50 random tiles. This is what stage ② does to build a MIP.
5. Time to read 1,000 random 256 × 256 windows across all Z. This is the classifier/clustering
   access pattern (segment crops).
6. Time to read a full plane (one Z, whole slide or whole region). This is the "can we view
   it" check.

Concurrency:
7. Write the output with 4 and 8 parallel workers (processes, each owning its own tiles or
   shards) and report wall time and whether any locking or serialisation was needed. HDF5 will
   probably need a single writer; say so if it does.

Report everything in one table, rows = formats, columns = measurements 1 to 7. Include the
Python, zarr, h5py, numcodecs, hdf5plugin and bioformats2raw versions and the Docker image used.

## Contract note (read this before writing any prototype)

Stages ② to ④ all read the PNG tree described in `palyim-ctx/pipeline/tile-cropping.md`
("Contract (output)"). `palyim-ctx/pipeline/overview.md` says, in the "File layout vs scale"
bullet: any change to a stage's on-disk layout alters the contracts in that file and must be
recorded there first.

So:
- The benchmark itself changes nothing and needs no contract edit.
- If you prototype a new output in the cropper, make it optional and additive (a new flag such
  as `--tile_format zarr`, default unchanged), so PNG consumers keep working.
- Before opening a PR that adds a format, write the proposed contract into
  `palyim-ctx/pipeline/overview.md` and `tile-cropping.md`: array shape and axis order, dtype,
  chunk and shard shapes, codec, where `metadata.json` content goes (Zarr attrs or kept as a
  file), how the 256 px overlap is expressed, and how stage ② locates a tile's z-stack. Keep
  the `{x}x_{y}y` tile key meaning (top-left px at full resolution) so segment IDs stay stable.
- Do not commit or push `palyim-ctx` without Rashmil's explicit OK; run
  `uv run tools/okf_lint.py` first. Never commit the NDPI, tiles or benchmark outputs anywhere.
- Open question to answer in the recommendation (`palyim-ctx/open-questions.md`, Rashmil's
  item): which module gets the container format first, tiles (①) or segments (②), and what
  the on-disk contract becomes for ③ and ④. Segments are the bigger inode consumer
  (about 340,000 vs 48,000 per slide), so say whether the tile result transfers to them.

## Out of scope

Running on Delta, changing the Snakemake workflow, merging anything, lossy compression as a
default, and pyramids / multiscale (the NDPI already has one; store level 0 only).
