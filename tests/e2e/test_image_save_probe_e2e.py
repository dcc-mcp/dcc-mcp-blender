"""Diagnostic probe: find which save path works under blender --background.

Temporary. Delete once save_image is fixed and this is replaced by assertions.

The last two attempts guessed: image.save() raises "does not have any image
data" because pixel data is not materialised in background mode, and len(pixels)
turned out to be a no-op on a lazily loaded collection rather than a decode
trigger. Rather than guess a third time, this measures every candidate in one
run and prints the result, so a single CI pass answers the whole question.

Each candidate is isolated on its own fresh image so one cannot influence the
next. Every print is flushed because the process may die mid-run.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e


def _emit(line: str) -> None:
    print(f"[save-probe] {line}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()


def _png(path: Path) -> Path:
    import struct
    import zlib

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 2 for _ in range(2))
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)
    return path


def _fresh_image(directory: Path, tag: str):
    """Load an independent copy of the source so candidates cannot interfere."""
    source = _png(directory / f"{tag}.png")
    return bpy.data.images.load(str(source)), source


def test_probe_background_save_paths():
    _emit(f"blender={bpy.app.version_string} background={bpy.app.background}")

    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)

        # Baseline: what does a freshly loaded image report before any attempt?
        image, source = _fresh_image(directory, "baseline")
        _emit(f"baseline has_data={getattr(image, 'has_data', 'NO_ATTR')} len(pixels)={len(image.pixels)}")
        _emit(f"baseline source={image.source} filepath={image.filepath} size={list(image.size)}")

        # Candidate 1: index the pixels instead of len(), which was a no-op.
        image, _ = _fresh_image(directory, "index")
        before = getattr(image, "has_data", None)
        try:
            _ = image.pixels[0]
            indexed = True
            error = ""
        except Exception as exc:
            indexed = False
            error = f"{type(exc).__name__}: {exc}"
        after = getattr(image, "has_data", None)
        _emit(f"index-pixels ok={indexed} error={error!r} has_data {before} -> {after}")

        # Candidate 2: explicit update() before touching pixels.
        image, _ = _fresh_image(directory, "update")
        before = getattr(image, "has_data", None)
        update_error = ""
        try:
            image.update()
        except Exception as exc:
            update_error = f"{type(exc).__name__}: {exc}"
        try:
            _ = image.pixels[0]
            pixels_after_update = True
        except Exception:
            pixels_after_update = False
        after = getattr(image, "has_data", None)
        _emit(f"update() error={update_error!r} pixels_readable={pixels_after_update} has_data {before} -> {after}")

        # Candidate 3: image.save() as currently implemented.
        image, _ = _fresh_image(directory, "save")
        target = directory / "save_out.png"
        save_error = ""
        try:
            image.save()
            wrote = (directory / Path(image.filepath).name).is_file() or target.is_file()
        except Exception as exc:
            save_error = f"{type(exc).__name__}: {exc}"
            wrote = False
        _emit(f"image.save() error={save_error!r} wrote={wrote}")

        # Candidate 4: save_render(), the documented headless-safe route.
        image, _ = _fresh_image(directory, "save_render")
        target = directory / "save_render_out.png"
        save_render_error = ""
        try:
            image.save_render(str(target))
            save_render_wrote = target.is_file()
            save_render_size = target.stat().st_size if save_render_wrote else 0
        except Exception as exc:
            save_render_error = f"{type(exc).__name__}: {exc}"
            save_render_wrote = False
            save_render_size = 0
        _emit(f"image.save_render() error={save_render_error!r} wrote={save_render_wrote} size={save_render_size}")

        # Candidate 5: copying the source file, valid when the image is unmodified.
        image, source = _fresh_image(directory, "copy")
        target = directory / "copy_out.png"
        try:
            shutil.copyfile(source, target)
            copy_wrote = target.is_file()
            copy_size = target.stat().st_size if copy_wrote else 0
            copy_error = ""
        except Exception as exc:
            copy_error = f"{type(exc).__name__}: {exc}"
            copy_wrote = False
            copy_size = 0
        _emit(f"shutil.copyfile() error={copy_error!r} wrote={copy_wrote} size={copy_size}")

        # Does a render-produced image behave differently from a loaded one?
        generated = bpy.data.images.new("ProbeGenerated", width=4, height=4)
        _emit(f"generated has_data={getattr(generated, 'has_data', 'NO_ATTR')} len(pixels)={len(generated.pixels)}")
        generated_target = directory / "generated_out.png"
        generated_error = ""
        try:
            generated.filepath = str(generated_target)
            generated.save()
            generated_wrote = generated_target.is_file()
        except Exception as exc:
            generated_error = f"{type(exc).__name__}: {exc}"
            generated_wrote = False
        _emit(f"generated.save() error={generated_error!r} wrote={generated_wrote}")

    _emit("probe complete")
