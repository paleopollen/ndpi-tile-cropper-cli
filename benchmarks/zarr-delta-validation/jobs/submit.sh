#!/bin/bash
# Submit a job template with the account and log folder from config.sh.
#   ./submit.sh [sbatch options] <cropper|segmentation>/<script>.sbatch [script arguments]
# Settings pass through the environment:  G2_KEEP_PNG=1 ./submit.sh cropper/g2-zarr-vs-png.sbatch
# Options given here override the #SBATCH lines:  ./submit.sh --array=1 cropper/g2-zarr-vs-png.sbatch
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
[ -f "$HERE/config.sh" ] || { echo "copy config.example.sh to config.sh and fill it in" >&2; exit 2; }
source "$HERE/config.sh"
opts=()
while [ $# -gt 0 ] && [[ $1 != *.sbatch ]]; do opts+=("$1"); shift; done
[ $# -gt 0 ] || { echo "usage: ./submit.sh [sbatch options] <folder>/<script>.sbatch [script arguments]" >&2; exit 2; }
script=$HERE/$1; shift
[ -f "$script" ] || { echo "no such script: $script" >&2; exit 2; }
case "$SLURM_ACCOUNT_CPU $SLURM_ACCOUNT_GPU $OUT_ROOT $WORK_ROOT $APPTAINER_BINDS" in
    *CHANGEME*) echo "config.sh still has CHANGEME values" >&2; exit 2 ;;
esac
account=$SLURM_ACCOUNT_CPU
if grep -q '^#SBATCH --gpus' "$script" || [[ " ${opts[*]-} " == *" --gpus"* ]]; then account=$SLURM_ACCOUNT_GPU; fi
log='%x-%j.out'
if grep -q '^#SBATCH --array' "$script" || [[ " ${opts[*]-} " == *" --array"* ]]; then log='%x-%A_%a.out'; fi
mkdir -p "$OUT_ROOT/logs"
cd "$(dirname "$script")"      # the jobs read common.sh and the helpers from $SLURM_SUBMIT_DIR
exec sbatch --account="$account" --output="$OUT_ROOT/logs/$log" ${opts[@]+"${opts[@]}"} "$(basename "$script")" "$@"
