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
#      The COM connection to Excel, and every read and write against it.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import TracebackType

from vatic.excel.errors import (
    CellResolutionError,
    ExcelLinkError,
    ExcelNotAvailableError,
    WorkbookNotFoundError,
    WorkbookReadOnlyError,
    classify,
)
from vatic.logger import get_logger
from vatic.sheetmodel import CellRef, InteriorState


LOGGER = get_logger(__name__)

# Excel enumerations, spelled out so no type library import is needed.
XL_CALC_AUTOMATIC = -4105
XL_CALC_MANUAL = -4135
XL_PATTERN_NONE = -4142
XL_PATTERN_SOLID = 1
XL_SHEET_VERY_HIDDEN = 2
XL_SHEET_VISIBLE = -1


def _to_bgr(rgb: str) -> int:
    """Convert an ``#RRGGBB`` string to the BGR integer Excel expects.

    Args:
        rgb: Hex colour string.

    Returns:
        The colour as Excel's little-endian BGR integer.
    """
    raw = rgb.lstrip("#")
    red, green, blue = (int(raw[i : i + 2], 16) for i in (0, 2, 4))
    return blue << 16 | green << 8 | red


@dataclass(frozen=True)
class ApplicationState:
    """The Excel settings a run changes, captured so they can be restored."""

    screen_updating: bool
    calculation: int
    enable_events: bool
    display_alerts: bool


def excel_available() -> bool:
    """Whether Excel can actually be driven on this machine.

    The registry lookup proves Excel is installed without launching it, which
    is what separates a machine that merely has pywin32 from one that has
    Excel. A Windows CI runner is exactly the former, and without this check
    the spreadsheet tests would try to start an Excel that is not there.

    Returns:
        True when Windows, pywin32 and a registered Excel are all present.
    """
    if sys.platform != "win32":
        return False

    try:
        import win32com.client  # noqa: F401
    except ImportError:
        LOGGER.debug("pywin32 is not installed; no spreadsheet link")
        return False

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, r"Excel.Application\CLSID"
        ):
            return True
    except OSError as exc:
        LOGGER.debug("Excel is not registered on this machine | %s", exc)
        return False


