# coding=utf-8
from __future__ import absolute_import

import threading
import time

from .ffmpeg_source import (
    FfmpegSnapshotSource,
    SnapshotConfigError,
    SnapshotTimeoutError,
    SnapshotAcquireError,
)
from .pipeline import Frame
from .util import is_probably_jpeg


class SnapshotService(object):
    """
    Orchestrates:
      - caching (TTL)
      - concurrency (single-flight capture)
      - last-good fallback (optional)
      - optional pipeline fan-out (processors/sinks)

    This is the layer your HTTP route should call.
    """
    def __init__(self, Logger=None, Source=None, Pipeline=None):
        self._logger = Logger
        self._source = Source or FfmpegSnapshotSource(Logger=Logger)
        self._pipeline = Pipeline  # may be None

        self._lock = threading.Lock()
        self._inflight = False
        self._inflight_done = threading.Condition(self._lock)

        self._cached_jpeg = None
        self._cached_at = 0.0

        self._last_good_jpeg = None
        self._last_good_at = 0.0

        self._last_error = None

    def get_last_error(self):
        with self._lock:
            return self._last_error

    def get_snapshot_jpeg(
        self,
        InputUrl,
        FfmpegPath,
        RtspTransport,
        TimeoutSec,
        CacheTtlMs,
        ExtraInputArgs,
        AllowLastGood=True,
    ):
        """
        Return JPEG bytes.

        Cache strategy:
          - If cache is fresh, return it immediately.
          - Otherwise, ensure only one FFmpeg capture runs at a time.
            Concurrent callers either:
              - wait briefly for the in-flight capture, then use the new cache
              - or (if capture fails) fall back as configured.
        """
        Now = time.time()
        TtlMs = int(CacheTtlMs or 0)

        with self._lock:
            # 1) Fresh cache?
            if self._cached_jpeg is not None and TtlMs > 0:
                AgeMs = (Now - self._cached_at) * 1000.0
                if AgeMs <= TtlMs:
                    return self._cached_jpeg

            # 2) Another capture in flight? Wait for it.
            if self._inflight:
                # Wait up to timeout (plus a small buffer) for the capture to finish.
                WaitSec = float(TimeoutSec or 6.0) + 0.5
                End = time.time() + WaitSec
                while self._inflight and time.time() < End:
                    self._inflight_done.wait(timeout=0.25)

                # After waiting, try cache again.
                Now2 = time.time()
                if self._cached_jpeg is not None and TtlMs > 0:
                    AgeMs = (Now2 - self._cached_at) * 1000.0
                    if AgeMs <= TtlMs:
                        return self._cached_jpeg

                # If we still don’t have a fresh cache, fall through and attempt capture.
                # (This can happen if the in-flight capture failed.)

            # 3) Mark that *we* will do the capture.
            self._inflight = True

        # Capture outside the lock so other requests can at least wait.
        try:
            Jpeg = self._source.capture_jpeg(
                InputUrl=InputUrl,
                FfmpegPath=FfmpegPath,
                RtspTransport=RtspTransport,
                TimeoutSec=TimeoutSec,
                ExtraInputArgs=ExtraInputArgs,
            )

            if not is_probably_jpeg(Jpeg):
                raise SnapshotAcquireError("ffmpeg output was not a complete JPEG")

            # Optional pipeline fan-out (ML hooks, storage, metrics, etc.)
            if self._pipeline is not None:
                FrameObj = Frame(Data=Jpeg, Source="ffmpeg", Meta={"url": InputUrl})
                FrameObj = self._pipeline.run(FrameObj)
                # If a processor replaced Data, prefer that.
                Jpeg = FrameObj.Data

            with self._lock:
                self._cached_jpeg = Jpeg
                self._cached_at = time.time()
                self._last_good_jpeg = Jpeg
                self._last_good_at = self._cached_at
                self._last_error = None

            return Jpeg

        except (SnapshotConfigError, SnapshotTimeoutError, SnapshotAcquireError) as Ex:
            with self._lock:
                self._last_error = str(Ex)

                if AllowLastGood and self._last_good_jpeg is not None:
                    return self._last_good_jpeg

            # Re-raise so the HTTP layer can map to codes/messages.
            raise

        finally:
            with self._lock:
                self._inflight = False
                self._inflight_done.notify_all()
