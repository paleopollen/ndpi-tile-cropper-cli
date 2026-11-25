"""Run the cropper CLI with its Bio-Formats reader wrapped, for tests.

The CLI file runs unchanged as __main__ (runpy); only bioformats.formatreader.make_image_reader_class is
replaced, so that the reader the CLI creates can fail chosen plane reads, count every read, or signal
this process after a number of reads. Reads still go through the real Bio-Formats reader otherwise.

Usage: python inject_driver.py <cli args...>
Environment:
  CROPPER_CLI                path to ndpi_tile_cropper_cli.py (required)
  INJECT_FAIL                "z:x:y,..."  these reads raise
  INJECT_MALFORMED           "z:x:y,..."  these reads return too few bytes
  INJECT_SIGNAL_AFTER        "N:SIGNAME"  send SIGNAME to this process after N reads (e.g. "10:SIGTERM")
  INJECT_LOG                 file that gets one line "z x y" per read
  INJECT_MODULES_REPORT      file that gets the names of loaded modules at exit
"""
import atexit
import os
import runpy
import signal
import sys

cli = os.environ["CROPPER_CLI"]
sys.path.insert(0, os.path.dirname(os.path.abspath(cli)))

import bioformats.formatreader as format_reader  # noqa: E402
import numpy as np  # noqa: E402


def _keys(name):
    value = os.environ.get(name, "")
    return {tuple(int(v) for v in item.split(":")) for item in value.split(",") if item}


FAIL = _keys("INJECT_FAIL")
MALFORMED = _keys("INJECT_MALFORMED")
SIGNAL_AFTER = os.environ.get("INJECT_SIGNAL_AFTER")
LOG = os.environ.get("INJECT_LOG")
REPORT = os.environ.get("INJECT_MODULES_REPORT")
_reads = [0]

if REPORT:
    atexit.register(lambda: open(REPORT, "w").write("\n".join(sorted(sys.modules)) + "\n"))

_original = format_reader.make_image_reader_class


def make_image_reader_class():
    base = _original()

    class InjectingReader(base):
        def openBytesXYWH(self, z, x, y, w, h):
            _reads[0] += 1
            if LOG:
                with open(LOG, "a") as f:
                    f.write("%d %d %d\n" % (z, x, y))
            if SIGNAL_AFTER:
                n, name = SIGNAL_AFTER.split(":")
                if _reads[0] == int(n) + 1:
                    os.kill(os.getpid(), getattr(signal, name))
            if (z, x, y) in FAIL:
                raise RuntimeError("injected read failure z=%d x=%d y=%d" % (z, x, y))
            img = base.openBytesXYWH(self, z, x, y, w, h)
            if (z, x, y) in MALFORMED:
                return np.ascontiguousarray(img[: len(img) // 2])
            return img

    return InjectingReader


format_reader.make_image_reader_class = make_image_reader_class
sys.argv = [cli] + sys.argv[1:]
runpy.run_path(cli, run_name="__main__")
