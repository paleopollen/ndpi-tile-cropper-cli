FROM jupyter/minimal-notebook:python-3.9

USER root

RUN apt-get update && apt-get install -y \
    build-essential \
    openslide-tools \
    gdal-bin \
    libtiff-dev \
    default-jdk \
    python3-opencv \
&& rm -rf /var/lib/apt/lists/*

USER ${NB_UID}

COPY requirements.txt ./

RUN pip install --upgrade pip && pip install -r requirements.txt
