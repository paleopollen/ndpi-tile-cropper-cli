"""--tile_format zarr against PNG mode, through the real Bio-Formats path on a synthetic ImageJ hyperstack TIFF."""
import filecmp
import inspect
import json
import os
import shutil
import signal
import sys

import numpy as np
import pytest

from conftest import (GRID, K, OVERLAP, SLIDE, SLIDE_FILE, SRC, TILE, TILE_ARGS, Z, expected_tile, make_pixels,
                      read_log, run_cli, start_cli_in_new_session, wait_for_reads, write_slide)

palyim_io = pytest.importorskip("palyim_io")
from palyim_io import layout, tile_store  # noqa: E402

N = len(GRID)
SHARDS = layout.shard_count(N, K)
ZARR_ARGS = ["--tile_format", "zarr", "--store-tiles-per-shard", str(K)] + TILE_ARGS


def zarr_run(slide, out, extra=(), env_extra=None, use_driver=False):
    return run_cli(["-i", slide, "-o", str(out)] + ZARR_ARGS + list(extra), env_extra=env_extra,
                   use_driver=use_driver)


def store_path(out):
    return os.path.join(str(out), SLIDE + ".zarr")


def progress(out):
    with open(os.path.join(store_path(out), "progress.json")) as f:
        return json.load(f)


def assert_matches_png(store, png, skip=()):
    """Every tile and plane of the store equals the decoded PNG, except the (tile, plane) pairs in skip,
    which must be zeros."""
    assert [tuple(v) for v in store.tile_xy.tolist()] == GRID
    for i, (x, y) in enumerate(GRID):
        stack = store.tile_stack(i)
        for z in range(Z):
            if (i, z) in skip:
                assert not stack[z].any(), (i, z)
            else:
                assert np.array_equal(stack[z], png["tiles"][(x, y)][z]), (i, x, y, z)


# -- PNG mode ---------------------------------------------------------------------------------------------------
def test_png_mode_has_no_new_metadata_keys_and_no_zarr_imports(png_reference):
    assert set(png_reference["metadata"]) == {"tile_size", "tile_overlap", "ome_metadata", "total_tile_count",
                                              "processed_tile_count", "percent_complete"}
    assert png_reference["metadata"]["total_tile_count"] == N
    assert png_reference["metadata"]["percent_complete"] == 100.0
    assert sorted(os.listdir(png_reference["dir"])) == sorted(["metadata.json"] + [layout.tile_name(x, y)
                                                                                    for x, y in GRID])
    loaded = png_reference["modules"]
    assert not any(m == "zarr" or m.startswith("zarr.") for m in loaded)
    assert not any(m == "palyim_io" or m.startswith("palyim_io.") for m in loaded)
    assert "zarr_mode" not in loaded


def test_png_mode_timings_go_to_log_and_json(png_reference):
    assert "timings: total=" in png_reference["log"]
    with open(png_reference["timings"]) as f:
        timings = json.load(f)
    assert timings["schema"] == "palyim-io.timings"
    assert {"read_metadata", "crop_tiles"} <= set(timings["phases"])


def test_vendored_timing_matches_palyim_io():
    sys.path.insert(0, SRC)
    try:
        import utils.palyim_timing as vendored
    finally:
        sys.path.remove(SRC)
    import palyim_io.timing

    assert inspect.getsource(palyim_io.timing) == inspect.getsource(vendored)


def test_grid_is_layout_tile_grid():
    assert layout.tile_grid(600, 600, TILE, OVERLAP) == GRID


def test_png_tiles_are_the_source_regions(png_reference):
    """The synthetic slide reads back as expected: right region, right plane (guards the fixtures)."""
    pixels = make_pixels()
    assert png_reference["metadata"]["ome_metadata"]["z_plane"] == Z
    assert png_reference["metadata"]["ome_metadata"]["calibration"] == 0.25
    for (x, y), stack in png_reference["tiles"].items():
        for z in range(Z):
            assert np.array_equal(stack[z], expected_tile(pixels, x, y, z)), (x, y, z)


