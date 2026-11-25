#!/bin/bash
# Full slide, PNG vs Zarr (segmentation, reported, not gated): the phase-1 headline numbers for stage 2. Runs the
# new code in OUR image on the whole slide in Zarr mode (--input-format zarr --output-format zarr), reading G2's full
# tile store, with the same command line, GPU and limits as G1. G1's run of the same slide is the PNG side.
#   Zarr side   this job: <out>/zarr/<slide>/{segments.zarr, metadata.json} and zarr.csv, all kept under OUT_ROOT
#               (a few files: that is the point)
#   PNG side    the newest finished G1 run of the slide ($ROOT/g1-seg/<job>/): its sizes.txt (the full PNG tree,
#               measured in scratch before G1's cleanup), new.log, new-metadata.json and new.csv
# Reports, PNG vs Zarr: files, directories and bytes (output tree + CSV), wall time (GNU time) and each PhaseTimer
# phase from the two logs, segment counts, CSV rows, and the segment_key overlap (compare_outputs.py
# summary-vs-production with a = G1's PNG run, b = this run). Not gated: GPU SAM 2 may vary between runs (see G0's
# result, quoted in the report), and G1 reads the production tiles when they exist (its tile-provenance.txt).
# Writes report.md (the PNG vs Zarr table) and report.json (read by ../make_phase1_table.py).
# Run after G1 has finished for the slide. Exits with the Zarr run's exit code.
# Submit: ../submit.sh segmentation/full-slide-png-vs-zarr.sbatch
# For the PAL slide: SLIDE_NAME=PAL1999_B2_sample100_slide1 GT_CSV= ../submit.sh segmentation/full-slide-png-vs-zarr.sbatch
#SBATCH --job-name=full-seg
#SBATCH --partition=gpuA40x4
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus-per-node=1
#SBATCH --gpu-bind=closest
#SBATCH --cpus-per-task=32
#SBATCH --mem=96g
#SBATCH --time=24:00:00
# Time and memory: as G1. Zarr mode keeps no per-tile files, so it should
# not take longer than G1; re-size from `sacct -j <id> -o Elapsed,MaxRSS` of both.
set -euo pipefail
DEVICE=${DEVICE:-gpu}   # before common.sh, whose own default (cpu) would otherwise win
source "$SLURM_SUBMIT_DIR/common.sh"
STORE=$G2_STORE_DIR/$SLIDE_NAME.zarr
TILES_DIR=$STORE        # for env.txt
check_inputs ""
[ -d "$STORE" ] || fail "tile store not found: $STORE (run the cropper's G2 for $SLIDE_NAME first)"
# The PNG side: the newest G1 run of this slide that finished with exit 0 (G1_DIR overrides).
G1_DIR=${G1_DIR:-}
if [ -z "$G1_DIR" ]; then
    while IFS= read -r d; do
        if grep -qF "slide: $SLIDE_NAME  " "$d/env.txt" 2>/dev/null && grep -qx "new exit 0" "$d/exit-codes.txt" 2>/dev/null; then
            G1_DIR=${d%/}; break
        fi
    done < <(ls -1td "$ROOT"/g1-seg/*/ 2>/dev/null)
fi
[ -n "$G1_DIR" ] || fail "no finished G1 run of $SLIDE_NAME in $ROOT/g1-seg (run g1-png-new-vs-production-outputs.sbatch first)"
grep -q "^tree: files" "$G1_DIR/sizes.txt" 2>/dev/null \
    || fail "$G1_DIR/sizes.txt has no 'tree: files' line (that G1 run predates the size recording; run G1 again)"
[ -f "$G1_DIR/new-metadata.json" ] || fail "no new-metadata.json in $G1_DIR"

OUT=$ROOT/full-seg/$SLURM_JOB_ID
mkdir -p "$OUT" "$SCRATCH"
record_env "$OUT"
{ echo "store: $STORE"; echo "png side (G1): $G1_DIR"; } >> "$OUT/env.txt"
rc=$(segment "$NEW_SIF" "$REPO_NEW" "$G2_STORE_DIR" "$OUT/zarr" "$OUT/zarr.csv" "$OUT/zarr.log" \
     --input-format zarr --output-format zarr -sn "$SLIDE_NAME")
echo "zarr exit $rc" | tee "$OUT/exit-codes.txt"
{   # the same measures as G1's sizes.txt
    echo "tree: files $(find "$OUT/zarr" -type f | wc -l), dirs $(find "$OUT/zarr" -type d | wc -l), bytes $(du -sb "$OUT/zarr" | cut -f1)"
    echo "csv: bytes $(cat "$OUT/zarr.csv" 2>/dev/null | wc -c)"
} | tee "$OUT/sizes.txt"
grep -h "timings" "$OUT/zarr.log" > "$OUT/timings.txt" || true

# Key overlap, reported: summary-vs-production reads only <root>/<slide>/metadata.json, so G1's kept slide metadata
# stands in for its PNG tree. In overlap.json "production" is G1's PNG run and "new" is this Zarr run.
mkdir -p "$SCRATCH/png/$SLIDE_NAME"
cp "$G1_DIR/new-metadata.json" "$SCRATCH/png/$SLIDE_NAME/metadata.json"
compare_outputs summary-vs-production "$SCRATCH/png" "$OUT/zarr" "$OUT/overlap.json" \
    --csv "$G1_DIR/new.csv" "$OUT/zarr.csv" --note "a = G1 PNG run $G1_DIR, b = Zarr run $OUT" > "$OUT/overlap.txt"

rrc=0
apptainer_run "$NEW_SIF" "$OUT" python3 "$SLURM_SUBMIT_DIR/full_slide_report.py" --slide "$SLIDE_NAME" \
    --png "$G1_DIR" --zarr "$OUT" --g0 "$ROOT/g0-seg-gpu-variance" > "$OUT/result.txt" 2> "$OUT/report.log" || rrc=$?
[ "$rrc" = 0 ] || echo "full_slide_report.py exit $rrc; see $OUT/report.log" | tee -a "$OUT/result.txt"
cat "$OUT/report.md" 2>/dev/null || true
cat "$OUT/result.txt"
rm -rf "$SCRATCH"
exit "$rc"
