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
#      Main OpenRisk window and interaction logic.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import mcerp
import numpy as np
from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vatic.about import INFO_TEXT, __version__
from vatic.analytics import (
    compute_capability_metrics,
    compute_statistics,
    tornado_correlations,
)
from vatic.assumption import Assumption
from vatic.chart import PlotCanvas
from vatic.dialogs import ParameterDialog
from vatic.distributions import (
    build_variable,
    default_parameters,
    distribution_labels,
    get_distribution_spec,
)
from vatic.formula import evaluate_formula
from vatic.logger import get_logger
from vatic.reporting import export_pdf_report as write_pdf_report
from vatic.reporting import export_pptx_report as write_pptx_report
from vatic.resources import app_icon, load_bundled_fonts, rounded_logo_pixmap
from vatic.storage import AnalysisStore
from vatic.theme import build_stylesheet


CHART_TYPES = [
    "Histogram",
    "CDF",
    "Exceedance",
    "VaR / CVaR",
    "Density (KDE)",
    "Q-Q Normal",
    "Pareto",
    "Trend",
    "Scatter",
    "Tornado",
    "Box",
    "Violin",
    "Rich Statistics",
]

FORMULA_SERIALIZATION_V1 = "__vatic_formula_v1__:"


LOGGER = get_logger(__name__)


class _ReportExportWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, task: Callable[[], None]) -> None:
        super().__init__()
        self._task = task

    def run(self) -> None:
        try:
            self._task()
            self.finished.emit("")
        except Exception:  # noqa: BLE001
            self.failed.emit(traceback.format_exc())


class VaticWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        LOGGER.debug("Initializing vatic main window")

        self.setWindowTitle(f"vatic {__version__}")
        # Set on the window as well as the application, so the icon is present
        # even when VaticWindow is constructed directly instead of via main().
        self.setWindowIcon(app_icon())
        self.resize(1340, 860)

        self.store = AnalysisStore(Path.cwd() / "vatic.db")
        self.current_analysis_id: int | None = None
        self.current_analysis_name = "Untitled Analysis"

        self.last_output: np.ndarray | None = None
        self.last_forecasts: dict[str, np.ndarray] = {}
        self.last_forecast_order: list[str] = []
        self.active_forecast_name: str | None = None
        self.last_inputs: dict[str, np.ndarray] = {}
        self.last_stats: dict[str, float] = {}
        self.last_capability: dict[str, float] = {}
        self.last_capability_by_forecast: dict[str, dict[str, float]] = {}
        self.last_forecast_specs: dict[str, dict[str, float | None]] = {}
        self._active_export_threads: list[
            tuple[QThread, _ReportExportWorker]
        ] = []
        self._export_jobs: dict[int, tuple[QThread, str, str, str]] = {}

        load_bundled_fonts()
        self._build_menu_bar()
        self._apply_styles()
        self.setStatusBar(QStatusBar(self))

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_header())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 12, 14, 12)

        sheets_panel = self._build_sheets_section()
        assumptions_panel = self._build_assumptions_section()
        simulation_panel = self._build_simulation_section()
        results_panel = self._build_results_section()

        left_panel = QWidget()
        left_layout = QGridLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setHorizontalSpacing(10)
        left_layout.setVerticalSpacing(10)
        left_layout.setRowStretch(0, 2)
        left_layout.setRowStretch(1, 7)
        left_layout.setRowStretch(2, 3)
        left_layout.addWidget(sheets_panel, 0, 0)
        left_layout.addWidget(assumptions_panel, 1, 0)
        left_layout.addWidget(simulation_panel, 2, 0)

        # The input sidebar is dense; letting it scroll keeps the window's
        # minimum height inside a 1366x768 laptop screen instead of forcing a
        # window taller than the display.
        left_scroll = QScrollArea()
        left_scroll.setWidget(left_panel)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(360)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(9)
        splitter.addWidget(left_scroll)
        splitter.addWidget(results_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 7)
        splitter.setSizes([460, 900])

        body_layout.addWidget(splitter)
        root_layout.addWidget(body, 1)

        self.load_defaults()
        self._reload_analysis_list()
        self._sync_row_actions()
        self._update_window_caption()
        LOGGER.debug("Vatic window ready")

    def _build_header(self) -> QWidget:
        """Build the branded application header.

        Returns:
            The header widget, carrying the logo, the active analysis name
            and the primary simulation action.
        """
        header = QWidget()
        header.setObjectName("appHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        mark = QLabel()
        mark.setPixmap(rounded_logo_pixmap(30))
        mark.setFixedSize(QSize(30, 30))
        layout.addWidget(mark)

        wordmark_box = QWidget()
        wordmark_layout = QVBoxLayout(wordmark_box)
        wordmark_layout.setContentsMargins(0, 0, 0, 0)
        wordmark_layout.setSpacing(0)

        wordmark = QLabel("vatic")
        wordmark.setObjectName("brandWordmark")
        tagline = QLabel("OPEN SOURCE RISK ANALYSIS")
        tagline.setObjectName("brandTagline")
        wordmark_layout.addWidget(wordmark)
        wordmark_layout.addWidget(tagline)
        layout.addWidget(wordmark_box)

        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setFixedWidth(1)
        divider.setFixedHeight(30)
        layout.addSpacing(6)
        layout.addWidget(divider)
        layout.addSpacing(6)

        self.header_analysis_label = QLabel(self.current_analysis_name)
        self.header_analysis_label.setObjectName("analysisName")
        layout.addWidget(self.header_analysis_label)

        layout.addStretch(1)

        self.run_button = QPushButton("Run Simulation")
        self.run_button.setProperty("variant", "primary")
        self.run_button.setToolTip("Run the Monte Carlo simulation (F5)")
        self.run_button.clicked.connect(self.run_simulation)
        layout.addWidget(self.run_button)

        return header

    def _build_menu_bar(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        self.new_analysis_action = QAction("New Analysis", self)
        self.new_analysis_action.setShortcut("Ctrl+N")
        self.new_analysis_action.triggered.connect(self.new_analysis)
        file_menu.addAction(self.new_analysis_action)

        self.save_analysis_action = QAction("Save Analysis", self)
        self.save_analysis_action.setShortcut("Ctrl+S")
        self.save_analysis_action.setShortcutContext(Qt.ApplicationShortcut)
        self.save_analysis_action.triggered.connect(self.auto_save_analysis)
        file_menu.addAction(self.save_analysis_action)

        self.save_as_analysis_action = QAction("Save Analysis As...", self)
        self.save_as_analysis_action.triggered.connect(self.save_analysis)
        file_menu.addAction(self.save_as_analysis_action)

        self.load_analysis_action = QAction("Load Selected", self)
        self.load_analysis_action.setShortcut("Ctrl+O")
        self.load_analysis_action.setEnabled(False)
        self.load_analysis_action.triggered.connect(self.load_selected_analysis)
        file_menu.addAction(self.load_analysis_action)

        file_menu.addSeparator()
        export_pdf_action = QAction("Export PDF Report...", self)
        export_pdf_action.triggered.connect(self.export_pdf_report)
        file_menu.addAction(export_pdf_action)

        export_ppt_action = QAction("Export PowerPoint Report...", self)
        export_ppt_action.triggered.connect(self.export_powerpoint_report)
        file_menu.addAction(export_ppt_action)

        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        edit_menu = menu.addMenu("&Edit")
        self.add_row_action = QAction("Add Variable", self)
        self.add_row_action.triggered.connect(self.add_row)
        edit_menu.addAction(self.add_row_action)

        self.edit_row_action = QAction("Edit Variable", self)
        self.edit_row_action.setEnabled(False)
        self.edit_row_action.triggered.connect(self.edit_selected_parameters)
        edit_menu.addAction(self.edit_row_action)

        self.remove_row_action = QAction("Remove Variable", self)
        self.remove_row_action.triggered.connect(self.remove_selected_rows)
        edit_menu.addAction(self.remove_row_action)

        edit_menu.addSeparator()
        self.add_formula_action = QAction("Add Formula", self)
        self.add_formula_action.triggered.connect(self.add_formula_row)
        edit_menu.addAction(self.add_formula_action)

        self.remove_formula_action = QAction("Remove Formula", self)
        self.remove_formula_action.setEnabled(False)
        self.remove_formula_action.triggered.connect(
            self.remove_selected_formula_rows
        )
        edit_menu.addAction(self.remove_formula_action)

        view_menu = menu.addMenu("&View")
        refresh_action = QAction("Refresh Analysis List", self)
        refresh_action.triggered.connect(self._reload_analysis_list)
        view_menu.addAction(refresh_action)

        run_action = QAction("Run Simulation", self)
        run_action.setShortcut("F5")
        run_action.triggered.connect(self.run_simulation)
        view_menu.addAction(run_action)

        help_menu = menu.addMenu("&Help")
        help_menu.addAction("Info", self.show_info)

    def _apply_styles(self) -> None:
        """Install the brand style sheet on the whole application."""
        self.setStyleSheet(build_stylesheet())

    def _build_sheets_section(self) -> QWidget:
        sheet = QWidget()
        layout = QVBoxLayout(sheet)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        box = QGroupBox("Analysis Sheets")
        box_layout = QVBoxLayout(box)

        self.analysis_search_input = QLineEdit()
        self.analysis_search_input.setPlaceholderText(
            "Filter saved analyses..."
        )
        self.analysis_search_input.textChanged.connect(
            self._filter_analysis_list
        )

        self.analysis_list = QListWidget()
        self.analysis_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.analysis_list.itemDoubleClicked.connect(
            self.load_selected_analysis
        )
        self.analysis_list.itemSelectionChanged.connect(self._sync_row_actions)

        self.analysis_meta_label = QLabel("No analysis loaded")
        self.analysis_meta_label.setObjectName("metaLabel")

        box_layout.setSpacing(8)
        box_layout.addWidget(self.analysis_search_input)
        box_layout.addWidget(self.analysis_list)
        box_layout.addWidget(self.analysis_meta_label)
        layout.addWidget(box)
        return sheet

    def _build_assumptions_section(self) -> QWidget:
        sheet = QWidget()
        layout = QVBoxLayout(sheet)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        box = QGroupBox("Assumptions")
        box_layout = QVBoxLayout(box)
        box_layout.setSpacing(8)

        assumption_actions = QHBoxLayout()
        assumption_actions.setSpacing(6)
        self.add_variable_button = QPushButton("Add Variable")
        self.add_variable_button.clicked.connect(self.add_row)
        self.remove_variable_button = QPushButton("Remove")
        self.remove_variable_button.setProperty("variant", "ghost")
        self.remove_variable_button.clicked.connect(self.remove_selected_rows)
        assumption_actions.addWidget(self.add_variable_button)
        assumption_actions.addWidget(self.remove_variable_button)
        assumption_actions.addStretch(1)
        box_layout.addLayout(assumption_actions)

        self.assumption_table = QTableWidget(0, 3)
        self.assumption_table.setHorizontalHeaderLabels([
            "Name",
            "Distribution",
            "Parameters",
        ])
        self.assumption_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.assumption_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.assumption_table.itemSelectionChanged.connect(
            self._sync_row_actions
        )
        self.assumption_table.itemChanged.connect(self._on_model_input_changed)
        self.assumption_table.setMinimumHeight(120)
        self.assumption_table.setAlternatingRowColors(True)
        self.assumption_table.verticalHeader().setDefaultSectionSize(32)
        box_layout.addWidget(self.assumption_table)

        self.assumption_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.assumption_table.customContextMenuRequested.connect(
            self._show_assumption_context_menu
        )
        self.assumption_table.cellDoubleClicked.connect(
            self._handle_assumption_double_click
        )

        formula_box = QGroupBox("Forecast Formulas")
        formula_layout = QVBoxLayout(formula_box)
        formula_layout.setSpacing(8)

        formula_actions = QHBoxLayout()
        formula_actions.setSpacing(6)
        self.add_formula_button = QPushButton("Add Formula")
        self.add_formula_button.clicked.connect(self.add_formula_row)
        self.remove_formula_button = QPushButton("Remove")
        self.remove_formula_button.setProperty("variant", "ghost")
        self.remove_formula_button.clicked.connect(
            self.remove_selected_formula_rows
        )
        formula_actions.addWidget(self.add_formula_button)
        formula_actions.addWidget(self.remove_formula_button)
        formula_actions.addStretch(1)
        formula_layout.addLayout(formula_actions)

        self.formula_table = QTableWidget(0, 5)
        self.formula_table.setHorizontalHeaderLabels([
            "Name",
            "Expression",
            "LSL",
            "USL",
            "Target",
        ])
        self.formula_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.formula_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.formula_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.formula_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.formula_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeToContents
        )
        self.formula_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.formula_table.itemSelectionChanged.connect(self._sync_row_actions)
        self.formula_table.itemChanged.connect(self._on_model_input_changed)
        self.formula_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.formula_table.customContextMenuRequested.connect(
            self._show_formula_context_menu
        )
        self.formula_table.setMinimumHeight(96)
        self.formula_table.setAlternatingRowColors(True)
        self.formula_table.verticalHeader().setDefaultSectionSize(30)
        formula_layout.addWidget(self.formula_table)

        assumptions_splitter = QSplitter(Qt.Vertical)
        assumptions_splitter.setChildrenCollapsible(False)
        assumptions_splitter.addWidget(box)
        assumptions_splitter.addWidget(formula_box)
        assumptions_splitter.setStretchFactor(0, 6)
        assumptions_splitter.setStretchFactor(1, 4)
        assumptions_splitter.setSizes([300, 210])

        layout.addWidget(assumptions_splitter)
        return sheet

    def _build_simulation_section(self) -> QWidget:
        sheet = QWidget()
        layout = QVBoxLayout(sheet)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        controls_box = QGroupBox("Simulation")
        controls_row = QHBoxLayout(controls_box)
        controls_row.setSpacing(10)

        self.iteration_spin = QSpinBox()
        self.iteration_spin.setRange(500, 200000)
        self.iteration_spin.setValue(10000)
        self.iteration_spin.setSingleStep(1000)
        self.iteration_spin.setGroupSeparatorShown(True)
        self.iteration_spin.valueChanged.connect(self._on_model_input_changed)

        iterations_label = QLabel("Iterations")
        iterations_label.setObjectName("sectionTitle")
        controls_row.addWidget(iterations_label)
        controls_row.addWidget(self.iteration_spin, 1)
        layout.addWidget(controls_box)

        calculator_box = QGroupBox("Formula Keypad")
        calculator_box.setObjectName("calculatorBox")
        calculator_grid = QGridLayout(calculator_box)
        calculator_grid.setSpacing(5)
        button_rows: list[list[tuple[str, str]]] = [
            [
                ("7", "7"),
                ("8", "8"),
                ("9", "9"),
                ("(", "("),
                (")", ")"),
                ("C", "__clear__"),
            ],
            [
                ("4", "4"),
                ("5", "5"),
                ("6", "6"),
                ("+", "+"),
                ("-", "-"),
                ("DEL", "__del__"),
            ],
            [
                ("1", "1"),
                ("2", "2"),
                ("3", "3"),
                ("*", "*"),
                ("/", "/"),
                (";", "; "),
            ],
            [
                ("0", "0"),
                (".", "."),
                ("%", "%"),
                ("=", " = "),
                ("pi", "pi"),
                ("e", "e"),
            ],
            [
                ("sin", "sin("),
                ("cos", "cos("),
                ("tan", "tan("),
                ("sqrt", "sqrt("),
                ("log", "log("),
                ("exp", "exp("),
            ],
            [
                ("abs", "abs("),
                ("min", "min("),
                ("max", "max("),
                ("sign", "sign("),
                ("floor", "floor("),
                ("ceil", "ceil("),
            ],
        ]

        for row_idx, row_buttons in enumerate(button_rows):
            for col_idx, (label, token) in enumerate(row_buttons):
                button = QPushButton(label)
                button.setMinimumHeight(28)
                if token in {"__clear__", "__del__"}:
                    button.setProperty("calcKey", "edit")
                elif label.isalpha() and len(label) > 1:
                    button.setProperty("calcKey", "fn")
                else:
                    button.setProperty("calcKey", "true")
                if token == "__clear__":
                    button.clicked.connect(self._clear_formula)
                elif token == "__del__":
                    button.clicked.connect(self._delete_formula_char)
                else:
                    button.clicked.connect(
                        lambda _checked=False, t=token: (
                            self._insert_formula_token(t)
                        )
                    )
                calculator_grid.addWidget(button, row_idx, col_idx)

        layout.addWidget(calculator_box)

        layout.addStretch(1)
        return sheet

    def show_info(self) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("vatic")
        dialog.setText(INFO_TEXT)
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.setStyleSheet("QLabel{min-width: 560px;}")
        dialog.exec()

    def _insert_formula_token(self, token: str) -> None:
        if self.formula_table.rowCount() == 0:
            self.add_formula_row(name="forecast", expression="")

        row = self.formula_table.currentRow()
        if row < 0:
            row = self.formula_table.rowCount() - 1

        item = self.formula_table.item(row, 1)
        if item is None:
            item = QTableWidgetItem("")
            self.formula_table.setItem(row, 1, item)

        item.setText(f"{item.text()}{token}")
        self.formula_table.setCurrentCell(row, 1)
        self.formula_table.setFocus()

    def _clear_formula(self) -> None:
        row = self.formula_table.currentRow()
        if row < 0:
            return
        item = self.formula_table.item(row, 1)
        if item is None:
            self.formula_table.setItem(row, 1, QTableWidgetItem(""))
        else:
            item.setText("")
        self.formula_table.setCurrentCell(row, 1)
        self.formula_table.setFocus()

    def _delete_formula_char(self) -> None:
        row = self.formula_table.currentRow()
        if row < 0:
            return
        item = self.formula_table.item(row, 1)
        if item is None:
            return
        text = item.text()
        if not text:
            return
        item.setText(text[:-1])
        self.formula_table.setCurrentCell(row, 1)
        self.formula_table.setFocus()

    def _on_model_input_changed(self, *_args) -> None:
        self._invalidate_simulation_results()

    def _invalidate_simulation_results(self) -> None:
        if (
            self.last_output is None
            and not self.last_inputs
            and not self.last_stats
        ):
            return
        self.last_output = None
        self.last_forecasts = {}
        self.last_forecast_order = []
        self.active_forecast_name = None
        self.last_inputs = {}
        self.last_stats = {}
        self.last_capability = {}
        self.last_capability_by_forecast = {}
        self.last_forecast_specs = {}
        self.scatter_var_combo.blockSignals(True)
        self.scatter_var_combo.clear()
        self.scatter_var_combo.blockSignals(False)
        self.stats_label.setText(
            "Model changed. Run simulation to refresh results"
        )
        self.canvas.draw_message(
            "Model changed. Run simulation to display charts"
        )

    def _build_results_section(self) -> QWidget:
        sheet = QWidget()
        layout = QGridLayout(sheet)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)

        chart_controls = QWidget()
        chart_controls.setObjectName("chartToolbar")
        chart_controls_layout = QHBoxLayout(chart_controls)
        chart_controls_layout.setContentsMargins(14, 10, 14, 10)
        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItems(CHART_TYPES)
        self.chart_type_combo.currentTextChanged.connect(
            self.render_selected_chart
        )
        self.chart_type_combo.setMinimumWidth(170)
        self.chart_type_combo.setMaximumWidth(240)
        self.scatter_var_combo = QComboBox()
        self.scatter_var_combo.currentTextChanged.connect(
            self.render_selected_chart
        )
        self.scatter_var_combo.setMinimumWidth(170)
        self.scatter_var_combo.setMaximumWidth(240)
        chart_label = QLabel("CHART")
        chart_label.setObjectName("sectionTitle")
        series_label = QLabel("SERIES")
        series_label.setObjectName("sectionTitle")
        chart_controls_layout.addWidget(chart_label)
        chart_controls_layout.addWidget(self.chart_type_combo)
        chart_controls_layout.addSpacing(14)
        chart_controls_layout.addWidget(series_label)
        chart_controls_layout.addWidget(self.scatter_var_combo)
        chart_controls_layout.addStretch(1)
        chart_controls.setMaximumHeight(58)

        chart_box = QWidget()
        chart_box.setObjectName("chartFrame")
        chart_layout = QVBoxLayout(chart_box)
        chart_layout.setContentsMargins(4, 4, 4, 4)
        self.canvas = PlotCanvas()
        self.canvas.setMinimumHeight(200)
        chart_layout.addWidget(self.canvas)

        self.stats_label = QLabel(
            "No results yet\n\n"
            "Define your assumptions and forecast formulas, then run the "
            "simulation to see\nstatistics and capability metrics here."
        )
        self.stats_label.setObjectName("statsCard")
        self.stats_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.stats_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.stats_label.setWordWrap(True)
        self.stats_label.setMinimumHeight(96)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setRowStretch(1, 5)
        layout.setRowStretch(2, 2)
        layout.addWidget(chart_controls, 0, 0, 1, 2)
        layout.addWidget(chart_box, 1, 0, 1, 2)
        layout.addWidget(self.stats_label, 2, 0, 1, 2)
        return sheet

    def add_row(
        self,
        name: str = "",
        distribution_label: str | None = None,
        parameters: dict[str, float | int] | None = None,
    ) -> None:
        LOGGER.debug(
            "Adding assumption row | name=%s | distribution=%s",
            name or "<empty>",
            distribution_label,
        )
        row = self.assumption_table.rowCount()
        self.assumption_table.insertRow(row)

        name_item = QTableWidgetItem(name)
        self.assumption_table.setItem(row, 0, name_item)

        dist_combo = QComboBox()
        dist_combo.addItems(distribution_labels())
        if distribution_label:
            dist_combo.setCurrentText(distribution_label)
        dist_combo.currentTextChanged.connect(self._distribution_changed)
        self.assumption_table.setCellWidget(row, 1, dist_combo)

        spec = get_distribution_spec(dist_combo.currentText())
        row_parameters = parameters or default_parameters(spec)
        self._set_row_parameters(row, row_parameters)

    def add_formula_row(
        self,
        name: str = "",
        expression: str = "",
        lsl: float | None = None,
        usl: float | None = None,
        target: float | None = None,
    ) -> None:
        LOGGER.debug("Adding formula row | name=%s", name or "<empty>")
        row = self.formula_table.rowCount()
        self.formula_table.insertRow(row)
        self.formula_table.setItem(row, 0, QTableWidgetItem(name))
        self.formula_table.setItem(row, 1, QTableWidgetItem(expression))
        self.formula_table.setItem(
            row, 2, QTableWidgetItem("" if lsl is None else str(lsl))
        )
        self.formula_table.setItem(
            row, 3, QTableWidgetItem("" if usl is None else str(usl))
        )
        self.formula_table.setItem(
            row, 4, QTableWidgetItem("" if target is None else str(target))
        )

    def remove_selected_formula_rows(self) -> None:
        rows = sorted(
            {index.row() for index in self.formula_table.selectedIndexes()},
            reverse=True,
        )
        LOGGER.debug("Removing selected formula rows | rows=%s", rows)
        for row in rows:
            self.formula_table.removeRow(row)
        if rows:
            self._invalidate_simulation_results()
        self._sync_row_actions()

    def _serialize_formula_rows(self) -> str:
        chunks: list[str] = []
        for row in range(self.formula_table.rowCount()):
            name_item = self.formula_table.item(row, 0)
            expr_item = self.formula_table.item(row, 1)
            name = name_item.text().strip() if name_item else ""
            expression = expr_item.text().strip() if expr_item else ""
            if not name and not expression:
                continue
            chunks.append(f"{name} = {expression}")
        return "; ".join(chunks)

    def _serialize_formula_rows_for_storage(self) -> str:
        rows: list[dict[str, object]] = []
        for row in range(self.formula_table.rowCount()):
            name_item = self.formula_table.item(row, 0)
            expr_item = self.formula_table.item(row, 1)
            lsl_item = self.formula_table.item(row, 2)
            usl_item = self.formula_table.item(row, 3)
            target_item = self.formula_table.item(row, 4)

            name = name_item.text().strip() if name_item else ""
            expression = expr_item.text().strip() if expr_item else ""
            if not name and not expression:
                continue

            rows.append({
                "name": name,
                "expression": expression,
                "lsl": lsl_item.text().strip() if lsl_item else "",
                "usl": usl_item.text().strip() if usl_item else "",
                "target": target_item.text().strip() if target_item else "",
            })

        return FORMULA_SERIALIZATION_V1 + json.dumps(
            rows, separators=(",", ":"), ensure_ascii=True
        )

    def _load_formula_rows_from_text(self, raw: str) -> None:
        self.formula_table.setRowCount(0)
        text = raw.strip()
        if not text:
            self.add_formula_row("profit", "revenue - cost")
            return

        if text.startswith(FORMULA_SERIALIZATION_V1):
            payload = text.removeprefix(FORMULA_SERIALIZATION_V1)
            try:
                rows = json.loads(payload)
            except json.JSONDecodeError:
                rows = []
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    try:
                        self.add_formula_row(
                            name=str(row.get("name", "")).strip(),
                            expression=str(row.get("expression", "")).strip(),
                            lsl=(
                                float(str(row.get("lsl", "")).strip())
                                if str(row.get("lsl", "")).strip()
                                else None
                            ),
                            usl=(
                                float(str(row.get("usl", "")).strip())
                                if str(row.get("usl", "")).strip()
                                else None
                            ),
                            target=(
                                float(str(row.get("target", "")).strip())
                                if str(row.get("target", "")).strip()
                                else None
                            ),
                        )
                    except ValueError:
                        continue
            if self.formula_table.rowCount() == 0:
                self.add_formula_row("profit", "revenue - cost")
            return

        chunks = [part.strip() for part in text.split(";") if part.strip()]
        if not chunks:
            self.add_formula_row("profit", "revenue - cost")
            return

        auto_index = 1
        for chunk in chunks:
            if "=" in chunk:
                raw_name, raw_expr = chunk.split("=", 1)
                name = raw_name.strip()
                expression = raw_expr.strip()
            else:
                name = f"forecast_{auto_index}"
                auto_index += 1
                expression = chunk
            self.add_formula_row(name=name, expression=expression)

    def edit_selected_parameters(self) -> None:
        row = self.assumption_table.currentRow()
        if row < 0:
            return
        LOGGER.debug("Editing parameters for row | row=%s", row)

        spec = self._distribution_spec_for_row(row)
        current = self._get_row_parameters(row)
        dialog = ParameterDialog(spec, current, self)
        if dialog.exec():
            self._set_row_parameters(row, dialog.values())

    def _show_assumption_context_menu(self, point) -> None:
        row = self.assumption_table.rowAt(point.y())
        if row >= 0:
            self.assumption_table.selectRow(row)

        menu = QMenu(self)
        edit_action = menu.addAction("Edit Parameters")
        edit_action.setEnabled(row >= 0)
        add_action = menu.addAction("Add Assumption")
        remove_action = menu.addAction("Remove Selected")

        chosen = menu.exec(self.assumption_table.viewport().mapToGlobal(point))
        if chosen is edit_action:
            self.edit_selected_parameters()
        elif chosen is add_action:
            self.add_row()
        elif chosen is remove_action:
            self.remove_selected_rows()

    def _show_formula_context_menu(self, point) -> None:
        row = self.formula_table.rowAt(point.y())
        if row >= 0:
            self.formula_table.selectRow(row)

        menu = QMenu(self)
        add_action = menu.addAction("Add Formula")
        remove_action = menu.addAction("Remove Selected")
        remove_action.setEnabled(row >= 0)

        chosen = menu.exec(self.formula_table.viewport().mapToGlobal(point))
        if chosen is add_action:
            self.add_formula_row()
        elif chosen is remove_action:
            self.remove_selected_formula_rows()

    def _handle_assumption_double_click(self, row: int, col: int) -> None:
        if col == 2:
            self.assumption_table.selectRow(row)
            self.edit_selected_parameters()

    def remove_selected_rows(self) -> None:
        rows = sorted(
            {index.row() for index in self.assumption_table.selectedIndexes()},
            reverse=True,
        )
        LOGGER.debug("Removing selected assumption rows | rows=%s", rows)
        for row in rows:
            self.assumption_table.removeRow(row)
        if rows:
            self._invalidate_simulation_results()
        self._sync_row_actions()

    def _sync_row_actions(self) -> None:
        has_selection = self.assumption_table.currentRow() >= 0
        has_formula_selection = self.formula_table.currentRow() >= 0
        has_analysis_selection = self._selected_analysis_id() is not None
        self.edit_row_action.setEnabled(has_selection)
        self.load_analysis_action.setEnabled(has_analysis_selection)
        self.remove_formula_action.setEnabled(has_formula_selection)

    def _selected_analysis_id(self) -> int | None:
        item = self.analysis_list.currentItem()
        if item is None:
            return None
        payload = item.data(Qt.UserRole)
        if isinstance(payload, int):
            return payload
        return None

    def _collect_current_assumptions(self) -> list[Assumption]:
        assumptions: list[Assumption] = []
        for row in range(self.assumption_table.rowCount()):
            name_item = self.assumption_table.item(row, 0)
            name = name_item.text().strip() if name_item else ""
            if not name:
                continue
            spec = self._distribution_spec_for_row(row)
            params = self._get_row_parameters(row)
            assumptions.append(
                Assumption(
                    name=name, distribution=spec.label, parameters=params
                )
            )
        return assumptions

    def _reload_analysis_list(self) -> None:
        selected_id = self._selected_analysis_id() or self.current_analysis_id
        self.analysis_list.clear()
        LOGGER.debug("Reloading analysis list | selected_id=%s", selected_id)
        for summary in self.store.list_analyses():
            item = QListWidgetItem(summary.name)
            item.setData(Qt.UserRole, summary.analysis_id)
            item.setData(Qt.UserRole + 1, summary.updated_at)
            self.analysis_list.addItem(item)
            if selected_id is not None and summary.analysis_id == selected_id:
                self.analysis_list.setCurrentItem(item)
        self._filter_analysis_list(self.analysis_search_input.text())
        self._sync_row_actions()

    def _filter_analysis_list(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self.analysis_list.count()):
            item = self.analysis_list.item(i)
            visible = needle in item.text().lower() if needle else True
            item.setHidden(not visible)

    def _update_window_caption(self) -> None:
        self.setWindowTitle(f"vatic {__version__}")
        self.analysis_meta_label.setText(
            f"Active: {self.current_analysis_name}"
        )
        if hasattr(self, "header_analysis_label"):
            self.header_analysis_label.setText(self.current_analysis_name)
        self.statusBar().showMessage(
            f"Current analysis: {self.current_analysis_name}"
        )
        LOGGER.debug(
            "Updated active analysis caption | name=%s",
            self.current_analysis_name,
        )

    def new_analysis(self) -> None:
        LOGGER.debug("Creating new analysis workspace")
        self.assumption_table.setRowCount(0)
        self.formula_table.setRowCount(0)
        self.iteration_spin.setValue(10000)
        self.last_output = None
        self.last_forecasts = {}
        self.last_forecast_order = []
        self.active_forecast_name = None
        self.last_inputs = {}
        self.last_stats = {}
        self.last_capability = {}
        self.last_capability_by_forecast = {}
        self.last_forecast_specs = {}
        self.stats_label.setText("Run a simulation to view results")
        self.canvas.draw_message("Run a simulation to display charts")
        self.current_analysis_id = None
        self.current_analysis_name = "Untitled Analysis"
        self.load_defaults()
        self._sync_row_actions()
        self._update_window_caption()

    def _save_analysis_named(self, clean_name: str) -> None:
        LOGGER.debug("Saving analysis | name=%s", clean_name)
        assumptions = self._collect_current_assumptions()
        if not assumptions:
            LOGGER.warning("Save aborted: no assumptions provided")
            QMessageBox.information(
                self,
                "Save Analysis",
                "Add at least one variable before saving.",
            )
            return

        payload: list[dict[str, object]] = [
            {
                "name": item.name,
                "distribution": item.distribution,
                "parameters": item.parameters,
            }
            for item in assumptions
        ]
        saved_id = self.store.save_analysis(
            clean_name,
            self._serialize_formula_rows_for_storage() or "0",
            self.iteration_spin.value(),
            payload,
        )
        self.current_analysis_id = saved_id
        self.current_analysis_name = clean_name
        self._reload_analysis_list()
        self._update_window_caption()
        LOGGER.debug(
            "Analysis save completed | id=%s | name=%s", saved_id, clean_name
        )

    def auto_save_analysis(self) -> None:
        LOGGER.debug(
            "Auto-save triggered | current_name=%s", self.current_analysis_name
        )
        if self.current_analysis_name != "Untitled Analysis":
            self._save_analysis_named(self.current_analysis_name)
            self.statusBar().showMessage(
                f"Auto-saved: {self.current_analysis_name}", 3000
            )
            return
        self.save_analysis()

    def save_analysis(self) -> None:
        LOGGER.debug("Save analysis dialog opened")
        assumptions = self._collect_current_assumptions()
        if not assumptions:
            LOGGER.warning("Save aborted: no assumptions provided")
            QMessageBox.information(
                self,
                "Save Analysis",
                "Add at least one variable before saving.",
            )
            return

        default_name = self.current_analysis_name
        if default_name == "Untitled Analysis":
            default_name = (
                f"Analysis {datetime.now().strftime('%Y-%m-%d %H%M')}"
            )
        name, ok = QInputDialog.getText(
            self, "Save Analysis", "Analysis name:", text=default_name
        )
        if not ok:
            LOGGER.debug("Save analysis cancelled by user")
            return
        clean_name = name.strip()
        if not clean_name:
            LOGGER.warning("Save aborted: empty analysis name")
            QMessageBox.warning(
                self, "Save Analysis", "Analysis name cannot be empty."
            )
            return
        self._save_analysis_named(clean_name)

    def load_selected_analysis(
        self, _item: QListWidgetItem | None = None
    ) -> None:
        analysis_id = self._selected_analysis_id()
        if analysis_id is None:
            LOGGER.debug("Load analysis skipped: no list selection")
            return
        LOGGER.debug("Loading selected analysis | id=%s", analysis_id)
        record = self.store.get_analysis(analysis_id)
        if record is None:
            QMessageBox.warning(
                self, "Load Analysis", "Selected analysis was not found."
            )
            self._reload_analysis_list()
            return

        self.assumption_table.setRowCount(0)
        for assumption in record.assumptions:
            if not isinstance(assumption, dict):
                continue
            name = str(assumption.get("name", "")).strip()
            distribution = str(assumption.get("distribution", "")).strip()
            raw_params = assumption.get("parameters", {})
            params: dict[str, float | int] = {}
            if isinstance(raw_params, dict):
                for key, value in raw_params.items():
                    if isinstance(value, (int, float)):
                        params[str(key)] = value
            if name and distribution:
                self.add_row(
                    name=name,
                    distribution_label=distribution,
                    parameters=params,
                )

        self._load_formula_rows_from_text(record.formula)
        self.iteration_spin.setValue(record.iterations)
        self.current_analysis_id = record.analysis_id
        self.current_analysis_name = record.name
        self.last_output = None
        self.last_forecasts = {}
        self.last_forecast_order = []
        self.active_forecast_name = None
        self.last_inputs = {}
        self.last_stats = {}
        self.last_capability = {}
        self.last_capability_by_forecast = {}
        self.last_forecast_specs = {}
        self.stats_label.setText("Run a simulation to view results")
        self.canvas.draw_message("Run a simulation to display charts")
        self._sync_row_actions()
        self._update_window_caption()
        LOGGER.debug(
            "Analysis loaded into workspace | id=%s | name=%s",
            record.analysis_id,
            record.name,
        )

    def load_defaults(self) -> None:
        LOGGER.debug("Loading default assumptions")
        self.add_row(
            name="revenue",
            distribution_label="Normal",
            parameters={"mu": 120, "sigma": 15},
        )
        self.add_row(
            name="cost",
            distribution_label="Tri",
            parameters={"low": 60, "peak": 75, "high": 100},
        )
        if self.formula_table.rowCount() == 0:
            self.add_formula_row("profit", "revenue - cost")

    def _report_payload(
        self,
    ) -> tuple[str, str, int, list[Assumption], str, dict[str, float]]:
        if self.last_output is None or not self.last_stats:
            raise ValueError("Run simulation before exporting reports")

        assumptions = self._collect_current_assumptions()
        if not assumptions:
            raise ValueError("No assumptions available for report export")

        analysis_name = self.current_analysis_name
        formula = self._serialize_formula_rows() or "0"
        iterations = self.iteration_spin.value()
        active_forecast_name = self.active_forecast_name or "forecast"
        capability_metrics = dict(self.last_capability)
        return (
            analysis_name,
            formula,
            iterations,
            assumptions,
            active_forecast_name,
            capability_metrics,
        )

    def _run_export_async(
        self,
        task: Callable[[], None],
        *,
        progress_message: str,
        success_title: str,
        success_message: str,
        failure_title: str,
    ) -> None:
        thread = QThread(self)
        worker = _ReportExportWorker(task)
        worker.moveToThread(thread)
        worker_id = id(worker)

        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(self._handle_export_success)
        worker.failed.connect(self._handle_export_failure)
        thread.finished.connect(thread.deleteLater)

        self._active_export_threads.append((thread, worker))
        self._export_jobs[worker_id] = (
            thread,
            success_title,
            success_message,
            failure_title,
        )
        self.statusBar().showMessage(progress_message)
        thread.start()

    def _release_export_worker(self, thread: QThread, worker: object) -> None:
        self._active_export_threads = [
            pair
            for pair in self._active_export_threads
            if pair[0] is not thread and pair[1] is not worker
        ]

    def _has_running_exports(self) -> bool:
        return any(
            thread.isRunning()
            for thread, _worker in self._active_export_threads
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._has_running_exports():
            QMessageBox.warning(
                self,
                "Export In Progress",
                "A PDF/PPT export is still running. Please wait for it to finish before closing the application.",
            )
            event.ignore()
            return
        super().closeEvent(event)

    def _handle_export_success(self, _unused: str = "") -> None:
        worker = self.sender()
        if not isinstance(worker, _ReportExportWorker):
            return
        job = self._export_jobs.pop(id(worker), None)
        if job is None:
            return

        thread, title, message, _failure_title = job
        self._release_export_worker(thread, worker)
        self.statusBar().showMessage(message, 5000)
        QMessageBox.information(self, title, message)

    def _handle_export_failure(self, detail: str) -> None:
        worker = self.sender()
        if not isinstance(worker, _ReportExportWorker):
            return
        job = self._export_jobs.pop(id(worker), None)
        if job is None:
            return

        thread, _success_title, _success_message, title = job
        self._release_export_worker(thread, worker)
        LOGGER.error("Report export failed\n%s", detail)
        lines = [line.strip() for line in detail.splitlines() if line.strip()]
        summary = lines[-1] if lines else "Export failed"
        self.statusBar().showMessage(summary, 8000)
        QMessageBox.critical(self, title, summary)

    def export_pdf_report(self) -> None:
        try:
            (
                analysis_name,
                formula,
                iterations,
                assumptions,
                active_forecast_name,
                capability_metrics,
            ) = self._report_payload()
        except ValueError as exc:
            QMessageBox.information(self, "Export PDF Report", str(exc))
            return

        base_name = (
            analysis_name.replace(" ", "_") if analysis_name else "Vatic_report"
        )
        default_name = f"{base_name}.pdf"
        file_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export PDF Report",
            str(Path.cwd() / default_name),
            "PDF Files (*.pdf)",
        )
        if not file_path:
            return

        destination = Path(file_path)
        if destination.suffix.lower() != ".pdf":
            destination = destination.with_suffix(".pdf")

        report_stats = dict(self.last_stats)
        report_output = np.asarray(self.last_output, dtype=float).copy()
        report_inputs = {
            name: np.asarray(series, dtype=float).copy()
            for name, series in self.last_inputs.items()
        }

        def task() -> None:
            write_pdf_report(
                destination=destination,
                analysis_name=analysis_name,
                formula=formula,
                iterations=iterations,
                assumptions=assumptions,
                stats=report_stats,
                output=report_output,
                inputs=report_inputs,
                active_forecast_name=active_forecast_name,
                capability_metrics=capability_metrics,
            )

        self._run_export_async(
            task,
            progress_message="Exporting PDF report...",
            success_title="Export PDF Report",
            success_message=f"Report exported to:\n{destination}",
            failure_title="Export PDF Report",
        )

    def export_powerpoint_report(self) -> None:
        try:
            (
                analysis_name,
                formula,
                iterations,
                assumptions,
                active_forecast_name,
                capability_metrics,
            ) = self._report_payload()
        except ValueError as exc:
            QMessageBox.information(self, "Export PowerPoint Report", str(exc))
            return

        base_name = (
            analysis_name.replace(" ", "_") if analysis_name else "Vatic_report"
        )
        default_name = f"{base_name}.pptx"
        file_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export PowerPoint Report",
            str(Path.cwd() / default_name),
            "PowerPoint Files (*.pptx)",
        )
        if not file_path:
            return

        destination = Path(file_path)
        if destination.suffix.lower() != ".pptx":
            destination = destination.with_suffix(".pptx")

        report_stats = dict(self.last_stats)
        report_output = np.asarray(self.last_output, dtype=float).copy()
        report_inputs = {
            name: np.asarray(series, dtype=float).copy()
            for name, series in self.last_inputs.items()
        }

        def task() -> None:
            write_pptx_report(
                destination=destination,
                analysis_name=analysis_name,
                formula=formula,
                iterations=iterations,
                assumptions=assumptions,
                stats=report_stats,
                output=report_output,
                inputs=report_inputs,
                active_forecast_name=active_forecast_name,
                capability_metrics=capability_metrics,
            )

        self._run_export_async(
            task,
            progress_message="Exporting PowerPoint report...",
            success_title="Export PowerPoint Report",
            success_message=f"Report exported to:\n{destination}",
            failure_title="Export PowerPoint Report",
        )

    def _distribution_spec_for_row(self, row: int):
        widget = self.assumption_table.cellWidget(row, 1)
        if not isinstance(widget, QComboBox):
            raise ValueError(f"Row {row + 1}: missing distribution selector")
        return get_distribution_spec(widget.currentText())

    def _distribution_changed(self) -> None:
        sender = self.sender()
        if not isinstance(sender, QComboBox):
            return
        for row in range(self.assumption_table.rowCount()):
            if self.assumption_table.cellWidget(row, 1) is sender:
                spec = self._distribution_spec_for_row(row)
                LOGGER.debug(
                    "Distribution changed | row=%s | distribution=%s",
                    row,
                    spec.label,
                )
                self._set_row_parameters(row, default_parameters(spec))
                return

    def _set_row_parameters(
        self, row: int, values: dict[str, float | int]
    ) -> None:
        summary = ", ".join(f"{k}={v}" for k, v in values.items())
        item = self.assumption_table.item(row, 2)
        if item is None:
            item = QTableWidgetItem(summary)
            self.assumption_table.setItem(row, 2, item)
        else:
            item.setText(summary)

        item.setData(Qt.UserRole, dict(values))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)

    def _get_row_parameters(self, row: int) -> dict[str, float | int]:
        item = self.assumption_table.item(row, 2)
        if item is None:
            return {}
        payload = item.data(Qt.UserRole)
        if isinstance(payload, dict):
            return payload
        return {}

    def _parse_assumptions(self) -> list[Assumption]:
        assumptions: list[Assumption] = []
        for row in range(self.assumption_table.rowCount()):
            name_item = self.assumption_table.item(row, 0)
            name = name_item.text().strip() if name_item else ""
            if not name:
                continue

            spec = self._distribution_spec_for_row(row)
            parameters = self._get_row_parameters(row)
            if not parameters:
                raise ValueError(
                    f"Row {row + 1}: open parameter popup and define values for {spec.label}"
                )

            assumptions.append(
                Assumption(
                    name=name, distribution=spec.label, parameters=parameters
                )
            )

        if not assumptions:
            raise ValueError("Add at least one assumption")
        LOGGER.debug(
            "Parsed assumptions successfully | count=%s", len(assumptions)
        )
        return assumptions

    def _parse_forecast_definitions(
        self, reserved_names: set[str]
    ) -> list[dict[str, object]]:
        definitions: list[dict[str, object]] = []
        seen = set(reserved_names)

        for row in range(self.formula_table.rowCount()):
            name_item = self.formula_table.item(row, 0)
            expr_item = self.formula_table.item(row, 1)
            lsl_item = self.formula_table.item(row, 2)
            usl_item = self.formula_table.item(row, 3)
            target_item = self.formula_table.item(row, 4)

            forecast_name = name_item.text().strip() if name_item else ""
            expression = expr_item.text().strip() if expr_item else ""
            lsl_text = lsl_item.text().strip() if lsl_item else ""
            usl_text = usl_item.text().strip() if usl_item else ""
            target_text = target_item.text().strip() if target_item else ""

            if not forecast_name and not expression:
                continue
            if not forecast_name:
                raise ValueError(f"Formula row {row + 1}: name is required")
            if not expression:
                raise ValueError(
                    f"Formula row {row + 1}: expression is required"
                )

            if not forecast_name.isidentifier():
                raise ValueError(
                    f"Invalid forecast name '{forecast_name}'. Use letters, numbers, and underscore only."
                )
            if forecast_name in seen:
                raise ValueError(f"Duplicate forecast name: {forecast_name}")

            lsl = self._parse_optional_float(lsl_text, "LSL", row + 1)
            usl = self._parse_optional_float(usl_text, "USL", row + 1)
            target = self._parse_optional_float(target_text, "Target", row + 1)
            if lsl is not None and usl is not None and lsl > usl:
                raise ValueError(
                    f"Formula row {row + 1}: LSL cannot be greater than USL"
                )

            definitions.append({
                "name": forecast_name,
                "expression": expression,
                "lsl": lsl,
                "usl": usl,
                "target": target,
            })
            seen.add(forecast_name)

        LOGGER.debug(
            "Parsed forecast definitions | count=%s | names=%s",
            len(definitions),
            [str(item["name"]) for item in definitions],
        )
        if not definitions:
            raise ValueError("Add at least one forecast formula row")
        return definitions

    def _parse_optional_float(
        self, text: str, label: str, row_index: int
    ) -> float | None:
        if not text:
            return None
        try:
            return float(text)
        except ValueError as exc:
            raise ValueError(
                f"Formula row {row_index}: {label} must be numeric"
            ) from exc

    def run_simulation(self) -> None:
        try:
            assumptions = self._parse_assumptions()
            formula_text = self._serialize_formula_rows()

            mcerp.npts = self.iteration_spin.value()
            LOGGER.info(
                "Starting simulation | iterations=%s | assumptions=%s | formulas=%s",
                mcerp.npts,
                len(assumptions),
                formula_text,
            )

            variables: dict[str, object] = {}
            for assumption in assumptions:
                if assumption.name in variables:
                    raise ValueError(
                        f"Duplicate assumption name: {assumption.name}"
                    )
                spec = get_distribution_spec(assumption.distribution)
                LOGGER.info(
                    "Assumption | name=%s | dist=%s | params=%s",
                    assumption.name,
                    spec.label,
                    assumption.parameters,
                )
                variables[assumption.name] = build_variable(
                    assumption.name, spec, assumption.parameters
                )

            definitions = self._parse_forecast_definitions(
                reserved_names=set(variables.keys())
            )
            forecast_outputs: dict[str, np.ndarray] = {}
            forecast_specs: dict[str, dict[str, float | None]] = {}
            forecast_capability: dict[str, dict[str, float]] = {}
            computed: dict[str, object] = {}

            for definition in definitions:
                forecast_name = str(definition["name"])
                expression = str(definition["expression"])
                context = {**variables, **computed}
                outcome = evaluate_formula(expression, context)
                computed[forecast_name] = outcome
                forecast_outputs[forecast_name] = self._extract_output_values(
                    outcome
                )
                lsl = definition["lsl"]
                usl = definition["usl"]
                target = definition["target"]
                forecast_specs[forecast_name] = {
                    "lsl": lsl,
                    "usl": usl,
                    "target": target,
                }
                forecast_capability[forecast_name] = compute_capability_metrics(
                    forecast_outputs[forecast_name],
                    lsl=lsl,
                    usl=usl,
                    target=target,
                )

            self.last_forecasts = forecast_outputs
            self.last_forecast_order = [
                str(item["name"]) for item in definitions
            ]
            self.active_forecast_name = self.last_forecast_order[-1]
            self.last_output = self.last_forecasts[self.active_forecast_name]
            self.last_forecast_specs = forecast_specs
            self.last_capability_by_forecast = forecast_capability
            self.last_capability = dict(
                self.last_capability_by_forecast.get(
                    self.active_forecast_name, {}
                )
            )
            self.last_inputs = {
                name: np.asarray(var._mcpts, dtype=float).copy()
                for name, var in variables.items()
                if hasattr(var, "_mcpts")
            }

            self.last_stats = compute_statistics(self.last_output)
            self._update_statistics_label()
            self._refresh_scatter_variable_combo()
            self.render_selected_chart()

            LOGGER.info(
                "Simulation complete | forecasts=%s | active=%s | samples=%s | mean=%.6f | std=%.6f | p_loss=%.6f",
                len(self.last_forecasts),
                self.active_forecast_name,
                int(self.last_stats["samples"]),
                self.last_stats["mean"],
                self.last_stats["std"],
                self.last_stats["prob_loss"],
            )
        except Exception as exc:
            LOGGER.exception("Simulation failed")
            self._invalidate_simulation_results()
            QMessageBox.critical(self, "Simulation Error", str(exc))

    def _extract_output_values(self, outcome: object) -> np.ndarray:
        if hasattr(outcome, "_mcpts"):
            values = np.asarray(outcome._mcpts, dtype=float)
        elif np.isscalar(outcome):
            values = np.full(mcerp.npts, float(outcome), dtype=float)
        else:
            values = np.asarray(outcome, dtype=float)

        if values.size == 0:
            raise ValueError("Simulation output is empty")
        LOGGER.debug(
            "Extracted simulation output values | count=%s", values.size
        )
        return values.copy()

    def _refresh_scatter_variable_combo(self) -> None:
        current = self.scatter_var_combo.currentText()
        self.scatter_var_combo.blockSignals(True)
        self.scatter_var_combo.clear()
        forecast_options = [
            f"Forecast: {name}" for name in self.last_forecast_order
        ]
        options = [*forecast_options, *sorted(self.last_inputs.keys())]
        self.scatter_var_combo.addItems(options)
        if current:
            idx = self.scatter_var_combo.findText(current)
            if idx >= 0:
                self.scatter_var_combo.setCurrentIndex(idx)
        if (
            self.scatter_var_combo.currentIndex() < 0
            and self.active_forecast_name
        ):
            target = f"Forecast: {self.active_forecast_name}"
            idx = self.scatter_var_combo.findText(target)
            if idx >= 0:
                self.scatter_var_combo.setCurrentIndex(idx)
        self.scatter_var_combo.blockSignals(False)
        LOGGER.debug(
            "Scatter variable choices refreshed | options=%s",
            self.scatter_var_combo.count(),
        )

    def _selected_series(self) -> tuple[str, np.ndarray | None, bool]:
        name = self.scatter_var_combo.currentText().strip()
        if not name:
            return "", None, False
        if name.startswith("Forecast: "):
            forecast_name = name.removeprefix("Forecast: ").strip()
            self.active_forecast_name = (
                forecast_name or self.active_forecast_name
            )
            values = self.last_forecasts.get(forecast_name)
            if values is not None:
                self.last_output = values
                self.last_stats = compute_statistics(values)
                self.last_capability = dict(
                    self.last_capability_by_forecast.get(forecast_name, {})
                )
                self._update_statistics_label()
            return forecast_name, values, True
        return name, self.last_inputs.get(name), False

    def _update_statistics_label(self) -> None:
        s = self.last_stats
        forecast_name = self.active_forecast_name or "forecast"
        summary_rows = [
            ("Forecast", forecast_name),
            ("Samples", f"{int(s['samples']):,}"),
            ("Mean", f"{s['mean']:,.4f}"),
            ("Std Dev", f"{s['std']:,.4f}"),
            ("Min / Max", f"{s['min']:,.4f} / {s['max']:,.4f}"),
            ("P01", f"{s['p01']:,.4f}"),
            ("P05", f"{s['p05']:,.4f}"),
            ("Median", f"{s['p50']:,.4f}"),
            ("P95", f"{s['p95']:,.4f}"),
            ("P99", f"{s['p99']:,.4f}"),
            ("Probability(Output < 0)", f"{s['prob_loss']:.2%}"),
        ]

        cap = self.last_capability
        capability_rows: list[tuple[str, str]] = []
        if cap:
            if "lsl" in cap or "usl" in cap or "target" in cap:
                lsl_text = f"{cap['lsl']:,.4f}" if "lsl" in cap else "None"
                usl_text = f"{cap['usl']:,.4f}" if "usl" in cap else "None"
                target_text = (
                    f"{cap['target']:,.4f}" if "target" in cap else "None"
                )
                capability_rows.append((
                    "LSL / USL / Target",
                    f"{lsl_text} / {usl_text} / {target_text}",
                ))
            if "Cp" in cap or "Cpk" in cap:
                cp_text = f"{cap['Cp']:.4f}" if "Cp" in cap else "N/A"
                cpk_text = f"{cap['Cpk']:.4f}" if "Cpk" in cap else "N/A"
                capability_rows.append(("Cp / Cpk", f"{cp_text} / {cpk_text}"))
            if "Pp" in cap or "Ppk" in cap:
                pp_text = f"{cap['Pp']:.4f}" if "Pp" in cap else "N/A"
                ppk_text = f"{cap['Ppk']:.4f}" if "Ppk" in cap else "N/A"
                capability_rows.append(("Pp / Ppk", f"{pp_text} / {ppk_text}"))
            if "p(N/C)-below" in cap or "p(N/C)-above" in cap:
                below = (
                    f"{cap['p(N/C)-below']:.4%}"
                    if "p(N/C)-below" in cap
                    else "N/A"
                )
                above = (
                    f"{cap['p(N/C)-above']:.4%}"
                    if "p(N/C)-above" in cap
                    else "N/A"
                )
                capability_rows.append(("P(below/above)", f"{below} / {above}"))
            if "PPM-total" in cap:
                capability_rows.append((
                    "PPM-total",
                    f"{cap['PPM-total']:,.2f}",
                ))
            if "Zst" in cap or "Zlt" in cap:
                zst = f"{cap['Zst']:.4f}" if "Zst" in cap else "N/A"
                zlt = f"{cap['Zlt']:.4f}" if "Zlt" in cap else "N/A"
                capability_rows.append(("Zst / Zlt", f"{zst} / {zlt}"))

        label_width = max(
            [len(label) for label, _ in summary_rows]
            + [len(label) for label, _ in capability_rows]
            + [len("Capability Metrics")]
        )
        lines = [
            f"{label:<{label_width}}  {value}" for label, value in summary_rows
        ]
        if capability_rows:
            lines.append("")
            lines.append("Capability Metrics")
            lines.extend(
                f"{label:<{label_width}}  {value}"
                for label, value in capability_rows
            )

        self.stats_label.setText("\n".join(lines))

    def render_selected_chart(self) -> None:
        if self.last_output is None:
            self.canvas.draw_message("Run a simulation to display charts")
            return

        chart = self.chart_type_combo.currentText()
        LOGGER.debug("Rendering selected chart | type=%s", chart)
        series_name, series_values, is_forecast_series = self._selected_series()
        output_series_charts = {
            "Histogram",
            "CDF",
            "Exceedance",
            "VaR / CVaR",
            "Density (KDE)",
            "Q-Q Normal",
            "Pareto",
            "Trend",
        }

        if chart in output_series_charts:
            if series_values is None:
                self.canvas.draw_message(
                    "Select a valid series to render this chart"
                )
                return

        if chart == "Histogram":
            self.canvas.draw_histogram(series_values)
        elif chart == "CDF":
            self.canvas.draw_cdf(series_values)
        elif chart == "Exceedance":
            self.canvas.draw_exceedance(series_values)
        elif chart == "VaR / CVaR":
            self.canvas.draw_var_cvar(series_values, confidence=0.95)
        elif chart == "Density (KDE)":
            self.canvas.draw_kde(series_values)
        elif chart == "Q-Q Normal":
            self.canvas.draw_qq_normal(series_values)
        elif chart == "Pareto":
            self.canvas.draw_pareto(series_values)
        elif chart == "Trend":
            self.canvas.draw_trend(series_values)
        elif chart == "Scatter":
            if series_values is None:
                self.canvas.draw_message(
                    "Select a valid series to render scatter"
                )
                return
            if is_forecast_series:
                x = np.arange(1, series_values.size + 1, dtype=float)
                self.canvas.draw_scatter(x, series_values, "Iteration")
                return
            self.canvas.draw_scatter(
                series_values, self.last_output, series_name
            )
        elif chart == "Tornado":
            points = tornado_correlations(self.last_inputs, self.last_output)
            self.canvas.draw_tornado(points)
        elif chart == "Box":
            groups = dict(self.last_inputs)
            groups["Forecast"] = self.last_output
            self.canvas.draw_box(groups)
        elif chart == "Violin":
            groups = dict(self.last_inputs)
            groups["Forecast"] = self.last_output
            self.canvas.draw_violin(groups)
        elif chart == "Rich Statistics":
            self.canvas.draw_statistics(self.last_stats)
        else:
            self.canvas.draw_message(f"Unsupported chart type: {chart}")
