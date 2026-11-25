# Zarr vs HDF5 tile-storage benchmark

Companion study for the container-format question (see `BRIEF.md`); results and recommendation in `RESULTS.md`.
Everything runs locally; the NDPI read side needs the cropper image built with `--platform linux/amd64`
(Bio-Formats has no arm64 libturbojpeg).

```
uv sync                                   # Python 3.12+, zarr 3, h5py, hdf5plugin
docker build --platform linux/amd64 -t ndpi-tile-cropper:amd64 ../..
docker run --rm --platform linux/amd64 --entrypoint python3 \
  -v <ndpi dir>:/data:ro -v $PWD/data/region:/bench -v $PWD/scripts:/scripts:ro ndpi-tile-cropper:amd64 \
  /scripts/extract_region.py --ndpi "/data/<slide>.ndpi" --out /bench --x0 71680 --y0 43008 --size 16384
cp data/region/read_timing.json results/
scripts/run_benchmark.sh data/region           # writes all formats, read benchmarks, concurrency runs
scripts/run_b2r.sh                             # bioformats2raw on the 1/8-scale series
uv run scripts/make_table.py                   # markdown table from results/*.jsonl
```
