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
#      The Microsoft Excel link.
#
# ----------------------------------------------------------------------------
#
#  Importing this package is safe on every platform: the error types and the
#  availability check carry no COM dependency, so the window can ask whether a
#  spreadsheet run is possible without pywin32 being installed. The session and
#  the runner import COM lazily, and only on Windows.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

from typing import TYPE_CHECKING

from vatic.excel.errors import (
    CellResolutionError,
    CircularReferenceError,
    ExcelBusyError,
    ExcelLinkError,
    ExcelNotAvailableError,
    SheetProtectedError,
    SimulationCancelled,
    VolatileModelError,
    WorkbookNotFoundError,
    WorkbookReadOnlyError,
    describe_error_value,
    is_error_value,
)
from vatic.excel.session import excel_available


if TYPE_CHECKING:  # pragma: no cover - import-time only
    from vatic.excel.runner import ExcelRunner
    from vatic.excel.session import ExcelSession


__all__ = [
    "CellResolutionError",
    "CircularReferenceError",
    "ExcelBusyError",
    "ExcelLinkError",
    "ExcelNotAvailableError",
    "ExcelRunner",
    "ExcelSession",
    "SheetProtectedError",
    "SimulationCancelled",
    "VolatileModelError",
    "WorkbookNotFoundError",
    "WorkbookReadOnlyError",
    "describe_error_value",
    "excel_available",
    "is_error_value",
]


def __getattr__(name: str) -> object:
    """Import the COM-backed classes only when they are actually used.

    Args:
        name: Attribute being looked up.

    Returns:
        The requested class.

    Raises:
        AttributeError: If the name is not part of the public surface.
    """
    if name == "ExcelSession":
        from vatic.excel.session import ExcelSession

        return ExcelSession
    if name == "ExcelRunner":
        from vatic.excel.runner import ExcelRunner

        return ExcelRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
