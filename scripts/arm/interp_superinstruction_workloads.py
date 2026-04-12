from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class WorkloadSpec:
    name: str
    target_pair: str
    workload: Callable[[int], int]


def load_fast_pair_loop(n: int) -> int:
    total = 0
    for i in range(n):
        left = i
        right = i + 1
        total += left + right
    return total


def store_fast_load_fast_loop(n: int) -> int:
    total = 0
    current = 1
    for i in range(n):
        current = i ^ current
        total += current
    return total


def load_const_load_fast_loop(n: int) -> int:
    total = 0
    for i in range(n):
        total += 7 * i
    return total


WORKLOAD_SPECS: tuple[WorkloadSpec, ...] = (
    WorkloadSpec("load_fast_pair_loop", "LOAD_FAST->LOAD_FAST", load_fast_pair_loop),
    WorkloadSpec(
        "store_fast_load_fast_loop",
        "STORE_FAST->LOAD_FAST",
        store_fast_load_fast_loop,
    ),
    WorkloadSpec(
        "load_const_load_fast_loop",
        "LOAD_CONST->LOAD_FAST",
        load_const_load_fast_loop,
    ),
)

WORKLOADS: dict[str, Callable[[int], int]] = {
    spec.name: spec.workload for spec in WORKLOAD_SPECS
}


def get_workload(name: str) -> Callable[[int], int]:
    try:
        return WORKLOADS[name]
    except KeyError as exc:
        raise KeyError(f"unknown superinstruction pilot workload: {name}") from exc
