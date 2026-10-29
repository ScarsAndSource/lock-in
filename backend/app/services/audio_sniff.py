"""
Audio upload sanity: what the bytes ARE (not what the client claimed) and, where the container says so, how long.

inspect_audio(data) -> AudioInfo | None
  None            not a recognised audio container: refuse it
  .filename/.content_type  the right names for the sniffed container (Groq picks the decoder from them, so a client
                  that mislabels a recording no longer breaks transcription)
  .seconds        best-effort duration, None when unknown. Known for WAV, Ogg, WebM (including MediaRecorder's
                  live-written files, which have no Duration: the last Cluster is read instead) and non-fragmented
                  MP4/M4A. Unknown (fragmented MP4 from Safari, MP3, AAC) simply isn't duration-checked: the byte
                  cap still applies.
Pure parsing, nothing is decoded or executed, and any malformed input yields seconds=None, never an exception.
"""
from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass

_UPLOAD_NAMES = {
    "webm": ("checkin.webm", "audio/webm"),
    "ogg": ("checkin.ogg", "audio/ogg"),
    "wav": ("checkin.wav", "audio/wav"),
    "mp4": ("checkin.m4a", "audio/mp4"),
    "aac": ("checkin.m4a", "audio/mp4"),
    "mp3": ("checkin.mp3", "audio/mpeg"),
}


@dataclass(frozen=True, slots=True)
class AudioInfo:
    kind: str
    filename: str
    content_type: str
    seconds: float | None


def sniff_audio(data: bytes) -> str | None:
    head = data[:16]
    if len(head) < 12:
        return None
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[4:8] == b"ftyp":
        return "mp4"
    if head[:3] == b"ID3":
        return "mp3"
    if head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:       # MPEG audio frame sync
        return "aac" if (head[1] & 0x06) == 0 else "mp3"   # layer bits 00 = ADTS AAC
    return None


def inspect_audio(data: bytes) -> AudioInfo | None:
    kind = sniff_audio(data)
    if kind is None:
        return None
    try:
        seconds = _DURATION.get(kind, lambda _d: None)(data)
    except (struct.error, IndexError, ValueError, OverflowError, RecursionError):
        seconds = None
    if seconds is not None and not (0 < seconds < 86400):
        seconds = None
    filename, content_type = _UPLOAD_NAMES[kind]
    return AudioInfo(kind, filename, content_type, seconds)


# ---------------------------------------------------------------- WAV
def _wav_seconds(d: bytes) -> float | None:
    pos, n, byte_rate = 12, len(d), None
    while pos + 8 <= n:
        cid = d[pos:pos + 4]
        size = struct.unpack_from("<I", d, pos + 4)[0]
        body = pos + 8
        if cid == b"fmt " and body + 12 <= n:
            byte_rate = struct.unpack_from("<I", d, body + 8)[0]
        elif cid == b"data":
            if not byte_rate:
                return None
            avail = n - body
            length = size if 0 < size <= avail else avail   # streamed WAVs write 0 / 0xFFFFFFFF
            return length / byte_rate
        pos = body + size + (size & 1)
    return None


# ---------------------------------------------------------------- Ogg (Opus / Vorbis)
def _ogg_seconds(d: bytes) -> float | None:
    last = d.rfind(b"OggS")
    if last < 0 or last + 14 > len(d):
        return None
    granule = struct.unpack_from("<q", d, last + 6)[0]
    if granule <= 0:
        return None
    if b"OpusHead" in d[:200]:
        rate = 48000
    else:
        i = d.find(b"\x01vorbis", 0, 200)
        if i < 0 or i + 16 > len(d):
            return None
        rate = struct.unpack_from("<I", d, i + 12)[0]
    return granule / rate if rate else None


# ---------------------------------------------------------------- WebM (EBML)
def _read_vint(d: bytes, pos: int, keep_marker: bool) -> tuple[int, int] | None:
    if pos >= len(d):
        return None
    first = d[pos]
    length, mask = 1, 0x80
    while length <= 8 and not (first & mask):
        length += 1
        mask >>= 1
    if length > 8 or pos + length > len(d):
        return None
    value = first if keep_marker else (first & (mask - 1))
    for b in d[pos + 1:pos + length]:
        value = (value << 8) | b
    return value, length


