# Deliverable: CinderX 3.14 vs CPython 3.14 Interpreter Differences

## Baseline
- CinderX branch: `bench-cur-7c361dce` @ `ed681292cab44e007effb96471999d172a90448d`
- CPython baseline: `3.14` branch @ `a58ea8c21239a23b03446aecd030995bbe40b7a7` (2026-02-27)

## What Is Different (Interpreter Hot Path)
1. Adaptive gating and call-count bookkeeping are added to frame transitions.
- CinderX adds `adaptive_enabled`, delayed adaptive threshold, and call-count updates:
  - `cinderx/Interpreter/3.14/interpreter.c:37-42`
  - `cinderx/Interpreter/3.14/Includes/ceval_macros.h:434-461`
  - generated call sites, e.g. `.../generated_cases.c.h:675`, `14108`
- Upstream CPython has no equivalent call-count macros in generated cases.

2. Adaptive counter advance is branch-gated in CinderX.
- CinderX:
  - `cinderx/Interpreter/3.14/Includes/ceval_macros.h:283-286`
- CPython:
  - `artifacts/cpython-3.14-upstream/Python/ceval_macros.h:288-291`

3. PEP523 checks are changed from pure-null-check to "null-or-self" check.
- CinderX check macro:
  - `cinderx/Interpreter/3.14/Includes/ceval_macros.h:170`
- Upstream check style:
  - `artifacts/cpython-3.14-upstream/Python/ceval_macros.h:178`

4. CinderX adds `EXTENDED_OPCODE` mega-dispatch and many static/primitive ops behind it.
- target entry:
  - `cinderx/Interpreter/3.14/Includes/generated_cases.c.h:5691`
- implementation source:
  - `cinderx/Interpreter/3.14/cinder-bytecodes.c:507-1292`
- target diff summary:
  - CinderX 229 targets vs CPython 227
  - extra targets: `EXTENDED_OPCODE`, `EAGER_IMPORT_NAME`

5. Core opcode overrides for Cinder features.
- call/send/frame ops:
  - `_DO_CALL` `:177`, `_DO_CALL_KW` `:269`, `_DO_CALL_FUNCTION_EX` `:340`, `_SEND` `:419`, `_PUSH_FRAME` `:249`
- collection ops:
  - `MAP_ADD` `:468` (`Ci_DictOrChecked_SetItem`)
  - `LIST_APPEND` `:493` (`Ci_ListOrCheckedList_Append`)
- return/yield hooks:
  - `RETURN_VALUE` `:1296`, `RETURN_GENERATOR` `:1317`, `YIELD_VALUE` `:1344`

6. Awaitable/coroutine helper path is Cinder-specific.
- Cinder uses JIT coroutine helpers in borrowed ceval:
  - `cinderx/Interpreter/3.14/borrowed-ceval.c.template:107-108`, `123-131`
- CPython uses `_PyCoro_GetAwaitableIter` / `_PyGen_yf`.

## Optimization Priorities (for Interpreter Execution)
### P0 (highest ROI, lowest risk)
- Minimize `CI_UPDATE_CALL_COUNT`/`CI_SET_ADAPTIVE...` overhead on hot paths.
- Idea:
  - Fast-path skip when adaptive delay is disabled.
  - Hoist code-object checks where possible.
  - Avoid repeated `PyCode_Check` + `codeExtra()` in the same frame transition.

### P1
- Reduce branch pressure from `if (adaptive_enabled)` around adaptive counters.
- Idea:
  - compile-time specialization of macros for always-on mode,
  - or keep a per-frame/epoch cached mode to avoid repeated branch checks.

### P2
- Break up `EXTENDED_OPCODE` mega-switch for high-frequency ext ops.
- Idea:
  - split hottest ext ops into dedicated real targets (or a small fast-switch front).
  - keep rare ext ops in fallback switch.

### P3
- Reassess PEP523 hot checks and checked-collection wrappers in non-checked common paths.
- Idea:
  - tighten likely/unlikely annotations and branch order.
  - keep semantics identical while reducing mispredicts.

## Suggested Measurement Plan
1. Add A/B build flags:
- disable only adaptive-bookkeeping macros.
- disable adaptive branch-gating only.
- split-ext-op prototype on top-N ext ops.

2. Run focused benchmarks:
- call-heavy (`richards`, recursive/function-call loops)
- container-heavy (`list.append`, dict-comprehension)
- static-python-heavy workloads that emit ext ops

3. Capture counters:
- `cycles`, `instructions`, `branches`, `branch-misses`, `icache misses`

4. Guard correctness:
- `cinderx/PythonLib/test_cinderx/*` static-related suites
- `test_oss_quick.py`
