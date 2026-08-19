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
#      The formula evaluator: the expressions the seal model needs, and the
#      constructs it must refuse.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import math

import pytest

from vatic.formula import evaluate_formula


def test_arithmetic_and_precedence() -> None:
    """Ordinary arithmetic evaluates as Python would."""
    assert evaluate_formula("2 + 3 * 4", {}) == 14
    assert evaluate_formula("(2 + 3) * 4", {}) == 20
    assert evaluate_formula("2 ** 3 ** 2", {}) == 512


def test_named_variables_resolve() -> None:
    """Assumptions and earlier forecasts are referenced by name."""
    context = {"revenue": 120.0, "cost": 78.0}
    assert evaluate_formula("revenue - cost", context) == pytest.approx(42.0)


def test_pi_and_power_cover_the_seal_formulas() -> None:
    """The Excel model translates directly once ^ becomes **."""
    context = {"cc": 0.75, "d": 0.071}
    result = evaluate_formula("cc * pi * (d / 2) ** 2", context)
    assert result == pytest.approx(0.75 * math.pi * (0.071 / 2) ** 2)


def test_whitelisted_functions_are_available() -> None:
    """The keypad's functions all evaluate."""
    assert evaluate_formula("sqrt(16)", {}) == pytest.approx(4.0)
    assert evaluate_formula("log(e)", {}) == pytest.approx(1.0)
    assert evaluate_formula("abs(-3)", {}) == 3
    assert evaluate_formula("max(1, 7, 3)", {}) == 7
    assert evaluate_formula("min(1, 7, 3)", {}) == 1


def test_unknown_name_is_rejected() -> None:
    """A typo in a variable name fails loudly rather than resolving oddly."""
    with pytest.raises(ValueError, match="Unknown name"):
        evaluate_formula("revenu - cost", {"revenue": 1.0, "cost": 1.0})


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo hi')",
        "open('secret.txt').read()",
        "(1).__class__.__bases__",
        "[x for x in range(3)]",
        "lambda: 1",
    ],
)
def test_dangerous_expressions_are_refused(expression: str) -> None:
    """The evaluator is a calculator, not a Python interpreter."""
    with pytest.raises((ValueError, SyntaxError)):
        evaluate_formula(expression, {})


def test_keyword_arguments_are_refused() -> None:
    """Only positional calls are allowed through the validator."""
    with pytest.raises(ValueError):
        evaluate_formula("round(1.234, ndigits=2)", {})
