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
#      CLI entrypoint and Qt app bootstrap.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from vatic.logger import configure_logging, emit_startup_banner, get_logger
from vatic.resources import (
    app_icon,
    load_bundled_fonts,
    register_app_user_model_id,
)
from vatic.window import VaticWindow


LOGGER = get_logger(__name__)


def main() -> None:
    configure_logging()
    emit_startup_banner()
    LOGGER.debug("Launching vatic application | argv=%s", sys.argv)

    # Must run before the first window exists, otherwise Windows has already
    # bound the task bar button to the host interpreter's identity.
    register_app_user_model_id()

    app = QApplication(sys.argv)
    app.setApplicationName("vatic")
    app.setApplicationDisplayName("vatic")
    app.setOrganizationName("eggzec")
    app.setWindowIcon(app_icon())

    # Registered after QApplication exists but before any widget is
    # built, so the style sheet's font stack resolves to the bundled
    # family rather than a system fallback.
    load_bundled_fonts()

    window = VaticWindow()
    window.show()

    exit_code = app.exec()
    LOGGER.debug("vatic shutdown complete | exit_code=%s", exit_code)
    sys.exit(exit_code)
