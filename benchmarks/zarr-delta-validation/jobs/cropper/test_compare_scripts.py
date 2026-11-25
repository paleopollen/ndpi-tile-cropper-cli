"""Local tests of the comparers (not run on Delta). They need palyim-io[zarr], Pillow and pytest, so run them
inside the cropper test image with this folder mounted:

    docker run --rm --platform linux/amd64 -v "$PWD":/jobs:ro \
        --entrypoint python3 ndpi-tile-cropper-test -m pytest -p no:cacheprovider -v /jobs/test_compare_scripts.py

Each bad case must fail the gate; the reviewer's three (store missing planes, an extra PNG folder, metadata.json
differing from attrs) are among them.
"""
import copy
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

from palyim_io import layout, tile_store

HERE = os.path.dirname(os.path.abspath(__file__))
T, Z, K = 32, 3, 2
XY = [(0, 0), (0, 24), (24, 0), (24, 24), (48, 0)]


def metadata(n=len(XY)):
    return {"tile_size": T, "tile_overlap": 8,
            "ome_metadata": {"calibration": 0.25, "calibration_unit": "µm", "width": 90, "height": 60, "z_plane": Z},
            "total_tile_count": n, "processed_tile_count": n, "percent_complete": 100.0 if n else 0.0}


def pixels(seed=1):
    return np.random.default_rng(seed).integers(0, 256, size=(len(XY), Z, T, T, 3), dtype=np.uint8)


def make_png(root, px, meta, xy=XY):
    d = os.path.join(root, "slide")
    os.makedirs(d)
    for i, (x, y) in enumerate(xy):
        t = os.path.join(d, layout.tile_name(x, y))
        os.makedirs(t)
        for z in range(Z):
            Image.fromarray(px[i, z]).save(os.path.join(t, "%dz.png" % z))
    with open(os.path.join(d, "metadata.json"), "w") as f:
        json.dump(meta, f, indent=4)
    return d


def make_store(root, px, meta, xy=XY, missing=()):
    path = os.path.join(root, "slide.zarr")
    store = tile_store.create(path, xy, Z, dict(meta, processed_tile_count=0, percent_complete=0.0), tile_size=T,
                              tiles_per_shard=K)
    for s in range(store.shards_total):
        a, b = store.shard_range(s)
        stack = px[a:b].copy()
        mask = np.ones((b - a, Z), bool)
        for i, z in missing:
            if a <= i < b:
                stack[i - a, z] = 0
                mask[i - a, z] = False
        store.record_shard(tile_store.write_shard(path, s, stack), mask)
    store.mark_complete(slide_metadata=meta)
    return path


