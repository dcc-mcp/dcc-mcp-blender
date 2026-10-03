import math
from types import SimpleNamespace

import pytest

from dcc_mcp_blender._text_geometry import _assert_builtin_fonts, validate_text


@pytest.mark.parametrize("text", ["BRASS RELAY", "FOUR BAR / 01", "One\nTwo\nThree"])
def test_bounded_ascii_text_is_accepted(text):
    validate_text("Name", text, 0.2, 0, "CENTER")


@pytest.mark.parametrize("text", ["", "x" * 161, "a\nb\nc\nd", "\x00", "字", None])
def test_unsupported_body_rejected(text):
    with pytest.raises(ValueError):
        validate_text("Name", text, 0.2, 0, "LEFT")


@pytest.mark.parametrize("size", [0, 11, math.inf, math.nan, True])
def test_size_is_finite_and_bounded(size):
    with pytest.raises(ValueError):
        validate_text("Name", "Word", size, 0, "LEFT")


@pytest.mark.parametrize("depth", [-1, 0.2, math.nan])
def test_extrusion_is_bounded(depth):
    with pytest.raises(ValueError):
        validate_text("Name", "Word", 0.2, depth, "LEFT")


def test_alignment_is_closed():
    with pytest.raises(ValueError):
        validate_text("Name", "Word", 0.2, 0, "JUSTIFY")


@pytest.mark.parametrize("slot", ["font", "font_bold", "font_italic", "font_bold_italic"])
@pytest.mark.parametrize("linked", [False, True])
def test_every_font_slot_requires_builtin_local_font(slot, linked):
    builtin = SimpleNamespace(filepath="<builtin>", library=None)
    data = SimpleNamespace(font=builtin, font_bold=None, font_italic=builtin, font_bold_italic=None)
    setattr(
        data,
        slot,
        SimpleNamespace(filepath="<builtin>" if linked else "//fonts/style.ttf", library=object() if linked else None),
    )
    with pytest.raises(ValueError, match="every style slot"):
        _assert_builtin_fonts(data)


def test_unassigned_style_fonts_use_the_builtin_regular_fallback():
    _assert_builtin_fonts(
        SimpleNamespace(
            font=SimpleNamespace(filepath="<builtin>", library=None),
            font_bold=None,
            font_italic=None,
            font_bold_italic=None,
        )
    )
