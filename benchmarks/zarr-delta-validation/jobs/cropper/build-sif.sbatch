#!/bin/bash
# Convert a `docker save` archive into a SIF on a compute node.
# Usage: ../submit.sh cropper/build-sif.sbatch <SIF_DIR>/<image>.tar   -> <SIF_DIR>/<image>.sif
#SBATCH --job-name=build-sif
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16g
#SBATCH --time=01:00:00
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
# The image's pins, saved next to the SIF.
{ echo "# $(apptainer exec "$SIF" python3 -V 2>&1)"; apptainer exec "$SIF" python3 -m pip freeze; } > "$SIF.pip-freeze.txt"
# Smoke check: Python, numpy, zarr and palyim-io as pinned, and Bio-Formats starts.
apptainer exec "$SIF" python3 -c "import sys, numpy, zarr, palyim_io; print(sys.version.split()[0], numpy.__version__, zarr.__version__, palyim_io.__version__)"
apptainer exec --pwd /usr/src/app "$SIF" python3 -c "import javabridge, bioformats; javabridge.start_vm(class_path=bioformats.JARS, run_headless=True); print('jvm ok'); javabridge.kill_vm()"
echo "Done. Delete $TAR when the SIF checks out."
