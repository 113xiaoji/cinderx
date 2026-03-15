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
