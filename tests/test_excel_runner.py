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
#  Description
#      End-to-end simulation through a live Excel workbook.
#
# ----------------------------------------------------------------------------
#
#  Every test here drives a PRIVATE Excel instance created with DispatchEx and
#  quits it afterwards, so a session the user has open is never touched. The
#  whole module skips where Excel is unavailable, which is every non-Windows
#  CI runner.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import gc
import math
from collections.abc import Iterator

import numpy as np
import pytest

from vatic.excel import excel_available
from vatic.sheetmodel import CellRef, SheetAssumption, SheetForecast, SheetModel


pytestmark = pytest.mark.skipif(
    not excel_available(), reason="Microsoft Excel is not available here"
)

MODEL_SHEET = "Model"


@pytest.fixture
def session() -> Iterator[object]:
    """Open a private Excel instance holding a small live model.

    The model is ``out = a * 10 + b`` with ``a`` also feeding a second
    forecast, and ``a`` deliberately holds a FORMULA so the restore path is
    exercised on the case the reference implementation destroyed.

    Yields:
        A connected :class:`~vatic.excel.session.ExcelSession`.
    """
    from vatic.excel import ExcelSession

    link = ExcelSession(visible=False, private=True)
    link.connect()
    link.new_workbook()
    book = link.workbook
    sheet = book.Worksheets(1)
    sheet.Name = MODEL_SHEET
    sheet.Range("A1").Formula = "=0.5+0.5"  # an assumption holding a formula
    sheet.Range("A2").Value = 2.0
    sheet.Range("A3").Formula = "=A1*10+A2"
    sheet.Range("A4").Formula = "=A1+A2"
    del sheet, book
    try:
        yield link
    finally:
        # Excel proxies must be released before the process it serves exits,
        # or their later collection raises RPC_E_DISCONNECTED.
        gc.collect()
        link.close()


@pytest.fixture
def model() -> SheetModel:
    """Build the sheet model matching the fixture workbook.

    Returns:
        A model with two assumptions and two forecasts.
    """
    return SheetModel(
        assumptions=[
            SheetAssumption(CellRef("A1", MODEL_SHEET), "a", "Normal", {}),
            SheetAssumption(CellRef("A2", MODEL_SHEET), "b", "Normal", {}),
        ],
        forecasts=[
            SheetForecast(CellRef("A3", MODEL_SHEET), "out"),
            SheetForecast(CellRef("A4", MODEL_SHEET), "total"),
        ],
    )


def test_connects_and_lists_sheets(session) -> None:
    """A connected session can see the workbook it attached to."""
    assert MODEL_SHEET in session.sheet_names()


def test_run_matches_numpy_exactly(session, model: SheetModel) -> None:
    """Every trial Excel computes agrees with the same arithmetic in numpy."""
    from vatic.excel import ExcelRunner

    trials = 500
    samples = np.column_stack([
        np.linspace(1.0, 5.0, trials),
        np.linspace(-2.0, 2.0, trials),
    ])

    result = ExcelRunner(session, model).run(samples)

    expected_out = samples[:, 0] * 10 + samples[:, 1]
    expected_total = samples[:, 0] + samples[:, 1]
    np.testing.assert_allclose(result.forecasts["out"], expected_out, rtol=1e-9)
    np.testing.assert_allclose(
        result.forecasts["total"], expected_total, rtol=1e-9
    )
    assert result.diagnostics.trials == trials
    assert result.diagnostics.error_count == 0


def test_inputs_are_returned_alongside_outputs(
    session, model: SheetModel
) -> None:
    """The sampled inputs come back so a tornado chart can be drawn."""
    from vatic.excel import ExcelRunner

    samples = np.column_stack([np.arange(50.0), np.arange(50.0) * -1])
    result = ExcelRunner(session, model).run(samples)

    np.testing.assert_allclose(result.inputs["a"], samples[:, 0])
    np.testing.assert_allclose(result.inputs["b"], samples[:, 1])


