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
#  Author(s)
#      Saud Zahir <m.saud.zahir@gmail.com>
#
#  Date
#      7 May 2026
#
#  Description
#      Brand palette, design tokens and the application style sheet.
#
# ----------------------------------------------------------------------------
#
#  The palette is deliberately closed: white plus the four hues taken from the
#  vatic banner. Every other value in this module is a tint (mixed toward
#  white) or a shade (mixed toward black) of one of those four hues, so the
#  whole interface stays inside the brand's hue family.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

from pathlib import Path

from vatic.logger import get_logger


LOGGER = get_logger(__name__)

# --------------------------------------------------------------- brand hues

WHITE = "#FFFFFF"
BLUE = "#2323FF"  # banner field      hue 240
VIOLET = "#7E3DFF"  # banner orb        hue 260
MAGENTA = "#C04AFF"  # banner highlight  hue 279
CYAN = "#24AEFF"  # banner spark      hue 202

BRAND_HUES = (BLUE, VIOLET, MAGENTA, CYAN)


def _channels(value: str) -> tuple[int, int, int]:
    """Split a ``#RRGGBB`` string into integer channels.

    Args:
        value: Hex colour string, with or without a leading hash.

    Returns:
        The red, green and blue channels.
    """
    raw = value.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def tint(colour: str, amount: float) -> str:
    """Mix ``colour`` toward white.

    Args:
        colour: Base hex colour.
        amount: Fraction of the base colour to keep, from 0.0 to 1.0.

    Returns:
        Hex string for the tinted colour.
    """
    r, g, b = _channels(colour)
    mixed = (
        round(r * amount + 255 * (1 - amount)),
        round(g * amount + 255 * (1 - amount)),
        round(b * amount + 255 * (1 - amount)),
    )
    return "#{:02X}{:02X}{:02X}".format(*mixed)


def shade(colour: str, amount: float) -> str:
    """Mix ``colour`` toward black.

    Args:
        colour: Base hex colour.
        amount: Fraction of the base colour to keep, from 0.0 to 1.0.

    Returns:
        Hex string for the shaded colour.
    """
    r, g, b = _channels(colour)
    return f"#{round(r * amount):02X}{round(g * amount):02X}{round(b * amount):02X}"


def alpha(colour: str, opacity: float) -> str:
    """Render ``colour`` as a Qt ``rgba()`` string.

    Qt reads eight digit hex as ``#AARRGGBB`` rather than CSS's ``#RRGGBBAA``,
    so transparency is always expressed as ``rgba()`` to avoid the ambiguity.

    Args:
        colour: Base hex colour.
        opacity: Alpha channel from 0.0 to 1.0.

    Returns:
        A Qt style sheet ``rgba(...)`` literal.
    """
    r, g, b = _channels(colour)
    return f"rgba({r}, {g}, {b}, {opacity:.3f})"


