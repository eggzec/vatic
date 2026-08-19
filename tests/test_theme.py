# -------------------------------------*- vatic -*----------------------------
#                               Open Source Risk Analysis
#
#                             Copyright (c) 2026, eggzec
#                          Contact: https://eggzec.github.io/
#
#                         License: GNU General Public License
#                              Version 3, 29 June 2007
#
# ----------------------------------------------------------------------------
#
#  Description
#      Guards the brand rules: a closed palette taken from the logo, and
#      legible contrast everywhere text meets a surface.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import colorsys
import re
from pathlib import Path

import pytest

from vatic.theme import (
    BRAND_HUES,
    TOKENS,
    audit_contrast,
    build_stylesheet,
    contrast,
    shade,
    tint,
)


#: Hue angle of each logo colour, in degrees.
BRAND_HUE_ANGLES = (240.0, 260.0, 279.0, 202.0)
HUE_TOLERANCE = 10.0


def _channel_spread(colour: str) -> int:
    """Return how far apart a colour's channels are.

    A near-white such as ``#FAFBFD`` reports a high HLS saturation despite
    being visually neutral, so neutrality is judged on the raw spread.

    Args:
        colour: Hex colour string.

    Returns:
        The difference between the largest and smallest channel, 0..255.
    """
    raw = colour.lstrip("#")
    channels = [int(raw[i : i + 2], 16) for i in (0, 2, 4)]
    return max(channels) - min(channels)


def _hue_and_saturation(colour: str) -> tuple[float, float]:
    """Return the hue angle and saturation of a hex colour.

    Args:
        colour: Hex colour string.

    Returns:
        Hue in degrees and saturation from 0.0 to 1.0.
    """
    raw = colour.lstrip("#")
    red, green, blue = (int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4))
    hue, _lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    return hue * 360.0, saturation


#: Tokens that carry brand identity and must therefore sit on a logo hue.
BRAND_TOKENS = (
    "accent",
    "accent.violet",
    "accent.magenta",
    "accent.cyan",
    "border.focus",
    "ink.brand",
    "selection.bg",
    "wash.cyan",
    "wash.blue",
    "wash.violet",
    "wash.magenta",
)


@pytest.mark.parametrize("name", BRAND_TOKENS)
def test_brand_tokens_sit_on_a_logo_hue(name: str) -> None:
    """Anything that carries identity uses a colour from the logo."""
    hue, saturation = _hue_and_saturation(TOKENS[name])
    assert saturation > 0.05, f"{name} is not a colour at all"
    assert any(
        abs(hue - angle) < HUE_TOLERANCE for angle in BRAND_HUE_ANGLES
    ), f"{name}={TOKENS[name]} has hue {hue:.0f}, outside the logo palette"


@pytest.mark.parametrize(
    "name",
    [
        "ink.strong",
        "ink.body",
        "ink.muted",
        "ink.placeholder",
        "surface.sunken",
        "surface.stripe",
        "border.hairline",
        "border.subtle",
    ],
)
def test_text_and_surfaces_are_neutral(name: str) -> None:
    """Ink and paper stay neutral so text is easy to read.

    Saturated blue body text passes the contrast threshold but is tiring
    over a long session and competes with the accents, so the ink scale is
    a cool near-black rather than the brand blue.
    """
    assert _channel_spread(TOKENS[name]) <= 40, (
        f"{name}={TOKENS[name]} is too colourful for text or paper"
    )


def test_body_ink_is_high_contrast() -> None:
    """Body text is comfortably past the AA threshold, not just over it."""
    assert contrast(TOKENS["ink.body"], TOKENS["surface.panel"]) > 12.0


def test_background_is_white() -> None:
    """White is the dominant surface, not a tinted near-white."""
    assert TOKENS["surface.canvas"] == "#FFFFFF"
    assert TOKENS["surface.panel"] == "#FFFFFF"


def test_every_audited_pairing_meets_wcag_aa() -> None:
    """Text clears 4.5:1 and meaningful borders clear 3:1."""
    failures = [
        (foreground, background, ratio)
        for foreground, background, ratio in audit_contrast()
        if ratio < (3.0 if foreground.startswith("border") else 4.5)
    ]
    assert not failures, f"contrast failures: {failures}"


def test_accent_is_a_logo_hue() -> None:
    """The primary action is painted in a colour from the icon."""
    assert TOKENS["accent"] in BRAND_HUES


def test_accent_works_as_a_fill_and_as_text() -> None:
    """The accent is legible under white text and as text on white.

    Only the brand blue satisfies both: cyan is 2.45:1 on white and cannot
    carry a white label, and magenta clears neither threshold for body text.
    """
    assert contrast(TOKENS["ink.onAccent"], TOKENS["accent"]) >= 4.5
    assert contrast(TOKENS["accent"], TOKENS["surface.panel"]) >= 4.5


def test_panel_washes_are_light() -> None:
    """Every panel wash stays close to white so the app reads bright."""
    for name in ("wash.cyan", "wash.blue", "wash.violet", "wash.magenta"):
        assert contrast(TOKENS[name], "#FFFFFF") < 1.35, name


def test_tint_and_shade_are_monotonic() -> None:
    """Tinting moves toward white and shading moves away from it."""
    base = TOKENS["accent"]
    assert contrast(tint(base, 0.2), "#FFFFFF") < contrast(base, "#FFFFFF")
    assert contrast(shade(base, 0.5), "#FFFFFF") > contrast(base, "#FFFFFF")


def test_stylesheet_has_no_unresolved_placeholders() -> None:
    """Every token referenced by the style sheet is defined."""
    sheet = build_stylesheet()
    leftovers = re.findall(r"\{[a-zA-Z_]+\}", sheet)
    assert not leftovers, f"unsubstituted tokens: {sorted(set(leftovers))}"


def test_stylesheet_uses_rgba_not_eight_digit_hex() -> None:
    """Qt reads #AARRGGBB, so an eight digit hex is almost always a bug."""
    sheet = build_stylesheet()
    assert not re.findall(r"#[0-9A-Fa-f]{8}\b", sheet)


def test_stylesheet_icon_assets_exist() -> None:
    """Every url() the style sheet points at is actually shipped."""
    sheet = build_stylesheet()
    for path in re.findall(r"url\(([^)]+)\)", sheet):
        assert Path(path).exists(), path
