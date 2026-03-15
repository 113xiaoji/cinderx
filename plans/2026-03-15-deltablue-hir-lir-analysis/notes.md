# Notes: DeltaBlue

## Initial questions
- Which functions dominate `bm_deltablue` runtime under the current JIT?
- Are they limited by attribute traffic, call overhead, iterator/generator overhead, or refcount pressure?
- Is the best next optimization HIR-local, lowering-specific, or benchmark-shape-specific?

## Setup plan
- Use a clean remote worktree for baseline.
- Use a second remote worktree for experiment builds.
- Run the benchmark under a fixed interpreter and toolchain.
- Record:
  - benchmark wall time
  - hottest compiled functions
  - final HIR opcode counts for hot functions
  - LIR dumps for the most suspicious hot path

## Baseline data
- Remote entrypoint: `ssh root@124.70.162.35` via host alias `arm-124-70-162-35`
- Python for runtime benchmarking:
  - `/root/venv-cinderx314-loadmethodstub-20260309_210647/bin/python`
- Worktree import mode:
  - `PYTHONPATH=<worktree>/cinderx/PythonLib:<worktree>/scratch/temp.linux-aarch64-cpython-314`
- Base worktree:
  - `/root/work/cinderx-deltablue-base`
  - commit `c3ac4a6`
- Dev worktree:
  - `/root/work/cinderx-deltablue-dev`
  - commit `c3ac4a6`

## Hot functions from direct `delta_blue(100)` sampling
- `BinaryConstraint.choose_method`
  - compiled size `7576`
  - HIR highlights:
    - `CallMethod: 5`
    - `LoadAttrCached: 24`
    - `LoadGlobalCached: 13`
    - `GuardIs: 13`
    - `PrimitiveCompare: 13`
- `projection_test`
  - compiled size `6800`
- `chain_test`
  - compiled size `5248`
- `Planner.remove_propagate_from`
  - compiled size `4784`
- `ScaleConstraint.execute`
  - compiled size `2992`

## HIR/LIR observations
- `BinaryConstraint.choose_method` is dominated by repeated type-method loads and calls to:
  - `Strength.stronger`
  - `Strength.weaker`
- These are classmethod wrappers. Current final HIR pattern is:
  - `LoadGlobalCached("Strength")`
  - `GuardIs(<Strength>)`
  - `LoadTypeMethodCacheEntryType / FillTypeMethodCache`
  - `GetSecondOutput`
  - `CallMethod`
- The wrapper functions themselves are tiny:
  - `Strength.stronger` compiled size `760`
  - `Strength.weaker` compiled size `760`
- `ScaleConstraint.execute` already uses split-dict field loads for `self.direction/v1/scale/offset/v2`, so the bigger remaining gap there is not `self` field access but the nested arithmetic / `Variable.value` loads.
- `Planner.remove_propagate_from` already benefits from specialized bytecode for:
  - `len(todo)` -> `CALL_LEN`
  - `todo.pop(0)` / `append` -> `LOAD_ATTR_METHOD_WITH_VALUES`
  so it is less attractive than `choose_method` as the first optimization target.

## Chosen optimization target
- Extend builtin load-method elimination to cover exact type-receiver method loads produced by `{LoadTypeMethodCacheEntryValue | FillTypeMethodCache}`.
- For mutable user classes, insert a `TypeAttrDeoptPatcher` so changing the classmethod after compilation remains correct.
- After builtin load-method elimination, rerun the inliner so the newly constant `VectorCall` targets can inline.

## Experiment results

### Phase 1: type-method `CallMethod -> VectorCall`
- Implementation:
  - guarded the resolved callable identity
  - guarded the bound receiver shape
  - replaced `CallMethod` with `VectorCall`
- Remote regression checks passed:
  - `test_type_classmethod_call_eliminates_callmethod`
  - `test_type_classmethod_call_deopts_on_mutation`
  - existing `test_set_genexpr_eliminates_generator_call`
- Small reproducer HIR became:
  - `CallMethod: 0`
  - `VectorCall: 1`
  - deopt on classmethod mutation worked
- But steady-state DeltaBlue signal was not good:
  - `choose_method` still had `VectorCall: 5`
  - steady-state `delta_blue(100)` medians were worse than base on the remote host

### Phase 2: rerun inliner after builtin-load-method elimination
- Added a second inliner pass after builtin-load-method elimination.
- This did not inline `Strength.stronger/weaker`.
- Root cause: exposing constant vectorcall targets was not sufficient in practice for these callsites.

