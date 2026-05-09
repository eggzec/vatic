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

from importlib.metadata import PackageNotFoundError, version


try:  # noqa RUF067
    __version__ = version("vatic")
except PackageNotFoundError:
    __version__ = "unknown"

from vatic.app import main


__all__ = ["__version__", "main"]
