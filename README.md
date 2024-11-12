# NDPI Tile Cropper Command Line Interface

[![Docker](https://github.com/paleopollen/ndpi-tile-cropper-cli/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/paleopollen/ndpi-tile-cropper-cli/actions/workflows/docker-publish.yml)

This command-line program to process NDPI images and generate cropped image tiles at all available focal points is developed based on [NDPI tile cropping Jupyter Notebook](https://github.com/fengzard/open_world_pollen_detection/blob/main/03_NDPI_Slide_Annotation/03_00_ndpi_cropping.ipynb) authored by [@fengzard](https://github.com/fengzard).

## Docker Installation and Run Instructions (Recommended)

### Prerequisites
Docker must be installed on the host machine. Please refer to the [official Docker documentation](https://docs.docker.com/get-docker/) for installation instructions.

### Clone Repository

```shell
git clone https://github.com/paleopollen/ndpi-tile-cropper-cli.git
cd ndpi-tile-cropper-cli
```

### Build Docker Images

```shell
docker build -t ndpi-tile-cropper .
docker build -t ndpi-tile-cropper-parallel -f parallel.Dockerfile .
```

### Run Command Line Interface (Serial)

The following command will process a single NDPI file. This assumes that the NDPI file is located in an input folder `data/NDPI` within the source code directory. 
The output tiles will be saved in an output folder `data/NDPI/NDPI_1_tiles`. The input and output folders can be changed by modifying the `-i` and `-o` arguments and mounting the appropriate volumes, 
i.e. `-v $(pwd)/data:/data` needs to be replaced with `-v /path/to/input/data/folder:/data`.

Example command:

```shell
docker run -it --rm -v $(pwd)/data:/data --name ndpi-tile-cropper-container ndpi-tile-cropper -i /data/NDPI/NDPI_1.ndpi -o /data/NDPI/NDPI_1_tiles
```

Help command:

```shell
docker run -it --rm ndpi-tile-cropper --help
```

### Run Command Line Interface (Parallel)

The following command will process NDPI files the input folder `data/NDPI` in parallel mode. By default, it uses 8 processes. 
The number of processes can be changed by modifying the `--num_processes` or `-n` argument.

Example command:

```shell
docker run -it --rm -v $(pwd)/data:/data --name ~~ ndpi-tile-cropper-parallel -i /data/NDPI -o /data/NDPI/output
```

Help command:

```shell
docker run -it --rm ndpi-tile-cropper-parallel --help
```

## Usage


### ndpi_tile_cropper_cli

```shell
usage: ndpi_tile_cropper_cli.py [-h] --input-file [INPUT_FILE] [--output-dir [OUTPUT_DIR]] [--tile_size TILE_SIZE] [--overwrite] [--tile_overlap TILE_OVERLAP] [--tile_format {png}] [--zip] [--verbose]

Crop tiles from an NDPISlide.

optional arguments:
  -h, --help            show this help message and exit
  --input-file [INPUT_FILE], -i [INPUT_FILE]
                        Path to the input NDPISlide file. E.g., data/NDPI/NDPI_1.ndpi
  --output-dir [OUTPUT_DIR], -o [OUTPUT_DIR]
                        Path to the output directory. E.g., data/NDPI/NDPI_1_tiles. If no output directory path is provided, the program will create a directory using the input file's name and save the tiles in
                        that directory.
  --tile_size TILE_SIZE, -s TILE_SIZE
                        Size of the tiles to crop. Only square tiles are supported at present.
  --overwrite, -w       Overwrite existing tiles.
  --tile_overlap TILE_OVERLAP, -l TILE_OVERLAP
                        Overlap of the tiles in pixels.
  --tile_format {png}   Format of the tiles. [not implemented yet]
  --zip, -z             Zip the tiles output directory and remove the tiles directory. Unzip the tiles directory zip file, if it exists, before starting with the tiles creation.
  --verbose, -v         Display more details.
```

### ndpi_tile_cropper_cli_parallel

```shell
usage: ndpi_tile_cropper_parallel_cli.py [-h] --input-dir [INPUT_DIR] [--output-dir [OUTPUT_DIR]] [--tile_size TILE_SIZE] [--tile_overlap TILE_OVERLAP] [--num_processes NUM_PROCESSES] [--overwrite] [--zip]
                                         [--verbose]

Crop tiles from an NDPISlide using parallel processing.

optional arguments:
  -h, --help            show this help message and exit
  --input-dir [INPUT_DIR], -d [INPUT_DIR]
                        Path to the input NDPISlide directory. E.g., data/NDPI
  --output-dir [OUTPUT_DIR], -o [OUTPUT_DIR]
                        Path to the output directory. E.g., data/NDPI/NDPI_1_tiles. If no output directory path is provided, the program will create a directory using the input file's name and save the tiles in
                        that directory.
  --tile_size TILE_SIZE, -s TILE_SIZE
                        Size of the tiles to crop. Only square tiles are supported at present.
  --tile_overlap TILE_OVERLAP, -l TILE_OVERLAP
                        Overlap of the tiles in pixels.
  --num_processes NUM_PROCESSES, -n NUM_PROCESSES
                        Number of processes to use for parallel processing.
  --overwrite, -w       Overwrite existing tiles.
  --zip, -z             Zip the tiles output directory and remove the tiles directory. Unzip the tiles directory zip file, if it exists, before starting with the tiles creation.
  --verbose, -v         Display more details.
```

## Local Installation Instructions (Not Fully Tested - Please Use Docker Instead)

### Prerequisites
- Python must be installed on the host machine. Please refer to the [official Python documentation](https://www.python.org/downloads/) for installation instructions.
- Java must be installed on the host machine. Please refer to the [official Java documentation](https://www.java.com/en/download/) for installation instructions.

Recommended Python version: 3.9

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

### Run Command Line Interface

```shell
cd src
python ndpi_tile_cropper_cli.py --help
```
