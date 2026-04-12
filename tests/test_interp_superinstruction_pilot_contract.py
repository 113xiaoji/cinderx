from pathlib import Path


SCRIPT_PATH = Path("scripts/arm/interp_superinstruction_pilot.sh")
EXPECTED_WORKLOADS = (
    "load_fast_pair_loop",
    "store_fast_load_fast_loop",
    "load_const_load_fast_loop",
)


def test_interp_superinstruction_pilot_script_exists_and_references_phase1_workloads() -> None:
    assert SCRIPT_PATH.is_file(), f"missing pilot driver script: {SCRIPT_PATH}"

    script = SCRIPT_PATH.read_text(encoding="utf-8")

    for workload in EXPECTED_WORKLOADS:
        assert workload in script
    assert "bench_compare_modes.py" in script
    assert "--producer cinder" in script
    assert ".cinderx.cinder.json" in script
