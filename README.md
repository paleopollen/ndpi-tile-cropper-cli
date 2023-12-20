# NDPI Images Cropping Command Line Interface

This command-line program to process NDPI images and generate cropped image tiles at all available focal points is developed based on NDPI images cropping [program](https://github.com/fengzard/open_world_pollen_detection/blob/main/03_NDPI_Slide_Annotation/03_00_ndpi_cropping.ipynb) authored by [@fengzard](https://github.com/fengzard).

## Docker Installation Instructions

### Build Docker Image

```shell
docker build -t ndpi_tile_cropper .
```

### Run Command Line Interface

Example command:

```shell
docker run -it --rm -v $(pwd)/data:/data ndpi_tile_cropper -i /data/NDPI/NDPI_1.ndpi -o /data/NDPI/NDPI_1_tiles
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

```shell
usage: ndpi_tile_cropper_cli.py [-h] --input-file [INPUT_FILE] [--output-dir [OUTPUT_DIR]] [--tile_size TILE_SIZE] [--tile_overlap TILE_OVERLAP] [--tile_format {png}] [--verbose]

Crop tiles from an NDPISlide.

optional arguments:
  -h, --help            show this help message and exit
  --input-file [INPUT_FILE], -i [INPUT_FILE]
                        Path to the input NDPISlide file.
  --output-dir [OUTPUT_DIR], -o [OUTPUT_DIR]
                        Path to the output directory.
  --tile_size TILE_SIZE, -s TILE_SIZE
                        Size of the tiles to crop. Only square tiles are supported at present.
  --tile_overlap TILE_OVERLAP, -l TILE_OVERLAP
                        Overlap of the tiles [not implemented yet].
  --tile_format {png}   Format of the tiles. [not implemented yet]
  --verbose, -v         Display more details.
```

