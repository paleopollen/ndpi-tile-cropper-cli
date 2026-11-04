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

# palyim-io is installed from a local wheel until paleopollen/palyim-io is published; build it first
# (see "Building the images" in the README). --only-binary: python-javabridge must come from the girder
# cp312 wheel (-f in requirements.txt), never from a source build.
COPY wheels/palyim_io-0.1.0-py3-none-any.whl /tmp/wheels/

RUN pip install --no-cache-dir pip==26.3 \
 && pip install --no-cache-dir --only-binary :all: -c constraints.txt -r requirements.txt \
        "/tmp/wheels/palyim_io-0.1.0-py3-none-any.whl[zarr]" \
 && rm -rf /tmp/wheels

COPY src/ndpi_tile_cropper_cli.py src/zarr_mode.py ./
COPY src/utils/__init__.py src/utils/palyim_timing.py ./utils/

ENTRYPOINT [ "python3", "./ndpi_tile_cropper_cli.py"]
