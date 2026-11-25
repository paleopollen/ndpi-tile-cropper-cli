"""Fixtures for the cropper tests. They run the real CLI, with the real Bio-Formats reader, in subprocesses
(javabridge can start one JVM per process). Run them inside the image built from Dockerfile + test.Dockerfile:

    docker run --rm --platform linux/amd64 ndpi-tile-cropper-test

CROPPER_SRC points at the directory holding ndpi_tile_cropper_cli.py (the image sets /usr/src/app;
default: this checkout's src/).
"""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("CROPPER_SRC", os.path.join(os.path.dirname(HERE), "src"))
CLI = os.path.join(SRC, "ndpi_tile_cropper_cli.py")
DRIVER = os.path.join(HERE, "inject_driver.py")

# Synthetic slide: 600 x 600 px, 3 planes, RGB. Tiles of 128 px with 16 px overlap give the grid
# arange(0, 472, 112) = 0, 112, 224, 336, 448 on both axes: 25 tiles. Columns 0..129 are zero on every plane,
# so the 5 tiles at x = 0 are all zero; with 4 tiles per shard, shard 0 is all zero (no shard file).
WIDTH = HEIGHT = 600
Z = 3
TILE = 128
OVERLAP = 16
K = 4
# An ImageJ hyperstack TIFF: Bio-Formats' TiffReader reports SizeZ = 3 and the calibration both through
# get_omexml_metadata (read_metadata) and through the ImageReader (crop). An OME-TIFF from tifffile does not:
# get_omexml_metadata reaches it through the plain TiffReader and reports one plane.
# Bio-Formats returns these RGB planes planar (isInterleaved False, unlike NDPI), so the cropper's
# reshape to (h, w, 3) reorders the bytes; it does so identically in both modes. expected_tile() models it.
SLIDE_FILE = "synth slide.tif"  # the cropper cuts the name at the first space: slide "synth"
SLIDE = "synth"
STEP = TILE - OVERLAP
XS = list(range(0, WIDTH - TILE, STEP))
YS = list(range(0, HEIGHT - TILE, STEP))
GRID = [(x, y) for x in XS for y in YS]
TILE_ARGS = ["-s", str(TILE), "-l", str(OVERLAP)]


def expected_tile(pixels, x, y, z):
    """What the cropper stores for tile (x, y), plane z: Bio-Formats' planar bytes (RRR..GGG..BBB) of the
    region, reshaped to (TILE, TILE, 3) as crop_tiles() does."""
    region = pixels[z, y:y + TILE, x:x + TILE, :]
    return np.ascontiguousarray(np.moveaxis(region, 2, 0)).reshape(TILE, TILE, 3)


def make_pixels(seed=7):
    rng = np.random.default_rng(seed)
    data = rng.integers(0, 256, size=(Z, HEIGHT, WIDTH, 3), dtype=np.uint8)
    data[:, :, :130, :] = 0
    return data


def write_slide(path, pixels_per_um=4.0):
    """Write the synthetic slide (calibration 1 / pixels_per_um um per pixel) to ``path``."""
    import tifffile

    tifffile.imwrite(path, make_pixels(), imagej=True, photometric="rgb",
                     resolution=(pixels_per_um, pixels_per_um), metadata={"axes": "ZYXS", "unit": "um", "spacing": 1.0})
    return path


@pytest.fixture(scope="session")
def slide(tmp_path_factory):
    d = tmp_path_factory.mktemp("slide")
    return write_slide(str(d / SLIDE_FILE))


def run_cli(args, env_extra=None, use_driver=False, cli=CLI, timeout=900):
    env = dict(os.environ)
    env["CROPPER_CLI"] = cli
    env.update(env_extra or {})
    cmd = [sys.executable, DRIVER if use_driver else cli] + list(args)
    proc = subprocess.run(cmd, env=env, cwd=os.path.dirname(cli), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout, universal_newlines=True)
    return proc


def start_cli_in_new_session(args, log_path, env_extra=None, use_driver=True, cli=CLI):
    """Start the CLI in its own process group (so the test can signal the whole group); returns the Popen."""
    env = dict(os.environ)
    env["CROPPER_CLI"] = cli
    env.update(env_extra or {})
    cmd = [sys.executable, DRIVER if use_driver else cli] + list(args)
    log = open(log_path, "w")
    return subprocess.Popen(cmd, env=env, cwd=os.path.dirname(cli), stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)


def wait_for_reads(log, n, proc, timeout=600):
    """Wait until the injection log has at least n reads (or the process ended)."""
    import time

    t0 = time.time()
    while time.time() - t0 < timeout:
        if len(read_log(log)) >= n or proc.poll() is not None:
            return len(read_log(log))
        time.sleep(0.2)
    raise AssertionError("timed out waiting for %d reads" % n)


def read_log(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [tuple(int(v) for v in line.split()) for line in f if line.strip()]


@pytest.fixture(scope="session")
def png_reference(slide, tmp_path_factory):
    """PNG-mode output of the current code, run through the driver to record which modules it loaded."""
    out = tmp_path_factory.mktemp("png")
    report = str(out.parent / "png-modules.txt")
    timings = str(out.parent / "png-timings.json")
    proc = run_cli(["-i", slide, "-o", str(out), "--timings-json", timings] + TILE_ARGS,
                   env_extra={"INJECT_MODULES_REPORT": report}, use_driver=True)
    assert proc.returncode == 0, proc.stdout
    from PIL import Image

    slide_dir = out / SLIDE
    tiles = {}
    for x, y in GRID:
        tiles[(x, y)] = np.stack([np.asarray(Image.open(str(slide_dir / ("%dx_%dy" % (x, y)) / ("%dz.png" % z))))
                                  for z in range(Z)])
    with open(str(slide_dir / "metadata.json")) as f:
        metadata = json.load(f)
    with open(report) as f:
        modules = set(f.read().split())
    return {"dir": str(slide_dir), "tiles": tiles, "metadata": metadata, "modules": modules,
            "timings": timings, "log": proc.stdout}
