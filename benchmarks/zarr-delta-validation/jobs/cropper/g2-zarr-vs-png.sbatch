#!/bin/bash
# G2 (cropper): Zarr vs PNG for each phase-1 slide in full (array task 0 = TADP, 1 = PAL), new code, OUR SIF,
# production tiling, Zarr writes in-process (--store-writers 0).
#   1. Zarr crop -> $G2_STORE_DIR/<slide>.zarr under OUT_ROOT, KEPT (segmentation G3 reads it there; common.sh is the
#      source of truth for the path). A rerun resumes an unfinished store and leaves a complete one alone.
#   2. PNG crop of the same slide, same code, same SIF -> node-local scratch (or $G2_PNG_DIR under OUT_ROOT if
#      G2_KEEP_PNG=1).
#   3. GATE: both crops exit 0 and compare_zarr_png.py passes: every one of the N x Z planes equal, no plane missing
#      on either side, the same tile set both ways, attrs "palyim" == metadata.json (every key), some content.
#   4. REPORTED SEPARATELY, not gating: the store against the slide's production PNG tiles (PROD_PNG_DIR;
#      the TADP tiles were cropped with the v1.1.1 image). If that image's Bio-Formats or javabridge differ from
#      ours, a mismatch can come from the image, not our code (our versions are in image-versions.txt).
# Submit: ../submit.sh cropper/g2-zarr-vs-png.sbatch
#SBATCH --job-name=g2-cropper
#SBATCH --partition=cpu
#SBATCH --array=0-1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24g
#SBATCH --time=24:00:00
# Memory, measured locally on 24 PAL tiles (peak RSS): Zarr with in-process writes 1.9 GB, PNG mode 1.2 GB; TADP
# shards are 504 MiB instead of 432 MiB. The crops run one after the other. Re-size from
# `sacct -j <id> -o MaxRSS`. Locally (emulated) Zarr took 1.9 s and PNG 5.5 s per tile.
set -uo pipefail
source "$SLURM_SUBMIT_DIR/common.sh"
select_slide "${SLURM_ARRAY_TASK_ID:-0}"
OUT=$ROOT/g2-cropper/${SLIDE_KEY}-${SLURM_ARRAY_JOB_ID:-$SLURM_JOB_ID}
STORE=$G2_STORE_DIR/$SLIDE_NAME.zarr
if [ "$G2_KEEP_PNG" = 1 ]; then PNG_ROOT=$G2_PNG_DIR; else PNG_ROOT=$SCRATCH/png; fi
PNG_OWN=$PNG_ROOT/$SLIDE_NAME
mkdir -p "$OUT" "$G2_STORE_DIR" "$PNG_ROOT" "$SCRATCH"
record_env "$OUT"
{ echo "store: $STORE"; echo "png (own run): $PNG_OWN"; } >> "$OUT/env.txt"
apptainer exec "$NEW_SIF" sh -c 'python3 --version; python3 -m pip freeze 2>/dev/null | grep -iE "javabridge|bioformats|numpy|pillow|zarr|palyim"' \
    > "$OUT/image-versions.txt" 2>&1 || true

RZ=$(crop "$CODE_NEW" "$G2_STORE_DIR" "$OUT/crop-zarr.log" --tile_format zarr --store-writers 0 \
    --timings-json "$OUT/timings-zarr.json")
RP=$(crop "$CODE_NEW" "$PNG_ROOT" "$OUT/crop-png.log" --timings-json "$OUT/timings-png.json")
{
    echo "store: files $(find "$STORE" -type f 2>/dev/null | wc -l), dirs $(find "$STORE" -type d 2>/dev/null | wc -l), bytes $(du -sb "$STORE" 2>/dev/null | cut -f1), .empty markers $(find "$STORE/tiles" -name '*.empty' 2>/dev/null | wc -l)"
    echo "png (own run): files $(find "$PNG_OWN" -type f 2>/dev/null | wc -l), dirs $(find "$PNG_OWN" -type d 2>/dev/null | wc -l), bytes $(du -sb "$PNG_OWN" 2>/dev/null | cut -f1)"
} > "$OUT/sizes.txt"
cp "$STORE/progress.json" "$OUT/progress.json" 2>/dev/null || true

RG=$(compare "$OUT/compare-own-png.log" compare_zarr_png.py "$STORE" "$PNG_OWN" "$OUT/compare-own-png.json" \
    "${SLURM_CPUS_PER_TASK:-4}")
# Write the gated result now: the production comparison below is report-only and slow (a second full pass over the shared filesystem),
# and a job that runs out of time there must not lose the gate's verdict (PAL, 2026-11-05).
GATE=FAIL; [ "$RZ" = 0 ] && [ "$RP" = 0 ] && [ "$RG" = 0 ] && GATE=PASS
{
    echo "exit zarr=$RZ png=$RP gate=$RG"
    echo "gate (Zarr vs own PNG): $(tail -1 "$OUT/compare-own-png.log")"
    echo "G2 $SLIDE_KEY (gate only, production comparison still to run): $GATE"
} | tee "$OUT/verdict-gate.txt"
if [ -n "$PROD_PNG_DIR" ] && [ -d "$PROD_PNG_DIR" ]; then
    RR=$(compare "$OUT/compare-production.log" compare_zarr_png.py "$STORE" "$PROD_PNG_DIR" \
        "$OUT/compare-production.json" "${SLURM_CPUS_PER_TASK:-4}" --report)
    PROD_LINE=$(tail -1 "$OUT/compare-production.log")
else
    PROD_LINE="no production tiles for $SLIDE_KEY (PROD_PNG_DIR='${PROD_PNG_DIR}')"
fi
VERDICT=FAIL; [ "$RZ" = 0 ] && [ "$RP" = 0 ] && [ "$RG" = 0 ] && VERDICT=PASS
{
    echo "exit zarr=$RZ png=$RP gate=$RG"
    echo "gate (Zarr vs own PNG): $(tail -1 "$OUT/compare-own-png.log")"
    echo "reported (Zarr vs production tiles): $PROD_LINE"
    echo "G2 $SLIDE_KEY: $VERDICT; store kept at $STORE"
} | tee "$OUT/verdict.txt"
rm -rf "$SCRATCH"
[ "$VERDICT" = PASS ]