def _elements(d: bytes, pos: int, end: int) -> Iterator[tuple[int, int, int | None]]:
    """(id, body_start, size) for sibling elements; size None = unknown (live-written), which can't be skipped."""
    n = min(end, len(d))
    count = 0
    while pos < n and count < 200_000:
        count += 1
        idv = _read_vint(d, pos, True)
        if idv is None:
            return
        eid, il = idv
        sv = _read_vint(d, pos + il, False)
        if sv is None:
            return
        size, sl = sv
        body = pos + il + sl
        if size == (1 << (7 * sl)) - 1:
            yield eid, body, None
            return
        yield eid, body, size
        pos = body + size


def _cluster_extent(d: bytes, pos: int, end: int) -> tuple[int, int]:
    """(cluster timecode, largest block offset inside it), in timecode ticks."""
    tc = last = 0
    for eid, body, size in _elements(d, pos, end):
        if size is None:
            continue
        if eid == 0xE7:
            tc = int.from_bytes(d[body:body + size], "big")
        elif eid in (0xA3, 0xA1):                      # SimpleBlock / Block: track vint, int16 offset, flags
            tv = _read_vint(d, body, False)
            if tv is not None and body + tv[1] + 2 <= len(d):
                last = max(last, struct.unpack_from(">h", d, body + tv[1])[0])
        elif eid == 0xA0:                              # BlockGroup
            last = max(last, _cluster_extent(d, body, body + size)[1])
    return tc, last


def _webm_seconds(d: bytes) -> float | None:
    segment = None
    for eid, body, _size in _elements(d, 0, len(d)):
        if eid == 0x18538067:
            segment = body
            break
    if segment is None:
        return None
    scale, duration = 1_000_000, None
    for eid, body, size in _elements(d, segment, len(d)):
        if eid == 0x1549A966 and size is not None:      # Info
            for cid, cb, cs in _elements(d, body, body + size):
                if cs is None:
                    continue
                if cid == 0x2AD7B1:                     # TimecodeScale
                    scale = int.from_bytes(d[cb:cb + cs], "big") or scale
                elif cid == 0x4489 and cs in (4, 8) and cb + cs <= len(d):   # Duration
                    duration = struct.unpack_from(">f" if cs == 4 else ">d", d, cb)[0]
        elif eid == 0x1F43B675:                         # first Cluster: the header is behind us
            break
    if duration and duration > 0:
        return duration * scale / 1e9
    c = d.rfind(b"\x1f\x43\xb6\x75")                    # live-written WebM: read the last Cluster
    if c < 0:
        return None
    for eid, body, size in _elements(d, c, len(d)):
        if eid == 0x1F43B675:
            tc, last = _cluster_extent(d, body, len(d) if size is None else body + size)
            return (tc + last) * scale / 1e9
        break
    return None


# ---------------------------------------------------------------- MP4 / M4A
def _boxes(d: bytes, pos: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    n = min(end, len(d))
    while pos + 8 <= n:
        size = struct.unpack_from(">I", d, pos)[0]
        kind = d[pos + 4:pos + 8]
        hdr = 8
        if size == 1:
            if pos + 16 > n:
                return
            size = struct.unpack_from(">Q", d, pos + 8)[0]
            hdr = 16
        elif size == 0:
            size = n - pos
        if size < hdr:
            return
        yield kind, pos + hdr, size - hdr
        pos += size


def _mp4_seconds(d: bytes) -> float | None:
    for kind, body, size in _boxes(d, 0, len(d)):
        if kind != b"moov":
            continue
        for k2, b2, _s2 in _boxes(d, body, body + size):
            if k2 != b"mvhd":
                continue
            version = d[b2]
            if version == 0 and b2 + 20 <= len(d):
                scale, dur = struct.unpack_from(">II", d, b2 + 12)
                unknown = dur == 0xFFFFFFFF
            elif version == 1 and b2 + 32 <= len(d):
                scale = struct.unpack_from(">I", d, b2 + 20)[0]
                dur = struct.unpack_from(">Q", d, b2 + 24)[0]
                unknown = dur == 0xFFFFFFFFFFFFFFFF
            else:
                return None
            return None if (not scale or not dur or unknown) else dur / scale   # fragmented MP4: duration 0
    return None


_DURATION = {"wav": _wav_seconds, "ogg": _ogg_seconds, "webm": _webm_seconds, "mp4": _mp4_seconds}
