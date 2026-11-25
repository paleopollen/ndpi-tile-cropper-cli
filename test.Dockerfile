# Test image: the cropper image plus pytest and tifffile, with the tests baked in. Build the cropper image first
# (see "Tests" in the README), then:
#   docker build --platform linux/amd64 -f test.Dockerfile --build-arg BASE_IMAGE=ndpi-tile-cropper -t ndpi-tile-cropper-test .
#   docker run --rm --platform linux/amd64 ndpi-tile-cropper-test
ARG BASE_IMAGE=ndpi-tile-cropper
FROM ${BASE_IMAGE}

COPY requirements-test.txt ./
RUN pip install --no-cache-dir --only-binary :all: -c constraints.txt -r requirements-test.txt

COPY tests/ ./tests/

ENV CROPPER_SRC=/usr/src/app
ENTRYPOINT [ "python3", "-m", "pytest", "-p", "no:cacheprovider", "-v", "tests" ]
