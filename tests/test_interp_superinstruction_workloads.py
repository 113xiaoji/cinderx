import dis

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
