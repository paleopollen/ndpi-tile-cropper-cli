# Shared settings for the segmentation tests (G0, G1a, G1, G3, full slide). Sourced by the sbatch templates; site
# paths come from ../config.sh. Every variable can be overridden at submit time:
# VAR=value ../submit.sh segmentation/<script>.sbatch
#
# Every test runs in one image (NEW_SIF): G1a compares base and new code inside it, and G1 is a reported summary
# against the existing production outputs, which were made by older images.

source "$(dirname "${BASH_SOURCE[0]}")/../config.sh"

ROOT=$OUT_ROOT                                    # test outputs, one folder per test
REPO_BASE=$BASE_ROOT/post-processing-cli-sam-2    # worktree at the base commit of the Zarr branch
REPO_NEW=$CODE_ROOT/post-processing-cli-sam-2     # clone on the Zarr branch (118-zarr-segment-io)

# The image built from the branch's Dockerfile, converted with ./build-sif.sbatch, which saves <sif>.sha256 and
# <sif>.pip-freeze.txt next to it.
NEW_SIF=${NEW_SIF:-$SEG_SIF}

TADP_SLIDE=$TADP_SLIDE_NAME
PAL_SLIDE=$PAL_SLIDE_NAME

# The cropper's outputs that stage 2 reads come from ../cropper/common.sh, the source of truth for them:
# G2_STORE_DIR (G2's tile stores, <dir>/<slide>.zarr) and G2_PNG_DIR (G2's PNG run, <dir>/<slide>/, kept only when
# G2 ran with G2_KEEP_PNG=1). It is read in a subshell, so none of its functions or other settings leak in here.
CROPPER_COMMON=${CROPPER_COMMON:-$(dirname "${BASH_SOURCE[0]}")/../cropper/common.sh}
if [ -f "$CROPPER_COMMON" ]; then
    eval "$(bash -c 'source "$1" >/dev/null 2>&1; declare -p G2_STORE_DIR G2_PNG_DIR 2>/dev/null' _ "$CROPPER_COMMON")"
else
    echo "WARNING: $CROPPER_COMMON not found; using this file's copies of G2_STORE_DIR and G2_PNG_DIR" >&2
fi
G2_STORE_DIR=${G2_STORE_DIR:-$ROOT/g2-cropper/stores}
G2_PNG_DIR=${G2_PNG_DIR:-$ROOT/g2-cropper/png}

# The slide the tests segment. The TADP slide is in the ground-truth CSV, so -mt gives a ratio.
# For the PAL slide: SLIDE_NAME=PAL1999_B2_sample100_slide1 GT_CSV= ../submit.sh segmentation/<script>.sbatch
SLIDE_NAME=${SLIDE_NAME:-$TADP_SLIDE}
# Production tiles and production segmentation output root of the slide (read only; G1's summary and tile picking).
case "$SLIDE_NAME" in
    "$TADP_SLIDE") PROD_TILES_DIR=${PROD_TILES_DIR:-${TADP_PROD_PNG_DIR:-}}; PROD_SEG_ROOT=${PROD_SEG_ROOT:-${TADP_PROD_SEG_ROOT:-}} ;;
    "$PAL_SLIDE")  PROD_TILES_DIR=${PROD_TILES_DIR:-${PAL_PROD_PNG_DIR:-}};  PROD_SEG_ROOT=${PROD_SEG_ROOT:-${PAL_PROD_SEG_ROOT:-}} ;;
    *)             PROD_TILES_DIR=${PROD_TILES_DIR:-}; PROD_SEG_ROOT=${PROD_SEG_ROOT:-} ;;
esac
# G2's PNG run of the slide: same code and image as its store, and equal to it by the G2 gate. The default PNG
# input of G0, G1a and G3, so G3's PNG and Zarr sides start from provably identical tiles. Needs G2 run with
# G2_KEEP_PNG=1 first.
G2_TILES_DIR=$G2_PNG_DIR/$SLIDE_NAME
# The slide folder the PNG runs read ({x}x_{y}y/{z}z.png + metadata.json, read only). G1 overrides it with the
# production tiles when PROD_TILES_DIR exists.
TILES_DIR=${TILES_DIR:-$G2_TILES_DIR}

# The command line used for the production runs, as far as it is documented: -mip -s, area filter 3600 to 84100 px,
# aspect ratio 0.4, -p, 8 MIP workers. -bp stays at its default 0.
MIN_AREA=${MIN_AREA:-3600}
prod_args() {  # prod_args [min_area]: the production flags, with -g/-mt only when GT_CSV is set
    PROD_ARGS=(-mip -s -a "${1:-$MIN_AREA}" -b 84100 -ar 0.4 -p -nt "${NT:-8}")
    if [ -n "${GT_CSV:-}" ]; then PROD_ARGS+=(-g "$GT_CSV" -mt); fi
}
prod_args