@pytest.mark.skipif(not os.environ.get("CROPPER_BASE_CLI"), reason="set CROPPER_BASE_CLI to the base commit's CLI")
def test_png_mode_identical_to_base_commit(slide, png_reference, tmp_path):
    """PNG output of the base commit's CLI, byte for byte (metadata.json included)."""
    base = os.environ["CROPPER_BASE_CLI"]
    proc = run_cli(["-i", slide, "-o", str(tmp_path)] + TILE_ARGS, cli=base)
    assert proc.returncode == 0, proc.stdout
    ours, theirs = png_reference["dir"], str(tmp_path / SLIDE)
    cmp = filecmp.dircmp(ours, theirs)
    assert sorted(os.listdir(ours)) == sorted(os.listdir(theirs))
    assert not cmp.diff_files and not cmp.left_only and not cmp.right_only
    for d in cmp.common_dirs:
        names = sorted(os.listdir(os.path.join(ours, d)))
        match, mismatch, errors = filecmp.cmpfiles(os.path.join(ours, d), os.path.join(theirs, d), names,
                                                   shallow=False)
        assert not mismatch and not errors, (d, mismatch, errors)
    assert filecmp.cmp(os.path.join(ours, "metadata.json"), os.path.join(theirs, "metadata.json"), shallow=False)


# -- Zarr mode --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("writers", [0, 1, 2])
def test_zarr_equals_png(slide, png_reference, tmp_path, writers):
    proc = zarr_run(slide, tmp_path, ["--store-writers", str(writers)])
    assert proc.returncode == 0, proc.stdout
    # The writer processes really ran (the tiny shards fit Docker's 64 MB /dev/shm; no fallback to in-process).
    assert "%d writer process(es)" % writers in proc.stdout
    assert "writing in this process instead" not in proc.stdout
    # Nothing under <out>/<slide>/: the store is the only output.
    assert os.listdir(str(tmp_path)) == [SLIDE + ".zarr"]
    store = tile_store.open(store_path(tmp_path))
    assert store.complete and store.n_tiles == N and store.z_planes == Z and store.tile_size == TILE
    assert store.tiles_per_shard == K and store.shards_total == SHARDS
    assert store.plane_present.all()
    assert store.slide_metadata() == png_reference["metadata"]
    assert_matches_png(store, png_reference)
    timings = store.timings()
    assert timings["schema"] == "palyim-io.timings" and "read_planes" in timings["phases"]
    p = progress(tmp_path)
    assert p["complete"] is True and p["shards_done"] == list(range(SHARDS)) and p["missing_planes"] == []
    # Shard 0 holds the 4 all-zero tiles at x = 0: an .empty marker instead of a shard file.
    files = os.listdir(os.path.join(store_path(tmp_path), "tiles"))
    assert "c.0.0.0.0.0.empty" in files and "c.0.0.0.0.0" not in files
    assert all("c.%d.0.0.0.0" % s in files for s in range(1, SHARDS))
    assert not [f for f in files if f.endswith(".partial")]


def test_zip_is_refused_in_zarr_mode(slide, tmp_path):
    proc = zarr_run(slide, tmp_path, ["--zip"])
    assert proc.returncode == 2, proc.stdout
    assert "--zip cannot be combined" in proc.stdout
    assert os.listdir(str(tmp_path)) == []


def test_complete_store_rerun_reads_nothing(slide, tmp_path):
    assert zarr_run(slide, tmp_path).returncode == 0
    before = progress(tmp_path)
    log = str(tmp_path / "reads.log")
    proc = zarr_run(slide, tmp_path, env_extra={"INJECT_LOG": log}, use_driver=True)
    assert proc.returncode == 0, proc.stdout
    assert read_log(log) == []
    assert progress(tmp_path)["completed"] == before["completed"]


@pytest.mark.parametrize("signame", ["SIGTERM", "SIGINT"])
def test_signal_stops_cleanly_and_rerun_resumes(slide, png_reference, tmp_path, signame):
    # Signal after 2.5 shards' worth of reads: shards 0 and 1 are handed to the writers, shard 2 is dropped.
    after = int(2.5 * K * Z)
    proc = zarr_run(slide, tmp_path, ["--store-writers", "1"], use_driver=True,
                    env_extra={"INJECT_SIGNAL_AFTER": "%d:%s" % (after, signame)})
    assert proc.returncode == 1, proc.stdout
    assert "rerun to resume" in proc.stdout
    p = progress(tmp_path)
    assert p["complete"] is False and p["shards_done"] == [0, 1]
    with pytest.raises(tile_store.IncompleteStoreError):
        tile_store.open(store_path(tmp_path))

    log = str(tmp_path / "reads.log")
    proc = zarr_run(slide, tmp_path, ["--store-writers", "2"], env_extra={"INJECT_LOG": log}, use_driver=True)
    assert proc.returncode == 0, proc.stdout
    # Only the pending shards were read: tiles 2K..N-1, every plane.
    expected = sorted((z, x, y) for i, (x, y) in enumerate(GRID) if i >= 2 * K for z in range(Z))
    assert sorted(read_log(log)) == expected
    assert_matches_png(tile_store.open(store_path(tmp_path)), png_reference)


