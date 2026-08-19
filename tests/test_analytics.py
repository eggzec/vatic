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
#      Statistics and process-capability maths, checked against closed-form
#      values rather than against the implementation itself.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats as sps

from vatic.analytics import compute_capability_metrics, compute_statistics


def test_moments_match_closed_form() -> None:
    """Mean, variance and extrema agree with hand computation."""
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    result = compute_statistics(values)

    assert result["samples"] == 5.0
    assert result["mean"] == pytest.approx(3.0)
    # Population variance, matching the reference implementation.
    assert result["variance"] == pytest.approx(2.0)
    # Sample standard deviation, ddof=1.
    assert result["std"] == pytest.approx(math.sqrt(2.5))
    assert result["min"] == pytest.approx(1.0)
    assert result["max"] == pytest.approx(5.0)
    assert result["p50"] == pytest.approx(3.0)


def test_skewness_and_kurtosis_use_reference_conventions() -> None:
    """Skewness is biased g1 and kurtosis is Pearson, not the excess form."""
    generator = np.random.default_rng(20260819)
    values = generator.gamma(shape=2.0, scale=1.5, size=50_000)

    result = compute_statistics(values)

    # scipy's defaults are the biased estimators, which is what the reference
    # implementation computes by hand.
    assert result["skewness"] == pytest.approx(sps.skew(values), rel=1e-9)
    assert result["kurtosis"] == pytest.approx(
        sps.kurtosis(values, fisher=False), rel=1e-9
    )
    # Pearson and excess kurtosis differ by exactly three.
    assert result["kurtosis_excess"] == pytest.approx(result["kurtosis"] - 3.0)


def test_symmetric_sample_has_zero_skew_and_normal_kurtosis() -> None:
    """A large normal sample lands on skew 0 and Pearson kurtosis 3."""
    generator = np.random.default_rng(7)
    values = generator.normal(loc=10.0, scale=2.0, size=200_000)

    result = compute_statistics(values)

    assert result["skewness"] == pytest.approx(0.0, abs=0.02)
    assert result["kurtosis"] == pytest.approx(3.0, abs=0.05)


def test_constant_sample_reports_zero_shape() -> None:
    """A zero-variance sample must not divide by zero."""
    result = compute_statistics(np.full(1000, 4.2))

    assert result["variance"] == pytest.approx(0.0)
    assert result["skewness"] == 0.0
    assert result["kurtosis"] == 0.0


def test_empty_sample_is_rejected() -> None:
    """An empty sample is a caller error, not a silent NaN."""
    with pytest.raises(ValueError):
        compute_statistics(np.array([]))


def _capability_reference(
    values: np.ndarray, lsl: float, usl: float, zshift: float = 1.5
) -> dict[str, float]:
    """Compute capability metrics independently for comparison.

    Args:
        values: Sample to measure.
        lsl: Lower spec limit.
        usl: Upper spec limit.
        zshift: Long-term shift applied to Zst.

    Returns:
        The reference metrics.
    """
    mean = float(np.mean(values))
    sigma = float(np.std(values, ddof=1))
    p_below = float(sps.norm.cdf((lsl - mean) / sigma))
    p_above = float(1.0 - sps.norm.cdf((usl - mean) / sigma))
    p_total = p_below + p_above
    return {
        "Cp": (usl - lsl) / (6.0 * sigma),
        "Cpk": min((mean - lsl) / (3.0 * sigma), (usl - mean) / (3.0 * sigma)),
        "p(N/C)-total": p_total,
        "PPM-total": p_total * 1e6,
        "Zst": float(-sps.norm.ppf(p_total)),
        "Zlt": float(-sps.norm.ppf(p_total)) - zshift,
    }


def test_capability_metrics_match_independent_reference() -> None:
    """Cp, Cpk, PPM and the Z scores agree with a separate derivation."""
    generator = np.random.default_rng(1234)
    values = generator.normal(loc=10.0, scale=1.0, size=100_000)

    metrics = compute_capability_metrics(values, lsl=7.0, usl=13.0, target=10.0)
    expected = _capability_reference(values, lsl=7.0, usl=13.0)

    for key, value in expected.items():
        assert metrics[key] == pytest.approx(value, rel=1e-9), key


def test_capability_uses_the_cumulative_distribution() -> None:
    """A centred 6-sigma process is near zero defects.

    The reference implementation used the probability *density* here, which
    put the defect rate off by orders of magnitude, so this pins the
    cumulative form down.
    """
    generator = np.random.default_rng(99)
    values = generator.normal(loc=0.0, scale=1.0, size=200_000)

    metrics = compute_capability_metrics(values, lsl=-6.0, usl=6.0, target=0.0)

    assert metrics["Cp"] == pytest.approx(2.0, rel=0.02)
    assert metrics["PPM-total"] < 1.0
    assert metrics["Zst"] > 4.0


def test_long_term_z_is_shifted_from_short_term() -> None:
    """Zlt is Zst less the shift; the reference left them identical."""
    generator = np.random.default_rng(5)
    values = generator.normal(loc=0.0, scale=1.0, size=50_000)

    metrics = compute_capability_metrics(values, lsl=-3.0, usl=3.0, target=0.0)

    assert metrics["Zst"] - metrics["Zlt"] == pytest.approx(1.5)


def test_cpm_is_penalised_by_being_off_target() -> None:
    """Cpm falls below Cp once the mean drifts away from target.

    The reference implementation wrote this exponent with ``^``, which is
    bitwise XOR in Python, so the metric could never be produced at all.
    """
    generator = np.random.default_rng(11)
    centred = generator.normal(loc=10.0, scale=1.0, size=50_000)
    metrics = compute_capability_metrics(
        centred, lsl=7.0, usl=13.0, target=10.0
    )
    assert metrics["Cpm"] == pytest.approx(metrics["Cp"], rel=0.02)

    drifted = centred + 1.5
    off = compute_capability_metrics(drifted, lsl=7.0, usl=13.0, target=10.0)
    assert off["Cpm"] < off["Cp"]


def test_one_sided_specification_omits_two_sided_metrics() -> None:
    """With only an upper limit there is no Cp and no total defect rate."""
    generator = np.random.default_rng(3)
    values = generator.normal(loc=0.0, scale=1.0, size=20_000)

    metrics = compute_capability_metrics(values, lsl=None, usl=2.0, target=None)

    assert "Cp" not in metrics
    assert "p(N/C)-total" not in metrics
    assert "Cpk-upper" in metrics
    assert "PPM-above" in metrics
