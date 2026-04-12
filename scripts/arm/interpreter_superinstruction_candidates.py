from __future__ import annotations

from dataclasses import dataclass

from scripts.arm.interp_superinstruction_workloads import WORKLOAD_SPECS


@dataclass(frozen=True)
class SuperinstructionCandidate:
    name: str
    source_pair: str
    workloads: tuple[str, ...]
    versions: tuple[str, ...]
    rationale: str


_WORKLOAD_NAMES_BY_PAIR = {
    spec.target_pair: spec.name for spec in WORKLOAD_SPECS
}


PHASE1_CANDIDATES: tuple[SuperinstructionCandidate, ...] = (
    SuperinstructionCandidate(
        name="LOAD_FAST__LOAD_FAST",
        source_pair="LOAD_FAST->LOAD_FAST",
        workloads=(_WORKLOAD_NAMES_BY_PAIR["LOAD_FAST->LOAD_FAST"],),
        versions=("3.14", "3.15"),
        rationale="Common adjacent fast-local reads in the first pilot workload.",
    ),
    SuperinstructionCandidate(
        name="STORE_FAST__LOAD_FAST",
        source_pair="STORE_FAST->LOAD_FAST",
        workloads=(_WORKLOAD_NAMES_BY_PAIR["STORE_FAST->LOAD_FAST"],),
        versions=("3.14", "3.15"),
        rationale="Captures the store-then-load pattern exercised by the second pilot workload.",
    ),
    SuperinstructionCandidate(
        name="LOAD_CONST__LOAD_FAST",
        source_pair="LOAD_CONST->LOAD_FAST",
        workloads=(_WORKLOAD_NAMES_BY_PAIR["LOAD_CONST->LOAD_FAST"],),
        versions=("3.14", "3.15"),
        rationale="Represents the const-to-local pattern in the third pilot workload.",
    ),
)