def test_killed_run_resumes(slide, png_reference, tmp_path):
    """SIGKILL of the parent (node failure, OOM kill): no cleanup at all; the rerun resumes from progress.json."""
    after = int(3.5 * K * Z)
    proc = zarr_run(slide, tmp_path, ["--store-writers", "2"], use_driver=True,
                    env_extra={"INJECT_SIGNAL_AFTER": "%d:SIGKILL" % after})
    assert proc.returncode == -9, proc.stdout
    p = progress(tmp_path)
    assert p["complete"] is False and len(p["shards_done"]) < SHARDS
    proc = zarr_run(slide, tmp_path)
    assert proc.returncode == 0, proc.stdout
    store = tile_store.open(store_path(tmp_path))
    assert_matches_png(store, png_reference)
    assert not [f for f in os.listdir(os.path.join(store_path(tmp_path), "tiles")) if f.endswith(".partial")]


def test_failed_planes_are_zeros_exit_1_and_rerun_rereads_only_them(slide, png_reference, tmp_path):
    fail_tile, fail_z = 6, 1  # shard 1
    bad_tile, bad_z = 13, 2  # shard 3
    fx, fy = GRID[fail_tile]
    bx, by = GRID[bad_tile]
    proc = zarr_run(slide, tmp_path, ["--store-writers", "2"], use_driver=True,
                    env_extra={"INJECT_FAIL": "%d:%d:%d" % (fail_z, fx, fy),
                               "INJECT_MALFORMED": "%d:%d:%d" % (bad_z, bx, by)})
    assert proc.returncode == 1, proc.stdout
    assert "2 planes in 2 tiles could not be read" in proc.stdout
    # The store is complete (every shard written); the failures are recorded, not hidden.
    store = tile_store.open(store_path(tmp_path))
    present = store.plane_present
    assert not present[fail_tile, fail_z] and not present[bad_tile, bad_z] and present.sum() == N * Z - 2
    assert progress(tmp_path)["missing_planes"] == [
        {"tile": fail_tile, "x": fx, "y": fy, "planes": [fail_z]},
        {"tile": bad_tile, "x": bx, "y": by, "planes": [bad_z]},
    ]
    assert_matches_png(store, png_reference, skip={(fail_tile, fail_z), (bad_tile, bad_z)})
    assert store.io_attrs()["missing_plane_count"] == 2

    log = str(tmp_path / "reads.log")
    proc = zarr_run(slide, tmp_path, ["--store-writers", "1"], env_extra={"INJECT_LOG": log}, use_driver=True)
    assert proc.returncode == 0, proc.stdout
    assert sorted(read_log(log)) == sorted([(fail_z, fx, fy), (bad_z, bx, by)])
    store = tile_store.open(store_path(tmp_path))
    assert store.plane_present.all() and progress(tmp_path)["missing_planes"] == []
    assert_matches_png(store, png_reference)


def test_failed_plane_that_fails_again_stays_missing(slide, tmp_path):
    x, y = GRID[9]
    env = {"INJECT_FAIL": "0:%d:%d" % (x, y)}
    assert zarr_run(slide, tmp_path, ["--store-writers", "0"], env_extra=env, use_driver=True).returncode == 1
    proc = zarr_run(slide, tmp_path, ["--store-writers", "0"], env_extra=env, use_driver=True)
    assert proc.returncode == 1, proc.stdout
    store = tile_store.open(store_path(tmp_path))
    assert store.missing_planes() == {9: [0]}


def test_mismatched_store_is_refused_and_overwrite_recreates(slide, tmp_path):
    assert zarr_run(slide, tmp_path).returncode == 0
    before = progress(tmp_path)
    other = ["-i", slide, "-o", str(tmp_path), "--tile_format", "zarr", "-s", "96", "-l", "0"]
    proc = run_cli(other)
    assert proc.returncode == 1, proc.stdout
    assert "does not match the input" in proc.stdout and "--overwrite" in proc.stdout
    assert progress(tmp_path) == before

    proc = run_cli(other + ["-w"])
    assert proc.returncode == 0, proc.stdout
    store = tile_store.open(store_path(tmp_path))
    assert store.tile_size == 96
    assert [tuple(v) for v in store.tile_xy.tolist()] == layout.tile_grid(600, 600, 96, 0)
    assert store.slide_metadata()["tile_size"] == 96


