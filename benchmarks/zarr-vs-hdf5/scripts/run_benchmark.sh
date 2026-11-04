#!/bin/bash
# Full write/read benchmark on the extracted region. Usage: run_benchmark.sh <data_dir> [x0] [y0]
# data_dir must hold region_raw.npy (from extract_region.py). Outputs land in <data_dir>/out and ../results.
set -u
B=$(cd "$(dirname "$0")/.." && pwd); D=$1; X0=${2:-71680}; Y0=${3:-43008}
R="$B/results"; W="$R/write_results.jsonl"; RD="$R/read_results.jsonl"; LOG="$R/run_benchmark.log"
cd "$B"; echo "=== $(date) start" >> "$LOG"
wf() { uv run python scripts/write_formats.py --raw "$D/region_raw.npy" --outdir "$D/out" --x0 "$X0" --y0 "$Y0" --results "$W" "$@" 2>&1 | tail -1 | tee -a "$LOG"; }
# single-worker writes, kept for the read benchmark
for f in png png-zip zarr-b zarr-c zarr-c-lz4 zarr-c-z hdf5; do wf --format $f --workers 1 --keep; done
# read side (warm page cache; rerun with --label cold after `sudo purge` if wanted)
for o in png_w1 zarr-b_w1.zarr zarr-c_w1.zarr zarr-c-lz4_w1.zarr zarr-c-z_w1.zarr hdf5_w1.h5; do
  uv run python scripts/read_bench.py "$D/out/$o" --results "$RD" --label warm 2>&1 | tail -1 | tee -a "$LOG"
done
# concurrency: outputs deleted after measuring
for n in 4 8; do for f in png zarr-b; do wf --format $f --workers $n; done; done
wf --format zarr-c --workers 4; wf --format zarr-c-z --workers 4; wf --format zarr-c-z --workers 8; wf --format hdf5 --workers 4
echo "=== $(date) done" >> "$LOG"; du -sh "$D/out"/* | tee -a "$LOG"
