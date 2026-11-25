FROM python:3.12-slim-bookworm

LABEL maintainers="Sandeep Puthanveetil Satheesan <sandeeps@illinois.edu>"

WORKDIR /usr/src/app

# bookworm, not plain python:3.12-slim (trixie), which has no openjdk-17. JAVA_HOME / CP_JAVA_HOME stay unset,
# so javabridge runs the Java 8 JRE bundled in its wheel, as in the Python 3.9 image.
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

# palyim-io (the Zarr tile store) comes from the wheel attached to its GitHub release. The repository is private,
# so the wheel goes into wheels/ (kept out of git) before the build:
#   gh release download v0.1.2 -R paleopollen/palyim-io -p 'palyim_io-*.whl' -D wheels
# GitHub Actions does the same with the PALYIM_IO_TOKEN secret (.github/workflows/docker-publish.yml).
# --only-binary: python-javabridge must come from the girder cp312 wheel (-f in requirements.txt), never from a
# source build.
ARG PALYIM_IO_VERSION=0.1.2
COPY wheels/palyim_io-${PALYIM_IO_VERSION}-py3-none-any.whl /tmp/wheels/

RUN pip install --no-cache-dir pip==26.3 \
 && pip install --no-cache-dir --only-binary :all: -c constraints.txt -r requirements.txt \
        "/tmp/wheels/palyim_io-${PALYIM_IO_VERSION}-py3-none-any.whl[zarr]" \
 && rm -rf /tmp/wheels

COPY src/ndpi_tile_cropper_cli.py src/zarr_mode.py ./
COPY src/utils/__init__.py src/utils/palyim_timing.py ./utils/

ENTRYPOINT [ "python3", "./ndpi_tile_cropper_cli.py"]
