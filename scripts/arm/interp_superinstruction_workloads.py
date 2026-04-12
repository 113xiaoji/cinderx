from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent
from typing import Callable


@dataclass(frozen=True)
class WorkloadSpec:
    name: str
    target_pair: str
    entry_name: str
    source: str


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


LOAD_FAST_PAIR_LOOP_SOURCE = dedent(
    """
    def load_fast_pair_loop(n: int) -> int:
        total = 0
        for i in range(n):
            left = i
            right = i + 1
            total += left + right
        return total
    """
).strip()

STORE_FAST_LOAD_FAST_LOOP_SOURCE = dedent(
    """
    def store_fast_load_fast_loop(n: int) -> int:
        total = 0
        current = 1
        for i in range(n):
            current = i ^ current
            total += current
        return total
    """
).strip()

LOAD_CONST_LOAD_FAST_LOOP_SOURCE = dedent(
    """
    def load_const_load_fast_loop(n: int) -> int:
        total = 0
        for i in range(n):
            total += 7 * i
        return total
    """
).strip()


WORKLOAD_SPECS: tuple[WorkloadSpec, ...] = (
    WorkloadSpec(
        "load_fast_pair_loop",
        "LOAD_FAST->LOAD_FAST",
        "load_fast_pair_loop",
        LOAD_FAST_PAIR_LOOP_SOURCE,
    ),
    WorkloadSpec(
        "store_fast_load_fast_loop",
        "STORE_FAST->LOAD_FAST",
        "store_fast_load_fast_loop",
        STORE_FAST_LOAD_FAST_LOOP_SOURCE,
    ),
    WorkloadSpec(
        "load_const_load_fast_loop",
        "LOAD_CONST->LOAD_FAST",
        "load_const_load_fast_loop",
        LOAD_CONST_LOAD_FAST_LOOP_SOURCE,
    ),
)

def get_workload_spec(name: str) -> WorkloadSpec:
    for spec in WORKLOAD_SPECS:
        if spec.name == name:
            return spec
    raise KeyError(f"unknown superinstruction pilot workload: {name}")


def get_workload_names() -> tuple[str, ...]:
    return tuple(spec.name for spec in WORKLOAD_SPECS)


def build_default_workload(spec: WorkloadSpec) -> Callable[[int], int]:
    namespace: dict[str, object] = {}
    exec(spec.source, namespace)
    workload = namespace[spec.entry_name]
    assert callable(workload)
    return workload


def get_workload(name: str) -> Callable[[int], int]:
    return build_default_workload(get_workload_spec(name))


WORKLOADS: dict[str, Callable[[int], int]] = {
    spec.name: build_default_workload(spec) for spec in WORKLOAD_SPECS
}
