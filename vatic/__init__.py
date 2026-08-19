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
from typing import TYPE_CHECKING


try:  # noqa RUF067
    __version__ = version("vatic")
except PackageNotFoundError:
    __version__ = "unknown"


if TYPE_CHECKING:  # pragma: no cover - import-time only
    from vatic.app import main


__all__ = ["__version__", "main"]


def __getattr__(name: str) -> object:
    """Import the Qt entry point only when it is actually asked for.

    Importing it eagerly meant that ``import vatic.analytics`` pulled in the
    whole Qt stack, QtWebEngine included, so the numerical and theme modules
    could not be imported at all on a head-less machine without the system
    libraries Qt needs. They have no Qt dependency of their own, and now
    nothing forces one on them.

    Args:
        name: Attribute being looked up on the package.

    Returns:
        The requested attribute.

    Raises:
        AttributeError: If the name is not part of the public surface.
    """
    if name == "main":
        from vatic.app import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