class ExcelSession:
    """A connection to Excel, scoped to one workbook.

    The session owns the COM objects and therefore belongs to exactly one
    thread. COM apartments are per-thread, so a session created on the GUI
    thread cannot be used from a worker; construct it where it is used.
    """

    def __init__(self, *, visible: bool = True, private: bool = False) -> None:
        """Prepare a session without connecting yet.

        Args:
            visible: Whether a newly started Excel should be shown.
            private: Start a dedicated Excel instance instead of attaching to
                the one the user already has open. Useful for tests, which
                must never disturb a real session.
        """
        self._visible = visible
        self._private = private
        self._owns_instance = False
        self._initialised_com = False
        self.app: object | None = None
        self.workbook: object | None = None
        self._saved: ApplicationState | None = None

    # ------------------------------------------------------------ lifecycle

    def connect(self, path: str | None = None) -> str:
        """Attach to Excel and select a workbook.

        Args:
            path: Workbook to open. When omitted the active workbook of a
                running Excel is used.

        Returns:
            The name of the connected workbook.

        Raises:
            ExcelNotAvailableError: If Excel cannot be reached.
            WorkbookNotFoundError: If no workbook could be selected.
            WorkbookReadOnlyError: If the workbook cannot be written to.
            ExcelLinkError: If Excel refused the connection for any other
                reason; the concrete type comes from ``classify``.
        """  # noqa: DOC501
        if not excel_available():
            raise ExcelNotAvailableError(
                "Microsoft Excel is not available on this machine"
            )

        import pythoncom
        import win32com.client as client

        try:
            pythoncom.CoInitialize()
            self._initialised_com = True
        except Exception:  # noqa: BLE001 - already initialised is fine
            self._initialised_com = False

        try:
            if self._private:
                self.app = client.DispatchEx("Excel.Application")
                self._owns_instance = True
            else:
                try:
                    self.app = client.GetActiveObject("Excel.Application")
                except Exception:  # noqa: BLE001 - nothing running yet
                    self.app = client.DispatchEx("Excel.Application")
                    self._owns_instance = True
            self.app.Visible = self._visible
        except Exception as exc:  # noqa: BLE001 - mapped to a typed error
            raise classify(exc) from exc

        try:
            if path is not None:
                self.workbook = self.app.Workbooks.Open(path)
            elif int(self.app.Workbooks.Count) > 0:
                self.workbook = self.app.ActiveWorkbook
            elif self._private:
                # A dedicated instance starts empty; the caller populates it.
                self.workbook = None
            else:
                raise WorkbookNotFoundError("No workbook is open in Excel")
        except ExcelLinkError:
            raise
        except Exception as exc:  # noqa: BLE001 - mapped to a typed error
            raise classify(exc) from exc

        if self.workbook is None:
            LOGGER.info("Connected to Excel with no workbook selected")
            return ""

        if bool(self.workbook.ReadOnly):
            raise WorkbookReadOnlyError(
                f"'{self.workbook.Name}' is open read-only"
            )

        name = str(self.workbook.Name)
        LOGGER.info("Connected to workbook | name=%s", name)
        return name

    def new_workbook(self) -> str:
        """Create and select an empty workbook.

        Connecting never creates one implicitly, because attaching to Excel
        and silently spawning a blank book would be a surprising side effect
        on someone's desktop. Callers that genuinely want a scratch workbook
        ask for it.

        Returns:
            The name of the new workbook.

        Raises:
            ExcelLinkError: If Excel refused to create it.
        """  # noqa: DOC501, DOC502
        if self.app is None:
            raise ExcelNotAvailableError("Not connected to Excel")
        try:
            self.workbook = self.app.Workbooks.Add()
        except Exception as exc:  # noqa: BLE001 - mapped to a typed error
            raise classify(exc) from exc
        name = str(self.workbook.Name)
        LOGGER.debug("Created workbook | name=%s", name)
        return name

    def close(self) -> None:
        """Release Excel, quitting only an instance this session started."""
        try:
            if self._owns_instance and self.app is not None:
                if self.workbook is not None:
                    self.workbook.Close(SaveChanges=False)
                self.app.Quit()
        except Exception as exc:  # noqa: BLE001 - teardown must not raise
            LOGGER.debug("Ignoring error while closing Excel | %s", exc)
        finally:
            self.workbook = None
            self.app = None
            # Deliberately no CoUninitialize here. Callers routinely still
            # hold Range or Worksheet proxies when the session is closed, and
            # tearing the apartment down underneath them makes their eventual
            # collection raise RPC_E_DISCONNECTED (0x80010108), which surfaces
            # as a hard interpreter crash rather than an exception. The
            # apartment is released when the owning thread ends, which is the
            # only point at which no proxy can outlive it.

    def __enter__(self) -> ExcelSession:
        """Enter the session context.

        Returns:
            This session.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Leave the session context, releasing Excel.

        Args:
            exc_type: Exception class, when leaving because of one.
            exc: The exception instance.
            traceback: The traceback.
        """
        self.close()

    # -------------------------------------------------------- app settings

    def begin_run(self) -> None:
        """Put Excel into a quiet, deterministic state for a run."""
        app = self.app
        self._saved = ApplicationState(
            screen_updating=bool(app.ScreenUpdating),
            calculation=int(app.Calculation),
            enable_events=bool(app.EnableEvents),
            display_alerts=bool(app.DisplayAlerts),
        )
        app.ScreenUpdating = False
        app.EnableEvents = False
        app.DisplayAlerts = False
        # Data tables are skipped under xlCalculationAutomaticExceptTables,
        # so the run insists on full automatic calculation.
        app.Calculation = XL_CALC_AUTOMATIC
        LOGGER.debug("Excel prepared for run | saved=%s", self._saved)

    def end_run(self) -> None:
        """Restore whatever Excel settings the run changed."""
        if self._saved is None or self.app is None:
            return
        app, saved = self.app, self._saved
        for attribute, value in (
            ("Calculation", saved.calculation),
            ("EnableEvents", saved.enable_events),
            ("DisplayAlerts", saved.display_alerts),
            ("ScreenUpdating", saved.screen_updating),
        ):
            try:
                setattr(app, attribute, value)
            except Exception as exc:  # noqa: BLE001 - best effort restore
                LOGGER.warning("Could not restore %s | %s", attribute, exc)
        self._saved = None
        LOGGER.debug("Excel settings restored")

    # --------------------------------------------------------------- cells

    def range(self, ref: CellRef):  # noqa: ANN201 - a COM object
        """Resolve a reference to a COM ``Range``.

        Args:
            ref: The cell to resolve.

        Returns:
            The Excel ``Range`` object.

        Raises:
            CellResolutionError: If the sheet or cell does not exist.
        """
        try:
            sheet = (
                self.workbook.Worksheets(ref.sheet)
                if ref.sheet
                else self.workbook.ActiveSheet
            )
            return sheet.Range(ref.cell)
        except Exception as exc:  # noqa: BLE001 - mapped to a typed error
            raise CellResolutionError(
                f"Cannot resolve {ref.qualified()} in "
                f"'{getattr(self.workbook, 'Name', '?')}'"
            ) from exc

    def read(self, ref: CellRef) -> object:
        """Read one cell's value.

        Args:
            ref: The cell to read.

        Returns:
            The cell's value, which may encode a worksheet error.
        """
        return self.range(ref).Value

    def read_formula(self, ref: CellRef) -> str:
        """Read one cell's formula text.

        Args:
            ref: The cell to read.

        Returns:
            The formula, or the literal text when the cell holds a constant.
        """
        return str(self.range(ref).Formula)

    def write_formula(self, ref: CellRef, formula: str) -> None:
        """Write a formula or a literal into one cell.

        Args:
            ref: The cell to write.
            formula: Formula text, including the leading equals sign.
        """
        self.range(ref).Formula = formula

    def sheet_names(self) -> list[str]:
        """List the worksheets in the connected workbook.

        Returns:
            Worksheet names in workbook order.
        """
        return [str(s.Name) for s in self.workbook.Worksheets]

    def label_of(self, ref: CellRef) -> str:
        """Guess a human label for a cell from the text to its left.

        Spreadsheet models put the name of a quantity immediately left of its
        value, which is how the reference implementation's examples derived
        every tag.

        Args:
            ref: The cell being tagged.

        Returns:
            The neighbouring label, or the cell reference when there is none.
        """
        try:
            cell = self.range(ref)
            for offset in (-1, -2):
                value = cell.Offset(1, offset).Value
                if isinstance(value, str) and value.strip():
                    return value.strip()
        except Exception as exc:  # noqa: BLE001 - a label is optional
            LOGGER.debug("No label found for %s | %s", ref, exc)
        return ref.cell

    # ------------------------------------------------------------ markup

    def capture_interior(self, ref: CellRef) -> InteriorState:
        """Record a cell's fill so it can be restored exactly.

        Args:
            ref: The cell to inspect.

        Returns:
            The captured fill.
        """
        interior = self.range(ref).Interior
        return InteriorState(
            color=int(interior.Color), pattern=int(interior.Pattern)
        )

    def highlight(self, ref: CellRef, rgb: str) -> None:
        """Tint a cell so the tagging is visible inside Excel.

        Args:
            ref: The cell to tint.
            rgb: Colour as ``#RRGGBB``.
        """
        interior = self.range(ref).Interior
        interior.Pattern = XL_PATTERN_SOLID
        interior.Color = _to_bgr(rgb)

    def restore_interior(self, ref: CellRef, state: InteriorState) -> None:
        """Put a captured fill back.

        Setting the colour alone would leave a solid white fill on a cell
        that previously had none, so the pattern is restored first.

        Args:
            ref: The cell to restore.
            state: The fill captured by :meth:`capture_interior`.
        """
        interior = self.range(ref).Interior
        if state.is_unfilled:
            interior.Pattern = XL_PATTERN_NONE
            return
        interior.Pattern = state.pattern
        interior.Color = state.color
