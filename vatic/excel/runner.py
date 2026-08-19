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
#      Runs a Monte Carlo simulation through a live Excel workbook.
#
# ----------------------------------------------------------------------------
#
#  The reference implementation wrote one cell and recalculated once per
#  trial, which costs a cross-process COM call per cell per iteration and
#  takes roughly eighteen minutes for ten thousand trials.
#
#  This runner instead writes the whole sample matrix to a hidden sheet, points
#  each assumption cell at its column through INDEX, and builds a one-variable
#  Data Table over a trial index. Excel then evaluates every trial in a single
#  recalculation. Measured against a live Excel 16.0 on a real workbook that is
#  about 1.4 seconds for ten thousand trials, and 0.45 seconds to re-run with
#  fresh samples.
#
#  Two details are load-bearing and were both found the hard way:
#
#  * The Data Table's input cell must live on the same worksheet as the table,
#    otherwise Excel rejects it with "Input cell reference is not valid".
#  * Assumption cells frequently hold formulas rather than constants, so the
#    original FORMULA is captured and restored. The reference implementation
#    restored the computed value instead, permanently destroying the formula.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from vatic.excel.errors import (
    ExcelLinkError,
    SimulationCancelled,
    classify,
    describe_error_value,
)
from vatic.excel.session import (
    XL_SHEET_VERY_HIDDEN,
    XL_SHEET_VISIBLE,
    ExcelSession,
)
from vatic.logger import get_logger
from vatic.sheetmodel import SheetModel


LOGGER = get_logger(__name__)

TRIALS_SHEET = "_vatic_trials"
TABLE_SHEET = "_vatic_table"

#: Excel caps a worksheet at 1,048,576 rows; the table needs a header row and
#: the trials sheet needs one row per trial.
MAX_TRIALS = 1_000_000

#: Cell tints applied while a model is connected, taken from the brand palette.
ASSUMPTION_TINT = "#24AEFF"
FORECAST_TINT = "#C04AFF"


@dataclass
class RunDiagnostics:
    """What happened during a run, beyond the numbers themselves."""

    trials: int = 0
    seconds: float = 0.0
    #: Worksheet errors seen per forecast tag, e.g. ``{"profit": {"#DIV/0!": 3}}``.
    errors: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        """Total number of trials that produced a worksheet error.

        Returns:
            The summed error tally across every forecast.
        """
        return sum(
            count for tally in self.errors.values() for count in tally.values()
        )


@dataclass
class RunResult:
    """The outcome of a spreadsheet-backed simulation."""

    #: Sampled inputs, one column per assumption, in model order.
    inputs: dict[str, np.ndarray]
    #: Collected outputs, one column per forecast, in model order.
    forecasts: dict[str, np.ndarray]
    diagnostics: RunDiagnostics


