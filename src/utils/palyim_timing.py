"""Per-phase wall-clock timers.

Stdlib only and Python 3.9 compatible, so module repos can vendor this one file verbatim for
PNG mode on images that do not have palyim-io installed (see the README). Keep it that way:
no imports from the rest of palyim_io, no syntax newer than 3.9.

Usage::

    timer = PhaseTimer()
    with timer.phase("read"):
        ...
    timer.add("encode", 1.25)          # time measured elsewhere, e.g. in a worker
    timer.merge(worker_timer.as_dict())
    timer.log(logger)                  # PNG mode
    timer.write_json("timings.json")   # --timings-json
    store.mark_complete(timings=timer.as_dict())   # Zarr mode: stored in the store's attrs
"""

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional

TIMINGS_SCHEMA = "palyim-io.timings"
TIMINGS_VERSION = 1


class PhaseTimer(object):
    """Accumulates wall-clock seconds and call counts per named phase.

    Phases may repeat (the time adds up) and may nest (each is timed independently, so nested
    phases are not subtracted from their parents). ``total_seconds`` is the wall time since the
    timer was created, or until :meth:`stop` was called. Thread-safe.
    """

    def __init__(self, clock: Optional[Callable[[], float]] = None) -> None:
        self._clock = clock if clock is not None else time.perf_counter
        self._lock = threading.Lock()
        self._seconds = {}  # type: Dict[str, float]
        self._counts = {}  # type: Dict[str, int]
        self._open = {}  # type: Dict[str, float]
        self._t0 = self._clock()
        self._t_end = None  # type: Optional[float]

    # -- recording ---------------------------------------------------------------------------
    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        """Time the body of a ``with`` block as one occurrence of ``name``."""
        t = self._clock()
        try:
            yield
        finally:
            self.add(name, self._clock() - t)

    def start(self, name: str) -> None:
        """Start ``name``; pair with :meth:`end`. Use :meth:`phase` where a ``with`` fits."""
        with self._lock:
            if name in self._open:
                raise RuntimeError("phase %r is already running" % name)
            self._open[name] = self._clock()

    def end(self, name: str) -> float:
        """End ``name`` started with :meth:`start`; returns the seconds of this occurrence."""
        with self._lock:
            if name not in self._open:
                raise RuntimeError("phase %r was not started" % name)
            dt = self._clock() - self._open.pop(name)
        self.add(name, dt)
        return dt

    def add(self, name: str, seconds: float, count: int = 1) -> None:
        """Add ``seconds`` (and ``count`` occurrences) to ``name``."""
        with self._lock:
            self._seconds[name] = self._seconds.get(name, 0.0) + float(seconds)
            self._counts[name] = self._counts.get(name, 0) + int(count)

    def merge(self, other: Any) -> None:
        """Add the phases of another timer, or of a dict from :meth:`as_dict` (e.g. sent back
        by a worker process). The other timer's total is ignored."""
        data = other.as_dict() if isinstance(other, PhaseTimer) else other
        for name, rec in data.get("phases", {}).items():
            self.add(name, rec["seconds"], rec.get("count", 1))

    def stop(self) -> None:
        """Freeze ``total_seconds`` (idempotent)."""
        with self._lock:
            if self._t_end is None:
                self._t_end = self._clock()

    # -- reading -----------------------------------------------------------------------------
    @property
    def total_seconds(self) -> float:
        end = self._t_end if self._t_end is not None else self._clock()
        return end - self._t0

    def seconds(self, name: str) -> float:
        with self._lock:
            return self._seconds.get(name, 0.0)

    def as_dict(self) -> Dict[str, Any]:
        """JSON-ready summary, phases in first-recorded order."""
        with self._lock:
            phases = dict(
                (name, {"seconds": round(self._seconds[name], 6), "count": self._counts[name]})
                for name in self._seconds
            )
        return {
            "schema": TIMINGS_SCHEMA,
            "version": TIMINGS_VERSION,
            "total_seconds": round(self.total_seconds, 6),
            "phases": phases,
        }

    def format(self) -> str:
        d = self.as_dict()
        parts = ["%s=%.2fs (n=%d)" % (k, v["seconds"], v["count"]) for k, v in d["phases"].items()]
        return "total=%.2fs; %s" % (d["total_seconds"], ", ".join(parts) if parts else "no phases")

    def log(self, logger: Optional[logging.Logger] = None, level: int = logging.INFO, prefix: str = "timings") -> None:
        (logger or logging.getLogger(__name__)).log(level, "%s: %s", prefix, self.format())

    def write_json(self, path: str) -> None:
        """Write :meth:`as_dict` to ``path`` atomically (temp file, fsync, rename)."""
        tmp = "%s.%d.partial" % (path, os.getpid())
        try:
            with open(tmp, "w") as f:
                json.dump(self.as_dict(), f, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
