## Round 0 - setup

### Context

- Case: `tomli_loads`
- Issue: `#48`
- Stage: `proposal + local code read`

### Goal

- identify where the `BinaryOp<Subscript>` exception path is lost and prepare a
  controlled remote reproduction

### Decision

- Status:
  - in progress
- Next action:
  - read the `BinaryOp` lowering and exception-edge plumbing
  - then reserve remote validation time on the standard ARM entrypoint

## Round 0 - local TDD draft

### Context

- Case: `tomli_loads`
- Issue: `#48`
- Stage:
  - local patch drafting before remote verification

### Goal

- prepare a minimal regression and first implementation candidate so remote
  verification can start immediately once the ARM host is reachable

### Evidence

- Draft regression:
  - `test_skip_chars_handled_index_error_avoids_repeated_unhandled_deopts`
- Draft patch:
  - runtime suppression for repeated handled-subscript `UnhandledException`
    deopts

### Decision

- Status:
  - blocked
- Blocker:
  - ARM host `124.70.162.35` is currently unreachable, so the standard remote
    entrypoint cannot be run yet
- Next action:
  - rerun the standard remote entrypoint once SSH connectivity returns

## Round 1 - standard remote entrypoint

### Context

- Case: `tomli_loads`
- Issue: `#48`
- Lease:
  - benchmark: `31`
- Remote workdir:
  - `/root/work/cinderx-tomli-issue48`

### Goal

- validate the first patch through the standard ARM entrypoint
- collect a `tomli_loads` benchmark signal

### Evidence

- Targeted runtime regression:
  - `ArmRuntimeTests.test_skip_chars_handled_index_error_avoids_repeated_unhandled_deopts`
  - `OK`
- Standard-entry jitlist gate:
  - `tomli_loads`: `3.71 sec`
- Standard-entry autojit2 gate:
  - still blocked
  - current failure mode:
    - benchmark-worker segmentation fault

### Decision

- Status:
  - in progress
- Result so far:
  - the first patch works on the minimal target shape
  - benchmark closure is still blocked by a later autojit crash
- Next action:
  - localize the later benchmark-worker crash so we can get a trustworthy
    autojit number

## Round 2 - isolated environment

### Context

- Case: `tomli_loads`
- Issue: `#48`
- Lease:
  - benchmark: `34`
- Isolated paths:
  - workdir:
    - `/root/work/cinderx-tomli-issue48-iso`
  - driver venv:
    - `/root/venv-cinderx314-issue48`

### Goal

- separate the issue48 patch signal from unrelated shared-environment crashes

### Evidence

- Targeted runtime regression:
  - `OK`
- jitlist benchmark with only `tomli._parser:skip_chars`:
  - `3.6831124689997523 s`
- autojit2 benchmark with only `tomli._parser:skip_chars`:
  - `3.6588112600002205 s`
- autojit log:
  - only one function compiled:
    - `tomli._parser:skip_chars`

### Decision

- Status:
  - complete
- Result:
  - the isolated environment removes the unrelated autojit crash chain
  - issue48 fix is validated under autojit2 without further crashes
  - benchmark gain exists but is small
- Next action:
  - decide whether to stop here with the documented small win or keep hunting
    for a larger `tomli_loads` improvement
