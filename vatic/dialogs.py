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
