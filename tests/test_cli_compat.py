"""PNG-mode compatibility with the base commit (ae045e0): option prefixes, exit codes, the tile grid."""
import importlib.util
import os
import sys

import numpy as np
import pytest

from conftest import CLI, SLIDE, SRC, Z, run_cli

BASE_CLI = os.environ.get("CROPPER_BASE_CLI")

# The long options of the base commit's parser and their dests (checked against the base parser when
# CROPPER_BASE_CLI is set). Any prefix that was unique among these must still select the same option: argparse
# accepts unique abbreviations, so a new option sharing a prefix would make old command lines ambiguous.
BASE_LONG_OPTIONS = {
    "--help": "help",
    "--input-file": "input_file",
    "--output-dir": "output_dir",
    "--tile_size": "tile_size",
    "--overwrite": "overwrite",
    "--tile_overlap": "tile_overlap",
    "--tile_format": "tile_format",
    "--zip": "zip",
    "--log-level": "log_level",
    "--verbose": "verbose",
}


def load_parser(cli_path, module_name):
    src = os.path.dirname(os.path.abspath(cli_path))
    added = src not in sys.path
    if added:
        sys.path.insert(0, src)
    if SRC not in sys.path:
        sys.path.append(SRC)  # utils.palyim_timing for the new CLI
    try:
        spec = importlib.util.spec_from_file_location(module_name, cli_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # importing never starts the JVM (that happens under __main__)
        return module.NDPITileCropperCLI._create_parser()
    finally:
        if added:
            sys.path.remove(src)


def long_actions(parser):
    return {s: a for a in parser._actions for s in a.option_strings if s.startswith("--")}


def parse(parser, option, action):
    """Parse ``option`` (maybe abbreviated) with a value suited to ``action``; (status, dest value or exit code)."""
    if action.nargs == 0:
        value_args, expected = [], True
    else:
        value = action.choices[0] if action.choices else ("in.ndpi" if action.dest == "input_file" else "5")
        value_args = [value]
        expected = action.type(value) if action.type else value
    argv = [option] + value_args
    if action.dest != "input_file":
        argv = ["-i", "in.ndpi"] + argv
    try:
        ns = parser.parse_args(argv)
    except SystemExit as e:
        return "exit", e.code, None
    return "ok", getattr(ns, action.dest), expected


def unique_prefixes():
    for option in BASE_LONG_OPTIONS:
        for k in range(3, len(option) + 1):
            prefix = option[:k]
            if prefix == option or sum(o.startswith(prefix) for o in BASE_LONG_OPTIONS) == 1:
                yield option, prefix


def test_base_option_snapshot_matches_base_parser():
    if not BASE_CLI:
        pytest.skip("set CROPPER_BASE_CLI to the base commit's CLI")
    base = long_actions(load_parser(BASE_CLI, "base_cli"))
    assert {o: a.dest for o, a in base.items()} == BASE_LONG_OPTIONS


def test_every_unique_prefix_of_a_base_option_still_parses_the_same(capsys):
    new = load_parser(CLI, "new_cli")
    base = load_parser(BASE_CLI, "base_cli") if BASE_CLI else None
    actions = long_actions(new)
    checked = 0
    for option, prefix in unique_prefixes():
        action = actions[option]
        assert action.dest == BASE_LONG_OPTIONS[option]
        got = parse(new, prefix, action)
        if option == "--help":
            assert got[:2] == ("exit", 0), prefix  # prints help, exits 0
        else:
            assert got[0] == "ok" and got[1] == got[2], (prefix, got)
        if base is not None:
            assert parse(base, prefix, long_actions(base)[option])[:2] == got[:2], prefix
        checked += 1
    capsys.readouterr()
    assert checked > 30
    # --z was --zip's shortest unique abbreviation before the Zarr options; it still is.
    assert parse(new, "--z", actions["--zip"])[:2] == ("ok", True)


@pytest.mark.parametrize("case, extra_env, input_override", [
    ("missing input", {}, "does not exist.tif"),
    ("SIGTERM after 10 reads", {"INJECT_SIGNAL_AFTER": "10:SIGTERM"}, None),
    ("SIGINT after 10 reads", {"INJECT_SIGNAL_AFTER": "10:SIGINT"}, None),
    ("failed plane read", {"INJECT_FAIL": "1:112:0"}, None),
])
def test_png_mode_exit_status_is_unchanged(slide, tmp_path, case, extra_env, input_override):
    """PNG mode exits 0 on exceptions, signals and read failures, as on the base commit (known issue, kept)."""
    inp = str(tmp_path / input_override) if input_override else slide
    codes = {}
    for side, cli in (("new", CLI), ("base", BASE_CLI)):
        if cli is None:
            continue
        out = tmp_path / side
        proc = run_cli(["-i", inp, "-o", str(out), "-s", "128", "-l", "16"], env_extra=extra_env, use_driver=True,
                       cli=cli)
        codes[side] = proc.returncode
    assert codes["new"] == 0, case
    if "base" in codes:
        assert codes["new"] == codes["base"], (case, codes)


def test_exactly_fitting_last_tile_is_dropped_in_both_modes(slide, tmp_path):
    """600 px with 120 px tiles and no overlap: arange(0, 480, 120) drops the tile at 480, which would fit exactly
    (known issue, kept). The Zarr tile set is the PNG tile set."""
    from PIL import Image
    from palyim_io import layout, tile_store

    args = ["-i", slide, "-s", "120", "-l", "0"]
    assert run_cli(args + ["-o", str(tmp_path / "png")]).returncode == 0
    assert run_cli(args + ["-o", str(tmp_path / "zarr"), "--tile_format", "zarr"]).returncode == 0
    png_dir = tmp_path / "png" / SLIDE
    png_tiles = sorted(d for d in os.listdir(str(png_dir)) if os.path.isdir(str(png_dir / d)))
    store = tile_store.open(str(tmp_path / "zarr" / (SLIDE + ".zarr")))
    xy = [tuple(int(v) for v in p) for p in store.tile_xy.tolist()]
    assert xy == layout.tile_grid(600, 600, 120, 0)
    assert sorted(layout.tile_name(x, y) for x, y in xy) == png_tiles
    assert len(xy) == 16 and not any(x == 480 or y == 480 for x, y in xy)
    for i, (x, y) in enumerate(xy):
        for z in range(Z):
            png = np.asarray(Image.open(str(png_dir / layout.tile_name(x, y) / ("%dz.png" % z))))
            assert np.array_equal(store.tile_stack(i)[z], png), (x, y, z)
