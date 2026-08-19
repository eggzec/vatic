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
#      Data model for a spreadsheet-backed analysis.
#
# ----------------------------------------------------------------------------
#
#  Deliberately free of COM, Qt and openpyxl so it imports on every platform.
#  Storage, pre-flight, the window and the Excel runner all share these types,
#  which keeps the Windows-only half of the feature a thin execution layer
#  rather than a parallel model.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import re
from dataclasses import dataclass, field

from vatic.logger import get_logger


LOGGER = get_logger(__name__)

#: ``[Book1.xlsx]Sheet One!$C$8``, with the workbook and sheet optional.
_REFERENCE = re.compile(
    r"^\s*(?:\[(?P<workbook>[^\]]+)\])?"
    r"(?:(?P<quoted>'[^']+'|[^!']+)!)?"
    r"(?P<cell>\$?[A-Za-z]{1,3}\$?\d{1,7})\s*$"
)

_CELL = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d{1,7})$")


class ReferenceError(ValueError):
    """Raised when a cell reference cannot be understood."""


@dataclass(frozen=True)
class CellRef:
    """A single cell, optionally qualified by sheet and workbook."""

    cell: str
    sheet: str | None = None
    workbook: str | None = None

    @classmethod
    def parse(cls, text: str) -> CellRef:
        """Parse an A1-style reference.

        Accepts ``C8``, ``Sheet1!C8``, ``'Seal-Groove Design'!$C$8`` and
        ``[Book1.xlsx]Sheet1!C8``.

        Args:
            text: The reference to parse.

        Returns:
            The parsed reference, with dollar signs stripped.

        Raises:
            ReferenceError: If the text is not an A1-style reference.
        """
        match = _REFERENCE.match(text or "")
        if match is None:
            raise ReferenceError(f"Not a cell reference: {text!r}")

        sheet = match.group("quoted")
        if sheet is not None:
            sheet = sheet.strip().strip("'")

        return cls(
            cell=match.group("cell").replace("$", "").upper(),
            sheet=sheet or None,
            workbook=match.group("workbook"),
        )

    @property
    def column(self) -> str:
        """Return the column letters.

        Returns:
            The column portion, upper case.

        Raises:
            ReferenceError: If the cell is malformed.
        """
        match = _CELL.match(self.cell)
        if match is None:
            raise ReferenceError(f"Malformed cell: {self.cell!r}")
        return match.group(1).upper()

    @property
    def row(self) -> int:
        """Return the one-based row number.

        Returns:
            The row portion as an integer.

        Raises:
            ReferenceError: If the cell is malformed.
        """
        match = _CELL.match(self.cell)
        if match is None:
            raise ReferenceError(f"Malformed cell: {self.cell!r}")
        return int(match.group(2))

    def qualified(self) -> str:
        """Render the reference the way Excel writes it in a formula.

        Returns:
            A reference string including the sheet when one is known.
        """
        if not self.sheet:
            return self.cell
        sheet = self.sheet
        if not sheet.replace("_", "").isalnum():
            sheet = f"'{sheet}'"
        return f"{sheet}!{self.cell}"

    def __str__(self) -> str:
        """Return the qualified reference.

        Returns:
            The same string as :meth:`qualified`.
        """
        return self.qualified()


@dataclass(frozen=True)
class InteriorState:
    """The fill of a cell, captured so it can be put back exactly.

    Restoring the colour alone is not enough: an unfilled cell reports
    ``Color == 16777215`` with ``Pattern == xlNone``, so writing the colour
    back leaves a solid white fill where there was none before.
    """

    #: ``Interior.Color`` as Excel's BGR integer.
    color: int
    #: ``Interior.Pattern``; ``-4142`` is ``xlNone``, meaning no fill at all.
    pattern: int

    XL_PATTERN_NONE = -4142

    @property
    def is_unfilled(self) -> bool:
        """Whether the cell had no fill.

        Returns:
            True when the pattern is ``xlNone``.
        """
        return self.pattern == self.XL_PATTERN_NONE


@dataclass
class SheetAssumption:
    """An input cell that a distribution is sampled into."""

    ref: CellRef
    tag: str
    distribution: str
    parameters: dict[str, float] = field(default_factory=dict)
    #: The cell's contents before vatic touched it. A formula is kept as its
    #: formula text, so restoring never silently replaces it with a number.
    original_formula: str | None = None
    original_interior: InteriorState | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation.

        Returns:
            The assumption as plain data, for storage.
        """
        return {
            "cell": self.ref.qualified(),
            "workbook": self.ref.workbook,
            "tag": self.tag,
            "distribution": self.distribution,
            "parameters": dict(self.parameters),
        }


@dataclass
class SheetForecast:
    """An output cell whose value is collected each trial."""

    ref: CellRef
    tag: str
    lsl: float | None = None
    usl: float | None = None
    target: float | None = None
    original_interior: InteriorState | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation.

        Returns:
            The forecast as plain data, for storage.
        """
        return {
            "cell": self.ref.qualified(),
            "workbook": self.ref.workbook,
            "tag": self.tag,
            "lsl": self.lsl,
            "usl": self.usl,
            "target": self.target,
        }


@dataclass
class SheetModel:
    """Everything vatic needs to run a workbook-backed simulation."""

    workbook: str = ""
    assumptions: list[SheetAssumption] = field(default_factory=list)
    forecasts: list[SheetForecast] = field(default_factory=list)

    def validate(self) -> None:
        """Check the model can be run at all.

        Raises:
            ValueError: If the model is missing inputs, missing outputs, or
                reuses a tag or a cell.
        """
        if not self.assumptions:
            raise ValueError("Tag at least one assumption cell before running")
        if not self.forecasts:
            raise ValueError("Tag at least one forecast cell before running")

        tags: set[str] = set()
        for item in (*self.assumptions, *self.forecasts):
            if item.tag in tags:
                raise ValueError(f"Duplicate tag: {item.tag}")
            tags.add(item.tag)

        cells = [a.ref.qualified() for a in self.assumptions]
        overlap = cells and set(cells) & {
            f.ref.qualified() for f in self.forecasts
        }
        if overlap:
            raise ValueError(
                f"A cell cannot be both an assumption and a forecast: "
                f"{', '.join(sorted(overlap))}"
            )
        if len(set(cells)) != len(cells):
            raise ValueError("The same cell is tagged as two assumptions")

        LOGGER.debug(
            "Sheet model validated | assumptions=%s | forecasts=%s",
            len(self.assumptions),
            len(self.forecasts),
        )
