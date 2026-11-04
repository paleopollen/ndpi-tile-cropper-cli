# A Command Line Interface for NDPI Format Image Tile Cropping

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.14502306.svg)](https://doi.org/10.5281/zenodo.14502306)
[![Docker](https://github.com/paleopollen/ndpi-tile-cropper-cli/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/paleopollen/ndpi-tile-cropper-cli/actions/workflows/docker-publish.yml)

We present `NDPI Tile Cropper`, a Command Line Interface (CLI) to read Hamamatsu NanoZoomer Digital Pathology Image
(NDPI) format files and generate cropped image tiles at all available focal points. This CLI is developed based on
Deep Learning and Pollen Detection in the Open
World [notebooks](https://github.com/fengzard/open_world_pollen_detection) authored by
Jennifer T. Feng, Shu Kong, Timme H. Donders, and Surangi W. Punyasena.

## Docker-based Installation and Run Instructions (Recommended)

Note: This is not tested on Apple Silicon M series chips.

### Prerequisites

Docker must be installed on the host machine. Please refer to
the [official Docker documentation](https://docs.docker.com/get-docker/) for installation instructions.

### Clone Repository

```shell
git clone https://github.com/paleopollen/ndpi-tile-cropper-cli.git
cd ndpi-tile-cropper-cli
```

### Build Docker Images

The images install [palyim-io](https://github.com/paleopollen/palyim-io) (the Zarr tile store) from a local wheel
until that package is published. Build the wheel first and copy it into `wheels/` (ignored by git):

```shell
git clone <palyim-io repository> ../palyim-io   # until paleopollen/palyim-io exists
(cd ../palyim-io && uv build --wheel)
mkdir -p wheels && cp ../palyim-io/dist/palyim_io-0.1.0-py3-none-any.whl wheels/
```

Then build the images. On Apple Silicon add `--platform linux/amd64` (Bio-Formats' bundled libturbojpeg is x86_64 only):

```shell
docker build -t ndpi-tile-cropper .
docker build -t ndpi-tile-cropper-parallel -f parallel.Dockerfile .
```

The images run Python 3.12 (`python:3.12-slim-bookworm`). Every Python package is pinned through
`constraints.txt`; the comment at its top says where the pins come from.

### Run CLI in Serial Mode

The following command will process a single NDPI file. This assumes that the NDPI file is located in an input folder
`data/NDPI` within the source code directory.
The output tiles will be saved in an output folder `data/NDPI/NDPI_1_tiles`. The input and output folders can be changed
by modifying the `-i` and `-o` arguments and mounting the appropriate volumes,
i.e. `-v $(pwd)/data:/data` needs to be replaced with `-v </path/to/input/data/folder>:/data`.

Example command:

```shell
docker run -it --rm -v $(pwd)/data:/data --name ndpi-tile-cropper-container ndpi-tile-cropper -i /data/NDPI/NDPI_1.ndpi -o /data/NDPI/NDPI_1_tiles
```

Help command:

```shell
docker run -it --rm ndpi-tile-cropper --help
```

### Run CLI in Parallel Mode

The following command will process NDPI files the input folder `data/NDPI` in parallel mode. By default, it uses 8
processes. The number of processes can be changed by modifying the `--num_processes` or `-n` argument.

Example command:

```shell
docker run -it --rm -v $(pwd)/data:/data --name ndpi-tile-cropper-parallel-container ndpi-tile-cropper-parallel -i /data/NDPI -o /data/NDPI/output
```

Help command:

```shell
docker run -it --rm ndpi-tile-cropper-parallel --help
```

### Zarr Tile Store (`--tile_format zarr`)

`--tile_format zarr` writes one Zarr v3 store per slide, `<output_dir>/<slide>.zarr`, instead of the
`<output_dir>/<slide>/{x}x_{y}y/{z}z.png` tree. It needs palyim-io with its `[zarr]` extra (Python >= 3.11; the
images have it). PNG stays the default and its output is unchanged.

- **Contents:** `tiles` (N, Z, T, T, 3) uint8 in the PNG mode's tile order, `tile_xy` (N, 2), `plane_present`
  (N, Z), the attrs `palyim` holding exactly what PNG mode writes to `metadata.json`, the attrs `palyim_cropper`
  (input file name and size), and `progress.json`. The full contract is in the palyim-io README. Tile `i` at
  `tile_xy[i] = (x, y)` holds the same pixels as the PNGs in `{x}x_{y}y/`, plane by plane. Nothing is written under
  `<output_dir>/<slide>/`.
- **Progress:** attrs `palyim` are written when the store is created (`processed_tile_count` 0) and when it is
  finished. While a store is incomplete, after an interruption for example, only `progress.json` (`shards_done`)
  says how far it got; readers refuse incomplete stores.
- **Files:** about one file per shard of k tiles (k = 4 for 9 planes at 2048 px), so roughly 940 files for a
  3,750-tile slide instead of about 34,000 PNGs and 3,750 folders.
- **Rerun:** an unfinished store is resumed from its `progress.json`, after checking that it was made from the same
  input: the same grid, planes and tile size, the same recorded width, height and calibration, and the same input
  file name and size. A store made from another input or with other settings is refused (exit 1) with a pointer to
  `--overwrite`, which deletes the store and starts over. A complete store is left alone.
- **Read failures:** a plane that cannot be read is stored as zeros, marked False in `plane_present` and listed in
  `progress.json` (`missing_planes`). The store is still completed, but the run exits 1. Rerunning the same command
  re-reads only those planes.
- **Exit status:** 0 when the store is complete with every plane present, 1 otherwise (read failures, a writer
  error, an exception, or SIGINT/SIGTERM), and 2 for `--zip`, which cannot be combined with `zarr`. PNG mode keeps
  its exit status (0, also after exceptions and signals).
- **Signals:** SIGINT or SIGTERM, to this process or to its whole process group (Ctrl-C, `scancel`), stop the
  reading; writer processes ignore both and finish the shard they hold, which is recorded before the run exits 1.
  The rerun resumes. SIGKILL (the OOM killer, or `scancel` after its grace period) loses the shards in flight; they
  are rewritten on resume.
- **Processes and memory:** by default this process reads a shard (k tiles, all planes) into one buffer, then
  compresses and writes it, using all its CPUs for the compression. With `--store-writers W` (W >= 1), W extra
  processes compress and write shards while this one reads the next. Reading is usually the bottleneck, so this
  gained 0-10% in local tests. The buffers are `writers + 1` blocks of shared memory in
  `/dev/shm`, one shard each (432 MiB for 9 planes at 2048 px, 504 MiB for 21 planes); each writer needs up to
  about 1 GB more while it compresses. **In Docker, pass `--shm-size`** (for example `--shm-size=2g` for one
  writer): if `/dev/shm` is too small (Docker's default is 64 MB) the run logs a warning and writes in the reading
  process instead, as with the default `--store-writers 0` (no extra processes, one buffer). Codec threads per writer
  are taken from `SLURM_CPUS_PER_TASK` (or the CPU affinity), with one CPU left to the reader.
- **Shared-memory leaks (writers only):** if the whole process group is SIGKILLed, its blocks stay in `/dev/shm` and
  hold memory. They are named `palyim-crop-j<SLURM_JOB_ID>-p<pid>-b<i>`; every later run with writers on that node
  removes the blocks of this user whose pid is no longer alive. To check by hand: `ls -l /dev/shm/palyim-crop-*`.
  The default `--store-writers 0` uses no shared memory.
- The parallel CLI (`ndpi_tile_cropper_parallel_cli.py`) does not pass `--tile_format` yet.

Example:

```shell
docker run -it --rm -v $(pwd)/data:/data ndpi-tile-cropper -i /data/NDPI/NDPI_1.ndpi -o /data/NDPI/tiles \
    -s 2048 -l 256 --tile_format zarr
```

Both modes log per-phase timings at the end of a run, and `--timings-json <file>` also writes them to a file. Zarr
mode stores them in the store's attrs as well.

## Usage

### ndpi_tile_cropper_cli

```shell
usage: python ndpi_tile_cropper_cli.py [-h] --input-file [INPUT_FILE] [--output-dir [OUTPUT_DIR]] [--tile_size TILE_SIZE] [--overwrite]
                                [--tile_overlap TILE_OVERLAP] [--tile_format {png,zarr}] [--store-writers STORE_WRITERS]
                                [--store-tiles-per-shard STORE_TILES_PER_SHARD] [--timings-json TIMINGS_JSON] [--zip]
                                [--log-level [{DEBUG,INFO,WARNING,ERROR,CRITICAL}]] [--verbose]

Crop and generate tile images from an NDPI format image file.

optional arguments:
  -h, --help            show this help message and exit
  --input-file [INPUT_FILE], -i [INPUT_FILE]
                        Path to the input NDPISlide file. E.g., data/NDPI/NDPI_1.ndpi
  --output-dir [OUTPUT_DIR], -o [OUTPUT_DIR]
                        Path to the output directory. E.g., data/NDPI/NDPI_1_tiles. If no output directory path is provided, the program will
                        create a directory using the input file\'s name and save the tiles in that directory.
  --tile_size TILE_SIZE, -s TILE_SIZE
                        Size of the tiles to crop. Only square tiles are supported at present.
  --overwrite, -w       Overwrite existing tiles.
  --tile_overlap TILE_OVERLAP, -l TILE_OVERLAP
                        Overlap of the tiles in pixels.
  --tile_format {png,zarr}
                        Format of the tiles. png (default): one PNG per focal plane under <output_dir>/<slide>/. zarr: one Zarr v3 tile
                        store <output_dir>/<slide>.zarr (needs palyim-io[zarr], Python >= 3.11); not combinable with --zip.
  --store-writers STORE_WRITERS
                        Zarr mode: number of writer processes that compress and write shards while this process reads the next one
                        (default 0: write in this process). Each writer needs one more shard buffer in /dev/shm (~432 MiB for 9 planes
                        at 2048 px; pass --shm-size to Docker) plus up to ~1 GB while it writes. Reading is usually the bottleneck, so
                        writers gain little (0-10% in local tests).
  --store-tiles-per-shard STORE_TILES_PER_SHARD
                        Zarr mode, for tests: tiles per shard when the store is created. Default: palyim-io's floor(512 MiB / (Z x tile
                        bytes)), e.g. 4 for 9 planes of 2048 px.
  --timings-json TIMINGS_JSON
                        Write the per-phase timings to this JSON file. They are always logged at the end of a run; Zarr mode also stores
                        them in the store's attrs.
  --zip, -z             Zip the tiles output directory and remove the tiles directory. Unzip the tiles directory zip file, if it exists, before
                        starting with the tiles creation.
  --log-level [{DEBUG,INFO,WARNING,ERROR,CRITICAL}], -g [{DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                        Set the logging level.
  --verbose, -v         Display more details.
```

### ndpi_tile_cropper_cli_parallel

```shell
usage: python ndpi_tile_cropper_parallel_cli.py [-h] --input-dir [INPUT_DIR] [--output-dir [OUTPUT_DIR]] [--tile_size TILE_SIZE]
                                         [--tile_overlap TILE_OVERLAP] [--num_processes NUM_PROCESSES] [--overwrite] [--zip]
                                         [--log-level [{DEBUG,INFO,WARNING,ERROR,CRITICAL}]] [--verbose]

Crop tiles from an NDPISlide using parallel processing.

optional arguments:
  -h, --help            show this help message and exit
  --input-dir [INPUT_DIR], -d [INPUT_DIR]
                        Path to the input NDPISlide directory. E.g., data/NDPI
  --output-dir [OUTPUT_DIR], -o [OUTPUT_DIR]
                        Path to the output directory. E.g., data/NDPI/NDPI_1_tiles. If no output directory path is provided, the program will
                        create a directory using the input file\'s name and save the tiles in that directory.
  --tile_size TILE_SIZE, -s TILE_SIZE
                        Size of the tiles to crop. Only square tiles are supported at present.
  --tile_overlap TILE_OVERLAP, -l TILE_OVERLAP
                        Overlap of the tiles in pixels.
  --num_processes NUM_PROCESSES, -n NUM_PROCESSES
                        Number of processes to use for parallel processing.
  --overwrite, -w       Overwrite existing tiles.
  --zip, -z             Zip the tiles output directory and remove the tiles directory. Unzip the tiles directory zip file, if it exists, before
                        starting with the tiles creation.
  --log-level [{DEBUG,INFO,WARNING,ERROR,CRITICAL}], -g [{DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                        Set the logging level.
  --verbose, -v         Display more details.
```

## Standard Installation Instructions (Not fully tested - please use Docker-based installation instead)

### Prerequisites

- Python must be installed on the host machine. Please refer to
  the [official Python documentation](https://www.python.org/downloads/) for installation instructions.
- Java must be installed on the host machine. Please refer to
  the [official Java documentation](https://www.java.com/en/download/) for installation instructions.

Recommended Python version: 3.12 (the images). PNG mode also runs on 3.9; Zarr mode needs >= 3.11 and palyim-io[zarr].

### Clone Repository

```shell
git clone https://github.com/paleopollen/ndpi-tile-cropper-cli.git
cd ndpi-tile-cropper-cli
```

### Setup Virtual Environment

```shell
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Tests

The tests run the real CLI and Bio-Formats on a small synthetic 3-plane TIFF (an ImageJ hyperstack written with
tifffile), in PNG and Zarr mode, inside the image:

```shell
docker build --platform linux/amd64 -t ndpi-tile-cropper .
docker build --platform linux/amd64 -f test.Dockerfile --build-arg BASE_IMAGE=ndpi-tile-cropper -t ndpi-tile-cropper-test .
docker run --rm --platform linux/amd64 ndpi-tile-cropper-test
```

To also check that PNG output is byte-identical to another commit's, mount that commit's CLI and point
`CROPPER_BASE_CLI` at it:

```shell
git show <commit>:src/ndpi_tile_cropper_cli.py > /tmp/base_cli/ndpi_tile_cropper_cli.py
docker run --rm --platform linux/amd64 -v /tmp/base_cli:/base -e CROPPER_BASE_CLI=/base/ndpi_tile_cropper_cli.py ndpi-tile-cropper-test
```

`src/utils/palyim_timing.py` is a verbatim copy of palyim-io's `timing.py`, so PNG mode has no palyim-io dependency
and runs on older images; a test fails if the copy drifts.

### Run CLI Help Command

```shell
cd src
python ndpi_tile_cropper_cli.py --help
```