def test_overwrite_deletes_and_recreates(slide, png_reference, tmp_path):
    assert zarr_run(slide, tmp_path).returncode == 0
    marker = os.path.join(store_path(tmp_path), "stray-file")
    open(marker, "w").close()
    created = tile_store.open(store_path(tmp_path)).io_attrs()["created"]
    assert zarr_run(slide, tmp_path, ["-w"]).returncode == 0
    assert not os.path.exists(marker)
    store = tile_store.open(store_path(tmp_path))
    assert store.io_attrs()["created"] != created
    assert_matches_png(store, png_reference)



def shm_blocks():
    return sorted(e for e in os.listdir("/dev/shm") if e.startswith("palyim-crop-"))


def test_group_sigterm_loses_no_shard_in_flight(slide, png_reference, tmp_path):
    """scancel-style SIGTERM to the whole process group: writers ignore it and finish their shards, the parent
    records them and exits 1; no write fails. The rerun completes the store."""
    log = str(tmp_path / "reads.log")
    proc = start_cli_in_new_session(["-i", slide, "-o", str(tmp_path)] + ZARR_ARGS + ["--store-writers", "2"],
                                    str(tmp_path / "run1.log"), env_extra={"INJECT_LOG": log})
    wait_for_reads(log, int(2.5 * K * Z), proc)
    os.killpg(proc.pid, signal.SIGTERM)
    assert proc.wait(timeout=600) == 1
    out = open(str(tmp_path / "run1.log")).read()
    assert "rerun to resume" in out and "writing shard" not in out, out
    p = progress(tmp_path)
    assert p["complete"] is False and len(p["shards_done"]) >= 2
    assert out.count("recorded (") == len(p["shards_done"])
    assert shm_blocks() == []  # the parent unlinked its blocks
    assert zarr_run(slide, tmp_path, ["--store-writers", "2"]).returncode == 0
    assert_matches_png(tile_store.open(store_path(tmp_path)), png_reference)


def test_group_sigkill_leaks_shm_blocks_and_the_next_run_removes_them(slide, png_reference, tmp_path):
    """SIGKILL of the whole group (OOM killer, node cleanup) cannot be handled: the /dev/shm blocks stay. They are
    named palyim-crop-j<job>-p<pid>-b<i>, and the next run with writers removes those whose pid is dead."""
    assert shm_blocks() == []
    log = str(tmp_path / "reads.log")
    proc = start_cli_in_new_session(["-i", slide, "-o", str(tmp_path)] + ZARR_ARGS + ["--store-writers", "2"],
                                    str(tmp_path / "run1.log"), env_extra={"INJECT_LOG": log})
    wait_for_reads(log, int(1.5 * K * Z), proc)
    os.killpg(proc.pid, signal.SIGKILL)
    assert proc.wait(timeout=60) == -9
    leaked = shm_blocks()
    assert len(leaked) == 3 and all("-p%d-" % proc.pid in b for b in leaked), leaked
    rerun = zarr_run(slide, tmp_path, ["--store-writers", "2"])
    assert rerun.returncode == 0, rerun.stdout
    assert "removed 3 stale shared-memory blocks" in rerun.stdout
    assert shm_blocks() == []
    assert_matches_png(tile_store.open(store_path(tmp_path)), png_reference)


def test_resume_refuses_a_store_made_from_another_input(slide, tmp_path):
    out = tmp_path / "out"
    assert zarr_run(slide, out).returncode == 0
    with open(os.path.join(store_path(out), "zarr.json")) as f:
        attrs = json.load(f)["attributes"]
    assert attrs["palyim_cropper"] == {"input_file": SLIDE_FILE, "input_bytes": os.path.getsize(slide)}
    before = progress(out)

    # Same file name, same size, same grid, other calibration (0.5 um/px instead of 0.25).
    other = write_slide(str(tmp_path / SLIDE_FILE), pixels_per_um=2.0)
    assert os.path.getsize(other) == os.path.getsize(slide)
    proc = zarr_run(other, out)
    assert proc.returncode == 1, proc.stdout
    assert "made from another input" in proc.stdout and "calibration" in proc.stdout and "--overwrite" in proc.stdout

    # The same pixels under another file name that maps to the same slide name.
    renamed = str(tmp_path / "synth copy.tif")
    shutil.copy(slide, renamed)
    proc = zarr_run(renamed, out)
    assert proc.returncode == 1, proc.stdout
    assert "input_file" in proc.stdout
    assert progress(out) == before

    proc = zarr_run(renamed, out, ["-w"])
    assert proc.returncode == 0, proc.stdout
