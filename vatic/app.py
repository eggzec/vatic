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
from vatic.window import VaticWindow


LOGGER = get_logger(__name__)


def main() -> None:
    configure_logging()
    emit_startup_banner()
    LOGGER.debug("Launching vatic application | argv=%s", sys.argv)

    app = QApplication(sys.argv)
    app.setApplicationName("vatic")

    window = VaticWindow()
    window.show()

    exit_code = app.exec()
    LOGGER.debug("vatic shutdown complete | exit_code=%s", exit_code)
    sys.exit(exit_code)