### Phase 3: directly inline trivial attr-compare wrappers
- Narrow pattern:
  - `return a.attr < b.attr`
  - `return a.attr > b.attr`
- This matched `Strength.stronger` / `Strength.weaker`.
- Remote regression checks still passed.
- But the result was decisively worse:
  - `BinaryConstraint.choose_method` compiled size jumped to `8808`
  - `LoadAttrCached` rose from `24` to `34`
  - steady-state `delta_blue(100)` median jumped to about `0.74s` for 120-iteration samples, versus base around `0.65s`

## Conclusion
- The apparent hotspot was real, but the straightforward classmethod-elimination approaches did not improve DeltaBlue.
- The wrapper-call overhead is not the dominant steady-state limiter once the extra guards and code size costs are accounted for.
- More promising remaining directions are likely:
  - `OrderedCollection` list-subclass method specialization in `Planner.remove_propagate_from`
  - `len()` truthiness / loop predicate cleanups already visible in planner paths
  - a more principled way to preload or inline dynamic exact-type helper functions without growing caller HIR too aggressively

## Follow-up: `len()` truthiness

### Observation
- `Planner.remove_propagate_from` already used `CALL_LEN`, but final HIR still boxed the primitive length result before comparing it against zero in the loop predicate.
- This is exactly the shape:
  - `GetLengthInt64`
  - `PrimitiveBox<CInt64>`
  - `PrimitiveCompare<NotEqual>(..., 0)`
  - `CondBranch`

### Implementation
- Added a narrow `simplifyPrimitiveCompare()` rule for:
  - `PrimitiveCompare<Equal|NotEqual>`
  - one side is `len()`-derived primitive integer (including `PrimitiveBox` of that integer)
  - the other side is boxed `0`
- The rewrite keeps the compare in primitive `CInt64` space and removes the boxed `LongExact` bridge.

### Remote validation
- Remote source was uploaded from local `HEAD` into:
  - `/root/work/deltablue-upload-base`
  - `/root/work/deltablue-upload-dev`
