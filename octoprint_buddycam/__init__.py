# coding=utf-8
from __future__ import absolute_import

import time
import threading
import subprocess

import flask
import octoprint.plugin


class BuddycamPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.BlueprintPlugin,
    octoprint.plugin.StartupPlugin,
):
    def __init__(self):
        self._cache_lock = threading.Lock()
        self._cached_jpeg = None
        self._cached_at = 0.0
        self._last_error = None

    # ---- Settings ----

    def get_settings_defaults(self):
        return dict(
            input_url="",              # rtsp://...
            ffmpeg_path="ffmpeg",      # or full path e.g. /usr/bin/ffmpeg
            rtsp_transport="tcp",      # tcp is usually more stable than udp
            timeout_sec=6,             # kill ffmpeg if it hangs
            cache_ttl_ms=750,          # avoid spawning ffmpeg too often
            extra_input_args="",       # optional: advanced flags, space-separated
        )

    def on_after_startup(self):
        self._logger.info("Buddycam: FFmpeg snapshot endpoint loaded")

    # ---- Blueprint security ----

    def is_blueprint_protected(self):
        # Must be public so OctoPrint (and dashboards) can pull snapshots without login
        return False

    def is_blueprint_csrf_protected(self):
        # GET-only endpoint
        return False

    # ---- Public snapshot endpoint ----

    @octoprint.plugin.BlueprintPlugin.route("/snapshot", methods=["GET"])
    def snapshot(self):
        ttl_ms = int(self._settings.get_int(["cache_ttl_ms"]) or 0)

        # Serve cached JPEG if still fresh
        with self._cache_lock:
            if self._cached_jpeg is not None and ttl_ms > 0:
                age_ms = (time.time() - self._cached_at) * 1000.0
                if age_ms <= ttl_ms:
                    return self._make_jpeg_response(self._cached_jpeg)

        # Otherwise capture a new frame
        jpeg = self._ffmpeg_grab_jpeg()

        # Cache it
        with self._cache_lock:
            self._cached_jpeg = jpeg
            self._cached_at = time.time()

        return self._make_jpeg_response(jpeg)

    def _make_jpeg_response(self, jpeg_bytes):
        resp = flask.make_response(jpeg_bytes)
        resp.headers["Content-Type"] = "image/jpeg"
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    # ---- ffmpeg snapshot ----

    def _ffmpeg_grab_jpeg(self):
        input_url = (self._settings.get(["input_url"]) or "").strip()
        if not input_url:
            flask.abort(400, description="Buddycam: input_url is not configured")

        ffmpeg = (self._settings.get(["ffmpeg_path"]) or "ffmpeg").strip()
        transport = (self._settings.get(["rtsp_transport"]) or "tcp").strip()
        timeout = float(self._settings.get_int(["timeout_sec"]) or 6)

        extra = (self._settings.get(["extra_input_args"]) or "").strip().split()
        # Example extras you might want later:
        #   -stimeout 5000000
        #   -fflags nobuffer
        #   -flags low_delay

        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
        ]

        # RTSP options (only if it looks like RTSP)
        if input_url.lower().startswith("rtsp://"):
            cmd += ["-rtsp_transport", transport]

        # Insert any extra input args (advanced users)
        cmd += extra

        # Input + single-frame output to stdout
        cmd += [
            "-i", input_url,
            "-frames:v", "1",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "pipe:1",
        ]

        try:
            p = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self._last_error = f"ffmpeg timed out after {timeout:.1f}s"
            self._logger.warning("Buddycam: %s", self._last_error)
            flask.abort(504, description="Buddycam: snapshot timed out")

        if p.returncode != 0 or not p.stdout:
            err = (p.stderr or b"").decode("utf-8", errors="replace").strip()
            self._last_error = f"ffmpeg failed rc={p.returncode}: {err}"
            self._logger.warning("Buddycam: %s", self._last_error)
            flask.abort(502, description="Buddycam: could not capture snapshot")

        self._last_error = None
        return p.stdout


__plugin_name__ = "Buddycam"
__plugin_pythoncompat__ = ">=3,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = BuddycamPlugin()
