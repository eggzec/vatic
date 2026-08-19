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
#      Bundled brand assets and the application icon.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFontDatabase, QIcon, QPainter, QPainterPath, QPixmap

from vatic.logger import get_logger


LOGGER = get_logger(__name__)

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

#: Raster sizes shipped alongside the vector logo. Qt picks the closest one for
#: window decorations, alt-tab and the task bar, so the small hand-tuned sizes
#: matter more than the large ones.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)

#: Windows uses the AppUserModelID to group task bar buttons and to decide which
#: icon to show there. Without it a ``python.exe``-hosted app inherits the
#: interpreter's icon no matter what ``setWindowIcon`` says.
APP_USER_MODEL_ID = "eggzec.vatic.RiskAnalysis"


def asset_path(name: str) -> Path:
    """Return the absolute path of a bundled asset.

    Args:
        name: File name relative to the package ``assets`` directory.

    Returns:
        Absolute path to the asset, which may not exist.
    """
    return ASSETS_DIR / name


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """Build the application icon from every bundled resolution.

    Returns:
        A multi-resolution icon, or an empty icon when no asset is bundled.
    """
    icon = QIcon()
    for size in ICON_SIZES:
        candidate = asset_path(f"vatic-icon-{size}.png")
        if candidate.exists():
            icon.addFile(str(candidate))

    if icon.isNull():
        fallback = asset_path("vatic-icon.png")
        if fallback.exists():
            icon.addFile(str(fallback))

    if icon.isNull():
        LOGGER.warning("No bundled application icon found in %s", ASSETS_DIR)
    else:
        LOGGER.debug(
            "Loaded application icon | sizes=%s",
            [f"{s.width()}x{s.height()}" for s in icon.availableSizes()],
        )
    return icon


def logo_pixmap(height: int) -> QPixmap:
    """Return the logo scaled to ``height`` for use as an in-app brand mark.

    Args:
        height: Target height in device-independent pixels.

    Returns:
        A square pixmap, or a null pixmap when no asset is bundled.
    """
    pixmap = app_icon().pixmap(height, height)
    if pixmap.isNull():
        LOGGER.warning("Logo pixmap unavailable at height=%s", height)
    return pixmap


def rounded_logo_pixmap(size: int, radius: int = 7) -> QPixmap:
    """Return the logo as a rounded square for use on light chrome.

    The mark is a full-bleed electric-blue square, which reads as an
    unfinished screenshot when dropped straight onto a white surface. Rounding
    the corners makes it read as a deliberate app icon instead.

    Args:
        size: Edge length in device-independent pixels.
        radius: Corner radius in device-independent pixels.

    Returns:
        A rounded pixmap, or a null pixmap when no asset is bundled.
    """
    source = app_icon().pixmap(size, size)
    if source.isNull():
        return source

    ratio = source.devicePixelRatio() or 1.0
    rounded = QPixmap(source.size())
    rounded.setDevicePixelRatio(ratio)
    rounded.fill(Qt.transparent)

    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), float(radius), float(radius))
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, size, size, source)
    painter.end()
    return rounded


#: Weights bundled under the SIL Open Font License (see assets/fonts/OFL.txt).
FONT_FILES = (
    "JetBrainsMono-Regular.ttf",
    "JetBrainsMono-Medium.ttf",
    "JetBrainsMono-SemiBold.ttf",
    "JetBrainsMono-Bold.ttf",
)


@lru_cache(maxsize=1)
def load_bundled_fonts() -> tuple[str, ...]:
    """Register the bundled JetBrains Mono weights with Qt.

    Shipping the font means the interface looks the same on machines that do
    not have it installed, instead of silently falling back.

    Returns:
        The font family names Qt registered, empty when none could be loaded.
    """
    families: list[str] = []
    for name in FONT_FILES:
        path = ASSETS_DIR / "fonts" / name
        if not path.exists():
            LOGGER.debug("Bundled font missing | file=%s", name)
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id == -1:
            LOGGER.warning("Qt rejected bundled font | file=%s", name)
            continue
        families.extend(QFontDatabase.applicationFontFamilies(font_id))

    unique = tuple(dict.fromkeys(families))
    if unique:
        LOGGER.debug("Registered bundled fonts | families=%s", list(unique))
    else:
        LOGGER.warning("No bundled fonts registered; falling back to system")
    return unique


def register_app_user_model_id() -> None:
    """Tell Windows this process is vatic so the task bar shows our icon.

    No-op on every platform other than Windows, and on Windows failures are
    swallowed because an unset identifier only degrades the task bar icon.
    """
    if sys.platform != "win32":
        return

    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except (AttributeError, OSError) as exc:
        LOGGER.debug("Could not set AppUserModelID | error=%s", exc)
    else:
        LOGGER.debug("AppUserModelID set | id=%s", APP_USER_MODEL_ID)
