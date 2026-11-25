#!/bin/bash
# G1 (cropper): new code in OUR SIF, PNG mode, production tiling, each phase-1 slide (array 0 = TADP, 1 = PAL),
# against the slide's EXISTING production PNG tiles (PROD_PNG_DIR, from config.sh; made by older images).
# REPORTED, NOT GATED: tile counts on both sides, the per-plane pixel equality rate over the planes both have,
# metadata.json on both sides, small (likely blank) plane counts, and the tiles that differ or exist on one side
# only. It measures image drift, not our code (G1a covers the code). The job fails only if our own crop fails.
# Our tree goes to node-local scratch; the production tiles are only read.
# Submit: ../submit.sh cropper/g1-png-new-vs-production-tiles.sbatch
#SBATCH --job-name=g1-cropper
#SBATCH --partition=cpu
#SBATCH --array=0-1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8g
#SBATCH --time=24:00:00
set -uo pipefail
source "$SLURM_SUBMIT_DIR/common.sh"
select_slide "${SLURM_ARRAY_TASK_ID:-0}"
OUT=$ROOT/g1-cropper/${SLIDE_KEY}-${SLURM_ARRAY_JOB_ID:-$SLURM_JOB_ID}
mkdir -p "$OUT" "$SCRATCH/png"
record_env "$OUT"
if [ -z "$PROD_PNG_DIR" ] || [ ! -f "$PROD_PNG_DIR/metadata.json" ]; then
    echo "G1 $SLIDE_KEY: no production tiles at '${PROD_PNG_DIR}' (set ${SLIDE_KEY}_PROD_PNG_DIR); nothing to compare" | tee "$OUT/verdict.txt"
    exit 2
fi

# Our side: G2's kept PNG run of this slide when it is complete (same new code, same SIF, PNG mode, full slide), so no
# second multi-hour crop; otherwise (or with G1_RECROP=1) crop again into node-local scratch.
OURS=$G2_PNG_DIR/$SLIDE_NAME
if [ "${G1_RECROP:-0}" != 1 ] && [ -f "$OURS/metadata.json" ] && \
   python3 -c "import json,sys; m=json.load(open(sys.argv[1])); sys.exit(0 if m.get('percent_complete') == 100.0 else 1)" "$OURS/metadata.json"; then
    R=0; echo "ours: G2's complete PNG run $OURS" | tee -a "$OUT/env.txt"
else
    [ "${G1_RECROP:-0}" = 1 ] || echo "G2's PNG run of $SLIDE_NAME is not complete (or absent): cropping again" | tee -a "$OUT/env.txt"
    R=$(crop "$CODE_NEW" "$SCRATCH/png" "$OUT/crop.log" --timings-json "$OUT/timings.json")
    OURS=$SCRATCH/png/$SLIDE_NAME
fi
cp "$OURS/metadata.json" "$OUT/metadata-ours.json" 2>/dev/null || true
cp "$PROD_PNG_DIR/metadata.json" "$OUT/metadata-production.json" 2>/dev/null || true
# Side a = production, side b = ours.
RC=$(compare "$OUT/compare.log" compare_png_trees.py "$PROD_PNG_DIR" "$OURS" "$OUT/compare.json" \
    "${SLURM_CPUS_PER_TASK:-4}" --summary)
{ echo "exit crop=$R compare=$RC"; tail -1 "$OUT/compare.log"; echo "G1 $SLIDE_KEY: reported (our crop exit $R)"; } | tee "$OUT/verdict.txt"
rm -rf "$SCRATCH"
[ "$R" = 0 ]
