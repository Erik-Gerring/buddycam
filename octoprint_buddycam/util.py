# coding=utf-8
from __future__ import absolute_import

import re


_JPEG_SOI = b"\xff\xd8"  # start of image
_JPEG_EOI = b"\xff\xd9"  # end of image


def is_jpeg(Data):
    """Return True if bytes look like a complete JPEG file."""
    if not Data or len(Data) < 4:
        return False
    return Data.startswith(_JPEG_SOI) and Data.endswith(_JPEG_EOI)


def redact_url_credentials(Url):
    """
    Redact credentials in URLs for safe logging.

    Examples:
      rtsp://user:pass@host/stream -> rtsp://user:***@host/stream
    """
    if not Url:
        return Url
    # This is intentionally conservative: keep user, drop password.
    return re.sub(r"(://[^:/@]+):[^@]+@", r"\1:***@", Url)
