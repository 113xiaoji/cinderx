import builtins
import dis

import pytest

from scripts.arm import interp_superinstruction_workloads as workloads


def loop_pairs(fn) -> set[str]:
    instructions = list(dis.get_instructions(fn))
    loop_start = next(i for i, instr in enumerate(instructions) if instr.opname == "FOR_ITER")
    loop_end = next(i for i, instr in enumerate(instructions) if instr.opname == "JUMP_BACKWARD")
    names = [instr.opname for instr in instructions[loop_start:loop_end]]
    return {f"{a}->{b}" for a, b in zip(names, names[1:])}


def test_workload_specs_are_the_single_source_of_truth() -> None:
    assert [spec.name for spec in workloads.WORKLOAD_SPECS] == list(workloads.WORKLOADS)
    assert {
        spec.name: spec.target_pair for spec in workloads.WORKLOAD_SPECS
    } == {
        "load_fast_pair_loop": "LOAD_FAST->LOAD_FAST",
        "store_fast_load_fast_loop": "STORE_FAST->LOAD_FAST",
        "load_const_load_fast_loop": "LOAD_CONST->LOAD_FAST",
    }
    assert [spec.entry_name for spec in workloads.WORKLOAD_SPECS] == [
        "load_fast_pair_loop",
        "store_fast_load_fast_loop",
        "load_const_load_fast_loop",
    ]
    assert [spec.source.startswith(f"def {spec.entry_name}(") for spec in workloads.WORKLOAD_SPECS] == [
        True,
        True,
        True,
    ]
    assert workloads.get_workload_names() == (
        "load_fast_pair_loop",
        "store_fast_load_fast_loop",
        "load_const_load_fast_loop",
    )


def test_get_workload_spec_returns_the_matching_spec() -> None:
    spec = workloads.get_workload_spec("store_fast_load_fast_loop")
    assert spec.name == "store_fast_load_fast_loop"
    assert spec.entry_name == "store_fast_load_fast_loop"
    assert spec.source.startswith("def store_fast_load_fast_loop(")


def test_build_default_workload_executes_source() -> None:
    spec = workloads.get_workload_spec("load_const_load_fast_loop")
    fn = workloads.build_default_workload(spec)
    assert isinstance(fn(8), int)
    assert fn(8) == fn(8)


def test_build_default_workload_compiles_source_before_exec() -> None:
    spec = workloads.get_workload_spec("load_fast_pair_loop")
    real_compile = builtins.compile
    calls: list[tuple[str, str, str]] = []

    def spy_compile(source, filename, mode, *args, **kwargs):
        calls.append((source, filename, mode))
        return real_compile(source, filename, mode, *args, **kwargs)

    original_exec = builtins.exec

    def spy_exec(code, namespace=None, *args, **kwargs):
        assert not isinstance(code, str)
        return original_exec(code, namespace, *args, **kwargs)

    try:
        builtins.compile = spy_compile
        builtins.exec = spy_exec
        fn = workloads.build_default_workload(spec)
    finally:
        builtins.compile = real_compile
        builtins.exec = original_exec

    assert calls == [(spec.source, f"<{spec.name}>", "exec")]
    assert fn(6) == workloads.get_workload(spec.name)(6)


def test_load_fast_pair_loop_runs_and_contains_adjacent_load_fast_in_loop() -> None:
    fn = workloads.get_workload("load_fast_pair_loop")
    assert isinstance(fn(8), int)
    assert fn(8) == fn(8)
    assert "LOAD_FAST->LOAD_FAST" in loop_pairs(fn)


def test_store_fast_load_fast_loop_runs_and_contains_store_then_load_fast_in_loop() -> None:
    fn = workloads.get_workload("store_fast_load_fast_loop")
    assert isinstance(fn(8), int)
    assert fn(8) == fn(8)
    assert "STORE_FAST->LOAD_FAST" in loop_pairs(fn)


def test_load_const_load_fast_loop_runs_and_contains_const_then_local_in_loop() -> None:
    fn = workloads.get_workload("load_const_load_fast_loop")
    assert isinstance(fn(8), int)
    assert fn(8) == fn(8)
    assert "LOAD_CONST->LOAD_FAST" in loop_pairs(fn)


def test_unknown_workload_raises_key_error() -> None:
    try:
        workloads.get_workload("missing")
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("expected KeyError for unknown workload")


def test_build_default_workload_raises_for_missing_entry() -> None:
    spec = workloads.WorkloadSpec(
        name="broken",
        target_pair="LOAD_FAST->LOAD_FAST",
        entry_name="broken",
        source="value = 1",
    )

    with pytest.raises(RuntimeError, match="broken"):
        workloads.build_default_workload(spec)


def test_build_default_workload_raises_for_non_callable_entry() -> None:
    spec = workloads.WorkloadSpec(
        name="broken",
        target_pair="LOAD_FAST->LOAD_FAST",
        entry_name="broken",
        source="broken = 1",
    )

    with pytest.raises(RuntimeError, match="not callable"):
        workloads.build_default_workload(spec)
