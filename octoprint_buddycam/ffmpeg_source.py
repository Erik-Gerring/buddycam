# coding=utf-8
from __future__ import absolute_import

import subprocess

from .util import redact_url_credentials


class SnapshotError(Exception):
    """Base error for snapshot acquisition."""


class SnapshotConfigError(SnapshotError):
    """Configuration is missing or invalid."""


class SnapshotTimeoutError(SnapshotError):
    """Acquisition timed out."""


class SnapshotAcquireError(SnapshotError):
    """FFmpeg returned an error or produced no output."""


class FfmpegSnapshotSource(object):
    """
    Pull a single JPEG frame from an input URL using FFmpeg.

    This module does NOT cache and does NOT know about HTTP.
    It’s just: config -> run -> bytes.
    """
    def __init__(self, Logger=None):
        self._logger = Logger

    def capture_jpeg(self, InputUrl, FfmpegPath, RtspTransport, TimeoutSec, ExtraInputArgs):
        InputUrl = (InputUrl or "").strip()
        if not InputUrl:
            raise SnapshotConfigError("input_url is not configured")

        FfmpegPath = (FfmpegPath or "ffmpeg").strip()
        RtspTransport = (RtspTransport or "tcp").strip()
        TimeoutSec = float(TimeoutSec or 6.0)

        Extra = (ExtraInputArgs or "").strip().split()

        Cmd = [
            FfmpegPath,
            "-hide_banner",
            "-loglevel", "error",
        ]

        # Only add RTSP transport if it looks like RTSP.
        if InputUrl.lower().startswith("rtsp://"):
            Cmd += ["-rtsp_transport", RtspTransport]

        # Advanced input flags (for power users).
        Cmd += Extra

        # Input + one frame JPEG to stdout.
        Cmd += [
            "-i", InputUrl,
            "-frames:v", "1",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "pipe:1",
        ]

        SafeUrl = redact_url_credentials(InputUrl)

        try:
            Proc = subprocess.run(
                Cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=TimeoutSec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            if self._logger:
                self._logger.warning("Buddycam FFmpeg timeout after %.1fs (url=%s)", TimeoutSec, SafeUrl)
            raise SnapshotTimeoutError("ffmpeg timed out after %.1fs" % TimeoutSec)

        if Proc.returncode != 0 or not Proc.stdout:
            Err = (Proc.stderr or b"").decode("utf-8", errors="replace").strip()
            if self._logger:
                self._logger.warning("Buddycam FFmpeg failed rc=%d (url=%s): %s", Proc.returncode, SafeUrl, Err)
            raise SnapshotAcquireError("ffmpeg failed rc=%d" % Proc.returncode)

        return Proc.stdout
