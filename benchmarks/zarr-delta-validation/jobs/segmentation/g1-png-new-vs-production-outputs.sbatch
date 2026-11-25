#!/bin/bash
# G1 (segmentation, reported, not gated): the new code in OUR image, PNG mode, the production command line, the whole
# slide, vs the slide's existing production segmentation outputs (read only). Measures image drift (Python,
# torch, SAM 2 and library versions) against what production produced: segment count, segments per tile, CSV rows,
# ground-truth match ratio and annotations matched, segment_key overlap (compare_outputs.py summary-vs-production).
# It also prints the segmentation parameters the production metadata.json records, which may show the production
# flags (model, area thresholds). Always exits 0 apart from a failed run.
# A slide without production outputs (PROD_SEG_ROOT empty or without the slide) still gets the full PNG run
# (sizes.txt, timings, CSV, metadata.json: the PNG side of full-slide-png-vs-zarr.sbatch); only the comparison is
# skipped, and result.txt says "no production outputs; PNG run only".
# Input tiles: the production tiles of the slide (PROD_TILES_DIR, from config.sh) if they exist, else
# G2's PNG run (G2 must have run with G2_KEEP_PNG=1), with a note in the summary that tile provenance differs.
# Outputs live in node-local scratch; only the CSV, the slide metadata.json, the summary and logs go to OUT_ROOT.
# Run on the GPU after G0 is EQUAL (production ran on GPUs); DEVICE=cpu for a whole slide is impractically slow.
# Submit: ../submit.sh segmentation/g1-png-new-vs-production-outputs.sbatch
#SBATCH --job-name=g1-seg
#SBATCH --partition=gpuA40x4
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus-per-node=1
#SBATCH --gpu-bind=closest
#SBATCH --cpus-per-task=32
#SBATCH --mem=96g
#SBATCH --time=24:00:00
# Time: production took about 16 h for two TADP slides with -ns 2 on one A40, i.e. roughly 8 h per slide.
# 24 h leaves room. Check the partition's maximum wall time.
set -euo pipefail
DEVICE=${DEVICE:-gpu}   # before common.sh, whose own default (cpu) would otherwise win
source "$SLURM_SUBMIT_DIR/common.sh"
N_TILES=${N_TILES:-0}
# Input tiles: the production tiles of the slide when known (what production segmented), else G2's PNG run of the
# same slide, which comes from our cropper image; then the summary notes that the tile provenance differs.
if [ -n "${PROD_TILES_DIR:-}" ] && [ -f "$PROD_TILES_DIR/metadata.json" ]; then
    TILES_DIR=$PROD_TILES_DIR
    NOTE="tiles: production tiles $PROD_TILES_DIR"
else
    TILES_DIR=$G2_TILES_DIR
    NOTE="tiles: G2's PNG run ($G2_TILES_DIR), not the production tiles; tile provenance differs from production"
fi
check_inputs
PROD_SLIDE=${PROD_SEG_ROOT:-}/$SLIDE_NAME
HAVE_PROD=0; [ -n "${PROD_SEG_ROOT:-}" ] && [ -f "$PROD_SLIDE/metadata.json" ] && HAVE_PROD=1
PROD_CSV=${PROD_CSV:-}   # the production -so CSV of this slide, if one exists; optional
OUT=$ROOT/g1-seg/$SLURM_JOB_ID
mkdir -p "$OUT" "$SCRATCH"
record_env "$OUT"
if [ "$HAVE_PROD" = 1 ]; then
    {   # provenance of the read-only production outputs
        echo "production slide: $PROD_SLIDE"
        stat "$PROD_SLIDE/metadata.json"
        sha256sum "$PROD_SLIDE/metadata.json"
        echo "files: $(find "$PROD_SLIDE" -type f | wc -l)"
        [ -n "$PROD_CSV" ] && { stat "$PROD_CSV"; sha256sum "$PROD_CSV"; }
    } > "$OUT/production-provenance.txt" 2>&1 || true
else
    echo "no production outputs: no metadata.json in $PROD_SLIDE (PROD_SEG_ROOT); PNG run only" \
        | tee "$OUT/production-provenance.txt"
fi
echo "$NOTE" | tee "$OUT/tile-provenance.txt"
pick_tiles "$TILES_DIR" "$SCRATCH/tiles" "$N_TILES"
rc=$(segment "$NEW_SIF" "$REPO_NEW" "$SCRATCH/tiles" "$SCRATCH/new" "$OUT/new.csv" "$OUT/new.log")
echo "new exit $rc" | tee "$OUT/exit-codes.txt"
cp "$SCRATCH/new/$SLIDE_NAME/metadata.json" "$OUT/new-metadata.json" || true
{   # the full PNG output, measured in scratch before cleanup; full-slide-png-vs-zarr.sbatch reads this file
    echo "tree: files $(find "$SCRATCH/new" -type f | wc -l), dirs $(find "$SCRATCH/new" -type d | wc -l), bytes $(du -sb "$SCRATCH/new" | cut -f1)"
    echo "csv: bytes $(cat "$OUT/new.csv" 2>/dev/null | wc -c)"
} | tee "$OUT/sizes.txt"
if [ "$HAVE_PROD" = 1 ]; then
    csv=(); [ -n "$PROD_CSV" ] && csv=(--csv "$PROD_CSV" "$OUT/new.csv")
    mkdir -p "$SCRATCH/prod" && ln -s "$PROD_SLIDE" "$SCRATCH/prod/$SLIDE_NAME"   # this slide only, read only
    compare_outputs summary-vs-production "$SCRATCH/prod" "$SCRATCH/new" "$OUT/summary.json" "${csv[@]}" \
        --note "$NOTE" > "$OUT/result.txt"
else
    NSEG=$(GNU_TIME=0 apptainer_run "$NEW_SIF" "$OUT" python3 -c 'import json, sys
s = (json.load(open(sys.argv[1])).get("segmentation") or {}).get("segments")
print(len(s) if isinstance(s, list) else "n/a")' "$OUT/new-metadata.json" 2>/dev/null) || NSEG=n/a
    echo "REPORTED (not gated)  $SLIDE_NAME: no production outputs; PNG run only, segments ${NSEG:-n/a}, files $(find "$SCRATCH/new" -type f | wc -l)  [note: $NOTE]" > "$OUT/result.txt"
fi
cat "$OUT/result.txt"
grep -h "timings" "$OUT/new.log" > "$OUT/timings.txt" || true
rm -rf "$SCRATCH"
exit "$rc"
