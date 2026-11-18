"""Rendered-pixel color safety analysis for photographic toy shots."""

from __future__ import annotations

import math
from typing import Any, Sequence

DEFAULT_HIGHLIGHT_THRESHOLD = 185.0 / 255.0
DEFAULT_SATURATION_THRESHOLD = 0.15
DEFAULT_WARM_BIAS_THRESHOLD = 0.08
DEFAULT_WARNING_RATIO = 0.10
DEFAULT_MAX_SAMPLES = 200_000


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _bounded(value: Any, label: str, minimum: float = 0.0, maximum: float = 1.0) -> float:
    result = _finite(value, label)
    if result < minimum or result > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return result


def _pixel_channels(pixels: Sequence[float], pixel_index: int, channels: int) -> tuple[float, float, float, float]:
    offset = pixel_index * channels
    red = _finite(pixels[offset], "pixels")
    green = _finite(pixels[offset + 1], "pixels")
    blue = _finite(pixels[offset + 2], "pixels")
    alpha = _finite(pixels[offset + 3], "pixels") if channels == 4 else 1.0
    return red, green, blue, alpha


def analyze_rgb_pixels(
    pixels: Sequence[float],
    *,
    channels: int = 4,
    highlight_threshold: float = DEFAULT_HIGHLIGHT_THRESHOLD,
    saturation_threshold: float = DEFAULT_SATURATION_THRESHOLD,
    warm_bias_threshold: float = DEFAULT_WARM_BIAS_THRESHOLD,
    warning_ratio: float = DEFAULT_WARNING_RATIO,
    max_samples: int = DEFAULT_MAX_SAMPLES,
) -> dict[str, Any]:
    """Measure bright saturated pixels and warm color bias in an image buffer.

    Pixel channels are expected to be normalized display-referred RGB values.
    The Blender bridge loads the rendered file as ``Non-Color`` so this check
    measures the encoded JPEG or PNG values against the 185/255 contract.
    """
    if channels not in (3, 4):
        raise ValueError("channels must be 3 or 4")
    highlight = _bounded(highlight_threshold, "highlight_threshold")
    saturation = _bounded(saturation_threshold, "saturation_threshold")
    warm_bias = _bounded(warm_bias_threshold, "warm_bias_threshold")
    warning = _bounded(warning_ratio, "warning_ratio")
    if isinstance(max_samples, bool) or not isinstance(max_samples, int) or max_samples < 1:
        raise ValueError("max_samples must be a positive integer")
    if len(pixels) % channels:
        raise ValueError("pixels length must be divisible by channels")

    total_pixels = len(pixels) // channels
    stride = max(1, math.ceil(total_pixels / max_samples))
    sampled_pixels = 0
    opaque_pixels = 0
    highlight_pixels = 0
    saturated_highlights = 0
    warm_highlights = 0
    warm_bias_sum = 0.0
    highlight_rgb_sum = [0.0, 0.0, 0.0]

    for pixel_index in range(0, total_pixels, stride):
        red, green, blue, alpha = _pixel_channels(pixels, pixel_index, channels)
        sampled_pixels += 1
        if alpha <= 0.0:
            continue
        opaque_pixels += 1
        maximum = max(red, green, blue)
        minimum = min(red, green, blue)
        if maximum < highlight:
            continue
        highlight_pixels += 1
        highlight_rgb_sum[0] += red
        highlight_rgb_sum[1] += green
        highlight_rgb_sum[2] += blue
        chroma = (maximum - minimum) / maximum if maximum > 0.0 else 0.0
        if chroma < saturation:
            continue
        saturated_highlights += 1
        bias = red - blue
        warm_bias_sum += bias
        pink_cast = red >= 0.75 and blue >= 0.55 and green + warm_bias <= min(red, blue)
        orange_cast = red >= green and bias >= warm_bias
        if orange_cast or pink_cast:
            warm_highlights += 1

    mean_highlight_rgb = [value / highlight_pixels for value in highlight_rgb_sum] if highlight_pixels else [0.0] * 3
    mean_warm_bias = warm_bias_sum / saturated_highlights if saturated_highlights else 0.0
    warm_ratio = warm_highlights / saturated_highlights if saturated_highlights else 0.0
    recommend_lower_key_energy = saturated_highlights > 0 and warm_ratio >= warning
    return {
        "analyzed_pixel_count": sampled_pixels,
        "opaque_pixel_count": opaque_pixels,
        "highlight_pixel_count": highlight_pixels,
        "highlight_pixel_ratio": highlight_pixels / opaque_pixels if opaque_pixels else 0.0,
        "saturated_highlight_count": saturated_highlights,
        "saturated_highlight_ratio": saturated_highlights / highlight_pixels if highlight_pixels else 0.0,
        "warm_highlight_count": warm_highlights,
        "warm_highlight_ratio": warm_ratio,
        "mean_highlight_rgb": mean_highlight_rgb,
        "mean_warm_bias": mean_warm_bias,
        "highlight_threshold": highlight,
        "saturation_threshold": saturation,
        "warm_bias_threshold": warm_bias,
        "warning_ratio": warning,
        "recommend_lower_key_energy": recommend_lower_key_energy,
        "recommendation": (
            "Lower the motivated key energy and rerender the preview. Preserve the material color."
            if recommend_lower_key_energy
            else "No warm saturated highlight bias was detected above the configured warning ratio."
        ),
        "material_color_mutated": False,
    }
