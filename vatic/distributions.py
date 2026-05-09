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
#      Distribution registry and variable builders.
#
# ----------------------------------------------------------------------------

from __future__ import annotations

import inspect
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import mcerp

from vatic.logger import get_logger


LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    kind: str
    default: float | int | None = None


@dataclass(frozen=True)
class DistributionSpec:
    key: str
    label: str
    constructor_name: str
    parameters: tuple[ParameterSpec, ...]


def _kind_from_annotation(annotation: Any) -> str:
    if annotation is int:
        return "int"
    text = str(annotation).lower()
    if "int" in text and "float" not in text:
        return "int"
    return "float"


def _default_for_parameter(param: ParameterSpec) -> float | int:
    if param.default is not None:
        return param.default

    key = param.name.lower()
    if param.kind == "int":
        if key in {"n", "k", "v", "d1", "d2", "npts"}:
            return 10
        return 1

    if key in {"p", "prob", "probability"}:
        return 0.5
    if key in {"low", "min"}:
        return 0.0
    if key in {"high", "max"}:
        return 1.0
    return 1.0


def default_parameters(spec: DistributionSpec) -> dict[str, float | int]:
    return {
        param.name: _default_for_parameter(param) for param in spec.parameters
    }


def coerce_parameter_value(raw: str, param: ParameterSpec) -> float | int:
    text = raw.strip()
    if not text:
        raise ValueError(f"Parameter '{param.name}' cannot be empty")

    if param.kind == "int":
        value = float(text)
        if not value.is_integer():
            raise ValueError(f"Parameter '{param.name}' must be an integer")
        return int(value)

    return float(text)


def _is_distribution_function(name: str, obj: object) -> bool:
    if not inspect.isfunction(obj):
        return False
    if not name or not name[0].isupper() or len(name) == 1:
        return False

    signature = inspect.signature(obj)
    return "tag" in signature.parameters


@lru_cache(maxsize=1)
def get_distribution_registry() -> dict[str, DistributionSpec]:
    registry: dict[str, DistributionSpec] = {}

    for name in sorted(dir(mcerp)):
        obj = getattr(mcerp, name)
        if not _is_distribution_function(name, obj):
            continue

        signature = inspect.signature(obj)
        parameters: list[ParameterSpec] = []
        for raw in signature.parameters.values():
            if raw.name == "tag":
                continue
            default = None
            if raw.default is not inspect.Signature.empty and isinstance(
                raw.default, (int, float)
            ):
                default = raw.default
            parameters.append(
                ParameterSpec(
                    name=raw.name,
                    kind=_kind_from_annotation(raw.annotation),
                    default=default,
                )
            )

        key = name.lower()
        registry[key] = DistributionSpec(
            key=key,
            label=name,
            constructor_name=name,
            parameters=tuple(parameters),
        )

    LOGGER.info("Distribution registry loaded | count=%s", len(registry))
    return registry


def distribution_labels() -> list[str]:
    return [spec.label for spec in get_distribution_registry().values()]


def get_distribution_spec(label: str) -> DistributionSpec:
    key = label.strip().lower()
    registry = get_distribution_registry()
    if key not in registry:
        raise ValueError(f"Unsupported distribution: {label}")
    return registry[key]


def build_variable(
    variable_name: str,
    spec: DistributionSpec,
    parameters: dict[str, float | int],
) -> object:
    LOGGER.debug(
        "Building variable | name=%s | distribution=%s | parameters=%s",
        variable_name,
        spec.label,
        parameters,
    )
    constructor = getattr(mcerp, spec.constructor_name)
    args: list[float | int] = []
    for param in spec.parameters:
        if param.name not in parameters:
            raise ValueError(
                f"Missing parameter '{param.name}' for {spec.label}"
            )
        value = parameters[param.name]
        args.append(int(value) if param.kind == "int" else float(value))

    built = constructor(*args, tag=variable_name)
    LOGGER.debug(
        "Variable built | name=%s | type=%s",
        variable_name,
        type(built).__name__,
    )
    return built
