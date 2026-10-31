"""
Image width and height from the file HEADER only: nothing is decoded, so a hostile "decompression bomb" costs a few
dozen bytes of reading, not memory.

Why: the byte cap (2.8 MB) says nothing about pixel count. A tiny, highly compressed PNG can be 30000 x 30000: the
provider that reads the picture then rejects it (a wasted, charged call) or chews through it. exceeds() lets
MediaService refuse such a file before any model call.

Policy: refuse only when the header is READABLE and the pixel count is over the limit (or zero). A header this module
can't read is let through: the real type check is audio/image sniffing, the byte cap still bounds the file, and the
provider has its own limits. Never raises.
"""
from __future__ import annotations

import struct

_JPEG_SOF = frozenset({0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF})
_JPEG_NO_LENGTH = frozenset({0x01, *range(0xD0, 0xDA)})     # TEM, RSTn, SOI, EOI: markers with no length field


def _png(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def _jpeg(data: bytes) -> tuple[int, int] | None:
    n, pos = len(data), 2
    while pos + 4 <= n:
        if data[pos] != 0xFF:
            pos += 1
            continue
        while pos < n and data[pos] == 0xFF:      # fill bytes
            pos += 1
        if pos >= n:
            return None
        marker = data[pos]
        pos += 1
        if marker in _JPEG_NO_LENGTH or marker == 0x00:
            continue
        if marker == 0xDA:                        # start of scan: no frame header came first
            return None
        if pos + 2 > n:
            return None
        length = struct.unpack(">H", data[pos:pos + 2])[0]
        if marker in _JPEG_SOF:
            if pos + 7 > n:
                return None
            height, width = struct.unpack(">HH", data[pos + 3:pos + 7])
            return width, height
        if length < 2:
            return None
        pos += length
    return None


def _webp(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30:
        return None
    kind = data[12:16]
    if kind == b"VP8 ":
        if data[23:26] != b"\x9d\x01\x2a":
            return None
        return struct.unpack("<H", data[26:28])[0] & 0x3FFF, struct.unpack("<H", data[28:30])[0] & 0x3FFF
    if kind == b"VP8L":
        if data[20] != 0x2F:
            return None
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if kind == b"VP8X":
        return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    return None


def dimensions(data: bytes) -> tuple[int, int] | None:
    """(width, height) for a PNG, JPEG or WebP, or None when the header can't be read."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return _png(data)
        if data[:3] == b"\xff\xd8\xff":
            return _jpeg(data)
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return _webp(data)
    except (struct.error, IndexError, ValueError):
        return None
    return None


def exceeds(data: bytes, max_pixels: int) -> bool:
    """True when the header says the picture has more than max_pixels pixels (or none at all)."""
    dims = dimensions(data)
    if dims is None:
        return False
    width, height = dims
    return width <= 0 or height <= 0 or width * height > max_pixels