- Only the following files were changed in `dev`:
  - `cinderx/Jit/hir/simplify.cpp`
  - `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Remote regression checks passed:
  - `ArmRuntimeTests.test_len_truthiness_avoids_boxed_int_compare`
  - `ArmRuntimeTests.test_len_arithmetic_uses_primitive_int_chain`

### Benchmark
- Remote steady-state benchmark:
  - benchmark body: `delta_blue(100)`
  - warmup: 120 calls before timing
  - timed samples: 7 samples, each sample runs 120 calls
- Results:
  - base median: `0.798756735981442`
  - dev median: `0.7747377860359848`
  - speedup: about `3.0%`

### Current assessment
- Unlike the classmethod experiment, this optimization is small, safe, and benchmark-positive.
- This is a viable candidate to keep and prepare for commit once the unrelated failed experiment changes are cleaned out locally.

## Current local follow-up: list-subclass queue methods

### Motivation
- DeltaBlue still spends meaningful time in planner queue maintenance.
- A direct repro with `OrderedCollection(list)` confirms 3.14 adaptive
  bytecode reaches:
  - `LOAD_ATTR_METHOD_WITH_VALUES`
  - `CALL_LIST_APPEND`
  - `CALL_METHOD_DESCRIPTOR_FAST`

### Attempted implementation
- Attempt 1:
  - in `simplifyCallMethod()`, convert constant-`PyMethodDescr` method calls to
    `VectorCall<..., static>`
- Attempt 2:
  - preserve `CALL_LIST_APPEND` and `CALL_METHOD_DESCRIPTOR_*` in
    `BytecodeInstruction::specializedOpcode()`
  - in `emitAnyCall()`, rewrite those specialized call families to
    `VectorCall<..., static>` so existing vectorcall/list-append fast paths can
    trigger

### Remote validation
- Host: `124.70.162.35`
- Workdir: `/root/work/cinderx-main`
- Runtime used for validation:
  - `/root/venv-cinderx314/bin/python`
  - `PYTHONPATH=/root/work/cinderx-main/cinderx/PythonLib`
- Result:
  - targeted repros still compiled to:
    - `LoadMethodCached`
    - `GetSecondOutput`
    - `CallMethod`
  - opcode counts stayed:
    - `append_once`: `CallMethod: 1`, `ListAppend: 0`
    - `pop_front`: `CallMethod: 1`, `VectorCall: 0`

### Conclusion
- The current code patch is not effective and should not be kept.
- The important finding is architectural:
  - the profitable DeltaBlue direction is still planner queue maintenance
  - but the real loss of specialization happens before the current HIR rewrite
    takes effect
- Best next step:
  - instrument or test the exact bytecode-to-HIR path for
    `LOAD_ATTR_METHOD_WITH_VALUES` + specialized call families
  - find where that path is collapsing back to
    `LoadMethodCached + GetSecondOutput + CallMethod`
  - only then add a new fast path

## Successful follow-up: builder-time method-descriptor calls

### Root cause
- Remote instrumentation on `append_once` / `pop_front` showed:
  - builder did see specialized call opcodes:
    - `CALL_LIST_APPEND`
    - `CALL_METHOD_DESCRIPTOR_FAST`
  - but the callable register still had no output type during HIR building
- The specialized load path was already doing the right thing:
  - `LOAD_ATTR_METHOD_WITH_VALUES` produced a constant `LoadConst` carrying the
    method descriptor
- The missed optimization was specifically:
  - checking the register output type too early instead of inspecting the
    defining `LoadConst` instruction

### Final implementation
- `BytecodeInstruction::specializedOpcode()` now preserves:
  - `CALL_LIST_APPEND`
  - `CALL_METHOD_DESCRIPTOR_FAST`
  - `CALL_METHOD_DESCRIPTOR_FAST_WITH_KEYWORDS`
  - `CALL_METHOD_DESCRIPTOR_NOARGS`
  - `CALL_METHOD_DESCRIPTOR_O`
- `HIRBuilder::emitAnyCall()` now:
  - detects those specialized call families
  - looks through the callable's defining `LoadConst`
  - rewrites exact method-descriptor calls to `VectorCall<..., static>`

### Remote validation
- Host: `124.70.162.35`
- Workdir: `/root/work/cinderx-main`
- Runtime:
  - `/root/venv-cinderx314/bin/python`
  - `PYTHONPATH=/root/work/cinderx-main/cinderx/PythonLib`
- Initial HIR after the fix:
  - `append_once`:
    - `LoadConst<method_descriptor>`
    - `VectorCall<2, static>` for `todo.append(value)`
  - `pop_front`:
    - `LoadConst<method_descriptor>`
    - `VectorCall<2, static>` for `todo.pop(0)`
- Final HIR opcode counts:
  - `append_once`:
    - `CallMethod: 0`
    - `ListAppend: 1`
  - `pop_front`:
    - `CallMethod: 0`
    - `VectorCall: 1`

### Regression coverage
- Added:
  - `ArmRuntimeTests.test_list_subclass_append_eliminates_callmethod`
  - `ArmRuntimeTests.test_list_subclass_pop_front_eliminates_callmethod`
- Remote targeted result:
  - both tests `OK`

### Benchmark
- Setup:
  - host: `124.70.162.35`
  - Python: `/opt/python-3.14/bin/python3.14`
  - isolated installs:
    - base venv: `/root/venv-deltablue-call-base`
    - dev venv: `/root/venv-deltablue-call-dev`
  - source trees:
    - base: `/root/work/deltablue-call-base` from local `HEAD`
    - dev: `/root/work/deltablue-call-dev` from the local working tree with
      the builder-time method-descriptor call patch
- Workload:
  - import `bm_deltablue/run_benchmark.py`
  - run `delta_blue(100)`
  - per sample:
    - warmup: 120 calls
    - timed section: 120 calls
  - JIT config:
    - `jit.enable()`
    - `jit.enable_specialized_opcodes()`
    - `jit.compile_after_n_calls(50)`

#### Sample set A
- Order:
  - each round ran `base` then `dev`
  - rounds: `9`
- Results:
  - base median: `0.6895708830561489`
  - dev median: `0.6754572099307552`
  - speedup: about `2.05%`

#### Sample set B
- Order:
  - odd rounds: `dev` then `base`
  - even rounds: `base` then `dev`
  - rounds: `8`
- Results:
  - base median: `0.6928998510120437`
  - dev median: `0.6767660090117715`
  - speedup: about `2.33%`

### Assessment
- The signal stayed positive even after removing fixed ordering bias.
- This looks like a real but modest DeltaBlue improvement.
- Current expectation:
  - worth keeping if code review stays comfortable with the builder-time
    specialized-call rewrite
  - not a huge benchmark swing, but meaningfully above noise
