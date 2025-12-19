# coding=utf-8
from __future__ import absolute_import

import flask
import octoprint.plugin

from .pipeline import FramePipeline
from .snapshot_service import SnapshotService
from .ffmpeg_source import SnapshotConfigError, SnapshotTimeoutError, SnapshotAcquireError


class BuddycamPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.BlueprintPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
):
    """
    OctoPrint-facing plugin class.

    Keep this class focused on:
      - settings
      - HTTP routes
      - startup logging
      - mapping service errors to HTTP responses
    """
    def __init__(self):
        self._snapshot_service = None

    # ---- Settings ----

    def get_settings_defaults(self):
        return dict(
            input_url="",
            ffmpeg_path="ffmpeg",
            rtsp_transport="tcp",
            timeout_sec=6,
            cache_ttl_ms=750,
            extra_input_args="",

            # Behaviour toggles
            allow_last_good=True,
        )
    
    def get_template_configs(self):
        return [
            dict(type="settings", custom_bindings=False),
        ]

    def on_after_startup(self):
        self._logger.info("Buddycam: plugin loaded")

        # Build a pipeline you can extend later.
        # Right now it's empty (no processors, no sinks), but the wiring exists.
        Pipeline = FramePipeline(Logger=self._logger)

        # Example future sink (placeholder):
        # Pipeline.add_sink(lambda FrameObj: self._logger.debug("Frame bytes=%d", len(FrameObj.Data)))

        self._snapshot_service = SnapshotService(Logger=self._logger, Pipeline=Pipeline)
        self._logger.info("Buddycam: snapshot endpoint ready at /plugin/buddycam/snapshot")

    # ---- Blueprint security ----

    def is_blueprint_protected(self):
        # Public endpoint for dashboards/automation. If you later want auth,
        # you can switch to True and require API key/session.
        return False

    def is_blueprint_csrf_protected(self):
        return False

    # ---- Routes ----

    @octoprint.plugin.BlueprintPlugin.route("/snapshot", methods=["GET"])
    def route_snapshot(self):
        """
        HTTP handler: return image/jpeg or an error code.

        All heavy lifting is delegated to SnapshotService.
        """
        InputUrl = self._settings.get(["input_url"])
        FfmpegPath = self._settings.get(["ffmpeg_path"])
        RtspTransport = self._settings.get(["rtsp_transport"])
        TimeoutSec = float(self._settings.get_int(["timeout_sec"]) or 6)
        CacheTtlMs = int(self._settings.get_int(["cache_ttl_ms"]) or 0)
        ExtraInputArgs = self._settings.get(["extra_input_args"]) or ""
        AllowLastGood = bool(self._settings.get_boolean(["allow_last_good"]))

        if self._snapshot_service is None:
            flask.abort(503, description="Buddycam: service not initialised yet")

        try:
            Jpeg = self._snapshot_service.get_snapshot_jpeg(
                InputUrl=InputUrl,
                FfmpegPath=FfmpegPath,
                RtspTransport=RtspTransport,
                TimeoutSec=TimeoutSec,
                CacheTtlMs=CacheTtlMs,
                ExtraInputArgs=ExtraInputArgs,
                AllowLastGood=AllowLastGood,
            )
            return self._make_jpeg_response(Jpeg)

        except SnapshotConfigError:
            flask.abort(400, description="Buddycam: input_url is not configured")

        except SnapshotTimeoutError:
            flask.abort(504, description="Buddycam: snapshot timed out")

        except SnapshotAcquireError:
            flask.abort(502, description="Buddycam: could not capture snapshot")

    def _make_jpeg_response(self, JpegBytes):
        Resp = flask.make_response(JpegBytes)
        Resp.headers["Content-Type"] = "image/jpeg"
        Resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"

        # Allow dashboards on other hosts to request this endpoint.
        Resp.headers["Access-Control-Allow-Origin"] = "*"
        Resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    
        return Resp


__plugin_name__ = "Buddycam"
__plugin_pythoncompat__ = ">=3,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = BuddycamPlugin()
