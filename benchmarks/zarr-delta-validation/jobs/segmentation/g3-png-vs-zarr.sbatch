#!/bin/bash
# G3 (segmentation, gated): PNG mode vs Zarr mode on the same 9 tiles, with the new code in our SIF.
#   inputs  (make_g3_inputs.py): 9 tile folders copied from G2's PNG run and a 9-tile store subset_tile_store'd out
#           of the full tile store G2 verified (every copied plane is checked against the store); both sides get
#           the same slide metadata (the store's attrs)
#   sides   png          PNG input, PNG output (today's mode)
#           zarr_png_in  PNG input, --output-format zarr
#           zarr_store   --input-format zarr --output-format zarr
#   passes  1: a clean run with a stricter area filter (-a $PASS1_MIN_AREA), so some tiles end up without segments;
#           2: -ps on the same output with the production filter, which segments those tiles again
# Pass, after each pass and for both Zarr sides: CSV equal to PNG mode's (segment_key included), slide
# metadata.json equal once the Zarr side drops segment_output and the Zarr-only record fields, extract folders
# pixel-equal (compare_outputs.py png-vs-zarr). Every comparison and both passes run even if one is DIFFERENT; the
# job exits with the worst comparison result. Everything is small (9 tiles), so it all goes to OUT_ROOT.
# Submit (CPU SAM 2, the default): ../submit.sh segmentation/g3-png-vs-zarr.sbatch
# On the GPU after G0 is EQUAL:
#   DEVICE=gpu ../submit.sh --partition=gpuA40x4 --gpus-per-node=1 segmentation/g3-png-vs-zarr.sbatch
#SBATCH --job-name=g3-seg
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=64g
#SBATCH --time=08:00:00
# Time: SAM 2 on CPU for 9 tiles x 3 sides, plus the -ps passes (only tiles without segments).
set -euo pipefail
source "$SLURM_SUBMIT_DIR/common.sh"
# G3 slide: SLIDE_NAME (default the TADP slide; GT_CSV gives -mt). For the PAL slide submit with
# SLIDE_NAME=PAL1999_B2_sample100_slide1 GT_CSV= . Inputs come from the cropper's G2 (paths from ../cropper/common.sh):
# the full store G2 verified, and G2's PNG run of the same slide, which G2 keeps only with G2_KEEP_PNG=1. Both come
# from the same code and image and are equal by the G2 gate, so the PNG and Zarr sides start from identical tiles.
G3_FULL_STORE=${G3_FULL_STORE:-$G2_STORE_DIR/$SLIDE_NAME.zarr}
G3_PNG_SLIDE_DIR=${G3_PNG_SLIDE_DIR-$G2_TILES_DIR}   # empty: the PNG tiles are written from the store
G3_TILES=${G3_TILES:-}                   # "x,y x,y ..." to pin the 9 tiles; empty: the grid's centre 3 x 3 block
PASS1_MIN_AREA=${PASS1_MIN_AREA:-6400}   # stricter than the production -a 3600 (80^2 px instead of 60^2)
check_inputs ""
[ -d "$G3_FULL_STORE" ] || fail "G3_FULL_STORE not found: $G3_FULL_STORE (run the cropper's G2 for $SLIDE_NAME first)"
if [ -n "$G3_PNG_SLIDE_DIR" ] && [ ! -d "$G3_PNG_SLIDE_DIR" ]; then
    fail "G3_PNG_SLIDE_DIR not found: $G3_PNG_SLIDE_DIR (run G2 with G2_KEEP_PNG=1, or set G3_PNG_SLIDE_DIR= to write the PNG tiles from the store)"
fi

OUT=$ROOT/g3-seg/$SLURM_JOB_ID
mkdir -p "$OUT" "$SCRATCH"
record_env "$OUT"
inputs=(--store "$G3_FULL_STORE" --slide "$SLIDE_NAME" --out "$OUT/inputs")
[ -n "$G3_PNG_SLIDE_DIR" ] && inputs+=(--png-slide-dir "$G3_PNG_SLIDE_DIR")
[ -n "$G3_TILES" ] && inputs+=(--tiles "$G3_TILES")
rc=0
apptainer_run "$NEW_SIF" "$OUT" python3 "$SLURM_SUBMIT_DIR/make_g3_inputs.py" "${inputs[@]}" > "$OUT/inputs.json" 2>&1 || rc=$?
[ "$rc" = 0 ] || { cat "$OUT/inputs.json"; fail "make_g3_inputs.py failed (exit $rc); see $OUT/inputs.json"; }

TILES_PNG=$OUT/inputs/tiles
TILES_ZARR=$OUT/inputs/stores
for pass in 1 2; do
    if [ "$pass" = 1 ]; then prod_args "$PASS1_MIN_AREA"; extra=(); else prod_args; extra=(-ps); fi
    for side in png zarr_png_in zarr_store; do
        case $side in
            png)         tiles=$TILES_PNG;  fmt=() ;;
            zarr_png_in) tiles=$TILES_PNG;  fmt=(--output-format zarr) ;;
            zarr_store)  tiles=$TILES_ZARR; fmt=(--input-format zarr --output-format zarr) ;;
        esac
        rc=$(segment "$NEW_SIF" "$REPO_NEW" "$tiles" "$OUT/$side" "$OUT/$side-pass$pass.csv" "$OUT/$side-pass$pass.log" \
             "${fmt[@]}" "${extra[@]}")
        echo "pass$pass $side exit $rc" | tee -a "$OUT/exit-codes.txt"
        rm -rf "$OUT/$side-extract-pass$pass"
        extract_segments "$NEW_SIF" "$REPO_NEW" "$OUT/$side" "$OUT/$side-extract-pass$pass" "$OUT/$side-extract-pass$pass.log"
    done
    for side in zarr_png_in zarr_store; do
        printf 'pass%s %s: ' "$pass" "$side" >> "$OUT/result.txt"
        compare_outputs png-vs-zarr "$OUT/png" "$OUT/$side" "$OUT/compare-$side-pass$pass.json" \
            --csv "$OUT/png-pass$pass.csv" "$OUT/$side-pass$pass.csv" \
            --extract "$OUT/png-extract-pass$pass" "$OUT/$side-extract-pass$pass" >> "$OUT/result.txt"
    done
done
for side in png zarr_png_in zarr_store; do
    echo "$side: $(find "$OUT/$side" -type f | wc -l) files, $(du -sb "$OUT/$side" | cut -f1) bytes"
done | tee "$OUT/sizes.txt"
grep -h "timings" "$OUT"/*-pass*.log > "$OUT/timings.txt" || true
cat "$OUT/result.txt"
rm -rf "$SCRATCH"
exit "$WORST"
