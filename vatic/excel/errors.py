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
#      Typed failures for the Excel link, and the worksheet error decoder.
#
# ----------------------------------------------------------------------------
#
#  Pure Python and pure integers: this module imports no COM, so it can be
#  tested on any platform and imported by the UI to render a message without
#  pulling pywin32 in.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

from vatic.logger import get_logger


LOGGER = get_logger(__name__)


class ExcelLinkError(Exception):
    """Base class for every failure raised by the Excel link."""

    #: Shown to the user. Subclasses override it with something actionable.
    advice = ""

    def user_message(self) -> str:
        """Return a message fit to put in a dialog.

        Returns:
            The error text, followed by advice when the class offers any.
        """
        text = str(self)
        return f"{text}\n\n{self.advice}" if self.advice else text


class ExcelNotAvailableError(ExcelLinkError):
    """Excel is not installed, or COM could not start it."""

    advice = (
        "The spreadsheet link needs Microsoft Excel installed on this "
        "machine. The in-app formula model works without it."
    )


class WorkbookNotFoundError(ExcelLinkError):
    """The named workbook is not open and could not be opened."""

    advice = "Open the workbook in Excel, then connect again."


class WorkbookReadOnlyError(ExcelLinkError):
    """The workbook cannot be written to."""

    advice = (
        "A simulation has to write trial values into the sheet. Close the "
        "read-only copy and reopen the workbook with write access."
    )


class SheetProtectedError(ExcelLinkError):
    """A protected sheet refused a write."""

    advice = "Unprotect the sheet in Excel, then run again."


class CellResolutionError(ExcelLinkError):
    """A tagged cell does not exist in the workbook any more."""

    advice = "Re-tag the cell; it may have been deleted or the sheet renamed."


class ExcelBusyError(ExcelLinkError):
    """Excel refused the call because it is busy or showing a dialog."""

    advice = (
        "Excel is busy. Close any open dialog or finish editing a cell, "
        "then run again."
    )


class CircularReferenceError(ExcelLinkError):
    """The workbook contains a circular reference."""

    advice = (
        "Excel cannot resolve a circular reference without iterative "
        "calculation, and the results would not be trustworthy. Fix the "
        "reference, then run again."
    )


class VolatileModelError(ExcelLinkError):
    """The workbook uses functions that make a batched run unsound."""

    advice = (
        "Volatile functions such as RAND, RANDBETWEEN, NOW and TODAY change "
        "on every recalculation, so each trial would use different values "
        "and the results would be meaningless."
    )


class SimulationCancelled(ExcelLinkError):
    """The user stopped the run."""


#: Worksheet error values arrive over COM as these negative integers.
ERROR_VALUES: dict[int, str] = {
    -2146826281: "#DIV/0!",
    -2146826246: "#N/A",
    -2146826259: "#NAME?",
    -2146826288: "#NULL!",
    -2146826252: "#NUM!",
    -2146826265: "#REF!",
    -2146826273: "#VALUE!",
}

#: HRESULTs worth naming when they come back from Excel.
_HRESULTS: dict[int, type[ExcelLinkError]] = {
    -2147221164: ExcelNotAvailableError,  # REGDB_E_CLASSNOTREG
    -2147221021: ExcelNotAvailableError,  # MK_E_UNAVAILABLE
    -2147418111: ExcelBusyError,  # RPC_E_CALL_REJECTED
    -2147417846: ExcelBusyError,  # RPC_E_SERVERCALL_RETRYLATER
}


def describe_error_value(value: object) -> str | None:
    """Name the worksheet error a cell returned, if it returned one.

    Args:
        value: A value read back from a cell.

    Returns:
        The Excel error text such as ``#DIV/0!``, or None for a real value.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return ERROR_VALUES.get(int(value))


def is_error_value(value: object) -> bool:
    """Whether a cell value is a worksheet error rather than a number.

    Args:
        value: A value read back from a cell.

    Returns:
        True when the value encodes an Excel error.
    """
    return describe_error_value(value) is not None


def classify(exc: BaseException) -> ExcelLinkError:
    """Turn a COM failure into a typed, explainable error.

    Args:
        exc: The exception raised by pywin32.

    Returns:
        A typed error carrying a message worth showing to a person.
    """
    if isinstance(exc, ExcelLinkError):
        return exc

    hresult = getattr(exc, "hresult", None)
    args = getattr(exc, "args", ())
    if hresult is None and args and isinstance(args[0], int):
        hresult = args[0]

    detail = ""
    for entry in args:
        if isinstance(entry, tuple):
            detail = next(
                (str(part) for part in entry if isinstance(part, str) and part),
                "",
            )
            break
    detail = detail or str(exc)

    lowered = detail.lower()
    if "read-only" in lowered or "read only" in lowered:
        return WorkbookReadOnlyError(detail)
    if "protect" in lowered:
        return SheetProtectedError(detail)
    if "circular" in lowered:
        return CircularReferenceError(detail)

    factory = _HRESULTS.get(int(hresult)) if hresult is not None else None
    if factory is not None:
        return factory(detail)

    LOGGER.debug("Unclassified COM failure | hresult=%s | %s", hresult, detail)
    return ExcelLinkError(detail)
