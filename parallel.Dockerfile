FROM python:3.12-slim-bookworm

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

COPY requirements.txt constraints.txt ./

# See Dockerfile: palyim-io comes from its release wheel in wheels/. Keep the version the same as there.
ARG PALYIM_IO_VERSION=0.1.2
COPY wheels/palyim_io-${PALYIM_IO_VERSION}-py3-none-any.whl /tmp/wheels/

RUN pip install --no-cache-dir pip==26.3 \
 && pip install --no-cache-dir --only-binary :all: -c constraints.txt -r requirements.txt \
        "/tmp/wheels/palyim_io-${PALYIM_IO_VERSION}-py3-none-any.whl[zarr]" \
 && rm -rf /tmp/wheels

COPY src/ndpi_tile_cropper_cli.py src/ndpi_tile_cropper_parallel_cli.py src/zarr_mode.py ./
COPY src/utils/__init__.py src/utils/palyim_timing.py ./utils/

ENTRYPOINT [ "python3", "./ndpi_tile_cropper_parallel_cli.py"]
