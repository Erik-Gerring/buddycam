# coding=utf-8
from __future__ import absolute_import

import time


class Frame(object):
    """
    A single captured frame with minimal metadata.

    Data - JPEG bytes
    CapturedAt - epoch seconds
    Source - short identifier (e.g. "ffmpeg")
    Meta - dict for optional extra info (camera name, request id, etc.)
    """
    __slots__ = ("Data", "CapturedAt", "Source", "Meta")

    def __init__(self, Data, Source, Meta=None):
        self.Data = Data
        self.CapturedAt = time.time()
        self.Source = Source
        self.Meta = Meta or {}


class FramePipeline(object):
    """
    Simple, composable pipeline.

    Processors:
      - transform or inspect frames (may return same or new Frame)
    Sinks:
      - side effects (store, publish, infer, etc.)
    """
    def __init__(self, Logger=None):
        self._processors = []
        self._sinks = []
        self._logger = Logger

    def add_processor(self, ProcessorFn):
        self._processors.append(ProcessorFn)

    def add_sink(self, SinkFn):
        self._sinks.append(SinkFn)

    def run(self, FrameObj):
        """
        Run processors then sinks.

        Design choice:
        - Processor failures abort the pipeline (frame could be invalid).
        - Sink failures are logged and ignored (don’t break snapshot serving).
        """
        Current = FrameObj
        for Proc in self._processors:
            Current = Proc(Current)

        for Sink in self._sinks:
            try:
                Sink(Current)
            except Exception as Ex:
                if self._logger:
                    self._logger.warning("Buddycam pipeline sink failed: %s", Ex)

        return Current
