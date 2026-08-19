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
#      The spreadsheet data model and the Excel error decoder. Both are pure
#      Python, so these run on every platform whether Excel exists or not.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import pytest

from vatic.excel import describe_error_value, is_error_value
from vatic.excel.errors import (
    ExcelBusyError,
    ExcelLinkError,
    ExcelNotAvailableError,
    SheetProtectedError,
    WorkbookReadOnlyError,
    classify,
)
from vatic.sheetmodel import (
    CellRef,
    InteriorState,
    ReferenceError,
    SheetAssumption,
    SheetForecast,
    SheetModel,
)


@pytest.mark.parametrize(
    ("text", "cell", "sheet", "workbook"),
    [
        ("C8", "C8", None, None),
        ("$C$8", "C8", None, None),
        ("c8", "C8", None, None),
        ("Sheet1!C8", "C8", "Sheet1", None),
        ("'Seal-Groove Design'!$C$8", "C8", "Seal-Groove Design", None),
        ("[Book1.xlsx]Sheet1!C8", "C8", "Sheet1", "Book1.xlsx"),
        ("  Sheet1!C8  ", "C8", "Sheet1", None),
        ("AA1048576", "AA1048576", None, None),
    ],
)
def test_reference_parsing(
    text: str, cell: str, sheet: str | None, workbook: str | None
) -> None:
    """A1 references parse in every form Excel writes them."""
    ref = CellRef.parse(text)
    assert ref.cell == cell
    assert ref.sheet == sheet
    assert ref.workbook == workbook


@pytest.mark.parametrize(
    "text", ["", "not a cell", "8C", "Sheet1!", "!C8", "C", "8"]
)
def test_bad_references_are_rejected(text: str) -> None:
    """Anything that is not a reference fails loudly."""
    with pytest.raises(ReferenceError):
        CellRef.parse(text)


def test_reference_column_and_row() -> None:
    """Column letters and row numbers come back separately."""
    ref = CellRef.parse("Sheet1!$AB$27")
    assert ref.column == "AB"
    assert ref.row == 27


def test_qualified_quotes_sheets_that_need_it() -> None:
    """A sheet name with punctuation is quoted the way Excel expects."""
    assert CellRef("C8", "Sheet1").qualified() == "Sheet1!C8"
    assert (
        CellRef("C8", "Seal-Groove Design").qualified()
        == "'Seal-Groove Design'!C8"
    )
    assert CellRef("C8").qualified() == "C8"


def test_unfilled_interior_is_recognised() -> None:
    """An unfilled cell is identified by its pattern, not its colour.

    Excel reports ``Color == 16777215`` for a cell with no fill, so restoring
    the colour alone would leave a solid white fill behind.
    """
    unfilled = InteriorState(color=16777215, pattern=-4142)
    filled = InteriorState(color=16777215, pattern=1)
    assert unfilled.is_unfilled
    assert not filled.is_unfilled


def _model() -> SheetModel:
    """Build a small valid model.

    Returns:
        A model with one assumption and one forecast.
    """
    return SheetModel(
        workbook="book.xlsx",
        assumptions=[
            SheetAssumption(CellRef("C8", "S"), "height", "Normal", {"mu": 1})
        ],
        forecasts=[SheetForecast(CellRef("C30", "S"), "fill", lsl=0.75)],
    )


def test_valid_model_passes_validation() -> None:
    """A model with inputs and outputs validates."""
    _model().validate()


def test_model_needs_assumptions_and_forecasts() -> None:
    """Neither half of the model may be empty."""
    with pytest.raises(ValueError, match="assumption"):
        SheetModel(forecasts=_model().forecasts).validate()
    with pytest.raises(ValueError, match="forecast"):
        SheetModel(assumptions=_model().assumptions).validate()


def test_duplicate_tags_are_rejected() -> None:
    """Two variables cannot share a name."""
    model = _model()
    model.forecasts[0].tag = "height"
    with pytest.raises(ValueError, match="Duplicate tag"):
        model.validate()


def test_a_cell_cannot_be_both_input_and_output() -> None:
    """Tagging one cell as both would make the run self-referential."""
    model = _model()
    model.forecasts[0].ref = CellRef("C8", "S")
    with pytest.raises(ValueError, match="both an assumption and a forecast"):
        model.validate()


def test_the_same_cell_cannot_be_two_assumptions() -> None:
    """Two assumptions writing the same cell would fight each other."""
    model = _model()
    model.assumptions.append(
        SheetAssumption(CellRef("C8", "S"), "other", "Normal", {"mu": 2})
    )
    with pytest.raises(ValueError, match="two assumptions"):
        model.validate()


def test_model_serialises_to_plain_data() -> None:
    """Assumptions and forecasts round-trip through plain dicts."""
    model = _model()
    assumption = model.assumptions[0].as_dict()
    assert assumption["cell"] == "S!C8"
    assert assumption["distribution"] == "Normal"
    forecast = model.forecasts[0].as_dict()
    assert forecast["cell"] == "S!C30"
    assert forecast["lsl"] == 0.75


@pytest.mark.parametrize(
    ("value", "name"),
    [
        (-2146826281, "#DIV/0!"),
        (-2146826246, "#N/A"),
        (-2146826259, "#NAME?"),
        (-2146826265, "#REF!"),
        (-2146826273, "#VALUE!"),
    ],
)
def test_worksheet_errors_are_decoded(value: int, name: str) -> None:
    """Excel's error sentinels are named rather than treated as numbers."""
    assert describe_error_value(value) == name
    assert is_error_value(value)


@pytest.mark.parametrize("value", [0, 1, 3.5, -1, "text", None, True, False])
def test_real_values_are_not_mistaken_for_errors(value: object) -> None:
    """Ordinary cell values pass through untouched."""
    assert describe_error_value(value) is None
    assert not is_error_value(value)


def test_com_failures_are_classified() -> None:
    """A COM error becomes a typed failure with advice attached."""
    read_only = classify(Exception("The workbook is read-only"))
    assert isinstance(read_only, WorkbookReadOnlyError)
    assert read_only.advice

    protected = classify(Exception("The sheet is protected"))
    assert isinstance(protected, SheetProtectedError)

    unknown = classify(Exception("something odd"))
    assert isinstance(unknown, ExcelLinkError)


def test_known_hresults_are_named() -> None:
    """A missing registration reads as 'Excel is not installed'."""

    class FakeComError(Exception):
        hresult = -2147221164

    error = classify(FakeComError("class not registered"))
    assert isinstance(error, ExcelNotAvailableError)

    class BusyError(Exception):
        hresult = -2147418111

    assert isinstance(classify(BusyError("rejected")), ExcelBusyError)


def test_typed_errors_already_pass_through() -> None:
    """Classifying an already-typed error does not re-wrap it."""
    original = SheetProtectedError("protected")
    assert classify(original) is original


def test_user_message_includes_advice() -> None:
    """The dialog text tells the user what to actually do."""
    message = ExcelNotAvailableError("no Excel").user_message()
    assert "no Excel" in message
    assert "Microsoft Excel" in message
