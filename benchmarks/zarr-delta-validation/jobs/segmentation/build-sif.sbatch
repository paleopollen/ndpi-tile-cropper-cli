#!/bin/bash
# Convert the segmentation image's `docker save` archive into a SIF on a compute node, and save its sha256 and
# `pip freeze` next to it (there is no production freeze; this is the record of what our image holds).
# Usage: ../submit.sh segmentation/build-sif.sbatch <SIF_DIR>/<image>.tar   -> <SIF_DIR>/<image>.sif
#SBATCH --job-name=build-sif-seg
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16g
#SBATCH --time=01:00:00
# The image is about 3 GB (5.2 GB of venv unpacked: torch 2.3.1+cu121).
set -euo pipefail
TAR=$1
SIF=${TAR%.tar}.sif
# Build entirely on node-local disk: Apptainer's layer handling on the network filesystem failed with
# "expected blob size N, but only wrote 1024" (2026-11-05). Only the finished SIF is copied back.
LOCAL=${TMPDIR:-/tmp}/apptainer-$USER-${SLURM_JOB_ID:-manual}
export APPTAINER_TMPDIR=$LOCAL/tmp APPTAINER_CACHEDIR=$LOCAL/cache
mkdir -p "$APPTAINER_TMPDIR" "$APPTAINER_CACHEDIR"
trap 'rm -rf "$LOCAL"' EXIT
df -hT "$LOCAL" | tail -1
cp "$TAR" "$LOCAL/image.tar"       # read the archive from local disk too
apptainer --version
# Docker 25+ `docker save` writes an OCI image layout (index.json + compressed blobs); oci-archive:// reads that layout
# directly, docker-archive:// reads the legacy manifest.json view of the same tar (fallback).
apptainer build --force "$LOCAL/out.sif" "oci-archive://$LOCAL/image.tar" || {
    echo "oci-archive:// failed; retrying with docker-archive://"
    apptainer build --force "$LOCAL/out.sif" "docker-archive://$LOCAL/image.tar"
}
cp "$LOCAL/out.sif" "$SIF.partial" && mv "$SIF.partial" "$SIF"
sha256sum "$SIF" | tee "$SIF.sha256"
{ echo "# $(apptainer exec "$SIF" python3 -V 2>&1)"; apptainer exec "$SIF" python3 -m pip freeze; } > "$SIF.pip-freeze.txt"
# Smoke check: the pinned stack and SAM 2 import (no GPU needed).
apptainer exec "$SIF" python3 -c "import sys, torch, numpy, zarr, palyim_io, sam2.build_sam, sam2.automatic_mask_generator; print(sys.version.split()[0], torch.__version__, numpy.__version__, zarr.__version__, palyim_io.__version__)"
echo "Done: $SIF, $SIF.sha256, $SIF.pip-freeze.txt. Delete $TAR when the SIF checks out."
