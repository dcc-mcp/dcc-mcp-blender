"""Real PNG Suite samples plus adversarial, dependency-free PNG fixtures."""

import io
import struct
import zlib
from pathlib import Path

import pytest

from dcc_mcp_blender import _png_integrity as png

FIXTURES = sorted((Path(__file__).parent / "fixtures" / "png").glob("*.png"))


def chunk(kind, data=b""):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def ihdr(width=1, height=1, depth=8, colour=6, compression=0, filtering=0, interlace=0):
    return chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, colour, compression, filtering, interlace))


def image(raw=b"\0\x10\x20\x30\xff", header=None, compressed=None):
    return (
        png._MAGIC
        + (header or ihdr())
        + chunk(b"IDAT", zlib.compress(raw) if compressed is None else compressed)
        + chunk(b"IEND")
    )


def valid(data):
    return png.is_complete_png(io.BytesIO(data), len(data))


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda path: path.name)
def test_real_libpng_suite_images_and_every_truncated_prefix(fixture):
    data = fixture.read_bytes()
    assert valid(data)
    for end in range(len(data)):
        assert not valid(data[:end]), (fixture.name, end)


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda path: path.name)
def test_real_libpng_suite_images_reject_every_single_byte_corruption(fixture):
    data = bytearray(fixture.read_bytes())
    for index in range(len(data)):
        data[index] ^= 1
        assert not valid(data), (fixture.name, index)
        data[index] ^= 1


def test_valid_idat_stream_split_at_every_byte_with_empty_chunks():
    compressed = zlib.compress(b"\0\x10\x20\x30\xff")
    data = png._MAGIC + ihdr() + chunk(b"IDAT")
    data += b"".join(chunk(b"IDAT", bytes([byte])) for byte in compressed)
    assert valid(data + chunk(b"IDAT") + chunk(b"IEND"))


def test_inflation_and_scanlines_cross_block_boundaries(monkeypatch):
    monkeypatch.setattr(png, "_BLOCK", 17)  # Header (13 bytes) still fits.
    # Every PNG filter and a row wider than an inflation block.
    raw = b"".join(bytes([filter_type]) + b"\0" * 400 for filter_type in range(5))
    assert valid(image(raw, ihdr(width=100, height=5)))


@pytest.mark.parametrize(
    "header",
    [
        ihdr(width=0),
        ihdr(height=0),
        ihdr(width=0x80000000),
        ihdr(height=0x80000000),
        ihdr(depth=4),
        ihdr(colour=1),
        ihdr(compression=1),
        ihdr(filtering=1),
        ihdr(interlace=2),
        chunk(b"IHDR", b"x" * 12),
        chunk(b"IHDR", b"x" * 14),
    ],
)
def test_rejects_invalid_ihdr(header):
    assert not valid(image(header=header))


@pytest.mark.parametrize(
    "compressed",
    [
        b"",
        b"not zlib",
        zlib.compress(b"\0\x10\x20\x30\xff")[:-1],
        zlib.compress(b"\0\x10\x20\x30\xff") + b"extra",
        zlib.compress(b"\0\x10\x20\x30\xff") + zlib.compress(b"second stream"),
    ],
)
def test_rejects_invalid_zlib_even_with_correct_chunk_crc(compressed):
    assert not valid(image(compressed=compressed))


@pytest.mark.parametrize("raw", [b"", b"\0", b"\0\x10\x20\x30", b"\0\x10\x20\x30\xff\0", b"\x05\x10\x20\x30\xff"])
def test_rejects_wrong_scanline_size_or_filter_even_with_valid_zlib(raw):
    assert not valid(image(raw))


def test_rejects_missing_iend_and_bytes_after_iend():
    data = image()
    assert not valid(data[:-12])
    assert not valid(data + b"trailing")
    assert not valid(data + chunk(b"IEND"))
    assert not valid(data[:-12] + chunk(b"IEND", b"x"))


