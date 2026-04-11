from __future__ import annotations

from typing import Callable


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


WORKLOADS: dict[str, Callable[[int], int]] = {
    "load_fast_pair_loop": load_fast_pair_loop,
    "store_fast_load_fast_loop": store_fast_load_fast_loop,
    "load_const_load_fast_loop": load_const_load_fast_loop,
}


def get_workload(name: str) -> Callable[[int], int]:
    try:
        return WORKLOADS[name]
    except KeyError as exc:
        raise KeyError(f"unknown superinstruction pilot workload: {name}") from exc
