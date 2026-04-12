from scripts.arm import interpreter_superinstruction_candidates as candidates


def test_phase1_candidates_are_in_expected_order() -> None:
    assert [candidate.name for candidate in candidates.PHASE1_CANDIDATES] == [
        "LOAD_FAST__LOAD_FAST",
        "STORE_FAST__LOAD_FAST",
        "LOAD_CONST__LOAD_FAST",
    ]


def test_phase1_candidates_use_the_expected_versions() -> None:
    assert all(
        candidate.versions == ("3.14", "3.15")
        for candidate in candidates.PHASE1_CANDIDATES
    )


def test_phase1_candidates_map_to_expected_source_pairs_and_workloads() -> None:
    assert [
        (candidate.source_pair, candidate.workloads)
        for candidate in candidates.PHASE1_CANDIDATES
    ] == [
        ("LOAD_FAST->LOAD_FAST", ("load_fast_pair_loop",)),
        ("STORE_FAST->LOAD_FAST", ("store_fast_load_fast_loop",)),
        ("LOAD_CONST->LOAD_FAST", ("load_const_load_fast_loop",)),
    ]
