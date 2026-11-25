# Shared settings for the cropper tests (G1, G2). Sourced by the sbatch templates; site paths come from ../config.sh.
# This file is the source of truth for the cropper outputs that segmentation reads (G2_STORE_DIR, G2_PNG_DIR).
# Any variable can be overridden at submit time: VAR=value ../submit.sh cropper/<script>.sbatch

source "$(dirname "${BASH_SOURCE[0]}")/../config.sh"

ROOT=$OUT_ROOT                                              # test outputs, one folder per test
CODE_BASE=${CODE_BASE:-$BASE_ROOT/ndpi-tile-cropper-cli/src}   # base commit of the Zarr branch (recorded in env.txt)
CODE_NEW=${CODE_NEW:-$CODE_ROOT/ndpi-tile-cropper-cli/src}     # the Zarr branch (117-zarr-tile-store)

# The image built from the branch's Dockerfile, converted with build-sif.sbatch (sha256 and pip freeze saved beside
# it). The jobs run the checkout's code inside it, so only a dependency change needs a new SIF.
NEW_SIF=${NEW_SIF:-$CROPPER_SIF}

# G2's Zarr stores: <G2_STORE_DIR>/<slide name>.zarr, kept; segmentation reads them from here. A rerun of G2
# resumes an unfinished store and leaves a complete one alone.
G2_STORE_DIR=$ROOT/g2-cropper/stores
# G2's PNG run of the same slide: node-local scratch (compared, then deleted) unless G2_KEEP_PNG=1, which writes it
# to G2_PNG_DIR (about 50,000 files for the TADP slide) for the segmentation tests, which need a PNG tile tree.
G2_KEEP_PNG=${G2_KEEP_PNG:-0}
G2_PNG_DIR=$ROOT/g2-cropper/png

select_slide() {  # select_slide <0|1|TADP|PAL>: sets SLIDE_KEY, SLIDE_NDPI, SLIDE_NAME, PROD_PNG_DIR
    case "$1" in
        0|TADP) SLIDE_KEY=TADP; SLIDE_NDPI=$TADP_SLIDE_NDPI; SLIDE_NAME=$TADP_SLIDE_NAME; PROD_PNG_DIR=$TADP_PROD_PNG_DIR ;;
        1|PAL)  SLIDE_KEY=PAL;  SLIDE_NDPI=$PAL_SLIDE_NDPI;  SLIDE_NAME=$PAL_SLIDE_NAME;  PROD_PNG_DIR=$PAL_PROD_PNG_DIR ;;
        *) echo "unknown slide $1" >&2; exit 2 ;;
    esac
    [ -f "$SLIDE_NDPI" ] || { echo "slide not found: $SLIDE_NDPI" >&2; exit 2; }
}

# Production tiling: -s 2048 -l 256. Zarr writes in-process (--store-writers 0, the default).
TILE_ARGS=(-s 2048 -l 256 -g INFO)

# Node-local scratch for PNG trees that only exist to be compared (purged after the job).
SCRATCH=${TMPDIR:-/tmp}/zarr-test-${SLURM_JOB_ID:-manual}-${SLURM_ARRAY_TASK_ID:-0}

apptainer_run() {  # apptainer_run <workdir> <command...>; in NEW_SIF, wrapped in /usr/bin/time -v when present
    local wd=$1; shift
    local timer=()
    # GNU_TIME=0: no timer, for the comparers, whose last log line is the verdict
    [ -x /usr/bin/time ] && [ "${GNU_TIME:-1}" = 1 ] && timer=(/usr/bin/time -v)
    # The CLI starts its JVM without a heap limit, so Java sizes the heap from the node's RAM and grows it lazily:
    # the TADP Zarr crop was killed at the job's memory limit after about 46,000 planes. JAVA_TOOL_OPTIONS is read by
    # the JVM itself, so this caps the heap without code changes; decoded pixels are unaffected.
    "${timer[@]}" apptainer exec --env "JAVA_TOOL_OPTIONS=-Xmx${JAVA_HEAP:-4g}" \
        --bind "$APPTAINER_BINDS","$SCRATCH" --pwd "$wd" "$NEW_SIF" "$@"
}

crop() {  # crop <code_dir> <out_dir> <log> [extra cropper args...]: prints the cropper's exit code, never aborts
    local code=$1 out=$2 log=$3; shift 3
    local rc=0
    apptainer_run "$code" python3 ndpi_tile_cropper_cli.py -i "$SLIDE_NDPI" -o "$out" "${TILE_ARGS[@]}" "$@" \
        > "$log" 2>&1 || rc=$?
    echo "$rc"
}

compare() {  # compare <log> <script> <args...>: runs a comparer in our SIF, prints its exit code, never aborts
    local log=$1 script=$2; shift 2
    local rc=0
    GNU_TIME=0 apptainer_run "$SLURM_SUBMIT_DIR" python3 "$SLURM_SUBMIT_DIR/$script" "$@" > "$log" 2>&1 || rc=$?
    echo "$rc"
}

record_env() {  # record_env <out_dir>: commits, SIF hash, node, slide, for the report
    local out=$1
    {
        echo "date: $(date -Is)"; echo "host: $(hostname)"
        echo "job: ${SLURM_JOB_ID:-} array task: ${SLURM_ARRAY_TASK_ID:-} cpus: ${SLURM_CPUS_PER_TASK:-}"
        for c in "$CODE_BASE" "$CODE_NEW"; do echo "code $c: $(git -C "$c" rev-parse HEAD 2>/dev/null)"; done
        echo "sif $NEW_SIF: $(cat "$NEW_SIF.sha256" 2>/dev/null || sha256sum "$NEW_SIF" | cut -d' ' -f1)"
        echo "slide $SLIDE_KEY: $SLIDE_NDPI ($SLIDE_NAME)"; ls -lL "$SLIDE_NDPI"
        echo "data root resolves to: $(readlink -f "$DATA_ROOT")"
        echo "production tiles: ${PROD_PNG_DIR:-none}"
        echo "/dev/shm: $(df -h /dev/shm | tail -1)"
    } > "$out/env.txt" 2>&1
}
