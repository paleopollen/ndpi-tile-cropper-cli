FROM python:3.9-slim-bookworm

LABEL maintainers="Sandeep Puthanveetil Satheesan <sandeeps@illinois.edu>"

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

# Create an arch-agnostic JAVA_HOME by symlinking the detected JDK path
RUN JH=$(dirname $(dirname $(readlink -f $(which javac)))) \
    && ln -s "$JH" /usr/lib/jvm/java-17-openjdk
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk
ENV LD_LIBRARY_PATH=$JAVA_HOME/lib/server:$LD_LIBRARY_PATH

COPY requirements.txt ./

RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir numpy==1.25.2 \
    && pip install --no-cache-dir -r requirements.txt

COPY src/ndpi_tile_cropper_cli.py ./

ENTRYPOINT [ "python3", "./ndpi_tile_cropper_cli.py"]