# SAM 2 device. cpu: run-to-run identical, slow; the gate until G0 shows the image repeats exactly on the GPU.
# gpu: --nv; submit on a GPU partition.
DEVICE=${DEVICE:-cpu}

# Node-local scratch for outputs that only exist to be compared (purged after the job).
SCRATCH=${TMPDIR:-/tmp}/zarr-test-${SLURM_JOB_ID:-manual}

# Worst exit code of the comparisons; scripts `exit "$WORST"` at the very end, after timings and cleanup.
WORST=0
track() { local rc=$1; if [ "$rc" -gt "$WORST" ]; then WORST=$rc; fi; }

fail() { echo "ERROR: $*" >&2; exit 2; }

check_inputs() {  # check_inputs [slide_dir]: fail fast on placeholders and missing files ("" skips the slide check)
    local slide_dir=${1-$TILES_DIR}
    [ -f "$NEW_SIF" ] || fail "NEW_SIF not found: $NEW_SIF (build it with build-sif.sbatch)"
    [ -f "$SAM2_CKPT" ] || fail "SAM2_CKPT not found: $SAM2_CKPT"
    [ -d "$REPO_NEW/src" ] || fail "REPO_NEW not found: $REPO_NEW"
    if [ -n "$PALYIM_IO_SRC" ]; then
        [ -f "$PALYIM_IO_SRC/palyim_io/__init__.py" ] || fail "PALYIM_IO_SRC not found: $PALYIM_IO_SRC (git clone palyim-io, checkout $PALYIM_IO_TAG; or PALYIM_IO_SRC= for the image's copy)"
        local head tag
        head=$(git -C "$PALYIM_IO_SRC" rev-parse HEAD 2>/dev/null)
        tag=$(git -C "$PALYIM_IO_SRC" rev-parse "$PALYIM_IO_TAG^{commit}" 2>/dev/null)
        [ -n "$head" ] && [ "$head" = "$tag" ] || fail "PALYIM_IO_SRC is not at $PALYIM_IO_TAG (HEAD ${head:-?}); git -C ${PALYIM_IO_SRC%/src} checkout $PALYIM_IO_TAG"
    fi
    if [ -n "${GT_CSV:-}" ] && [ ! -f "$GT_CSV" ]; then
        fail "GT_CSV not found: $GT_CSV. Set GT_CSV to the Batch_ROI_Export CSV, or GT_CSV= to run without -g/-mt."
    fi
    if [ -n "$slide_dir" ] && [ ! -f "$slide_dir/metadata.json" ]; then
        fail "no slide metadata.json in $slide_dir (SLIDE_NAME=$SLIDE_NAME). G2's PNG tiles exist only if G2 ran with G2_KEEP_PNG=1; or set TILES_DIR"
    fi
    case "$TILES_DIR ${PROD_SEG_ROOT:-} $SAM2_CKPT ${GT_CSV:-}" in
        *CHANGEME*) echo "WARNING: a CHANGEME path from config.sh is still in use; check env.txt" >&2 ;;
    esac
}

apptainer_run() {  # apptainer_run <sif> <workdir> <command...>; GNU time when present
    local sif=$1 wd=$2; shift 2
    local timer=() nv=() pyenv=()
    # GNU_TIME=0: no timer, for the comparers, whose last log line is the verdict
    [ -x /usr/bin/time ] && [ "${GNU_TIME:-1}" = 1 ] && timer=(/usr/bin/time -v)
    if [ "$DEVICE" = gpu ]; then nv=(--nv); else export APPTAINERENV_CUDA_VISIBLE_DEVICES=""; fi
    [ -n "$PALYIM_IO_SRC" ] && pyenv=(--env "PYTHONPATH=$PALYIM_IO_SRC")
    # The same binds as ../cropper/common.sh: outputs read-write, code, images and data read-only, plus scratch.
    "${timer[@]}" apptainer exec "${nv[@]}" "${pyenv[@]}" --bind "$APPTAINER_BINDS","$SCRATCH" \
        --pwd "$wd" "$sif" "$@"
}