def _luminance(colour: str) -> float:
    """Return the WCAG relative luminance of ``colour``.

    Args:
        colour: Hex colour string.

    Returns:
        Relative luminance between 0.0 and 1.0.
    """

    def channel(value: int) -> float:
        srgb = value / 255
        if srgb <= 0.04045:
            return srgb / 12.92
        return ((srgb + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _channels(colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(foreground: str, background: str) -> float:
    """Return the WCAG contrast ratio between two colours.

    Args:
        foreground: Hex colour of the text or glyph.
        background: Hex colour behind it.

    Returns:
        Contrast ratio, from 1.0 to 21.0.
    """
    first, second = _luminance(foreground), _luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


# ------------------------------------------------------------------- tokens

#: Semantic design tokens. Each value is white, one of the four brand hues, or
#: a tint or shade of one of them, so the closed palette holds everywhere.
TOKENS: dict[str, str] = {
    # Surfaces. White dominates. The recessed washes are tints of CYAN, the
    # lightest hue in the logo, which keeps the whole interface airy.
    "surface.canvas": WHITE,
    "surface.panel": WHITE,
    "surface.sunken": tint(CYAN, 0.06),
    "surface.stripe": tint(CYAN, 0.04),
    "surface.hover": tint(CYAN, 0.14),
    "surface.pressed": tint(CYAN, 0.26),
    "surface.header": tint(CYAN, 0.05),
    # Ink. Deliberately the bright brand blue rather than a near-black navy,
    # so the interface reads light. Every step still clears WCAG AA on white.
    "ink.strong": shade(BLUE, 0.80),
    "ink.body": BLUE,
    "ink.muted": tint(BLUE, 0.834),
    "ink.placeholder": tint(BLUE, 0.834),
    # Cyan is only 2.45:1 on white, so anything sitting ON it needs deep ink.
    "ink.onAccent": shade(BLUE, 0.55),
    "ink.brand": BLUE,
    # Lines. Hairlines are decorative and may sit under 3:1, but a boundary
    # that carries meaning has to clear it, and no tint of cyan ever can.
    "border.hairline": tint(CYAN, 0.26),
    "border.subtle": tint(CYAN, 0.42),
    "border.strong": tint(BLUE, 0.42),
    "border.input": tint(BLUE, 0.55),
    "border.focus": BLUE,
    # Interaction. The primary action uses the lightest logo hue.
    "accent": CYAN,
    "accent.hover": shade(CYAN, 0.90),
    "accent.pressed": shade(CYAN, 0.78),
    "accent.wash": tint(CYAN, 0.16),
    "accent.violet": VIOLET,
    "accent.magenta": MAGENTA,
    "accent.cyan": CYAN,
    "selection.bg": CYAN,
    "selection.fg": shade(BLUE, 0.55),
    "selection.soft": tint(CYAN, 0.30),
}

#: Ordered categorical ramp for charts. Lightness is deliberately staggered so
#: the series stay separable for viewers with red-green colour deficiency,
#: where hue alone across four blue-to-magenta hues would not be enough.
CHART_SEQUENCE: tuple[str, ...] = (
    CYAN,
    BLUE,
    MAGENTA,
    shade(VIOLET, 0.62),
    tint(BLUE, 0.45),
    shade(MAGENTA, 0.60),
)

#: JetBrains Mono ships with the package under the SIL Open Font License, so
#: it leads the stack as a family that is actually present rather than a
#: hopeful first entry. The rest are safety nets for a checkout with the font
#: assets stripped out.
FONT_STACK = (
    '"JetBrains Mono", "Cascadia Mono", "Consolas", '
    '"DejaVu Sans Mono", monospace'
)
MONO_STACK = FONT_STACK


def audit_contrast() -> list[tuple[str, str, float]]:
    """Check every meaningful ink and surface pairing.

    Returns:
        Triples of foreground token, background token and contrast ratio,
        ordered worst first.
    """
    pairs = [
        ("ink.strong", "surface.panel"),
        ("ink.body", "surface.panel"),
        ("ink.body", "surface.stripe"),
        ("ink.body", "surface.sunken"),
        ("ink.body", "surface.hover"),
        ("ink.muted", "surface.panel"),
        ("ink.muted", "surface.sunken"),
        ("ink.placeholder", "surface.panel"),
        ("ink.brand", "surface.panel"),
        ("ink.brand", "surface.sunken"),
        ("ink.onAccent", "accent"),
        ("ink.body", "accent.wash"),
        ("ink.muted", "surface.hover"),
        ("selection.fg", "selection.bg"),
        ("ink.strong", "selection.soft"),
        ("border.input", "surface.panel"),
    ]
    report = [(fg, bg, contrast(TOKENS[fg], TOKENS[bg])) for fg, bg in pairs]
    report.sort(key=lambda row: row[2])
    return report


# ------------------------------------------------------------- style sheet

#: Qt style sheets have no vector primitives, so chevrons and the tick ship as
#: tiny SVGs. Paths are POSIX-style because Qt treats a backslash inside a
#: style sheet url() as an escape character.
_ASSETS = (Path(__file__).resolve().parent / "assets").as_posix()

_STYLE_SHEET = """
/* ----------------------------------------------------------- foundation */
QWidget {{
    background: {surface_canvas};
    color: {ink_body};
    font-family: {font};
    font-size: 10pt;
    selection-background-color: {selection_bg};
    selection-color: {selection_fg};
}}
QMainWindow, QDialog {{ background: {surface_canvas}; }}

/* ------------------------------------------------------------- menu bar */
QMenuBar {{
    background: {surface_canvas};
    border-bottom: 1px solid {border_hairline};
    padding: 2px 6px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
    margin: 2px;
    border-radius: 7px;
    color: {ink_body};
}}
QMenuBar::item:selected {{ background: {accent_wash}; color: {ink_brand}; }}
QMenuBar::item:pressed {{ background: {surface_pressed}; }}

QMenu {{
    background: {surface_panel};
    border: 1px solid {border_subtle};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 18px;
    border-radius: 7px;
    color: {ink_body};
}}
QMenu::item:selected {{ background: {accent}; color: {ink_on_accent}; }}
QMenu::item:disabled {{ color: {ink_muted}; }}
QMenu::separator {{
    height: 1px;
    background: {border_hairline};
    margin: 5px 8px;
}}

/* --------------------------------------------------------------- panels */
QGroupBox {{
    background: {surface_panel};
    border: 1px solid {border_hairline};
    border-radius: 12px;
    margin-top: 15px;
    padding: 14px 12px 12px 12px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: {ink_muted};
    font-size: 8pt;
    font-weight: 700;
}}

/* --------------------------------------------------------------- labels */
QLabel {{ background: transparent; color: {ink_body}; }}
QLabel#brandWordmark {{
    color: {ink_strong};
    font-size: 15pt;
    font-weight: 700;
}}
QLabel#brandTagline {{ color: {ink_muted}; font-size: 8pt; font-weight: 600; }}
QLabel#sectionTitle {{
    color: {ink_muted};
    font-size: 8pt;
    font-weight: 700;
}}
QLabel#analysisName {{
    color: {ink_brand};
    font-size: 11pt;
    font-weight: 700;
}}
QLabel#metaLabel {{ color: {ink_muted}; font-size: 9pt; }}
QLabel#statsCard {{
    background: {surface_sunken};
    border: 1px solid {border_hairline};
    border-radius: 12px;
    padding: 14px 16px;
    color: {ink_body};
    font-family: {mono};
    font-size: 9pt;
}}
QLabel#emptyState {{ color: {ink_muted}; font-size: 10pt; }}

/* --------------------------------------------------------------- inputs */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {surface_panel};
    border: 1px solid {border_input};
    border-radius: 9px;
    padding: 7px 11px;
    color: {ink_body};
    min-height: 18px;
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {ink_muted}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border: 2px solid {border_focus};
    padding: 6px 10px;
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    background: {surface_sunken};
    color: {ink_muted};
    border-color: {border_subtle};
}}

QComboBox {{ padding-right: 32px; }}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 28px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    image: url({assets}/chevron-down.svg);
    width: 14px;
    height: 14px;
}}
QComboBox::down-arrow:disabled {{
    image: url({assets}/chevron-down-muted.svg);
}}
QComboBox QAbstractItemView {{
    background: {surface_panel};
    border: 1px solid {border_subtle};
    border-radius: 10px;
    padding: 5px;
    outline: none;
    selection-background-color: {accent};
    selection-color: {ink_on_accent};
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    border-radius: 6px;
    min-height: 20px;
}}

/* Editors embedded in table cells must fit the row, so they drop the
   standalone control's generous padding and minimum height. */
QTableWidget QComboBox, QTableView QComboBox,
QTableWidget QLineEdit, QTableView QLineEdit,
QTableWidget QSpinBox, QTableView QSpinBox {{
    min-height: 0;
    padding: 2px 8px;
    border-radius: 6px;
    border: 1px solid {border_hairline};
    background: {surface_panel};
}}
QTableWidget QComboBox {{ padding-right: 26px; }}
QTableWidget QComboBox:hover, QTableView QComboBox:hover {{
    border-color: {accent};
}}
QTableWidget QComboBox::drop-down, QTableView QComboBox::drop-down {{
    width: 22px;
}}
QTableWidget QComboBox::down-arrow, QTableView QComboBox::down-arrow {{
    width: 12px;
    height: 12px;
}}

QSpinBox, QDoubleSpinBox {{ padding-right: 28px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 24px;
    height: 15px;
    border: none;
    background: transparent;
    margin-right: 4px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 24px;
    height: 15px;
    border: none;
    background: transparent;
    margin-right: 4px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({assets}/chevron-up.svg);
    width: 11px;
    height: 11px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({assets}/chevron-down.svg);
    width: 11px;
    height: 11px;
}}

QCheckBox, QRadioButton {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 17px;
    height: 17px;
    border: 1px solid {border_input};
    background: {surface_panel};
}}
QCheckBox::indicator {{ border-radius: 5px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: url({assets}/check.svg);
}}
QRadioButton::indicator:checked {{
    border: 1px solid {accent};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
        fx:0.5, fy:0.5,
        stop:0 {accent}, stop:0.55 {accent},
        stop:0.6 {surface_panel}, stop:1 {surface_panel});
}}

/* -------------------------------------------------------------- buttons */
QPushButton {{
    background: {surface_panel};
    border: 1px solid {border_input};
    border-radius: 9px;
    padding: 8px 16px;
    color: {ink_brand};
    font-weight: 600;
    min-height: 18px;
}}
QPushButton:hover {{ background: {accent_wash}; border-color: {accent}; }}
QPushButton:pressed {{ background: {surface_pressed}; }}
QPushButton:disabled {{
    background: {surface_sunken};
    color: {ink_muted};
    border-color: {border_subtle};
}}

QPushButton[variant="primary"] {{
    background: {accent};
    border: 1px solid {accent};
    color: {ink_on_accent};
    padding: 9px 22px;
    font-weight: 700;
}}
QPushButton[variant="primary"]:hover {{
    background: {accent_hover};
    border-color: {accent_hover};
}}
QPushButton[variant="primary"]:pressed {{ background: {accent_pressed}; }}
QPushButton[variant="primary"]:disabled {{
    background: {border_subtle};
    border-color: {border_subtle};
    color: {surface_panel};
}}

QPushButton[variant="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {ink_muted};
    padding: 7px 12px;
}}
QPushButton[variant="ghost"]:hover {{
    background: {accent_wash};
    color: {ink_brand};
}}

QPushButton[calcKey="true"] {{
    background: {surface_sunken};
    border: 1px solid {border_hairline};
    border-radius: 8px;
    color: {ink_brand};
    font-family: {mono};
    font-size: 9pt;
    font-weight: 600;
    padding: 6px 4px;
}}
QPushButton[calcKey="true"]:hover {{
    background: {accent_wash};
    border-color: {accent};
}}
QPushButton[calcKey="true"]:pressed {{
    background: {accent};
    color: {ink_on_accent};
}}
QPushButton[calcKey="fn"] {{
    background: {surface_sunken};
    border: 1px solid {border_hairline};
    border-radius: 8px;
    color: {accent_violet};
    font-family: {mono};
    font-size: 9pt;
    font-weight: 600;
    padding: 6px 4px;
}}
QPushButton[calcKey="fn"]:hover {{
    background: {accent_wash};
    border-color: {accent_violet};
}}
QPushButton[calcKey="edit"] {{
    background: {surface_sunken};
    border: 1px solid {border_hairline};
    border-radius: 8px;
    color: {accent_magenta};
    font-family: {mono};
    font-size: 9pt;
    font-weight: 700;
    padding: 6px 4px;
}}
QPushButton[calcKey="edit"]:hover {{
    background: {accent_wash};
    border-color: {accent_magenta};
}}

/* --------------------------------------------------------------- tables */
QTableWidget, QTableView {{
    background: {surface_panel};
    alternate-background-color: {surface_stripe};
    gridline-color: {border_hairline};
    border: 1px solid {border_hairline};
    border-radius: 10px;
    color: {ink_body};
    outline: none;
}}
QTableWidget::item, QTableView::item {{ padding: 5px 7px; border: none; }}
QTableWidget::item:selected, QTableView::item:selected {{
    background: {selection_soft};
    color: {ink_strong};
}}

QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {surface_panel};
    color: {ink_muted};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {border_subtle};
    font-size: 8pt;
    font-weight: 700;
}}
QHeaderView::section:horizontal {{ border-right: 1px solid {border_hairline}; }}
QHeaderView::section:vertical {{
    border-right: 1px solid {border_hairline};
    border-bottom: 1px solid {border_hairline};
    padding: 4px 6px;
    font-weight: 600;
}}
QHeaderView::section:hover {{ color: {ink_brand}; }}
QTableCornerButton::section {{
    background: {surface_panel};
    border: none;
    border-bottom: 1px solid {border_subtle};
    border-right: 1px solid {border_hairline};
}}

/* ---------------------------------------------------------------- lists */
QListWidget, QListView, QTreeView {{
    background: {surface_panel};
    border: 1px solid {border_hairline};
    border-radius: 10px;
    padding: 5px;
    outline: none;
    color: {ink_body};
}}
QListWidget::item, QListView::item {{
    padding: 8px 10px;
    border-radius: 7px;
    margin: 1px 0;
}}
QListWidget::item:hover {{ background: {accent_wash}; }}
QListWidget::item:selected {{ background: {accent}; color: {ink_on_accent}; }}

/* ---------------------------------------------------------- scroll bars */
QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 3px 2px 3px 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 0 3px 2px;
}}
QScrollBar::handle:vertical {{
    background: {border_strong};
    border-radius: 5px;
    min-height: 34px;
}}
QScrollBar::handle:horizontal {{
    background: {border_strong};
    border-radius: 5px;
    min-width: 34px;
}}
QScrollBar::handle:hover {{ background: {ink_muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
    border: none;
    background: transparent;
}}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* -------------------------------------------------------------- chrome  */
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 9px; }}
QSplitter::handle:vertical {{ height: 9px; }}
QSplitter::handle:hover {{ background: {accent_wash}; }}

QStatusBar {{
    background: {surface_canvas};
    border-top: 1px solid {border_hairline};
    color: {ink_muted};
    padding: 2px 8px;
}}
QStatusBar::item {{ border: none; }}

QToolTip {{
    background: {ink_strong};
    color: {surface_panel};
    border: none;
    border-radius: 7px;
    padding: 6px 9px;
}}

QDialogButtonBox QPushButton {{ min-width: 84px; }}
QMessageBox {{ background: {surface_panel}; }}
QMessageBox QLabel {{ color: {ink_body}; }}

QProgressBar {{
    background: {surface_sunken};
    border: none;
    border-radius: 5px;
    height: 8px;
    text-align: center;
    color: {ink_brand};
    font-size: 8pt;
}}
QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}

QSlider::groove:horizontal {{
    background: {surface_pressed};
    height: 5px;
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    background: {surface_panel};
    border: 2px solid {accent};
    width: 13px;
    height: 13px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{ border-color: {accent_magenta}; }}

/* ------------------------------------------------- named layout regions */
QWidget#appHeader {{
    background: {surface_panel};
    border-bottom: 1px solid {border_hairline};
}}
QWidget#keypadPanel {{
    background: {surface_sunken};
    border: 1px solid {border_hairline};
    border-radius: 12px;
}}
QWidget#chartToolbar {{
    background: {surface_panel};
    border: 1px solid {border_hairline};
    border-radius: 12px;
}}
QWidget#chartFrame {{
    background: {surface_panel};
    border: 1px solid {border_hairline};
    border-radius: 12px;
}}
"""


def build_stylesheet() -> str:
    """Render the application style sheet from the design tokens.

    Returns:
        A Qt style sheet string ready to hand to ``setStyleSheet``.
    """
    values = {key.replace(".", "_"): value for key, value in TOKENS.items()}
    values["ink_on_accent"] = TOKENS["ink.onAccent"]
    values["font"] = FONT_STACK
    values["mono"] = MONO_STACK
    values["assets"] = _ASSETS
    return _STYLE_SHEET.format(**values)
