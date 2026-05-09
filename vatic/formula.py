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
#      Safe formula validation and evaluation engine.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import ast
import math

import mcerp
import numpy as np

from vatic.logger import get_logger


LOGGER = get_logger(__name__)


class FormulaValidator(ast.NodeVisitor):
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.Call,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.FloorDiv,
        ast.USub,
        ast.UAdd,
    )

    def __init__(self, allowed_names: set[str]) -> None:
        super().__init__()
        self.allowed_names = allowed_names

    def generic_visit(self, node: ast.AST) -> None:
        if not isinstance(node, self.allowed_nodes):
            raise ValueError(f"Unsupported token: {node.__class__.__name__}")
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id not in self.allowed_names:
            raise ValueError(f"Unknown name: {node.id}")

    def visit_Call(self, node: ast.Call) -> None:
        if (
            not isinstance(node.func, ast.Name)
            or node.func.id not in self.allowed_names
        ):
            raise ValueError("Only whitelisted function calls allowed")
        for arg in node.args:
            self.visit(arg)
        if node.keywords:
            raise ValueError("Keyword arguments not allowed")


def _build_allowed_functions() -> dict[str, object]:
    def _to_mcpts(value: object, npts: int) -> np.ndarray:
        if hasattr(value, "_mcpts"):
            return np.asarray(value._mcpts, dtype=float)
        return np.full(npts, float(value), dtype=float)

    def _adaptive_npts(values: tuple[object, ...]) -> int:
        for value in values:
            if hasattr(value, "_mcpts"):
                return int(np.asarray(value._mcpts).size)
        return int(mcerp.npts)

    def _uncertain_min(*values: object) -> object:
        if len(values) < 2:
            raise ValueError("min() needs at least two values")
        npts = _adaptive_npts(values)
        result = _to_mcpts(values[0], npts)
        for value in values[1:]:
            result = np.minimum(result, _to_mcpts(value, npts))
        return mcerp.UncertainFunction(result)

    def _uncertain_max(*values: object) -> object:
        if len(values) < 2:
            raise ValueError("max() needs at least two values")
        npts = _adaptive_npts(values)
        result = _to_mcpts(values[0], npts)
        for value in values[1:]:
            result = np.maximum(result, _to_mcpts(value, npts))
        return mcerp.UncertainFunction(result)

    def _uncertain_sign(value: object) -> object:
        npts = _adaptive_npts((value,))
        return mcerp.UncertainFunction(np.sign(_to_mcpts(value, npts)))

    allowed_funcs: dict[str, object] = {
        "abs": abs,
        "min": _uncertain_min,
        "max": _uncertain_max,
        "round": round,
        "pow": pow,
        "sign": _uncertain_sign,
    }

    common = (
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "sinh",
        "cosh",
        "tanh",
        "exp",
        "expm1",
        "log",
        "log10",
        "log2",
        "sqrt",
        "floor",
        "ceil",
        "fabs",
    )
    for name in common:
        if hasattr(mcerp, "umath") and hasattr(mcerp.umath, name):
            allowed_funcs[name] = getattr(mcerp.umath, name)
        elif hasattr(mcerp, name):
            allowed_funcs[name] = getattr(mcerp, name)
        elif hasattr(math, name):
            allowed_funcs[name] = getattr(math, name)

    allowed_funcs["pi"] = math.pi
    allowed_funcs["e"] = math.e
    LOGGER.debug(
        "Allowed formula functions built | count=%s", len(allowed_funcs)
    )
    return allowed_funcs


def evaluate_formula(expr: str, names: dict[str, object]) -> object:
    LOGGER.info(
        "Evaluating formula | expression=%s | variables=%s",
        expr,
        sorted(names.keys()),
    )
    allowed_funcs = _build_allowed_functions()

    safe = set(names.keys()) | set(allowed_funcs.keys())
    parsed = ast.parse(expr, mode="eval")
    FormulaValidator(safe).visit(parsed)

    context = {**names, **allowed_funcs}
    result = eval(
        compile(parsed, filename="<formula>", mode="eval"),
        {"__builtins__": {}},
        context,
    )
    LOGGER.debug(
        "Formula evaluated successfully | result_type=%s", type(result).__name__
    )
    return result
