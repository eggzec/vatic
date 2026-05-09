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
# ----------------------------------------------------------------------------

from __future__ import annotations

import logging
import os
import sys
import traceback
import warnings
from logging.handlers import RotatingFileHandler

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text

from vatic.about import INFO_TEXT


# **************** Logger ****************

LOGGER = logging.getLogger("vatic")
LOG_FILE = "vatic.log"
_BANNER_PRINTED = False

file_formatter = logging.Formatter(
    "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%d-%m-%Y %H:%M:%S",
)
rich_formatter = logging.Formatter("%(message)s")


def _debug_enabled() -> bool:
    return "--debug" in sys.argv or os.getenv("DEBUG", "").lower() in {
        "1",
        "true",
        "yes",
    }


def __warning_handler(
    message, category, filename, lineno, file=None, line=None
) -> None:
    if _debug_enabled():
        warnings.filterwarnings("always")
        WARN(f"{filename}:{lineno}: {category.__name__}: {message}")
    else:
        warnings.filterwarnings("ignore")
        WARN(f"{category.__name__}: {message}")


def __exception_handler(exc_type, exc_value, exc_traceback) -> None:
    if _debug_enabled():
        error_lines = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )
        for error_line in error_lines.split("\n"):
            if error_line.strip():
                ERROR(error_line, exit=False)
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    else:
        ERROR(f"{exc_type.__name__}: {exc_value}", exit=False)


def configure_logging() -> None:
    if LOGGER.handlers:
        return

    stdout_handler = RichHandler(
        rich_tracebacks=True, show_path=False, console=Console()
    )
    stdout_handler.setLevel(logging.DEBUG if _debug_enabled() else logging.INFO)
    stdout_handler.addFilter(lambda record: record.levelno < logging.ERROR)
    stdout_handler.setFormatter(rich_formatter)
    LOGGER.addHandler(stdout_handler)

    stderr_handler = RichHandler(
        rich_tracebacks=True, show_path=False, console=Console(stderr=True)
    )
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(rich_formatter)
    LOGGER.addHandler(stderr_handler)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    LOGGER.addHandler(file_handler)

    LOGGER.setLevel(logging.DEBUG)
    LOGGER.propagate = False

    warnings.showwarning = __warning_handler
    sys.excepthook = __exception_handler


def get_logger(name: str | None = None) -> logging.Logger:
    if not name:
        return LOGGER
    if "vatic" in name:
        return logging.getLogger(name)
    return LOGGER.getChild(name)


def emit_startup_banner() -> None:
    global _BANNER_PRINTED
    if _BANNER_PRINTED:
        return

    Console()
    banner = Text(
        """\
██╗   ██╗ █████╗ ████████╗██╗ ██████╗
██║   ██║██╔══██╗╚══██╔══╝██║██╔════╝
██║   ██║███████║   ██║   ██║██║
╚██╗ ██╔╝██╔══██║   ██║   ██║██║
 ╚████╔╝ ██║  ██║   ██║   ██║╚██████╗
  ╚═══╝  ╚═╝  ╚═╝   ╚═╝   ╚═╝ ╚═════╝""",
        style="bold white on black",
    )
    panel_content = Text.assemble(banner)

    LOGGER.info("\n")
    [
        LOGGER.info(line)
        for line in str(
            Panel.fit(panel_content, border_style="bright_white").renderable
        ).split("\n")
    ]
    [LOGGER.info(line) for line in INFO_TEXT.split("\n")]
    _BANNER_PRINTED = True


def DEBUG(*args) -> None:
    LOGGER.debug(" ".join(map(str, args)))


def INFO(*args) -> None:
    LOGGER.info(" ".join(map(str, args)))


def WARN(*args) -> None:
    LOGGER.warning(" ".join(map(str, args)))


def ERROR(*args, exit: bool = True) -> None:
    LOGGER.error(" ".join(map(str, args)))
    if exit:
        LOGGER.error("For more info contact: https://eggzec.github.io/")
        sys.exit(1)
