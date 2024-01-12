FROM python:3.9-slim

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y \
    build-essential \
    openslide-tools \
    gdal-bin \
    libtiff-dev \
    openjdk-17-jdk-headless \
    ca-certificates-java \
    python3-opencv \
    nano \
&& mkdir -p /data \
&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY src/ndpi_tile_cropper_cli.py ./

ENTRYPOINT [ "python3", "./ndpi_tile_cropper_cli.py"]