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

import numpy as np
import plotly.graph_objects as go
from PySide6.QtWebEngineWidgets import QWebEngineView
from scipy import stats

from vatic.logger import get_logger


LOGGER = get_logger(__name__)


class PlotCanvas(QWebEngineView):
    def __init__(self) -> None:
        super().__init__()
        self.setContextMenuPolicy(self.contextMenuPolicy())
        self.draw_message("Run a simulation to display charts")

    def _base_layout(self, title: str) -> go.Layout:
        return go.Layout(
            title=title,
            template="plotly_white",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#f8fbff",
            margin=dict(l=70, r=50, t=70, b=60),
            font=dict(family="Segoe UI, sans-serif", size=12, color="#10233f"),
            hovermode="closest",
        )

    def _render(self, figure: go.Figure) -> None:
        html = figure.to_html(
            include_plotlyjs="cdn",
            full_html=False,
            config={
                "displaylogo": False,
                "responsive": True,
                "scrollZoom": True,
            },
        )
        self.setHtml(html)

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
                    color="#2A9D8F", line=dict(color="#264653", width=1)
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
                line=dict(color="#1D3557", width=2),
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
                line=dict(color="#E76F51", width=2),
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
                    color="#8ECAE6", line=dict(color="#1D3557", width=1)
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
                line=dict(color="#E76F51", width=2, dash="dash"),
                name=f"VaR {confidence:.0%}",
                hovertemplate=f"VaR {confidence:.0%}: {var_threshold:,.4f}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[cvar_value, cvar_value],
                y=[0.0, y_max],
                mode="lines",
                line=dict(color="#D00000", width=2, dash="dot"),
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
            font=dict(color="#9C2D1D", size=12),
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
            font=dict(color="#7A0000", size=12),
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
                line=dict(color="#2A9D8F", width=2.5),
                fill="tozeroy",
                fillcolor="rgba(42,157,143,0.22)",
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
                marker=dict(size=6, color="#3A7CA5", opacity=0.6),
                hovertemplate="Theoretical=%{x:.4f}<br>Observed=%{y:.4f}<extra></extra>",
                name="Sample quantiles",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=theoretical,
                y=fit_line,
                mode="lines",
                line=dict(color="#E76F51", width=2),
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
                marker=dict(color="#3A7CA5"),
                name="Frequency",
                hovertemplate="Bucket=%{x}<br>Frequency=%{y}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=cumulative,
                mode="lines+markers",
                marker=dict(color="#E76F51", size=8),
                line=dict(color="#E76F51", width=2),
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
                line=dict(color="#1D3557", width=2.2),
                name="Running mean",
                hovertemplate="Iteration=%{x}<br>Mean=%{y:.4f}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=sampled,
                mode="lines",
                line=dict(color="#A8DADC", width=1),
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
                marker=dict(color="#457B9D", size=6, opacity=0.45),
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
        colors = ["#E76F51" if value < 0 else "#2A9D8F" for value in values]

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
        for name, values in groups.items():
            fig.add_trace(
                go.Box(
                    x=values,
                    name=name,
                    boxpoints=False,
                    marker=dict(color="#3A7CA5"),
                    line=dict(color="#1D3557"),
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
        for name, values in groups.items():
            fig.add_trace(
                go.Violin(
                    x=values,
                    name=name,
                    box_visible=True,
                    meanline_visible=True,
                    points=False,
                    line_color="#1D3557",
                    fillcolor="rgba(69,123,157,0.35)",
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
                        fill_color="#1D3557",
                        font=dict(color="white", size=13),
                        align="left",
                    ),
                    cells=dict(
                        values=[labels, values],
                        fill_color=["#f8fbff", "#ffffff"],
                        align="left",
                        font=dict(color="#10233f", size=12),
                        height=30,
                    ),
                )
            ]
        )
        fig.update_layout(
            title="Rich Statistics",
            template="plotly_white",
            margin=dict(l=40, r=40, t=70, b=20),
            paper_bgcolor="#ffffff",
            font=dict(family="Segoe UI, sans-serif", size=12, color="#10233f"),
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
                    font=dict(size=16, color="#264653"),
                )
            ],
        )
        self._render(fig)
