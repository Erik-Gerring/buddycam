# Buddycam – OctoPrint RTSP Snapshot Plugin

**Purpose:** Reliable, FFmpeg-based camera snapshots for OctoPrint  
**Scope:** Snapshots only (no streaming)  
**Status:** Working, minimal, extensible

---

## Overview

Buddycam is an OctoPrint plugin that exposes a **stable HTTP snapshot endpoint** backed by **FFmpeg** and **RTSP/IP cameras**.

It intentionally avoids OctoPrint’s legacy webcam stack and instead provides:
- A deterministic snapshot URL
- Minimal moving parts
- A small, extensible processing pipeline for future use (e.g. ML, storage, automation)

---

## Snapshot Flow

    HTTP GET /plugin/buddycam/snapshot
            ↓
    SnapshotService
            ↓
    FFmpegSnapshotSource → JPEG bytes
            ↓
    FramePipeline (optional)
            ↓
    HTTP response (image/jpeg)


Key behaviours:
- One FFmpeg capture at a time (concurrency-safe)
- Short-lived caching to avoid repeated spawns
- Optional “last good frame” fallback
- Clean HTTP error mapping

---

## OctoPrint Integration

- Implemented as a standard OctoPrint plugin
- Registers a public Flask route at: /plugin/buddycam/snapshot

- OctoPrint handles lifecycle, settings persistence, and logging
- Plugin code focuses only on routing and configuration

---

## Pipeline Framework

Captured frames are wrapped in a lightweight `Frame` object and may pass through a simple pipeline:

- **Processors** – inspect or transform frames
- **Sinks** – side effects (ML inference, storage, publishing, etc.)

Pipeline failures do not break snapshot delivery.

---

## File Structure

### `__init__.py`
OctoPrint glue:
- Plugin class and mixins
- Settings defaults
- HTTP route
- Error → HTTP status mapping

### `snapshot_service.py`
Snapshot orchestration:
- Caching and concurrency control
- Last-good fallback
- Pipeline execution

### `ffmpeg_source.py`
Frame acquisition:
- FFmpeg command construction
- Subprocess execution with timeout
- Structured error handling

### `pipeline.py`
Extensibility layer:
- `Frame` container
- Processor and sink fan-out

### `util.py`
Shared helpers:
- JPEG validation
- Safe URL logging (credential redaction)

---

## Configuration

| Setting | Description |
|------|-------------|
| `input_url` | RTSP camera URL |
| `ffmpeg_path` | Path to FFmpeg |
| `rtsp_transport` | `tcp` or `udp` |
| `timeout_sec` | FFmpeg timeout |
| `cache_ttl_ms` | Snapshot cache lifetime |
| `extra_input_args` | Advanced FFmpeg flags |
| `allow_last_good` | Serve last good frame on failure |

---

## Design Intent

Buddycam is:
- Snapshot-only
- Minimal and explicit
- Easy to extend without touching FFmpeg or HTTP logic

Simplicity is intentional.

---
