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
#      End-to-end check of the Double-D seal gland example against the
#      closed-form nominal values of the same model.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
sys.path.insert(0, str(EXAMPLES))

seal_tolerance = pytest.importorskip("seal_tolerance")


def _nominal() -> dict[str, float]:
    """Evaluate the seal model at nominal dimensions, by hand.

    Returns:
        The nominal value of every characteristic in the model.
    """
    dims = {k: v[0] for k, v in seal_tolerance.DIMENSIONS.items()}
    core_hole_area = (
        dims["core_compression"]
        * math.pi
        * (dims["core_hole_diameter"] / 2) ** 2
    )
    seal_area = (
        math.pi * (dims["seal_width"] / 4) ** 2
        + dims["seal_width"] * (dims["seal_height"] - dims["seal_width"] / 4)
        - core_hole_area
    )
    groove_area = dims["groove_width"] * (
        dims["groove_height"] + dims["lid_flatness"] + dims["box_flatness"]
    )
    return {
        "core_hole_area": core_hole_area,
        "seal_area": seal_area,
        "groove_area": groove_area,
        "gland_fill": seal_area / groove_area,
        "seal_compression": 1 - dims["groove_height"] / dims["seal_height"],
    }


@pytest.fixture(scope="module")
def results() -> dict[str, dict[str, float]]:
    """Run the stack-up once for the whole module.

    Returns:
        Statistics keyed by characteristic name.
    """
    return seal_tolerance.run()


def test_every_characteristic_is_reported(results) -> None:
    """All three intermediates and both outputs come back."""
    assert set(results) == {
        "core_hole_area",
        "seal_area",
        "groove_area",
        "gland_fill",
        "seal_compression",
    }


@pytest.mark.parametrize(
    "name",
    [
        "core_hole_area",
        "seal_area",
        "groove_area",
        "gland_fill",
        "seal_compression",
    ],
)
def test_mean_tracks_the_nominal_value(results, name: str) -> None:
    """Each simulated mean sits on the deterministic nominal value.

    Every input is symmetric about its nominal, so the mean of a
    near-linear characteristic must land on the nominal result.
    """
    expected = _nominal()[name]
    assert results[name]["mean"] == pytest.approx(expected, rel=5e-3)


def test_groove_area_is_exact_at_nominal(results) -> None:
    """Groove area is linear in its inputs, so its mean is exact."""
    assert results["groove_area"]["mean"] == pytest.approx(
        _nominal()["groove_area"], rel=1e-3
    )


def test_seal_compression_meets_its_specification(results) -> None:
    """Seal compression sits inside 0.25 .. 0.50 with capability to spare."""
    stats = results["seal_compression"]
    assert 0.25 < stats["mean"] < 0.50
    assert stats["Cpk"] > 1.0
    assert stats["PPM-total"] < 10_000.0


def test_gland_fill_breaches_its_upper_limit(results) -> None:
    """Gland fill overfills at nominal, which the metrics must surface.

    The nominal design sits above the 1.00 upper limit, so a negative Cpk
    and a large defect rate are the correct answer, not a bug.
    """
    stats = results["gland_fill"]
    assert stats["mean"] > 1.0
    assert stats["Cpk"] < 0.0
    assert stats["PPM-total"] > 100_000.0


def test_outputs_are_approximately_normal(results) -> None:
    """Near-linear combinations of normals stay near-normal."""
    for name in ("gland_fill", "seal_compression"):
        stats = results[name]
        assert abs(stats["skewness"]) < 0.3
        assert stats["kurtosis"] == pytest.approx(3.0, abs=0.4)
