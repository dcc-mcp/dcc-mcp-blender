"""Bounded PNG completeness checks without bpy or optional image libraries.

Validate chunk structure, CRCs and the complete decompressed scanline layout,
not just the signature. This does not reconstruct pixels or interpret every
ancillary chunk, and is not a colour-management or visual-quality check.
Memory is bounded by the block size, even for highly compressed input. Files
or inflated scanlines exceeding 1 GiB, or more than one million total pass
rows, fail closed to bound work in a status query. No image data is retained
and no Blender data blocks are touched.
"""

from __future__ import annotations

import struct
import zlib

_MAGIC = b"\x89PNG\r\n\x1a\n"
_BLOCK = 64 * 1024
_MAX_BYTES = 1024 * 1024 * 1024
_MAX_SCANLINES = 1_000_000
_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


class _Scanlines:
    """Consume filtered bytes a block at a time, including Adam7 pass rows."""

    def __init__(self, header):
        width, height, depth, colour, compression, filtering, interlace = struct.unpack(">IIBBBBB", header)
        if (
            not 0 < width <= 0x7FFFFFFF
            or not 0 < height <= 0x7FFFFFFF
            or depth not in _DEPTHS.get(colour, ())
            or compression != 0
            or filtering != 0
            or interlace not in (0, 1)
        ):
            raise ValueError("Invalid PNG IHDR")
        passes = _ADAM7 if interlace else ((0, 0, 1, 1),)
        self.layout = []
        for x, y, dx, dy in passes:
            columns = max(0, (width - x + dx - 1) // dx)
            rows = max(0, (height - y + dy - 1) // dy)
            if columns and rows:
                self.layout.append([rows, 1 + (columns * depth * _CHANNELS[colour] + 7) // 8])
        if sum(rows * length for rows, length in self.layout) > _MAX_BYTES:
            raise ValueError("PNG decompressed data exceeds the validation limit")
        if sum(rows for rows, _length in self.layout) > _MAX_SCANLINES:
            raise ValueError("PNG scanline count exceeds the validation limit")
        self.offset = 0
        self.colour = colour
        self.depth = depth

    def consume(self, data):
        index = 0
        while index < len(data):
            if not self.layout:
                raise ValueError("Excess PNG pixel data")
            if self.offset == 0 and data[index] > 4:
                raise ValueError("Invalid PNG scanline filter")
            count = min(len(data) - index, self.layout[0][1] - self.offset)
            index += count
            self.offset += count
            if self.offset == self.layout[0][1]:
                self.offset = 0
                self.layout[0][0] -= 1
                if self.layout[0][0] == 0:
                    self.layout.pop(0)


def _inflate(decoder, data, scanlines):
    while True:
        output = decoder.decompress(data, _BLOCK)
        scanlines.consume(output)
        if decoder.unused_data:
            raise ValueError("Trailing data in PNG zlib stream")
        data = decoder.unconsumed_tail
        if not data and len(output) < _BLOCK:
            return


def is_complete_png(stream, size):
    """Reject incomplete/invalid checked structures and unsupported sizes.

    ``stream`` must be a binary file at offset zero. Unknown ancillary chunks
    are streamed and CRC-checked; unknown critical chunks fail closed. The
    only compressed stream interpreted here is image IDAT, not optional
    metadata. PNG animation chunks are rejected: render outputs are stills.
    """
    try:
        if size > _MAX_BYTES or stream.read(8) != _MAGIC:
            return False
        scanlines = None
        decoder = zlib.decompressobj()
        palette = False
        image_data = False
        data_ended = False
        while True:
            header = stream.read(8)
            if len(header) != 8:
                return False
            length, kind = struct.unpack(">I4s", header)
            if (
                length > 0x7FFFFFFF
                or stream.tell() + length + 4 > size
                or not all(65 <= char <= 90 or 97 <= char <= 122 for char in kind)
                or kind[2] & 32
            ):
                return False
            if scanlines is None:
                if kind != b"IHDR" or length != 13:
                    return False
            elif kind == b"IHDR":
                return False
            if kind in (b"acTL", b"fcTL", b"fdAT"):
                return False
            if kind not in (b"IHDR", b"PLTE", b"IDAT", b"IEND") and not kind[0] & 32:
                return False
            if kind == b"PLTE":
                if (
                    palette
                    or image_data
                    or not 0 < length <= 768
                    or length % 3
                    or scanlines.colour in (0, 4)
                    or (scanlines.colour == 3 and length // 3 > 2**scanlines.depth)
                ):
                    return False
                palette = True
            if kind == b"IDAT":
                if data_ended or (scanlines.colour == 3 and not palette):
                    return False
                image_data = True
            elif image_data:
                data_ended = True
            crc = zlib.crc32(kind)
            remaining = length
            while remaining:
                block = stream.read(min(remaining, _BLOCK))
                if not block:
                    return False
                remaining -= len(block)
                crc = zlib.crc32(block, crc)
                if kind == b"IHDR":
                    scanlines = _Scanlines(block)
                elif kind == b"IDAT":
                    _inflate(decoder, block, scanlines)
            checksum = stream.read(4)
            if len(checksum) != 4 or struct.unpack(">I", checksum)[0] != crc & 0xFFFFFFFF:
                return False
            if kind == b"IEND":
                return (
                    length == 0
                    and image_data
                    and decoder.eof
                    and not scanlines.layout
                    and stream.tell() == size
                    and not stream.read(1)
                )
    except (OSError, ValueError, struct.error, zlib.error):
        return False