@pytest.mark.parametrize("kind", [b"ABCD", b"abcD", b"1BCD", b"ab\xffD", b"acTL", b"fcTL", b"fdAT"])
def test_rejects_unknown_critical_invalid_names_and_animation(kind):
    assert not valid(png._MAGIC + ihdr() + chunk(kind) + image()[33:])


def test_accepts_crc_checked_unknown_ancillary_chunks():
    data = png._MAGIC + ihdr() + chunk(b"abCD", b"opaque metadata") + image()[33:]
    assert valid(data)
    damaged = data[:48] + bytes([data[48] ^ 1]) + data[49:]
    assert not valid(damaged)


def test_rejects_nonconsecutive_idat_and_duplicate_ihdr():
    compressed = zlib.compress(b"\0\x10\x20\x30\xff")
    assert not valid(png._MAGIC + ihdr() + ihdr() + image()[33:])
    assert not valid(
        png._MAGIC
        + ihdr()
        + chunk(b"IDAT", compressed[:3])
        + chunk(b"abCD")
        + chunk(b"IDAT", compressed[3:])
        + chunk(b"IEND")
    )
    assert not valid(png._MAGIC + chunk(b"abCD") + image()[8:])


def test_palette_constraints():
    header = ihdr(depth=1, colour=3)
    data = chunk(b"IDAT", zlib.compress(b"\0\0")) + chunk(b"IEND")
    palette = chunk(b"PLTE", b"\0\0\0\xff\xff\xff")
    assert valid(png._MAGIC + header + palette + data)
    assert not valid(png._MAGIC + header + data)
    assert not valid(png._MAGIC + header + palette + palette + data)
    assert not valid(png._MAGIC + header + data[:-12] + palette + data[-12:])
    for entries in (b"", b"xx", b"x" * 9, b"x" * 771):
        assert not valid(png._MAGIC + header + chunk(b"PLTE", entries) + data)
    assert not valid(png._MAGIC + ihdr(colour=0) + palette + data)


def test_rejects_forged_chunk_lengths_without_large_reads():
    assert not valid(png._MAGIC + struct.pack(">I", 0xFFFFFFFF) + b"IHDR")
    assert not valid(png._MAGIC + ihdr() + struct.pack(">I", 1000000) + b"IDAT")


def test_file_and_inflated_limits_fail_closed(monkeypatch):
    monkeypatch.setattr(png, "_MAX_BYTES", 100)
    assert valid(image())
    assert not valid(image(header=ihdr(width=100, height=100)))
    assert not valid(image() + b"x" * 100)


def test_scanline_limit_includes_every_adam7_pass(monkeypatch):
    # No image-sized allocation or inflation is needed to reject tall images.
    png._Scanlines(ihdr(height=png._MAX_SCANLINES)[8:-4])
    with pytest.raises(ValueError, match="scanline count"):
        png._Scanlines(ihdr(height=png._MAX_SCANLINES + 1)[8:-4])
    monkeypatch.setattr(png, "_MAX_SCANLINES", 5)
    # A 3x3 Adam7 image has 6 total pass rows, not just its 3 image rows.
    with pytest.raises(ValueError, match="scanline count"):
        png._Scanlines(ihdr(width=3, height=3, interlace=1)[8:-4])
    monkeypatch.setattr(png, "_MAX_SCANLINES", 6)
    png._Scanlines(ihdr(width=3, height=3, interlace=1)[8:-4])


def test_decompression_bomb_stops_at_first_excess_bounded_block(monkeypatch):
    consumed = []
    original = png._Scanlines.consume

    def consume(self, data):
        consumed.append(len(data))
        return original(self, data)

    monkeypatch.setattr(png._Scanlines, "consume", consume)
    assert not valid(image(raw=b"\0" * (2 * 1024 * 1024)))
    assert consumed == [png._BLOCK]


def test_short_reads_and_io_errors_fail_closed():
    class BrokenFile(io.BytesIO):
        def read(self, size=-1):
            raise OSError("unreadable")

    assert not png.is_complete_png(BrokenFile(image()), len(image()))
    assert not png.is_complete_png(io.BytesIO(image()), len(image()) + 1)
