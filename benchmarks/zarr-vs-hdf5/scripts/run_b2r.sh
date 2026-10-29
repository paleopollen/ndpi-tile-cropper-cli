#!/bin/bash
# bioformats2raw on the NDPI's 1/8-scale series (series 1: 9 x 11328 x 16864 x 3) -> OME-Zarr, level 0 only.
# Full-resolution series 0 would be ~330 GB raw; too big for this Mac. Image: openmicroscopy/bioformats2raw:latest (amd64).
set -u
B=$(cd "$(dirname "$0")/.." && pwd); NDPI_DIR=${NDPI_DIR:-/Users/rmp6/Documents/palyim/ndpi-tile-cropper-cli/data}; OUT="$B/data/b2r"; rm -rf "$OUT"; mkdir -p "$OUT"
NDPI="/data/PAL1999_B2_sample103_slide1 - 2023-01-11 08.16.52.ndpi"
V=$(docker run --rm --platform linux/amd64 openmicroscopy/bioformats2raw:latest --version 2>/dev/null | tr '\n' ' ')
START=$(date +%s)
docker run --rm --platform linux/amd64 -v "$NDPI_DIR:/data:ro" -v "$OUT:/out" \
  openmicroscopy/bioformats2raw:latest --series 1 --resolutions 1 --tile-width 2048 --tile-height 2048 \
  --compression blosc --compression-properties cname=zstd --compression-properties clevel=3 --compression-properties shuffle=1 \
  --max-workers 4 "$NDPI" /out/series1.zarr > "$B/results/b2r.log" 2>&1
RC=$?; END=$(date +%s)
echo "bioformats2raw: $V | rc=$RC | wall=$((END-START))s | files=$(find "$OUT" -type f | wc -l | tr -d ' ') | bytes=$(du -sk "$OUT" | cut -f1)k" | tee -a "$B/results/b2r.log"
find "$OUT" -maxdepth 3 | head -20 >> "$B/results/b2r.log"
