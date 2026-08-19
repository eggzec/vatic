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
#      Qt dialogs for distribution parameter input.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from vatic.distributions import (
    DistributionSpec,
    coerce_parameter_value,
    default_parameters,
)
from vatic.logger import get_logger


LOGGER = get_logger(__name__)


class ParameterDialog(QDialog):
    def __init__(
        self,
        spec: DistributionSpec,
        initial_values: dict[str, float | int] | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.spec = spec
        self._values: dict[str, float | int] = {}
        self._inputs: dict[str, QLineEdit] = {}

        self.setWindowTitle(f"Parameters - {spec.label}")
        self.resize(440, 10)
        LOGGER.debug("Parameter dialog opened | distribution=%s", spec.label)

        root = QVBoxLayout(self)
        hint = QLabel("Provide values for the selected distribution.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QFormLayout()
        resolved = dict(default_parameters(spec))
        if initial_values:
            resolved.update(initial_values)

        for parameter in spec.parameters:
            editor = QLineEdit(str(resolved.get(parameter.name, "")))
            editor.setPlaceholderText(parameter.kind)
            form.addRow(f"{parameter.name} ({parameter.kind})", editor)
            self._inputs[parameter.name] = editor

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> dict[str, float | int]:
        return dict(self._values)

    def _accept(self) -> None:
        try:
            parsed: dict[str, float | int] = {}
            for parameter in self.spec.parameters:
                widget = self._inputs[parameter.name]
                parsed[parameter.name] = coerce_parameter_value(
                    widget.text(), parameter
                )
            self._values = parsed
            LOGGER.debug(
                "Parameter dialog accepted | distribution=%s | values=%s",
                self.spec.label,
                parsed,
            )
            self.accept()
        except ValueError as exc:
            LOGGER.warning(
                "Parameter validation failed | distribution=%s | error=%s",
                self.spec.label,
                exc,
            )
            QMessageBox.critical(self, "Invalid Parameters", str(exc))


class ForecastDialog(QDialog):
    """Edit one forecast formula row away from the table grid.

    The expression is the most awkward field to edit in place: a table cell
    editor is a few characters wide, so a long formula scrolls out of sight
    while it is being typed. Editing happens here instead.
    """

    def __init__(
        self,
        name: str = "",
        expression: str = "",
        lsl: str = "",
        usl: str = "",
        target: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._values: dict[str, str] = {}

        self.setWindowTitle("Forecast formula")
        self.setMinimumWidth(520)
        LOGGER.debug("Forecast dialog opened | name=%s", name or "<new>")

        root = QVBoxLayout(self)
        hint = QLabel(
            "Reference assumptions and earlier forecasts by name. Operators: "
            "+ - * / ** and functions such as sqrt, log, exp, min, max, pi."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QFormLayout()
        self.name_input = QLineEdit(name)
        self.name_input.setPlaceholderText("profit")
        self.expression_input = QLineEdit(expression)
        self.expression_input.setPlaceholderText("revenue - cost")
        self.lsl_input = QLineEdit(lsl)
        self.lsl_input.setPlaceholderText("optional")
        self.usl_input = QLineEdit(usl)
        self.usl_input.setPlaceholderText("optional")
        self.target_input = QLineEdit(target)
        self.target_input.setPlaceholderText("optional")

        form.addRow("Name", self.name_input)
        form.addRow("Expression", self.expression_input)
        form.addRow("Lower spec limit", self.lsl_input)
        form.addRow("Upper spec limit", self.usl_input)
        form.addRow("Target", self.target_input)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> dict[str, str]:
        """Return the accepted field values.

        Returns:
            Mapping of ``name``, ``expression``, ``lsl``, ``usl`` and
            ``target`` to their raw text.
        """
        return dict(self._values)

    def _accept(self) -> None:
        """Validate the fields and close the dialog when they are usable."""
        name = self.name_input.text().strip()
        expression = self.expression_input.text().strip()

        if not name:
            QMessageBox.critical(self, "Invalid forecast", "Name is required.")
            return
        if not name.isidentifier():
            QMessageBox.critical(
                self,
                "Invalid forecast",
                f"'{name}' is not a valid name. Use letters, numbers and "
                "underscores, and do not start with a number.",
            )
            return
        if not expression:
            QMessageBox.critical(
                self, "Invalid forecast", "Expression is required."
            )
            return

        limits: dict[str, float] = {}
        for label, widget in (
            ("Lower spec limit", self.lsl_input),
            ("Upper spec limit", self.usl_input),
            ("Target", self.target_input),
        ):
            text = widget.text().strip()
            if not text:
                continue
            try:
                limits[label] = float(text)
            except ValueError:
                QMessageBox.critical(
                    self,
                    "Invalid forecast",
                    f"{label} must be a number, or left empty.",
                )
                return

        lower = limits.get("Lower spec limit")
        upper = limits.get("Upper spec limit")
        if lower is not None and upper is not None and lower > upper:
            QMessageBox.critical(
                self,
                "Invalid forecast",
                "The lower spec limit cannot be greater than the upper one.",
            )
            return

        self._values = {
            "name": name,
            "expression": expression,
            "lsl": self.lsl_input.text().strip(),
            "usl": self.usl_input.text().strip(),
            "target": self.target_input.text().strip(),
        }
        LOGGER.debug("Forecast dialog accepted | name=%s", name)
        self.accept()


EXCEL_HELP_HTML = """
<h2>Using vatic with Microsoft Excel</h2>

<p>vatic can drive a spreadsheet directly. Your workbook stays the model:
vatic samples the inputs you nominate, lets Excel recalculate, and collects
the outputs you care about. Every formula, lookup and add-in behaves exactly
as it does when you use the workbook by hand.</p>

<h3>What you need</h3>
<ul>
<li>Windows, with Microsoft Excel installed.</li>
<li>The workbook open, and not read-only.</li>
</ul>
<p>On macOS and Linux the rest of vatic still works; only the spreadsheet
link is Windows-only.</p>

<h3>Step by step</h3>
<ol>
<li><b>Spreadsheet &gt; Connect Workbook.</b> Pick a file, or cancel the file
    picker to attach to the workbook already open in Excel.</li>
<li><b>Select an input cell in Excel</b> &mdash; a nominal dimension, a cost, a
    rate &mdash; then choose <b>Spreadsheet &gt; Tag Selected Cell as
    Assumption</b>. Give it a name and a distribution. vatic suggests the name
    from the label to the left of the cell, and seeds the distribution from
    the value already in it.</li>
<li><b>Select an output cell</b> &mdash; whatever the workbook calculates that
    you want to understand &mdash; and choose <b>Tag Selected Cell as
    Forecast</b>. Add lower and upper spec limits here if the value has to
    stay inside a range; that is what turns on the capability metrics.</li>
<li>Set <b>Iterations</b>, and a <b>Seed</b> if you want the run to be exactly
    reproducible.</li>
<li>Press <b>Run Simulation</b>.</li>
</ol>
<p>Tagged cells are tinted in the sheet so you can see what vatic is driving:
inputs in cyan, outputs in magenta. <b>Clear Tagged Cells</b> puts the
original colours back.</p>

<h3>A worked example</h3>
<p>The <code>examples</code> folder contains a tolerance stack-up:
<code>seal_tolerance.xlsx</code>. Its inputs sit in <code>C8:C15</code> with
their tolerances beside them, and its two outputs are in <code>C30</code> and
<code>C31</code> with limits in <code>C19:D20</code>. A tolerance is
conventionally three sigma, so an input with a &plusmn;0.005 tolerance becomes
<code>Normal(nominal, 0.005/3)</code>.</p>

<h3>What vatic changes, and what it puts back</h3>
<p>During a run vatic adds two hidden sheets, points each tagged input at a
column of trial values, and builds an Excel data table so the whole simulation
resolves in a single recalculation. That is why ten thousand trials take about
a second instead of many minutes.</p>
<p>When the run finishes &mdash; or fails, or you cancel it &mdash; the hidden
sheets are deleted, every tagged cell gets its <b>original formula</b> back,
and Excel's calculation mode, screen updating and event settings are restored.
Nothing is saved to disk; if anything still looks wrong, close the workbook
without saving.</p>

<h3>If something goes wrong</h3>
<ul>
<li><b>"Excel is not available"</b> &mdash; Excel is not installed, or this is
    not Windows.</li>
<li><b>"Open read-only"</b> &mdash; the run has to write into the sheet. Reopen
    the workbook with write access.</li>
<li><b>"Excel is busy"</b> &mdash; a dialog is open in Excel, or a cell is
    still being edited. Finish that and run again.</li>
<li><b>Errors reported after a run</b> &mdash; some trials produced
    <code>#DIV/0!</code>, <code>#REF!</code> or similar. Those trials are left
    out of the statistics rather than being counted as zero, and the tally
    tells you how many.</li>
<li><b>Volatile functions</b> &mdash; <code>RAND</code>,
    <code>RANDBETWEEN</code>, <code>NOW</code> and <code>TODAY</code> change on
    every recalculation, so a model that uses them cannot give a meaningful
    answer.</li>
</ul>
"""

NO_EXCEL_HTML = """
<h2>Microsoft Excel is not available here</h2>
<p>The spreadsheet link needs Windows with Excel installed. vatic could not
find it, so <b>Spreadsheet &gt; Connect Workbook</b> will not work on this
machine.</p>
<p>Everything else still works: define your inputs in the
<b>Assumptions</b> table, write expressions in <b>Forecast Formulas</b>, and
press <b>Run Simulation</b>. The statistics, capability metrics, charts and
reports are identical either way.</p>
<p>If you do have Excel, install the optional dependency and restart:</p>
<pre>uv pip install "vatic[excel]"</pre>
"""


class ExcelHelpDialog(QDialog):
    """Explains how to drive a spreadsheet model from vatic."""

    def __init__(
        self, *, available: bool = True, parent: QWidget | None = None
    ) -> None:
        """Build the help window.

        Args:
            available: Whether the Excel link can be used on this machine.
                When False the dialog explains why instead.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Using vatic with Excel")
        self.resize(720, 620)

        root = QVBoxLayout(self)
        body = QTextBrowser()
        body.setOpenExternalLinks(True)
        body.setHtml(EXCEL_HELP_HTML if available else NO_EXCEL_HTML)
        root.addWidget(body)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)
        LOGGER.debug("Excel help opened | available=%s", available)
