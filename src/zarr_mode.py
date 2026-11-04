#  Copyright 2026 The Board of Trustees of the University of Illinois. All Rights Reserved.
#
#  Licensed under the terms of Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  The License is included in the distribution as LICENSE file.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""Zarr tile-store mode of the cropper (``--tile_format zarr``).

Imported only by ``NDPIFileCropper.crop_tiles_zarr()``, never at module level, so PNG mode runs on images
without palyim-io. Needs ``palyim-io[zarr]`` (zarr 3.1.5, Python >= 3.11); the syntax stays 3.9-compatible.

The store is ``<output_dir>/<slide>.zarr``, the palyim-io tile store (see its README for the contract):
``tiles`` (N, Z, T, T, 3) uint8 in the cropper's tile order, ``tile_xy``, ``plane_present``, attrs ``palyim``
= the PNG-mode ``metadata.json`` dict, and ``progress.json``.

How the work is split:

- This process (the parent) owns the JVM and the one Bio-Formats reader, as in PNG mode. It reads the k tiles
  of a shard, all planes, into one (k, Z, T, T, 3) buffer with the same ``openBytesXYWH`` calls as
  ``crop_tiles()``.
- The buffers are ``writers + 1`` blocks of shared memory (``multiprocessing.shared_memory``, i.e. /dev/shm),
  allocated once. The parent reads planes straight into a free block and hands its name to a pool of
  ``writers`` spawned processes (``spawn``: never fork a process that holds a JVM). The writer maps the block,
  encodes and writes the shard with ``palyim_io.tile_store.write_shard`` and returns the receipt; the block is
  free again when the receipt is back. Every shard is submitted once, to one writer; at most ``writers`` are in
  flight while the parent reads the next one. Pickling the 432 MiB stack through the executor's pipe instead
  cost 2.6 s wall and 1.3 s of the reader's CPU per shard in a local benchmark, and doubled the copies.
