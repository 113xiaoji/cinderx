import dis

from scripts.arm import interp_superinstruction_workloads as workloads


def opcode_pairs(fn) -> set[str]:
    names = [instr.opname for instr in dis.get_instructions(fn)]
    return {f"{a}->{b}" for a, b in zip(names, names[1:])}


def test_load_fast_pair_loop_contains_adjacent_load_fast() -> None:
    fn = workloads.get_workload("load_fast_pair_loop")
    assert "LOAD_FAST->LOAD_FAST" in opcode_pairs(fn)


def test_store_fast_load_fast_loop_contains_store_then_load_fast() -> None:
    fn = workloads.get_workload("store_fast_load_fast_loop")
    assert "STORE_FAST->LOAD_FAST" in opcode_pairs(fn)


def test_load_const_load_fast_loop_contains_const_then_local() -> None:
    fn = workloads.get_workload("load_const_load_fast_loop")
    assert "LOAD_CONST->LOAD_FAST" in opcode_pairs(fn)


def test_unknown_workload_raises_key_error() -> None:
    try:
        workloads.get_workload("missing")
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("expected KeyError for unknown workload")