def run(script, *args):
    proc = subprocess.run([sys.executable, os.path.join(HERE, script)] + [str(a) for a in args],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    return proc.returncode, proc.stdout


@pytest.fixture
def good(tmp_path):
    px, meta = pixels(), metadata()
    return {"png": make_png(str(tmp_path / "png"), px, meta), "store": make_store(str(tmp_path / "zarr"), px, meta),
            "px": px, "meta": meta, "tmp": tmp_path}


# -- compare_zarr_png.py (G2) ------------------------------------------------------------------------------------
def test_g2_gate_passes_equal_outputs(good):
    rc, out = run("compare_zarr_png.py", good["store"], good["png"], good["tmp"] / "r.json", 2)
    assert rc == 0 and "VERDICT gate: PASS" in out, out


def test_g2_gate_fails_store_with_missing_planes(good):
    # Reviewer case 1: the Zarr run lost planes the PNG run has (stored as zeros, plane_present False).
    store = make_store(str(good["tmp"] / "zarr2"), good["px"], good["meta"], missing=[(3, 0), (3, 1), (3, 2)])
    rc, out = run("compare_zarr_png.py", store, good["png"], good["tmp"] / "r.json", 2)
    assert rc == 1 and "no_store_planes_missing" in out and "every_plane_equal" in out, out


def test_g2_gate_fails_extra_png_folder(good):
    # Reviewer case 2: a PNG tile folder the store does not have.
    extra = os.path.join(good["png"], "999x_999y")
    os.makedirs(extra)
    shutil.copy(os.path.join(good["png"], "24x_24y", "0z.png"), extra)
    rc, out = run("compare_zarr_png.py", good["store"], good["png"], good["tmp"] / "r.json", 2)
    assert rc == 1 and "every_png_folder_in_store" in out, out


def test_g2_gate_fails_metadata_json_differing_from_attrs(good):
    # Reviewer case 3.
    p = os.path.join(good["png"], "metadata.json")
    meta = json.load(open(p))
    meta["percent_complete"] = 12.5
    json.dump(meta, open(p, "w"))
    rc, out = run("compare_zarr_png.py", good["store"], good["png"], good["tmp"] / "r.json", 2)
    assert rc == 1 and "attrs_equal_metadata_json" in out and "percent_complete" in out, out


def test_g2_gate_fails_missing_png_plane_and_pixel_change(good):
    os.remove(os.path.join(good["png"], "0x_24y", "2z.png"))
    px = good["px"].copy()
    px[4, 1, 0, 0, 0] ^= 1
    Image.fromarray(px[4, 1]).save(os.path.join(good["png"], "48x_0y", "1z.png"))
    rc, out = run("compare_zarr_png.py", good["store"], good["png"], good["tmp"] / "r.json", 2)
    assert rc == 1 and "no_png_planes_missing" in out and "no_mismatches" in out, out


def test_g2_gate_fails_empty_store_and_blank_outputs(tmp_path):
    rc, out = run("compare_zarr_png.py", make_store(str(tmp_path / "e"), pixels()[:0], metadata(0), xy=[]),
                  make_png(str(tmp_path / "ep"), pixels()[:0], metadata(0), xy=[]), tmp_path / "r.json", 2)
    assert rc == 1 and "store_has_tiles_and_planes" in out and "every_plane_equal" in out, out
    blank, meta = np.zeros_like(pixels()), metadata()
    rc, out = run("compare_zarr_png.py", make_store(str(tmp_path / "b"), blank, meta),
                  make_png(str(tmp_path / "bp"), blank, meta), tmp_path / "r2.json", 2)
    assert rc == 1 and "some_planes_have_content" in out, out


def test_g2_report_mode_never_fails(good):
    os.remove(os.path.join(good["png"], "0x_24y", "2z.png"))
    rc, out = run("compare_zarr_png.py", good["store"], good["png"], good["tmp"] / "r.json", 2, "--report")
    assert rc == 0 and "VERDICT report: FAIL" in out, out


# -- compare_png_trees.py (G1a gate, G1 summary) -----------------------------------------------------------------
def test_g1a_gate_passes_identical_trees(good):
    other = make_png(str(good["tmp"] / "png2"), good["px"], good["meta"])
    rc, out = run("compare_png_trees.py", good["png"], other, good["tmp"] / "r.json", 2)
    assert rc == 0 and "VERDICT gate: PASS" in out, out


def test_g1a_gate_fails_two_equally_truncated_runs(good):
    # Both sides stopped after 3 of 5 tiles (and say so in metadata.json): identical, but not complete.
    meta = dict(copy.deepcopy(good["meta"]), processed_tile_count=3, percent_complete=60.0)
    a = make_png(str(good["tmp"] / "ta"), good["px"][:3], meta, xy=XY[:3])
    b = make_png(str(good["tmp"] / "tb"), good["px"][:3], meta, xy=XY[:3])
    rc, out = run("compare_png_trees.py", a, b, good["tmp"] / "r.json", 2)
    assert rc == 1 and "a_complete" in out and "b_complete" in out, out


def test_g1a_gate_fails_missing_plane_and_metadata_difference(good):
    other = make_png(str(good["tmp"] / "png2"), good["px"], dict(good["meta"], tile_overlap=0))
    os.remove(os.path.join(other, "24x_0y", "1z.png"))
    rc, out = run("compare_png_trees.py", good["png"], other, good["tmp"] / "r.json", 2)
    assert rc == 1 and "b_complete" in out and "same_file_lists" in out and "metadata_equal" in out, out


def test_g1a_gate_fails_two_blank_runs(tmp_path):
    blank, meta = np.zeros_like(pixels()), metadata()
    a, b = make_png(str(tmp_path / "a"), blank, meta), make_png(str(tmp_path / "b"), blank, meta)
    rc, out = run("compare_png_trees.py", a, b, tmp_path / "r.json", 2)
    assert rc == 1 and "some_planes_have_content" in out, out


def test_g1_summary_reports_and_never_fails(good):
    px = good["px"].copy()
    px[0, 0] = 0
    other = make_png(str(good["tmp"] / "prod"), px, good["meta"])
    rc, out = run("compare_png_trees.py", other, good["png"], good["tmp"] / "r.json", 2, "--summary")
    assert rc == 0 and "REPORTED ONLY" in out, out
    summary = json.load(open(str(good["tmp"] / "r.json")))["summary"]
    assert summary["tiles_differing"] == ["0x_0y"]
    assert summary["plane_pixel_equality_rate"] == pytest.approx(14 / 15)