class ExcelRunner:
    """Drives one simulation against a connected workbook."""

    def __init__(self, session: ExcelSession, model: SheetModel) -> None:
        """Prepare a runner.

        Args:
            session: A connected session, owned by the calling thread.
            model: The tagged assumptions and forecasts.
        """
        self.session = session
        self.model = model
        self._created_sheets: list[str] = []
        self._original_formulas: dict[str, str] = {}

    # ------------------------------------------------------------- helpers

    def _worksheet(self, name: str):  # noqa: ANN202 - a COM object
        """Return a scratch worksheet, creating it if needed.

        Args:
            name: Worksheet name.

        Returns:
            The Excel ``Worksheet`` object.
        """
        book = self.session.workbook
        for sheet in book.Worksheets:
            if str(sheet.Name) == name:
                return sheet
        sheet = book.Worksheets.Add()
        sheet.Name = name
        sheet.Visible = XL_SHEET_VERY_HIDDEN
        self._created_sheets.append(name)
        LOGGER.debug("Created scratch sheet | name=%s", name)
        return sheet

    @staticmethod
    def _column_letters(index: int) -> str:
        """Convert a one-based column index to its letters.

        Args:
            index: One-based column number.

        Returns:
            The column letters, such as ``AA`` for 27.
        """
        letters = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            letters = chr(65 + remainder) + letters
        return letters

    # ---------------------------------------------------------------- run

    def run(
        self,
        samples: np.ndarray,
        *,
        progress: Callable[[str, float], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> RunResult:
        """Evaluate every trial through the workbook.

        Args:
            samples: Array shaped ``(trials, assumptions)`` holding one column
                per assumption, in model order.
            progress: Called with a stage description and a 0..1 fraction.
            should_cancel: Polled between stages; returning True aborts.

        Returns:
            The sampled inputs and the collected forecast columns.

        Raises:
            ValueError: If the sample matrix does not match the model.
            SimulationCancelled: If the caller asked to stop; raised from
                the nested cancellation check.
            ExcelLinkError: If Excel refused any step; the concrete type
                comes from ``classify``.
        """  # noqa: DOC501, DOC502
        self.model.validate()
        trials, columns = samples.shape
        if columns != len(self.model.assumptions):
            raise ValueError(
                f"Sample matrix has {columns} columns but the model has "
                f"{len(self.model.assumptions)} assumptions"
            )
        if not 0 < trials <= MAX_TRIALS:
            raise ValueError(f"Trial count out of range: {trials}")

        def announce(stage: str, fraction: float) -> None:
            if progress is not None:
                progress(stage, fraction)

        def check_cancelled() -> None:
            if should_cancel is not None and should_cancel():
                raise SimulationCancelled("Simulation cancelled")

        started = time.monotonic()
        self.session.begin_run()
        try:
            check_cancelled()
            announce("Writing trial values", 0.05)
            self._write_trials(samples)

            check_cancelled()
            announce("Rewiring assumption cells", 0.25)
            self._rewire_assumptions(trials)

            check_cancelled()
            announce("Calculating all trials", 0.40)
            self._build_table(trials)

            check_cancelled()
            announce("Reading results", 0.85)
            outputs, diagnostics = self._read_results(trials)
        except ExcelLinkError:
            raise
        except Exception as exc:  # noqa: BLE001 - mapped to a typed error
            raise classify(exc) from exc
        finally:
            # Restoration runs even on cancellation or crash, so the user's
            # workbook is never left rewired.
            self._restore()
            self.session.end_run()
            announce("Done", 1.0)

        diagnostics.trials = trials
        diagnostics.seconds = time.monotonic() - started
        LOGGER.info(
            "Excel run complete | trials=%s | seconds=%.2f | errors=%s",
            trials,
            diagnostics.seconds,
            diagnostics.error_count,
        )

        inputs = {
            assumption.tag: samples[:, index]
            for index, assumption in enumerate(self.model.assumptions)
        }
        return RunResult(
            inputs=inputs, forecasts=outputs, diagnostics=diagnostics
        )

    # ------------------------------------------------------------- stages

    def _write_trials(self, samples: np.ndarray) -> None:
        """Write the whole sample matrix to the hidden trials sheet.

        Args:
            samples: Array shaped ``(trials, assumptions)``.
        """
        sheet = self._worksheet(TRIALS_SHEET)
        trials, columns = samples.shape
        sheet.Range(
            sheet.Cells(1, 1), sheet.Cells(trials, columns)
        ).ClearContents()
        block = tuple(tuple(float(v) for v in row) for row in samples)
        sheet.Range(
            sheet.Cells(1, 1), sheet.Cells(trials, columns)
        ).Value = block

    def _rewire_assumptions(self, trials: int) -> None:
        """Point each assumption cell at its trial column.

        The cell's existing contents are captured first so the original
        formula, not merely its value, can be put back.

        Args:
            trials: Number of trials in the matrix.
        """
        table = self._worksheet(TABLE_SHEET)
        table.Range("A1").Value = 1

        for index, assumption in enumerate(self.model.assumptions, start=1):
            ref = assumption.ref
            key = ref.qualified()
            if key not in self._original_formulas:
                self._original_formulas[key] = self.session.read_formula(ref)
                assumption.original_formula = self._original_formulas[key]

            column = self._column_letters(index)
            self.session.write_formula(
                ref,
                f"=INDEX({TRIALS_SHEET}!${column}$1:${column}${trials},"
                f"{TABLE_SHEET}!$A$1)",
            )

    def _build_table(self, trials: int) -> None:
        """Build and evaluate the one-variable Data Table.

        Args:
            trials: Number of trials to evaluate.
        """
        table = self._worksheet(TABLE_SHEET)
        forecasts = self.model.forecasts

        # Header row: A1 is the input cell, B1.. probe each forecast.
        for offset, forecast in enumerate(forecasts, start=2):
            letter = self._column_letters(offset)
            table.Range(f"{letter}1").Formula = f"={forecast.ref.qualified()}"

        indices = tuple((float(i),) for i in range(1, trials + 1))
        table.Range(
            table.Cells(2, 1), table.Cells(trials + 1, 1)
        ).Value = indices

        last_column = len(forecasts) + 1
        table.Range(
            table.Cells(1, 1), table.Cells(trials + 1, last_column)
        ).Table(ColumnInput=table.Range("A1"))

    def _read_results(
        self, trials: int
    ) -> tuple[dict[str, np.ndarray], RunDiagnostics]:
        """Read the computed table back in one block per forecast.

        Args:
            trials: Number of trials evaluated.

        Returns:
            The forecast columns and the diagnostics gathered while reading.
        """
        table = self._worksheet(TABLE_SHEET)
        diagnostics = RunDiagnostics()
        outputs: dict[str, np.ndarray] = {}

        for offset, forecast in enumerate(self.model.forecasts, start=2):
            block = table.Range(
                table.Cells(2, offset), table.Cells(trials + 1, offset)
            ).Value
            column = np.full(trials, np.nan, dtype=float)
            tally: dict[str, int] = {}
            for row, entry in enumerate(block):
                value = entry[0] if isinstance(entry, tuple) else entry
                name = describe_error_value(value)
                if name is not None:
                    tally[name] = tally.get(name, 0) + 1
                    continue
                if isinstance(value, (int, float)) and not isinstance(
                    value, bool
                ):
                    column[row] = float(value)
            if tally:
                diagnostics.errors[forecast.tag] = tally
                LOGGER.warning(
                    "Worksheet errors in forecast | tag=%s | %s",
                    forecast.tag,
                    tally,
                )
            outputs[forecast.tag] = column

        return outputs, diagnostics

    # ---------------------------------------------------------- restore

    def _restore(self) -> None:
        """Undo every change the run made to the workbook."""
        for key, formula in self._original_formulas.items():
            try:
                from vatic.sheetmodel import CellRef

                self.session.write_formula(CellRef.parse(key), formula)
            except Exception as exc:  # noqa: BLE001 - keep restoring
                LOGGER.error("Could not restore %s | %s", key, exc)
        self._original_formulas.clear()

        book = self.session.workbook
        app = self.session.app
        for name in list(self._created_sheets):
            try:
                for sheet in book.Worksheets:
                    if str(sheet.Name) != name:
                        continue
                    # Excel refuses to delete a very hidden sheet, and it
                    # prompts for confirmation on a visible one, so the sheet
                    # is revealed and the prompt suppressed around the delete.
                    sheet.Visible = XL_SHEET_VISIBLE
                    previous_alerts = bool(app.DisplayAlerts)
                    app.DisplayAlerts = False
                    try:
                        sheet.Delete()
                    finally:
                        app.DisplayAlerts = previous_alerts
                    break
            except Exception as exc:  # noqa: BLE001 - keep restoring
                LOGGER.error(
                    "Could not delete scratch sheet %s | %s", name, exc
                )
        self._created_sheets.clear()
        LOGGER.debug("Workbook restored")
