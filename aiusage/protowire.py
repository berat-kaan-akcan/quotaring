"""Minimal protobuf wire-format reader (no schema, no dependencies).

Only what is needed to pull a few known numeric/string fields out of Antigravity blobs.
Malformed input raises ValueError.
"""

from __future__ import annotations


def _varint(b: bytes, i: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if i >= len(b):
            raise ValueError("truncated varint")
        x = b[i]
        i += 1
        result |= (x & 0x7F) << shift
        if not x & 0x80:
            return result, i
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def parse(b: bytes) -> dict[int, list]:
    """Return {field_number: [values]}; varints as int, length-delimited as bytes."""
    out: dict[int, list] = {}
    i = 0
    n = len(b)
    while i < n:
        key, i = _varint(b, i)
        field, wt = key >> 3, key & 7
        if field == 0:
            raise ValueError("field 0")
        if wt == 0:
            v, i = _varint(b, i)
        elif wt == 1:
            if i + 8 > n:
                raise ValueError("truncated fixed64")
            v = b[i:i + 8]
            i += 8
        elif wt == 2:
            length, i = _varint(b, i)
            if i + length > n:
                raise ValueError("truncated bytes")
            v = b[i:i + length]
            i += length
        elif wt == 5:
            if i + 4 > n:
                raise ValueError("truncated fixed32")
            v = b[i:i + 4]
            i += 4
        else:
            raise ValueError(f"unsupported wire type {wt}")
        out.setdefault(field, []).append(v)
    return out


def first(msg: dict[int, list], field: int, default=None):
    vals = msg.get(field)
    return vals[0] if vals else default


def submessage(msg: dict[int, list], field: int) -> dict[int, list] | None:
    v = first(msg, field)
    if not isinstance(v, (bytes, bytearray)):
        return None
    return parse(v)


def packed_varints(msg: dict[int, list], field: int) -> list[int]:
    """Repeated uint32 fields may be packed (bytes) or unpacked (ints)."""
    out: list[int] = []
    for v in msg.get(field, []):
        if isinstance(v, int):
            out.append(v)
        elif isinstance(v, (bytes, bytearray)):
            i = 0
            while i < len(v):
                x, i = _varint(v, i)
                out.append(x)
    return out
