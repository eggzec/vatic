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


#: The highlight is white text on the lightest logo hue, which measures
#: 2.45:1. That is below the WCAG AA threshold and is a deliberate product
#: decision, recorded here as a single named exception so the contrast guards
#: keep protecting every other pairing instead of being switched off.
SELECTION_EXCEPTION = ("#FFFFFF", "#24AEFF")


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
        and (foreground, background) != ("selection.fg", "selection.bg")
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


def test_no_rule_paints_light_text_on_a_light_background() -> None:
    """No style sheet rule may set an unreadable colour pair.

    The token audit only covers pairs the palette declares. This walks the
    generated style sheet itself and checks every rule that sets both a
    colour and a background, which is how a white-on-near-white disabled
    button slipped through.
    """
    sheet = build_stylesheet()
    failures = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", sheet):
        foreground = re.search(
            r"(?<!-)\bcolor\s*:\s*(#[0-9A-Fa-f]{6})\s*;", body
        )
        background = re.search(
            r"\bbackground(?:-color)?\s*:\s*(#[0-9A-Fa-f]{6})\s*;", body
        )
        if not foreground or not background:
            continue
        pair = (foreground.group(1).upper(), background.group(1).upper())
        if pair == SELECTION_EXCEPTION:
            continue
        ratio = contrast(foreground.group(1), background.group(1))
        if ratio < 3.0:
            failures.append((
                selector.strip(),
                foreground.group(1),
                background.group(1),
                round(ratio, 2),
            ))
    assert not failures, f"unreadable style sheet rules: {failures}"


def test_selection_colours_are_readable_in_every_rule() -> None:
    """Wherever a selection colour pair is set, it must be legible.

    An item view draws cell text through its delegate, which uses
    ``selection-color`` rather than the ``::item:selected`` rule. A rule that
    changes the selection background without changing the text colour to
    match leaves white text on a pale row.
    """
    sheet = build_stylesheet()
    failures = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", sheet):
        background = re.search(
            r"selection-background-color\s*:\s*(#[0-9A-Fa-f]{6})\s*;", body
        )
        foreground = re.search(
            r"selection-color\s*:\s*(#[0-9A-Fa-f]{6})\s*;", body
        )
        if not background:
            continue
        assert foreground, (
            f"{selector.strip()} sets a selection background but no "
            "selection-color, so the text colour is inherited and may not "
            "suit it"
        )
        pair = (foreground.group(1).upper(), background.group(1).upper())
        if pair == SELECTION_EXCEPTION:
            continue
        ratio = contrast(foreground.group(1), background.group(1))
        if ratio < 4.5:
            failures.append((
                selector.strip(),
                foreground.group(1),
                background.group(1),
                round(ratio, 2),
            ))
    assert not failures, f"unreadable selections: {failures}"


def test_the_highlight_is_the_lightest_logo_hue() -> None:
    """The highlight uses the light colour from the icon, with white text."""
    from vatic.theme import _luminance

    assert TOKENS["selection.bg"] == max(BRAND_HUES, key=_luminance)
    assert TOKENS["selection.fg"] == "#FFFFFF"


def test_every_selection_surface_uses_the_same_highlight() -> None:
    """Tables, lists and menus all highlight the same way.

    They were previously painted three different ways, one of which put
    white text on a near-white row.
    """
    sheet = build_stylesheet()
    highlight = TOKENS["selection.bg"].upper()
    surfaces = (
        "QTableWidget::item:selected",
        "QListWidget::item:selected",
        "QMenu::item:selected",
    )
    for name in surfaces:
        block = re.search(re.escape(name) + r"[^{]*\{([^}]*)\}", sheet)
        assert block, f"no rule found for {name}"
        assert highlight in block.group(1).upper(), (
            f"{name} does not use the shared highlight"
        )


def test_white_text_never_sits_on_a_light_fill() -> None:
    """White is the colour of text on a highlight, never text on paper."""
    sheet = build_stylesheet()
    offenders = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", sheet):
        foreground = re.search(
            r"(?<!-)\bcolor\s*:\s*(#[0-9A-Fa-f]{6})\s*;", body
        )
        background = re.search(
            r"\bbackground(?:-color)?\s*:\s*(#[0-9A-Fa-f]{6})\s*;", body
        )
        if not foreground or not background:
            continue
        if foreground.group(1).upper() != "#FFFFFF":
            continue
        if contrast("#FFFFFF", background.group(1)) < 2.0:
            offenders.append((selector.strip(), background.group(1)))
    assert not offenders, f"white text on a light fill: {offenders}"


def test_the_recorded_exception_still_matches_the_palette() -> None:
    """The exception must describe the colours it actually excuses.

    If the highlight changes, this fails and forces the exception to be
    re-examined rather than silently covering a different pair.
    """
    assert SELECTION_EXCEPTION == (
        TOKENS["selection.fg"].upper(),
        TOKENS["selection.bg"].upper(),
    )
    assert contrast(*SELECTION_EXCEPTION) == pytest.approx(2.45, abs=0.05)


def test_combo_popup_paints_its_own_item_states() -> None:
    """The drop-down's rows must paint their own selected and hover states.

    Styling ``::item`` gives the popup's rows their own box model, at which
    point the view's ``selection-background-color`` stops painting them while
    ``selection-color`` still applies. The row under the cursor then drew
    white text on a white row and vanished, so both states have to be stated.
    """
    sheet = build_stylesheet()
    highlight = TOKENS["selection.bg"].upper()

    item_rule = re.search(
        r"QComboBox QAbstractItemView::item\s*\{([^}]*)\}", sheet
    )
    assert item_rule, "the popup's items are not styled at all"

    states = re.search(
        r"QComboBox QAbstractItemView::item:selected[^{]*\{([^}]*)\}", sheet
    )
    assert states, "the popup's items have no selected state"
    body = states.group(1).upper()
    assert highlight in body, "the popup does not use the shared highlight"
    assert "#FFFFFF" in body, "the popup's highlighted text is not white"


def test_every_item_view_state_is_readable() -> None:
    """No item-view state may leave text the same colour as its row."""
    sheet = build_stylesheet()
    offenders = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", sheet):
        if "::item" not in selector:
            continue
        background = re.search(
            r"\bbackground(?:-color)?\s*:\s*(#[0-9A-Fa-f]{6})\s*;", body
        )
        foreground = re.search(
            r"(?<!-)\bcolor\s*:\s*(#[0-9A-Fa-f]{6})\s*;", body
        )
        if not background or not foreground:
            continue
        pair = (foreground.group(1).upper(), background.group(1).upper())
        if pair == SELECTION_EXCEPTION:
            continue
        if contrast(*pair) < 4.5:
            offenders.append((
                selector.strip(),
                *pair,
                round(contrast(*pair), 2),
            ))
    assert not offenders, f"unreadable item states: {offenders}"