- Only the parent records receipts (``record_shard``), so only it writes ``progress.json``, ``plane_present``
  and attrs. ``writers=0`` writes in the parent instead (no extra processes, no shared memory, least memory);
  it is also the fallback when /dev/shm cannot hold the buffers (Docker's default is 64 MB), and the CLI default:
  on 24 PAL tiles (local, emulated amd64, 8 CPUs) it cropped in 46.6 s, against 46.6 s with one writer and 41.7 s
  with two, because the parent's reads are the bottleneck and slow down while writers compete for CPU.

Failures: a plane whose read raises or returns the wrong number of bytes is stored as zeros with
``plane_present`` False and listed in ``progress.json``; the store is still completed and the CLI exits 1.
Rerunning the same command re-reads only those planes and rewrites their shards (the other planes of the
shard come from the store via ``read_shard``). A write error or a signal stops the run after the shards in
flight are recorded; the store stays incomplete and a rerun resumes from ``progress.json``.
"""

import logging
import multiprocessing
import os
import signal
import threading
import time
from collections import namedtuple
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from multiprocessing import shared_memory

import numpy as np

import palyim_io
from palyim_io import tile_store

logger = logging.getLogger("ndpi_tile_cropper_cli.py")

CropResult = namedtuple("CropResult", ["failed_planes", "processed_tile_count", "store_path"])


class CropInterrupted(Exception):
    """A signal stopped the run; the store is incomplete and a rerun resumes it."""


class ShardWriteError(Exception):
    """A writer failed; the store is incomplete and a rerun resumes it."""


def available_cpus():
    """CPUs this job may use: SLURM_CPUS_PER_TASK if set, else the process's CPU affinity."""
    value = os.environ.get("SLURM_CPUS_PER_TASK")
    if value:
        try:
            return max(1, int(value))
        except ValueError:
            pass
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except AttributeError:  # not on Linux
        return max(1, os.cpu_count() or 1)


def codec_threads(writers, cpus):
    """Codec threads per writer: one CPU stays with the reader (and its JVM), the rest is shared by the writers.
    With writers=0 the parent writes and gets all CPUs."""
    if writers <= 0:
        return max(1, cpus)
    return max(1, (cpus - 1) // writers)


# -- writer processes (module-level functions so spawn can pickle them by name) -------------------------------
def _init_writer(threads):
    # Ctrl-C reaches the whole process group; the parent handles it (stops reading, waits for the shards in
    # flight, records them), so a writer finishes its shard. SIGTERM keeps its default: the executor itself
    # uses it to stop broken workers, and a writer killed mid-write leaves only a stray *.partial file.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    _exit_with_parent()
    palyim_io.configure_worker(threads=threads)


def _exit_with_parent():
    """End this writer when the parent dies without shutting the pool down (SIGKILL, OOM kill). Pool workers
    otherwise wait for work forever, because each holds both ends of the executor's call queue."""
    parent = multiprocessing.parent_process()
    if parent is None:
        return

    def watch():
        parent.join()  # returns once the parent's sentinel pipe closes, i.e. the parent has exited
        os._exit(1)

    threading.Thread(target=watch, name="exit-with-parent", daemon=True).start()


def write_shard_task(path, shard_index, stack):
    """Write a whole shard read by the parent (in-process writes). Returns (receipt, seconds)."""
    t0 = time.perf_counter()
    receipt = tile_store.write_shard(path, shard_index, stack)
    return receipt, time.perf_counter() - t0


def write_shared_shard_task(path, shard_index, payload):
    """Write a whole shard from the parent's shared-memory block ``payload = (block name, shape)``.
    Returns (receipt, seconds)."""
    t0 = time.perf_counter()
    block_name, shape = payload
    block = shared_memory.SharedMemory(name=block_name)
    try:
        stack = np.ndarray(shape, dtype=np.uint8, buffer=block.buf)
        receipt = tile_store.write_shard(path, shard_index, stack)
        del stack  # release the view before closing the mapping
    finally:
        block.close()
    return receipt, time.perf_counter() - t0


def patch_shard_task(path, shard_index, patches):
    """Rewrite a shard after re-reading some of its planes: the other planes come from the store.
    ``patches``: [(tile offset in the shard, plane, (T, T, 3) uint8), ...]. Returns (receipt, seconds)."""
    t0 = time.perf_counter()
    stack = np.array(tile_store.read_shard(path, shard_index))  # a writable copy
    for j, z, plane in patches:
        stack[j, z] = plane
    receipt = tile_store.write_shard(path, shard_index, stack)
    return receipt, time.perf_counter() - t0


def shm_free_bytes():
    try:
        st = os.statvfs("/dev/shm")
    except OSError:
        return 0
    return st.f_bavail * st.f_frsize


class _ShardWriters(object):
    """Runs shard writes in ``writers`` spawned processes (or in this process if 0), at most ``writers`` in
    flight, and records each receipt in the store as it comes back (parent only).

    With writer processes, full-shard stacks live in ``writers + 1`` shared-memory blocks: ``buffer()`` hands
    out a free one (waiting for a writer if none is free) and ``submit_buffer()`` passes it to a writer."""

    def __init__(self, store, writers, threads, timer, name, shard_shape):
        self.store = store
        self.writers = int(writers)
        self.timer = timer
        self.name = name
        self.errors = []  # [(shard, exception)]
        self._inflight = {}  # future -> (shard, plane_present mask, block index or None)
        self._executor = None
        self._shape = tuple(int(v) for v in shard_shape)
        self._blocks = []
        self._free = []
        if self.writers > 0:
            nbytes = int(np.prod(self._shape))
            for _ in range(self.writers + 1):
                self._blocks.append(shared_memory.SharedMemory(create=True, size=max(1, nbytes)))
            self._free = list(range(len(self._blocks)))
            ctx = multiprocessing.get_context("spawn")
            self._executor = ProcessPoolExecutor(max_workers=self.writers, mp_context=ctx,
                                                 initializer=_init_writer, initargs=(threads,))
        else:
            palyim_io.configure_worker(threads=threads)

    @property
    def failed(self):
        return bool(self.errors)

    def buffer(self, n_tiles):
        """(block index, (n_tiles, Z, T, T, 3) uint8 array) to read a shard into. The array is NOT zeroed
        (blocks are reused): the caller writes every plane, zeros included."""
        shape = (int(n_tiles),) + self._shape[1:]
        if self._executor is None:
            return None, np.empty(shape, dtype=np.uint8)
        while not self._free:
            self._wait_one()
        b = self._free.pop()
        return b, np.ndarray(shape, dtype=np.uint8, buffer=self._blocks[b].buf)

    def release(self, block):
        if block is not None:
            self._free.append(block)

    def submit_buffer(self, shard, block, stack, mask):
        """Write ``stack`` (from :meth:`buffer`) as ``shard``; the block is reused once the writer is done."""
        if self._executor is None:
            self.submit(write_shard_task, shard, stack, mask)
            return
        self.submit(write_shared_shard_task, shard, (self._blocks[block].name, stack.shape), mask, block)

    def submit(self, fn, shard, payload, mask, block=None):
        if self._executor is None:
            try:
                receipt, seconds = fn(self.store.path, shard, payload)
            except Exception as e:  # noqa: BLE001 - reported and turned into a non-zero exit
                self._fail(shard, e)
                return
            self._record(shard, receipt, mask, seconds)
            return
        while len(self._inflight) >= self.writers and not self.failed:
            self._wait_one()
        if self.failed:
            self.release(block)
            return
        try:
            future = self._executor.submit(fn, self.store.path, shard, payload)
        except Exception as e:  # noqa: BLE001 - e.g. BrokenProcessPool after a writer was killed
            self.release(block)
            self._fail(shard, e)
            return
        self._inflight[future] = (shard, mask, block)

    def _wait_one(self):
        with self.timer.phase("wait_for_writers"):
            done, _ = wait(list(self._inflight), return_when=FIRST_COMPLETED)
        for future in done:
            shard, mask, block = self._inflight.pop(future)
            self.release(block)
            try:
                receipt, seconds = future.result()
            except Exception as e:  # noqa: BLE001
                self._fail(shard, e)
                continue
            self._record(shard, receipt, mask, seconds)

    def drain(self):
        while self._inflight:
            self._wait_one()

    def close(self):
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None
        for block in self._blocks:
            try:
                block.close()
            except BufferError:  # a view is still alive; unlink anyway, the mapping goes with the process
                pass
            block.unlink()
        self._blocks = []

    def _record(self, shard, receipt, mask, seconds):
        self.timer.add("write_shards", seconds)
        with self.timer.phase("record_shards"):
            self.store.record_shard(receipt, mask)
        done = len(self.store.done_shards())
        missing = int((~mask).sum())
        logger.info("%s: shard %d recorded (%d/%d shards done%s)", self.name, shard, done, self.store.shards_total,
                    ", %d planes missing" % missing if missing else "")

    def _fail(self, shard, error):
        logger.error("%s: writing shard %d failed: %r", self.name, shard, error)
        self.errors.append((shard, error))


class _StopOnSignal(object):
    """SIGINT/SIGTERM set a flag the read loop checks; the previous handlers come back on exit."""

    def __init__(self):
        self.signum = None
        self._previous = {}

    def __enter__(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            self._previous[sig] = signal.signal(sig, self._handle)
        return self

    def __exit__(self, *exc):
        for sig, handler in self._previous.items():
            signal.signal(sig, handler)
        return False

    def _handle(self, signum, frame):
        if self.signum is None:
            logger.warning("Received signal %d: finishing the shards in flight, then stopping", signum)
        self.signum = signum


def _read_plane(reader, z, x, y, size, tile_index, name):
    """One plane with crop_tiles()'s call; None if the read raises or returns the wrong number of bytes."""
    try:
        img = reader.openBytesXYWH(z, x, y, size, size)
        img.shape = (size, size, 3)
        if img.dtype != np.uint8:
            raise ValueError("plane has dtype %s, expected uint8" % img.dtype)
    except Exception as e:  # noqa: BLE001 - stored as a missing plane, reported, exit 1
        logger.error("%s: Error processing z-plane %d for tile %d (%dx_%dy): %s", name, z, tile_index, x, y, e)
        return None
    return img


def _read_shard(reader, stack, tile_xy, start, stop, z_planes, size, stopper, timer, name):
    """Fill ``stack`` (n, Z, T, T, 3) with tiles [start, stop), all planes; failed planes become zeros.
    Returns the (n, Z) plane-present mask, or None if a signal arrived (the shard is dropped)."""
    mask = np.ones((stop - start, z_planes), dtype=bool)
    for j, i in enumerate(range(start, stop)):
        if stopper.signum is not None:
            return None
        x, y = tile_xy[i]
        with timer.phase("read_planes"):
            for z in range(z_planes):
                img = _read_plane(reader, z, x, y, size, i, name)
                if img is None:
                    mask[j, z] = False
                    stack[j, z] = 0
                else:
                    stack[j, z] = img
    return mask


def _open_or_create(path, tile_xy, z_planes, size, slide_metadata, overwrite, tiles_per_shard, name):
    if overwrite or not os.path.lexists(path):
        if overwrite and os.path.lexists(path):
            logger.info("%s: --overwrite: deleting and recreating %s", name, path)
        return tile_store.create(path, tile_xy, z_planes, slide_metadata, tile_size=size,
                                 tiles_per_shard=tiles_per_shard, overwrite=overwrite)
    store = tile_store.open(path, "r+")
    try:
        store.validate(tile_xy, z_planes, size)
    except ValueError as e:
        raise ValueError("%s; rerun with --overwrite to delete and recreate the store" % e)
    if tiles_per_shard and int(tiles_per_shard) != store.tiles_per_shard:
        logger.warning("%s: resuming a store with %d tiles per shard; --zarr-tiles-per-shard %d is ignored",
                       name, store.tiles_per_shard, tiles_per_shard)
    if store.removed_partials:
        logger.info("%s: removed %d stray partial files from an earlier run", name, len(store.removed_partials))
    logger.info("%s: resuming %s: %d of %d shards done, %d planes to re-read", name, path,
                len(store.done_shards()), store.shards_total, sum(len(p) for p in store.missing_planes().values()))
    return store


def crop_to_store(reader, path, tile_xy, z_planes, tile_size, slide_metadata, overwrite=False, writers=0,
                  tiles_per_shard=None, timer=None, name=""):
    """Fill the tile store at ``path`` from an open Bio-Formats ``reader`` (the parent's; it stays open).

    ``tile_xy``: the cropper's grid as a list of (x, y) Python ints, in order. ``slide_metadata``: the dict
    PNG mode writes to metadata.json (attrs ``palyim``); at finish ``processed_tile_count`` and
    ``percent_complete`` are updated the way ``write_metadata_before_exiting`` updates metadata.json.
    Raises CropInterrupted or ShardWriteError if the store could not be finished.
    """
    if timer is None:
        from utils.palyim_timing import PhaseTimer
        timer = PhaseTimer()
    size = int(tile_size)
    z_planes = int(z_planes)
    with timer.phase("open_store"):
        store = _open_or_create(path, tile_xy, z_planes, size, slide_metadata, overwrite, tiles_per_shard, name)
    n = store.n_tiles

    pending = store.pending_shards()
    pending_set = set(pending)
    missing = store.missing_planes()
    repair = [s for s in store.shards_with_missing_planes() if s not in pending_set]
    if not pending and not repair and store.complete:
        logger.info("%s: %s is complete; nothing to do", name, path)
        return CropResult(0, n, path)
    if store.complete:
        store.mark_incomplete()  # readers refuse the store from the start of the update

    writers = max(0, int(writers))
    shard_shape = (store.tiles_per_shard, z_planes, size, size, 3)
    if writers:
        need = (writers + 1) * int(np.prod(shard_shape))
        free = shm_free_bytes()
        if free < need + 16 * 1024 * 1024:
            logger.warning("%s: /dev/shm has %d MiB free, %d writer(s) need %d MiB of shard buffers: writing in "
                           "this process instead (--zarr-writers 0). In Docker, pass --shm-size.", name,
                           free // 2 ** 20, writers, need // 2 ** 20)
            writers = 0
    cpus = available_cpus()
    threads = codec_threads(writers, cpus)
    logger.info("%s: %d tiles, %d planes, %d tiles per shard: %d shards to write, %d to repair; %d writer "
                "process(es), %d codec thread(s) each (%d CPUs)", name, n, z_planes, store.tiles_per_shard,
                len(pending), len(repair), writers, threads, cpus)

    with _StopOnSignal() as stopper:
        pool = _ShardWriters(store, writers, threads, timer, name, shard_shape)
        try:
            for s in pending:
                if stopper.signum is not None or pool.failed:
                    break
                start, stop = store.shard_range(s)
                block, stack = pool.buffer(stop - start)
                mask = _read_shard(reader, stack, tile_xy, start, stop, z_planes, size, stopper, timer, name)
                if mask is None:
                    del stack
                    pool.release(block)
                    break
                pool.submit_buffer(s, block, stack, mask)
                del stack
            if repair and stopper.signum is None and not pool.failed:
                present = store.plane_present
                for s in repair:
                    if stopper.signum is not None or pool.failed:
                        break
                    start, stop = store.shard_range(s)
                    mask = present[start:stop].copy()
                    patches = []
                    with timer.phase("read_planes"):
                        for i in range(start, stop):
                            x, y = tile_xy[i]
                            for z in missing.get(i, []):
                                img = _read_plane(reader, z, x, y, size, i, name)
                                if img is not None:
                                    patches.append((i - start, z, img))
                                    mask[i - start, z] = True
                    if patches:
                        logger.info("%s: shard %d: re-read %d missing planes", name, s, len(patches))
                        pool.submit(patch_shard_task, s, patches, mask)
            pool.drain()
        finally:
            pool.close()

    if stopper.signum is not None:
        raise CropInterrupted("stopped by signal %d with %d of %d shards done; %s is incomplete, rerun to resume"
                              % (stopper.signum, len(store.done_shards()), store.shards_total, path))
    if pool.failed:
        raise ShardWriteError("%d shard write(s) failed (first: shard %d: %r); %s is incomplete, rerun to resume"
                              % (len(pool.errors), pool.errors[0][0], pool.errors[0][1], path))

    with timer.phase("finish_store"):
        # As write_metadata_before_exiting() updates metadata.json; every shard is recorded, so every tile
        # was visited (PNG mode counts tiles with failed planes as processed too).
        processed = n
        final = store.slide_metadata()
        final['processed_tile_count'] = processed
        final['percent_complete'] = 0.0 if n == 0 else round((processed / n) * 100, 2)
        store.mark_complete(timings=timer.as_dict(), slide_metadata=final)

    failed = int((~store.plane_present).sum())
    if failed:
        tiles = len(store.missing_planes())
        logger.error("%s: %d planes in %d tiles could not be read; they are stored as zeros, False in "
                     "plane_present and listed under missing_planes in %s. Rerun the same command to re-read "
                     "only those planes.", name, failed, tiles, os.path.join(path, "progress.json"))
    logger.info("%s: %s complete: %d tiles, %d shards", name, path, n, store.shards_total)
    return CropResult(failed, processed, path)
