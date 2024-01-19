# NDPI Tile Cropper Command Line Interface

This command-line program to process NDPI images and generate cropped image tiles at all available focal points is developed based on [NDPI tile cropping Jupyter Notebook](https://github.com/fengzard/open_world_pollen_detection/blob/main/03_NDPI_Slide_Annotation/03_00_ndpi_cropping.ipynb) authored by [@fengzard](https://github.com/fengzard).

## Docker Installation Instructions

### Build Docker Images

```shell
docker build -t ndpi-tile-cropper .
docker build -t ndpi-tile-cropper-parallel -f parallel.Dockerfile .
```

### Run Command Line Interface (Serial)

Example command:

```shell
docker run -it --rm -v $(pwd)/data:/data --name ndpi-tile-cropper-container ndpi-tile-cropper -i /data/NDPI/NDPI_1.ndpi -o /data/NDPI/NDPI_1_tiles
```

Help command:

```shell
docker run -it --rm ndpi-tile-cropper --help
```

### Run Command Line Interface (Parallel)

The following command will process NDPI files the input folder `/data/NDPI` in parallel mode. By default, it uses 8 processes. The number of processes can be changed by modifying the `--num_processes` or `-n` argument.

Example command:

```shell
docker run -it --rm -v $(pwd)/data:/data --name ndpi-tile-cropper-container-parallel ndpi-tile-cropper-parallel -i /data/NDPI -o /data/NDPI/output
```

Help command:

```shell
docker run -it --rm ndpi-tile-cropper-parallel --help
```


## Local Installation Instructions (Not Fully Tested)

Recommended Python version: 3.9

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

## Usage


### ndpi_tile_cropper_cli

```shell
usage: ndpi_tile_cropper_cli.py [-h] --input-file [INPUT_FILE] [--output-dir [OUTPUT_DIR]] [--tile_size TILE_SIZE] [--tile_overlap TILE_OVERLAP] [--tile_format {png}] [--verbose]

Crop tiles from an NDPISlide.

optional arguments:
  -h, --help            show this help message and exit
  --input-file [INPUT_FILE], -i [INPUT_FILE]
                        Path to the input NDPISlide file. E.g., data/NDPI/NDPI_1.ndpi
  --output-dir [OUTPUT_DIR], -o [OUTPUT_DIR]
                        Path to the output directory. E.g., data/NDPI/NDPI_1_tiles. If no output directory path is provided, the program will create a directory using the input file's name and save the tiles in that directory.
  --tile_size TILE_SIZE, -s TILE_SIZE
                        Size of the tiles to crop. Only square tiles are supported at present.
  --tile_overlap TILE_OVERLAP, -l TILE_OVERLAP
                        Overlap of the tiles [not implemented yet].
  --tile_format {png}   Format of the tiles. [not implemented yet]
  --verbose, -v         Display more details.
```

### ndpi_tile_cropper_cli_parallel

```shell
usage: ndpi_tile_cropper_parallel_cli.py [-h] --input-dir [INPUT_DIR] [--output-dir [OUTPUT_DIR]] [--num_processes NUM_PROCESSES] [--verbose]

Crop tiles from an NDPISlide using parallel processing.

optional arguments:
  -h, --help            show this help message and exit
  --input-dir [INPUT_DIR], -d [INPUT_DIR]
                        Path to the input NDPISlide directory. E.g., data/NDPI
  --output-dir [OUTPUT_DIR], -o [OUTPUT_DIR]
                        Path to the output directory. E.g., data/NDPI/NDPI_1_tiles. If no output directory path is provided, the program will create a directory using the input file's name and save the tiles in that directory.
  --num_processes NUM_PROCESSES, -n NUM_PROCESSES
                        Number of processes to use for parallel processing.
  --verbose, -v         Display more details.
```
