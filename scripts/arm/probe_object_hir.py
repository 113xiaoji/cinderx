#!/usr/bin/env python3
"""Print HIR opcode counts for object-heavy pyperformance benchmarks."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import cinderx.jit as jit
import cinderjit


INTERESTING_OPS = (
    "Incref",
    "XIncref",
    "Decref",
    "XDecref",
    "BatchDecref",
    "Guard",
    "GuardIs",
    "GuardType",
    "CondBranch",
    "CondBranchCheckType",
    "CallMethod",
    "VectorCall",
    "CallStatic",
    "LoadMethod",
    "LoadMethodCached",
    "LoadAttr",
    "LoadAttrCached",
    "LoadField",
    "StoreAttr",
    "StoreAttrCached",
    "StoreField",
    "ListAppend",
    "GetLength",
    "GetLengthInt64",
    "LongBinaryOp",
    "PrimitiveCompare",
    "PrimitiveBox",
    "PrimitiveUnbox",
    "DoubleBinaryOp",
    "DoubleSqrt",
)


def benchmark_path(name: str) -> Path:
    import pyperformance

    return (
        Path(pyperformance.__file__).parent
        / "data-files"
        / "benchmarks"
        / f"bm_{name}"
        / "run_benchmark.py"
    )


def import_benchmark(name: str):
    path = benchmark_path(name)
    spec = importlib.util.spec_from_file_location(f"probe_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def warm_go(mod) -> None:
    mod.random.seed(1)
    board = mod.Board()
    mod.computer_move(board)


def warm_richards(mod) -> None:
    mod.Richards().run(1)


def print_counts(label: str, func) -> None:
    try:
        ok = jit.force_compile(func)
    except Exception as exc:  # noqa: BLE001 - diagnostic script
        print(f"{label}: force_compile_error={type(exc).__name__}:{exc}")
        return
    if not ok:
        print(f"{label}: force_compile=False")
        return
    counts = cinderjit.get_function_hir_opcode_counts(func)
    selected = {op: counts.get(op, 0) for op in INTERESTING_OPS if counts.get(op, 0)}
    print(f"{label}: {selected}")


def probe_go() -> None:
    mod = import_benchmark("go")
    warm_go(mod)
    targets = [
        ("go.Square.move", mod.Square.move),
        ("go.Square.remove", mod.Square.remove),
        ("go.Square.find", mod.Square.find),
        ("go.EmptySet.random_choice", mod.EmptySet.random_choice),
        ("go.EmptySet.add", mod.EmptySet.add),
        ("go.EmptySet.remove", mod.EmptySet.remove),
        ("go.EmptySet.set", mod.EmptySet.set),
        ("go.ZobristHash.update", mod.ZobristHash.update),
        ("go.ZobristHash.add", mod.ZobristHash.add),
        ("go.ZobristHash.dupe", mod.ZobristHash.dupe),
        ("go.Board.move", mod.Board.move),
        ("go.Board.random_move", mod.Board.random_move),
        ("go.Board.useful_fast", mod.Board.useful_fast),
        ("go.Board.useful", mod.Board.useful),
        ("go.Board.useful_moves", mod.Board.useful_moves),
        ("go.Board.replay", mod.Board.replay),
        ("go.Board.score", mod.Board.score),
        ("go.UCTNode.play", mod.UCTNode.play),
        ("go.UCTNode.select", mod.UCTNode.select),
        ("go.UCTNode.random_playout", mod.UCTNode.random_playout),
        ("go.UCTNode.update_path", mod.UCTNode.update_path),
        ("go.UCTNode.score", mod.UCTNode.score),
        ("go.UCTNode.best_child", mod.UCTNode.best_child),
        ("go.UCTNode.best_visited", mod.UCTNode.best_visited),
        ("go.computer_move", mod.computer_move),
        ("go.versus_cpu", mod.versus_cpu),
    ]
    for label, func in targets:
        print_counts(label, func)


def probe_richards() -> None:
    mod = import_benchmark("richards")
    warm_richards(mod)
    targets = []
    for name, obj in sorted(mod.__dict__.items()):
        if isinstance(obj, type):
            for attr, value in sorted(obj.__dict__.items()):
                if callable(value) and getattr(value, "__code__", None) is not None:
                    targets.append((f"richards.{name}.{attr}", value))
        elif callable(obj) and getattr(obj, "__code__", None) is not None:
            targets.append((f"richards.{name}", obj))
    for label, func in targets:
        print_counts(label, func)


def main() -> int:
    jit.enable()
    jit.enable_specialized_opcodes()
    jit.compile_after_n_calls(1_000_000)
    for name in sys.argv[1:] or ["go", "richards"]:
        print(f"=== {name} ===")
        if name == "go":
            probe_go()
        elif name == "richards":
            probe_richards()
        else:
            raise SystemExit(f"unknown benchmark: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
