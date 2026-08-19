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
#      Interactive Plotly chart rendering canvas for UI.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from scipy import stats

from vatic.logger import get_logger
from vatic.theme import CHART_SEQUENCE, TOKENS, WHITE
from vatic.theme import alpha as rgba


LOGGER = get_logger(__name__)

CHART_PAPER = WHITE
CHART_INK = TOKENS["ink.body"]
CHART_MUTED = TOKENS["ink.muted"]
CHART_GRID = TOKENS["border.hairline"]
CHART_AXIS = TOKENS["border.subtle"]

PLOT_CONFIG = {"displaylogo": False, "responsive": True, "scrollZoom": True}

_SHELL_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><script src="plotly.min.js"></script>
<style>
  html, body {{ margin: 0; padding: 0; height: 100%;
                background: {background}; overflow: hidden; }}
  #vatic-chart {{ width: 100%; height: 100%; }}
</style></head>
<body><div id="vatic-chart"></div></body></html>
"""


def _plotly_asset_dir() -> Path:
    """Return a directory holding a local copy of ``plotly.min.js``.

    The bundled copy is written once per machine so charts never depend on a
    CDN round-trip and keep working with no network at all.

    Returns:
        Directory containing ``plotly.min.js``.
    """
    directory = Path(tempfile.gettempdir()) / "vatic-plotly"
    directory.mkdir(parents=True, exist_ok=True)

    script = directory / "plotly.min.js"
    payload = get_plotlyjs()
    if not script.exists() or script.stat().st_size != len(payload.encode()):
        script.write_text(payload, encoding="utf-8")
        LOGGER.debug("Cached plotly.js | path=%s", script)
    return directory


class PlotCanvas(QWebEngineView):
    #: Page background, kept in step with the chart paper colour so resizing
    #: and re-plotting never flashes a foreign colour.
    BACKGROUND = "#FFFFFF"

    def __init__(self) -> None:
        super().__init__()
        self.setContextMenuPolicy(self.contextMenuPolicy())

        self._ready = False
        self._pending: go.Figure | None = None

        asset_dir = _plotly_asset_dir()
        self.loadFinished.connect(self._on_load_finished)
        self.setHtml(
            _SHELL_HTML.format(background=self.BACKGROUND),
            QUrl.fromLocalFile(f"{asset_dir}/"),
        )

        self.draw_message("Run a simulation to display charts")

    def _on_load_finished(self, ok: bool) -> None:
        """Flush any figure that was requested before the page was ready.

        Args:
            ok: Whether the shell document loaded successfully.
        """
        self._ready = bool(ok)
        if not ok:
            LOGGER.warning("Chart shell failed to load; charts unavailable")
            return

        LOGGER.debug("Chart shell ready")
        if self._pending is not None:
            figure, self._pending = self._pending, None
            self._render(figure)

    def _base_layout(self, title: str) -> go.Layout:
        """Return the shared brand layout for every figure.

        Args:
            title: Chart title.

        Returns:
            A layout carrying the vatic palette, so that the charts and the
            application chrome read as a single system.
        """
        return go.Layout(
            title=dict(text=title, font=dict(color=CHART_INK, size=15)),
            template="plotly_white",
            paper_bgcolor=CHART_PAPER,
            plot_bgcolor=CHART_PAPER,
            colorway=list(CHART_SEQUENCE),
            margin=dict(l=70, r=40, t=64, b=56),
            font=dict(family="Segoe UI, sans-serif", size=12, color=CHART_INK),
            hovermode="closest",
            legend=dict(font=dict(color=CHART_MUTED, size=11)),
            xaxis=dict(
                gridcolor=CHART_GRID,
                zerolinecolor=CHART_AXIS,
                linecolor=CHART_AXIS,
                tickfont=dict(color=CHART_MUTED, size=11),
            ),
            yaxis=dict(
                gridcolor=CHART_GRID,
                zerolinecolor=CHART_AXIS,
                linecolor=CHART_AXIS,
                tickfont=dict(color=CHART_MUTED, size=11),
            ),
        )

    def _render(self, figure: go.Figure) -> None:
        """Draw ``figure`` into the already-loaded page.

        Uses ``Plotly.react`` against a persistent document rather than
        replacing the whole page, so switching chart type re-uses the parsed
        plotly.js instead of downloading and re-parsing it every time.

        Args:
            figure: The figure to display.
        """
        if not self._ready:
            self._pending = figure
            return

        payload = json.loads(figure.to_json())
        script = (
            "Plotly.react("
            "'vatic-chart',"
            f"{json.dumps(payload.get('data', []))},"
            f"{json.dumps(payload.get('layout', {}))},"
            f"{json.dumps(PLOT_CONFIG)}"
            ");"
        )
        self.page().runJavaScript(script)

    def _downsample(
        self, values: np.ndarray, max_points: int = 6000
    ) -> np.ndarray:
        if values.size <= max_points:
            return values
        idx = np.linspace(0, values.size - 1, num=max_points, dtype=int)
        return values[idx]

    def draw_histogram(self, data: np.ndarray) -> None:
        LOGGER.debug("Rendering chart | type=Histogram | points=%s", data.size)
        bins = min(70, max(20, int(np.sqrt(data.size))))
        fig = go.Figure(layout=self._base_layout("Forecast Distribution"))
        fig.add_trace(
            go.Histogram(
                x=data,
                nbinsx=bins,
                marker=dict(
                    color="#24AEFF", line=dict(color="#2323FF", width=1)
                ),
                opacity=0.9,
                hovertemplate="Outcome=%{x:.4f}<br>Frequency=%{y}<extra></extra>",
            )
        )
        fig.update_xaxes(title_text="Outcome")
        fig.update_yaxes(title_text="Frequency")
        self._render(fig)

    def draw_cdf(self, data: np.ndarray) -> None:
        LOGGER.debug("Rendering chart | type=CDF | points=%s", data.size)
        sorted_values = np.sort(data)
        cumulative = (
            np.arange(1, sorted_values.size + 1, dtype=float)
            / sorted_values.size
        )

        fig = go.Figure(
            layout=self._base_layout("Cumulative Distribution (CDF)")
        )
        fig.add_trace(
            go.Scatter(
                x=sorted_values,
                y=cumulative,
                mode="lines",
                line=dict(color="#2323FF", width=2),
                hovertemplate="Outcome=%{x:.4f}<br>CDF=%{y:.4f}<extra></extra>",
                name="CDF",
            )
        )
        fig.update_xaxes(title_text="Outcome")
        fig.update_yaxes(title_text="Probability", range=[0, 1])
        self._render(fig)

    def draw_exceedance(self, data: np.ndarray) -> None:
        LOGGER.debug("Rendering chart | type=Exceedance | points=%s", data.size)
        sorted_values = np.sort(data)
        exceedance = 1.0 - (
            np.arange(1, sorted_values.size + 1, dtype=float)
            / sorted_values.size
        )

        fig = go.Figure(layout=self._base_layout("Exceedance Curve (P(X > x))"))
        fig.add_trace(
            go.Scatter(
                x=sorted_values,
                y=exceedance,
                mode="lines",
                line=dict(color="#C04AFF", width=2),
                hovertemplate="Threshold=%{x:.4f}<br>P(X>x)=%{y:.4f}<extra></extra>",
                name="Exceedance",
            )
        )
        fig.update_xaxes(title_text="Threshold")
        fig.update_yaxes(title_text="Probability", range=[0, 1])
        self._render(fig)

    def draw_var_cvar(self, data: np.ndarray, confidence: float = 0.95) -> None:
        LOGGER.debug(
            "Rendering chart | type=VaR/CVaR | points=%s | confidence=%.3f",
            data.size,
            confidence,
        )
        alpha = 1.0 - confidence
        var_threshold = float(np.quantile(data, alpha))
        tail = data[data <= var_threshold]
        cvar_value = float(np.mean(tail)) if tail.size else var_threshold

        bins = min(70, max(20, int(np.sqrt(data.size))))
        y_max = float(np.max(np.histogram(data, bins=bins)[0]))
        if y_max <= 0.0:
            y_max = 1.0
        fig = go.Figure(
            layout=self._base_layout(f"Tail Risk (VaR/CVaR @ {confidence:.0%})")
        )
        fig.add_trace(
            go.Histogram(
                x=data,
                nbinsx=bins,
                marker=dict(
                    color="#87D2FF", line=dict(color="#2323FF", width=1)
                ),
                opacity=0.85,
                hovertemplate="Outcome=%{x:.4f}<br>Frequency=%{y}<extra></extra>",
                name="Forecast",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[var_threshold, var_threshold],
                y=[0.0, y_max],
                mode="lines",
                line=dict(color="#C04AFF", width=2, dash="dash"),
                name=f"VaR {confidence:.0%}",
                hovertemplate=f"VaR {confidence:.0%}: {var_threshold:,.4f}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[cvar_value, cvar_value],
                y=[0.0, y_max],
                mode="lines",
                line=dict(color="#772E9E", width=2, dash="dot"),
                name="CVaR",
                hovertemplate=f"CVaR: {cvar_value:,.4f}<extra></extra>",
            )
        )
        fig.update_layout(margin=dict(l=70, r=50, t=120, b=60))
        fig.add_annotation(
            x=0.01,
            y=1.08,
            xref="paper",
            yref="paper",
            xanchor="left",
            showarrow=False,
            text=f"VaR {confidence:.0%}: {var_threshold:,.4f}",
            font=dict(color="#7E3DFF", size=12),
            bgcolor="rgba(255,255,255,0.85)",
        )
        fig.add_annotation(
            x=0.99,
            y=1.08,
            xref="paper",
            yref="paper",
            xanchor="right",
            showarrow=False,
            text=f"CVaR: {cvar_value:,.4f}",
            font=dict(color="#45228C", size=12),
            bgcolor="rgba(255,255,255,0.85)",
        )
        fig.update_xaxes(title_text="Outcome")
        fig.update_yaxes(title_text="Frequency")
        self._render(fig)

    def draw_kde(self, data: np.ndarray) -> None:
        LOGGER.debug(
            "Rendering chart | type=Density (KDE) | points=%s", data.size
        )
        if data.size < 2 or np.isclose(float(np.std(data)), 0.0):
            self.draw_message(
                "KDE unavailable: output has insufficient variance"
            )
            return

        kde = stats.gaussian_kde(data)
        x_grid = np.linspace(float(np.min(data)), float(np.max(data)), 400)
        y_density = kde(x_grid)

        fig = go.Figure(layout=self._base_layout("Probability Density (KDE)"))
        fig.add_trace(
            go.Scatter(
                x=x_grid,
                y=y_density,
                mode="lines",
                line=dict(color="#2323FF", width=2.5),
                fill="tozeroy",
                fillcolor="rgba(35,35,255,0.18)",
                hovertemplate="Outcome=%{x:.4f}<br>Density=%{y:.6f}<extra></extra>",
                name="KDE",
            )
        )
        fig.update_xaxes(title_text="Outcome")
        fig.update_yaxes(title_text="Density")
        self._render(fig)

    def draw_qq_normal(self, data: np.ndarray) -> None:
        LOGGER.debug("Rendering chart | type=Q-Q Normal | points=%s", data.size)
        if data.size < 3:
            self.draw_message("Q-Q plot unavailable: need at least 3 samples")
            return

        (theoretical, observed), (slope, intercept, corr) = stats.probplot(
            data, dist="norm"
        )
        fit_line = slope * theoretical + intercept

        fig = go.Figure(layout=self._base_layout("Q-Q Plot vs Normal"))
        fig.add_trace(
            go.Scatter(
                x=theoretical,
                y=observed,
                mode="markers",
                marker=dict(size=6, color="#24AEFF", opacity=0.6),
                hovertemplate="Theoretical=%{x:.4f}<br>Observed=%{y:.4f}<extra></extra>",
                name="Sample quantiles",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=theoretical,
                y=fit_line,
                mode="lines",
                line=dict(color="#C04AFF", width=2),
                name=f"Reference line (r={corr:.4f})",
                hoverinfo="skip",
            )
        )
        fig.update_xaxes(title_text="Theoretical quantiles (Normal)")
        fig.update_yaxes(title_text="Observed quantiles")
        self._render(fig)

    def draw_pareto(self, data: np.ndarray) -> None:
        LOGGER.debug("Rendering chart | type=Pareto | points=%s", data.size)
        bins = min(24, max(8, int(np.sqrt(data.size))))
        counts, edges = np.histogram(data, bins=bins)
        order = np.argsort(counts)[::-1]
        counts = counts[order]
        labels = [f"{edges[i]:.2f}..{edges[i + 1]:.2f}" for i in order]
        cumulative = (np.cumsum(counts) / np.sum(counts)) * 100

        fig = go.Figure(layout=self._base_layout("Pareto (Binned Outcomes)"))
        fig.add_trace(
            go.Bar(
                x=labels,
                y=counts,
                marker=dict(color="#24AEFF"),
                name="Frequency",
                hovertemplate="Bucket=%{x}<br>Frequency=%{y}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=cumulative,
                mode="lines+markers",
                marker=dict(color="#C04AFF", size=8),
                line=dict(color="#C04AFF", width=2),
                name="Cumulative %",
                yaxis="y2",
                hovertemplate="Bucket=%{x}<br>Cumulative=%{y:.2f}%<extra></extra>",
            )
        )
        fig.update_layout(
            yaxis=dict(title="Frequency"),
            yaxis2=dict(
                title="Cumulative %",
                overlaying="y",
                side="right",
                range=[0, 105],
                showgrid=False,
            ),
            xaxis=dict(tickangle=45),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        )
        self._render(fig)

    def draw_trend(self, data: np.ndarray) -> None:
        LOGGER.debug("Rendering chart | type=Trend | points=%s", data.size)
        sampled = self._downsample(data)
        x = np.arange(1, sampled.size + 1)
        running_mean = np.cumsum(sampled) / x

        fig = go.Figure(layout=self._base_layout("Trend (Simulation Path)"))
        fig.add_trace(
            go.Scatter(
                x=x,
                y=running_mean,
                mode="lines",
                line=dict(color="#2323FF", width=2.2),
                name="Running mean",
                hovertemplate="Iteration=%{x}<br>Mean=%{y:.4f}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=sampled,
                mode="lines",
                line=dict(color="#9C9CFF", width=1),
                opacity=0.6,
                name="Sample outcome",
                hovertemplate="Iteration=%{x}<br>Value=%{y:.4f}<extra></extra>",
            )
        )
        fig.update_xaxes(title_text="Iteration")
        fig.update_yaxes(title_text="Value")
        self._render(fig)

    def draw_scatter(self, x: np.ndarray, y: np.ndarray, x_label: str) -> None:
        LOGGER.debug(
            "Rendering chart | type=Scatter | x_points=%s | y_points=%s | x_label=%s",
            x.size,
            y.size,
            x_label,
        )
        x_sampled = self._downsample(x)
        y_sampled = self._downsample(y, max_points=x_sampled.size)
        count = min(x_sampled.size, y_sampled.size)

        fig = go.Figure(layout=self._base_layout("Scatter (Input vs Forecast)"))
        fig.add_trace(
            go.Scattergl(
                x=x_sampled[:count],
                y=y_sampled[:count],
                mode="markers",
                marker=dict(color="#4E269E", size=6, opacity=0.45),
                hovertemplate=f"{x_label}=%{{x:.4f}}<br>Forecast=%{{y:.4f}}<extra></extra>",
                name="Samples",
            )
        )
        fig.update_xaxes(title_text=x_label)
        fig.update_yaxes(title_text="Forecast")
        self._render(fig)

    def draw_tornado(self, points: list[tuple[str, float]]) -> None:
        LOGGER.debug("Rendering chart | type=Tornado | points=%s", len(points))
        if not points:
            self.draw_message("Tornado chart unavailable: no varying inputs")
            return

        names = [name for name, _ in points]
        values = [value for _, value in points]
        colors = ["#C04AFF" if value < 0 else "#24AEFF" for value in values]

        fig = go.Figure(layout=self._base_layout("Tornado (Sensitivity)"))
        fig.add_trace(
            go.Bar(
                x=values,
                y=names,
                orientation="h",
                marker=dict(color=colors),
                hovertemplate="Variable=%{y}<br>Correlation=%{x:.4f}<extra></extra>",
                name="Correlation",
            )
        )
        fig.update_layout(showlegend=False)
        fig.update_xaxes(
            title_text="Correlation with forecast",
            range=[-1.0, 1.0],
            zeroline=True,
        )
        fig.update_yaxes(autorange="reversed")
        self._render(fig)

    def draw_box(self, groups: dict[str, np.ndarray]) -> None:
        LOGGER.debug("Rendering chart | type=Box | groups=%s", len(groups))
        fig = go.Figure(
            layout=self._base_layout("Box Plot (Inputs + Forecast)")
        )
        for index, (name, values) in enumerate(groups.items()):
            colour = CHART_SEQUENCE[index % len(CHART_SEQUENCE)]
            fig.add_trace(
                go.Box(
                    x=values,
                    name=name,
                    boxpoints=False,
                    marker=dict(color=colour),
                    line=dict(color=colour),
                    hovertemplate="%{x:.4f}<extra>%{fullData.name}</extra>",
                )
            )
        fig.update_xaxes(title_text="Value")
        self._render(fig)

    def draw_violin(self, groups: dict[str, np.ndarray]) -> None:
        LOGGER.debug("Rendering chart | type=Violin | groups=%s", len(groups))
        fig = go.Figure(
            layout=self._base_layout("Violin Plot (Inputs + Forecast)")
        )
        for index, (name, values) in enumerate(groups.items()):
            colour = CHART_SEQUENCE[index % len(CHART_SEQUENCE)]
            fig.add_trace(
                go.Violin(
                    x=values,
                    name=name,
                    box_visible=True,
                    meanline_visible=True,
                    points=False,
                    line_color=colour,
                    fillcolor=rgba(colour, 0.28),
                    hovertemplate="%{x:.4f}<extra>%{fullData.name}</extra>",
                )
            )
        fig.update_xaxes(title_text="Value")
        self._render(fig)

    def draw_statistics(self, stats: dict[str, float]) -> None:
        LOGGER.debug(
            "Rendering chart | type=Rich Statistics | samples=%s",
            int(stats["samples"]),
        )
        labels = [
            "Samples",
            "Mean",
            "Std Dev",
            "Min / Max",
            "P01 / P05",
            "P50 / P95 / P99",
            "Probability(Output < 0)",
        ]
        values = [
            f"{int(stats['samples']):,}",
            f"{stats['mean']:,.6f}",
            f"{stats['std']:,.6f}",
            f"{stats['min']:,.6f} / {stats['max']:,.6f}",
            f"{stats['p01']:,.6f} / {stats['p05']:,.6f}",
            f"{stats['p50']:,.6f} / {stats['p95']:,.6f} / {stats['p99']:,.6f}",
            f"{stats['prob_loss']:.2%}",
        ]

        fig = go.Figure(
            data=[
                go.Table(
                    header=dict(
                        values=["Metric", "Value"],
                        fill_color="#24AEFF",
                        font=dict(color="#13138C", size=13),
                        align="left",
                    ),
                    cells=dict(
                        values=[labels, values],
                        fill_color=["#FFFFFF", "#FFFFFF"],
                        align="left",
                        font=dict(color="#13138C", size=12),
                        height=30,
                    ),
                )
            ]
        )
        fig.update_layout(
            title="Rich Statistics",
            template="plotly_white",
            margin=dict(l=40, r=40, t=70, b=20),
            paper_bgcolor="#FFFFFF",
            font=dict(family="Segoe UI, sans-serif", size=12, color="#13138C"),
        )
        self._render(fig)

    def draw_message(self, message: str) -> None:
        LOGGER.debug(
            "Rendering chart placeholder message | message=%s", message
        )
        fig = go.Figure(layout=self._base_layout("Visualization"))
        fig.update_layout(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            annotations=[
                dict(
                    text=message,
                    x=0.5,
                    y=0.5,
                    xref="paper",
                    yref="paper",
                    showarrow=False,
                    font=dict(size=16, color="#0F0F6B"),
                )
            ],
        )
        self._render(fig)
