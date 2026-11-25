#!/bin/bash
# G1a (segmentation, gated): base code (2a1d6b6) vs new code (118-zarr-segment-io), both in OUR image
# (NEW_SIF; the production SIFs are not available), PNG mode, the production command
# line, the same tile subset, one after the other on the same node. Input: G2's PNG run of the slide (TILES_DIR;
# G2 must have run with G2_KEEP_PNG=1), or any slide folder given as TILES_DIR.
# Pass: same files; PNG pixels equal; JSON values equal (last_updated ignored); the new CSV is the base CSV plus a
# trailing segment_key and nothing else; extract folders equal. Byte identity and segment counts are reported.
# This runs on Python 3.12. PNG-path code on the Python 3.10 production image is covered by the local
# golden check on 3.10 (tests/golden/png_golden.py), not by this job.
# Outputs live in node-local scratch; the report, logs and both CSVs go to OUT_ROOT.
# Submit (CPU SAM 2, the default): ../submit.sh segmentation/g1a-png-base-vs-new.sbatch
# On the GPU after G0 is EQUAL:
#   DEVICE=gpu ../submit.sh --partition=gpuA40x4 --gpus-per-node=1 segmentation/g1a-png-base-vs-new.sbatch
# Whole slide: N_TILES=0 (raise --time).
#SBATCH --job-name=g1a-seg
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=96g
#SBATCH --time=12:00:00
# Resources: SAM 2 large on CPU needs most of the 32 CPUs; memory covers -nt 8 MIP workers (2048 px x 21 planes,
# about 250 MB each) plus SAM 2. Time: 50 tiles x 2 sides, SAM 2 on CPU.
set -euo pipefail
source "$SLURM_SUBMIT_DIR/common.sh"
N_TILES=${N_TILES:-50}
check_inputs
[ -d "$REPO_BASE/src" ] || fail "REPO_BASE not found: $REPO_BASE"
OUT=$ROOT/g1a-seg/$SLURM_JOB_ID
mkdir -p "$OUT" "$SCRATCH"
record_env "$OUT"
pick_tiles "$TILES_DIR" "$SCRATCH/tiles" "$N_TILES" | tee "$OUT/tiles.json"
for side in base new; do
    repo=$REPO_BASE; [ "$side" = new ] && repo=$REPO_NEW
    rc=$(segment "$NEW_SIF" "$repo" "$SCRATCH/tiles" "$SCRATCH/$side" "$OUT/$side.csv" "$OUT/$side.log")
    echo "$side exit $rc" | tee -a "$OUT/exit-codes.txt"
    extract_segments "$NEW_SIF" "$repo" "$SCRATCH/$side" "$SCRATCH/$side-extract" "$OUT/$side-extract.log"
    echo "$side: $(find "$SCRATCH/$side" -type f | wc -l) files, $(du -sb "$SCRATCH/$side" | cut -f1) bytes" >> "$OUT/sizes.txt"
done
compare_outputs png-vs-png "$SCRATCH/base" "$SCRATCH/new" "$OUT/compare.json" --csv "$OUT/base.csv" "$OUT/new.csv" \
    --extract "$SCRATCH/base-extract" "$SCRATCH/new-extract" > "$OUT/result.txt"
cat "$OUT/result.txt"
grep -h "timings" "$OUT/base.log" "$OUT/new.log" > "$OUT/timings.txt" || true
rm -rf "$SCRATCH"
exit "$WORST"
