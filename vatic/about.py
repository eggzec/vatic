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


try:
    __version__ = version("vatic")
except PackageNotFoundError:
    __version__ = "unknown"

INFO_TEXT = (
    "vatic\n"
    f"v{__version__}\n\n"
    "Open Source Risk Analysis\n\n"
    "License: GNU General Public License\n"
    "Version 3, 29 June 2007\n\n"
    "Copyright (c) 2026, eggzec\n\n"
    "For more info see:\n"
    "https://eggzec.github.io/"
)