segment() {  # segment <sif> <repo> <tiles_root> <out_dir> <csv> <log> [extra args...]; prints the CLI's exit code
    local sif=$1 repo=$2 tiles=$3 out=$4 csv=$5 log=$6; shift 6
    local rc=0
    apptainer_run "$sif" "$repo/src" python3 "$repo/src/post_processing_cli.py" process \
        -d "$tiles" -od "$out" -m "$SAM2_CKPT" -c "$SAM2_CFG" "${PROD_ARGS[@]}" -so "$csv" "$@" > "$log" 2>&1 || rc=$?
    echo "$rc"
}

extract_segments() {  # extract_segments <sif> <repo> <in> <out> <log>
    local rc=0
    apptainer_run "$1" "$2/src" python3 "$2/src/post_processing_cli.py" extract -i "$3" -o "$4" -p \
        -n "${SLURM_CPUS_PER_TASK:-4}" > "$5" 2>&1 || rc=$?
    echo "extract exit $rc" >> "$5"
}

compare_outputs() {  # compare_outputs <mode> <a> <b> <json> [--csv a b] [--extract a b]
    # Runs in our SIF, prints the verdict line (with segment counts), records the rc in WORST, never aborts.
    # Call it with a redirect (>> file), never in a pipeline: a pipeline runs it in a subshell and loses WORST.
    local mode=$1 a=$2 b=$3 json=$4; shift 4
    local rc=0
    GNU_TIME=0 apptainer_run "$NEW_SIF" "$REPO_NEW" python3 "$REPO_NEW/tests/golden/compare_outputs.py" --mode "$mode" \
        "$a" "$b" --json-out "$json" "$@" > "${json%.json}.log" 2>&1 || rc=$?
    tail -1 "${json%.json}.log"
    track "$rc"
}

pick_tiles() {  # pick_tiles <src_slide_dir> <dst_root> <n>: <dst_root>/$SLIDE_NAME with metadata.json + n tiles
    # n=0: the whole slide (a symlink; read-only use). Otherwise the tiles with the most production segments
    # (if PROD_SEG_ROOT has the slide), else the n tiles nearest the grid centre, never the blank left edge.
    local src=$1 dst=$2 n=$3
    if [ "$n" = 0 ]; then mkdir -p "$dst"; ln -sfn "$src" "$dst/$SLIDE_NAME"; return; fi
    apptainer_run "$NEW_SIF" "$REPO_NEW" python3 "$SLURM_SUBMIT_DIR/pick_tiles.py" --src "$src" --dst "$dst" --n "$n" \
        --name "$SLIDE_NAME" --prod-metadata "${PROD_SEG_ROOT:-/nonexistent}/$SLIDE_NAME/metadata.json"
}

record_env() {  # record_env <out_dir>
    local out=$1
    {
        echo "date: $(date -Is)"; echo "host: $(hostname)"; echo "job: ${SLURM_JOB_ID:-} cpus: ${SLURM_CPUS_PER_TASK:-}"
        echo "device: $DEVICE"; nvidia-smi -L 2>/dev/null || true
        for r in "$REPO_BASE" "$REPO_NEW"; do echo "code $r: $(git -C "$r" rev-parse HEAD 2>/dev/null)"; done
        echo "sif $NEW_SIF: $(sha256sum "$NEW_SIF" 2>/dev/null | cut -d' ' -f1)"
        echo "checkpoint: $(sha256sum "$SAM2_CKPT" 2>/dev/null | cut -d' ' -f1)"
        echo "slide: $SLIDE_NAME  tiles: $TILES_DIR  production segments: ${PROD_SEG_ROOT:-none}  gt: ${GT_CSV:-none}"
        echo "G2 stores: $G2_STORE_DIR  G2 PNG: $G2_PNG_DIR  production tiles: ${PROD_TILES_DIR:-none}"
        echo "data root resolves to: $(readlink -f "$DATA_ROOT")"
        printf 'args:'; printf ' %q' "${PROD_ARGS[@]}"; echo
    } > "$out/env.txt" 2>&1
    apptainer exec "$NEW_SIF" python3 -m pip freeze > "$out/pip-freeze.txt" 2>&1 || true
    {
        echo "palyim-io overlay: ${PALYIM_IO_SRC:-none} at $(git -C "${PALYIM_IO_SRC:-/nonexistent}" describe --tags --always 2>/dev/null) $(git -C "${PALYIM_IO_SRC:-/nonexistent}" rev-parse HEAD 2>/dev/null)"
        echo -n "palyim_io imported: "
        GNU_TIME=0 apptainer_run "$NEW_SIF" "$out" python3 -c 'import palyim_io; print(palyim_io.__version__, palyim_io.__file__)' || echo "(import failed)"
    } >> "$out/env.txt" 2>&1
}
