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
#      Statistics and sensitivity helper calculations.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import numpy as np
from scipy.stats import norm

from vatic.logger import get_logger


LOGGER = get_logger(__name__)


def compute_statistics(values: np.ndarray) -> dict[str, float]:
    if values.size == 0:
        raise ValueError("Cannot compute statistics for empty output")

    LOGGER.debug("Computing statistics | sample_count=%s", values.size)

    percentiles = np.percentile(values, [1, 5, 50, 95, 99])
    return {
        "samples": float(values.size),
        "mean": float(np.mean(values)),
        "std": float(np.std(values, ddof=1)) if values.size > 1 else 0.0,
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "p01": float(percentiles[0]),
        "p05": float(percentiles[1]),
        "p50": float(percentiles[2]),
        "p95": float(percentiles[3]),
        "p99": float(percentiles[4]),
        "prob_loss": float(np.mean(values < 0.0)),
    }


def tornado_correlations(
    input_samples: dict[str, np.ndarray], output_values: np.ndarray
) -> list[tuple[str, float]]:
    LOGGER.debug(
        "Computing tornado correlations | inputs=%s | output_size=%s",
        len(input_samples),
        output_values.size,
    )
    points: list[tuple[str, float]] = []
    output_std = float(np.std(output_values))
    if output_std == 0.0:
        return points

    for name, series in input_samples.items():
        if series.size != output_values.size:
            continue
        if float(np.std(series)) == 0.0:
            continue
        corr = float(np.corrcoef(series, output_values)[0, 1])
        if np.isnan(corr):
            continue
        points.append((name, corr))

    points.sort(key=lambda item: abs(item[1]), reverse=True)
    LOGGER.debug("Tornado correlations computed | points=%s", len(points))
    return points


def compute_capability_metrics(
    values: np.ndarray,
    *,
    lsl: float | None,
    usl: float | None,
    target: float | None,
    zshift: float = 1.5,
) -> dict[str, float]:
    if values.size == 0:
        return {}

    mean = float(np.mean(values))
    sigma = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
    if sigma <= 0.0:
        return {
            "mean": mean,
            "sigma": sigma,
            "lsl": float(lsl) if lsl is not None else np.nan,
            "usl": float(usl) if usl is not None else np.nan,
            "target": float(target) if target is not None else np.nan,
        }

    metrics: dict[str, float] = {"mean": mean, "sigma": sigma}
    if lsl is not None:
        metrics["lsl"] = float(lsl)
    if usl is not None:
        metrics["usl"] = float(usl)
    if target is not None:
        metrics["target"] = float(target)

    if lsl is not None and usl is not None:
        spread = float(usl - lsl)
        metrics["Cp"] = spread / (6.0 * sigma)
        metrics["Pp"] = spread / (6.0 * sigma)

    if lsl is not None:
        cpk_lower = (mean - float(lsl)) / (3.0 * sigma)
        metrics["Cpk-lower"] = cpk_lower
        metrics["Ppk-lower"] = cpk_lower
        z_lsl = (mean - float(lsl)) / sigma
        p_below = float(norm.cdf((float(lsl) - mean) / sigma))
        metrics["Z-LSL"] = z_lsl
        metrics["p(N/C)-below"] = p_below
        metrics["PPM-below"] = p_below * 1_000_000.0

    if usl is not None:
        cpk_upper = (float(usl) - mean) / (3.0 * sigma)
        metrics["Cpk-upper"] = cpk_upper
        metrics["Ppk-upper"] = cpk_upper
        z_usl = (float(usl) - mean) / sigma
        p_above = float(1.0 - norm.cdf((float(usl) - mean) / sigma))
        metrics["Z-USL"] = z_usl
        metrics["p(N/C)-above"] = p_above
        metrics["PPM-above"] = p_above * 1_000_000.0

    if "Cpk-lower" in metrics and "Cpk-upper" in metrics:
        metrics["Cpk"] = min(metrics["Cpk-lower"], metrics["Cpk-upper"])
        metrics["Ppk"] = min(metrics["Ppk-lower"], metrics["Ppk-upper"])

    if lsl is not None and usl is not None and target is not None:
        denom = 6.0 * float(np.sqrt(sigma**2 + (mean - float(target)) ** 2))
        if denom > 0.0:
            spread = float(usl - lsl)
            metrics["Cpm"] = spread / denom
            metrics["Ppm"] = spread / denom

    if "p(N/C)-below" in metrics and "p(N/C)-above" in metrics:
        p_total = min(1.0, metrics["p(N/C)-below"] + metrics["p(N/C)-above"])
        metrics["p(N/C)-total"] = p_total
        metrics["PPM-total"] = p_total * 1_000_000.0
        if 0.0 < p_total < 1.0:
            z_st = float(-norm.ppf(p_total))
            metrics["Zst"] = z_st
            metrics["Zlt"] = z_st - float(zshift)

    LOGGER.debug(
        "Capability metrics computed | has_lsl=%s | has_usl=%s | has_target=%s",
        lsl is not None,
        usl is not None,
        target is not None,
    )
    return metrics
