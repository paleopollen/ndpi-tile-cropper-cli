#!/bin/bash
# G0 (segmentation): does SAM 2 repeat exactly on an A40 in OUR image? Runs NEW_SIF twice in PNG mode with the new
# code on the same tile subset, on the GPU, and compares the outputs (same-code mode). EQUAL: G1a/G1/G3 may use
# DEVICE=gpu. DIFFERENT: they stay on DEVICE=cpu. The report shows the segment counts of both runs.
# Input: G2's PNG run of the slide (TILES_DIR; G2 must have run with G2_KEEP_PNG=1).
# Submit: ../submit.sh segmentation/g0-gpu-variance.sbatch
#SBATCH --job-name=g0-seg-gpu-variance
#SBATCH --partition=gpuA40x4
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus-per-node=1
#SBATCH --gpu-bind=closest
#SBATCH --cpus-per-task=16
#SBATCH --mem=64g
#SBATCH --time=04:00:00
# Time: production took about 8 h per slide per GPU; 50 tiles take minutes.
set -euo pipefail
source "$SLURM_SUBMIT_DIR/common.sh"
DEVICE=gpu
N_TILES=${N_TILES:-50}
check_inputs
OUT=$ROOT/g0-seg-gpu-variance/$SLURM_JOB_ID
mkdir -p "$OUT" "$SCRATCH"
record_env "$OUT"
pick_tiles "$TILES_DIR" "$SCRATCH/tiles" "$N_TILES" | tee "$OUT/tiles.json"
for run in 1 2; do
    rc=$(segment "$NEW_SIF" "$REPO_NEW" "$SCRATCH/tiles" "$SCRATCH/run$run" "$OUT/run$run.csv" "$OUT/run$run.log")
    echo "run$run exit $rc" | tee -a "$OUT/exit-codes.txt"
done
compare_outputs same-code "$SCRATCH/run1" "$SCRATCH/run2" "$OUT/compare.json" --csv "$OUT/run1.csv" "$OUT/run2.csv" \
    > "$OUT/result.txt"
cat "$OUT/result.txt"
grep -h "timings" "$OUT"/run*.log > "$OUT/timings.txt" || true
rm -rf "$SCRATCH"
exit "$WORST"
