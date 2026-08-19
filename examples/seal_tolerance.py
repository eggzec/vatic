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
#      Double-D seal gland tolerance stack-up, run head-less through the
#      vatic API. Reproduces the worked example that ships with the original
#      vatic project by Abraham Lee (https://github.com/tisimst/vatic), which
#      drove the same model through a Microsoft Excel workbook.
#
# ----------------------------------------------------------------------------
#
#  A PSA-backed double-D single-hole gland is specified by eight dimensions,
#  each with a symmetric tolerance. Following the convention used in the
#  original workbook, a tolerance is read as a three sigma bound, so a
#  dimension with a +/- t tolerance is modelled as Normal(nominal, t / 3).
#
#  Two characteristics are then checked against their requirements:
#
#      Gland Fill %  = seal area / groove area          spec 0.75 .. 1.00
#      Seal Comp. %  = 1 - groove height / seal height  spec 0.25 .. 0.50
#
#  Run it with:
#
#      python examples/seal_tolerance.py
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import mcerp
import numpy as np

from vatic.analytics import compute_capability_metrics, compute_statistics
from vatic.distributions import (
    build_variable,
    get_distribution_spec,
    seed_sampler,
)
from vatic.formula import evaluate_formula


#: Nominal value and symmetric tolerance for each input dimension, in inches
#: except for the dimensionless compression fraction. These are the values
#: from the original worked example.
DIMENSIONS: dict[str, tuple[float, float]] = {
    "seal_height": (0.162, 0.005),
    "seal_width": (0.118, 0.005),
    "core_hole_diameter": (0.071, 0.005),
    "core_compression": (0.75, 0.10),
    "groove_height": (0.117, 0.002),
    "groove_width": (0.130, 0.002),
    "lid_flatness": (0.0, 0.005),
    "box_flatness": (0.0, 0.005),
}

#: A tolerance is treated as a three sigma bound.
TOLERANCE_SIGMAS = 3.0

#: Intermediate and output characteristics, in dependency order. Each may
#: reference the assumptions and any characteristic defined above it.
FORECASTS: tuple[tuple[str, str, float | None, float | None], ...] = (
    (
        "core_hole_area",
        "core_compression * pi * (core_hole_diameter / 2) ** 2",
        None,
        None,
    ),
    (
        "seal_area",
        "pi * (seal_width / 4) ** 2"
        " + seal_width * (seal_height - seal_width / 4)"
        " - core_hole_area",
        None,
        None,
    ),
    (
        "groove_area",
        "groove_width * (groove_height + lid_flatness + box_flatness)",
        None,
        None,
    ),
    ("gland_fill", "seal_area / groove_area", 0.75, 1.00),
    ("seal_compression", "1 - groove_height / seal_height", 0.25, 0.50),
)

ITERATIONS = 10_000

#: Fixed so the printed numbers and the tests are reproducible. Pass
#: ``seed=None`` to run() for a fresh sample set each time.
SEED = 20260819


def build_assumptions() -> dict[str, object]:
    """Create one uncertain variable per toleranced dimension.

    Returns:
        Mapping of dimension name to its mcerp random variable.
    """
    spec = get_distribution_spec("Normal")
    variables: dict[str, object] = {}
    for name, (nominal, tolerance) in DIMENSIONS.items():
        variables[name] = build_variable(
            name, spec, {"mu": nominal, "sigma": tolerance / TOLERANCE_SIGMAS}
        )
    return variables


def run(seed: int | None = SEED) -> dict[str, dict[str, float]]:
    """Run the stack-up and report statistics for every characteristic.

    Args:
        seed: Sampler seed. The default fixes the run so the numbers are
            reproducible; pass ``None`` for a fresh sample set.

    Returns:
        Mapping of characteristic name to its statistics, with capability
        metrics merged in for the two that carry spec limits.
    """
    mcerp.npts = ITERATIONS
    seed_sampler(seed)

    context: dict[str, object] = dict(build_assumptions())
    results: dict[str, dict[str, float]] = {}

    for name, expression, lsl, usl in FORECASTS:
        outcome = evaluate_formula(expression, context)
        context[name] = outcome

        samples = getattr(outcome, "_mcpts", None)
        if samples is None:
            continue

        values = np.asarray(samples, dtype=float)
        stats = compute_statistics(values)
        if lsl is not None or usl is not None:
            stats |= compute_capability_metrics(
                values, lsl=lsl, usl=usl, target=None
            )
        results[name] = stats

    return results


def main() -> None:
    """Print the stack-up results in a readable table."""
    results = run()

    print(f"Double-D seal gland tolerance stack-up  ({ITERATIONS:,} trials)")
    print("=" * 68)

    for name, stats in results.items():
        print(f"\n{name}")
        print("-" * len(name))
        print(f"  mean            {stats['mean']:12.6f}")
        print(f"  std dev         {stats['std']:12.6f}")
        print(f"  variance        {stats['variance']:12.6e}")
        print(f"  skewness        {stats['skewness']:12.6f}")
        print(f"  kurtosis        {stats['kurtosis']:12.6f}")
        print(f"  min / max       {stats['min']:12.6f} / {stats['max']:.6f}")
        print(f"  P05 / P95       {stats['p05']:12.6f} / {stats['p95']:.6f}")

        if "Cpk" in stats:
            print(f"  Cp  / Cpk       {stats['Cp']:12.4f} / {stats['Cpk']:.4f}")
            print(f"  Pp  / Ppk       {stats['Pp']:12.4f} / {stats['Ppk']:.4f}")
            print(
                f"  Zst / Zlt       {stats['Zst']:12.4f} / {stats['Zlt']:.4f}"
            )
            print(f"  PPM total       {stats['PPM-total']:12.2f}")


if __name__ == "__main__":
    main()