def test_original_formula_is_restored_not_its_value(
    session, model: SheetModel
) -> None:
    """A1 holds a formula and must still hold it after a run.

    The reference implementation snapshotted the computed value and wrote
    that back, permanently replacing the user's formula with a number.
    """
    from vatic.excel import ExcelRunner

    before = session.read_formula(CellRef("A1", MODEL_SHEET))
    assert before.startswith("=")

    ExcelRunner(session, model).run(np.ones((25, 2)))

    after = session.read_formula(CellRef("A1", MODEL_SHEET))
    assert after == before, "the assumption cell's formula was destroyed"


def test_scratch_sheets_are_removed(session, model: SheetModel) -> None:
    """The hidden helper sheets do not survive the run."""
    from vatic.excel import ExcelRunner
    from vatic.excel.runner import TABLE_SHEET, TRIALS_SHEET

    ExcelRunner(session, model).run(np.ones((25, 2)))

    remaining = session.sheet_names()
    assert TRIALS_SHEET not in remaining
    assert TABLE_SHEET not in remaining


def test_application_settings_are_restored(session, model: SheetModel) -> None:
    """Excel is handed back in the state it was found in."""
    from vatic.excel import ExcelRunner

    app = session.app
    before = (
        bool(app.ScreenUpdating),
        int(app.Calculation),
        bool(app.EnableEvents),
    )

    ExcelRunner(session, model).run(np.ones((25, 2)))

    after = (
        bool(app.ScreenUpdating),
        int(app.Calculation),
        bool(app.EnableEvents),
    )
    assert after == before


def test_worksheet_errors_are_counted_not_silently_zeroed(
    session, model: SheetModel
) -> None:
    """A #DIV/0! trial is reported as an error and left as NaN."""
    from vatic.excel import ExcelRunner

    # Make the second forecast divide by the first assumption.
    session.write_formula(CellRef("A4", MODEL_SHEET), "=1/A1")
    samples = np.column_stack([np.array([1.0, 0.0, 2.0, 0.0]), np.zeros(4)])

    result = ExcelRunner(session, model).run(samples)

    assert result.diagnostics.error_count == 2
    assert result.diagnostics.errors["total"]["#DIV/0!"] == 2
    assert math.isnan(result.forecasts["total"][1])
    assert result.forecasts["total"][0] == pytest.approx(1.0)


def test_interior_capture_and_restore_round_trips(session) -> None:
    """An unfilled cell is still unfilled after being highlighted."""
    ref = CellRef("D10", MODEL_SHEET)
    original = session.capture_interior(ref)
    assert original.is_unfilled

    session.highlight(ref, "#24AEFF")
    assert not session.capture_interior(ref).is_unfilled

    session.restore_interior(ref, original)
    assert session.capture_interior(ref).is_unfilled


def test_mismatched_sample_matrix_is_rejected(
    session, model: SheetModel
) -> None:
    """A matrix whose width does not match the model is a caller error."""
    from vatic.excel import ExcelRunner

    with pytest.raises(ValueError, match="columns"):
        ExcelRunner(session, model).run(np.ones((10, 3)))


def test_cancellation_still_restores_the_workbook(
    session, model: SheetModel
) -> None:
    """Stopping mid-run leaves the workbook exactly as it was."""
    from vatic.excel import ExcelRunner
    from vatic.excel.errors import SimulationCancelled
    from vatic.excel.runner import TRIALS_SHEET

    before = session.read_formula(CellRef("A1", MODEL_SHEET))
    calls = {"n": 0}

    def should_cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    with pytest.raises(SimulationCancelled):
        ExcelRunner(session, model).run(
            np.ones((100, 2)), should_cancel=should_cancel
        )

    assert session.read_formula(CellRef("A1", MODEL_SHEET)) == before
    assert TRIALS_SHEET not in session.sheet_names()
