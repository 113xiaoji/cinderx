# Mistake Ledger: tomli_loads BinaryOp exception edge

## Active prevention rules

- No remote build before:
  - local code path identification
  - a written hypothesis
  - and an explicit validation target
- No repeated remote run without:
  - a new hypothesis
  - a changed patch
  - or a changed benchmark method
- Do not trust issue wording alone; refresh current-tip evidence first

## 2026-03-19 - current exception model can make the issue wording misleading

- Symptom:
  - issue text frames the problem as a missing `BinaryOp` exception edge
- Root cause:
  - current local code read suggests generic exceptions on these paths already
    deopt by design instead of branching to compiled handlers
- Detection gap:
  - it was easy to assume a single missing CFG edge without checking the wider
    exception-handling model
- Prevention rule:
  - before implementing a handler-edge fix, verify whether the relevant
    exception opcodes are compiled at all on the current path
- Validation added:
  - local notes now explicitly distinguish:
    - compiled-exception support
    - pragmatic repeated-deopt suppression

## 2026-03-19 - do not treat network outages as failed validation hypotheses

- Symptom:
  - the ARM host timed out during tar upload and SSH entry
- Root cause:
  - remote connectivity, not build/test logic
- Detection gap:
  - none in the JIT investigation itself
- Prevention rule:
  - when the remote host is unreachable, stop remote retries after a light
    confirmation attempt and keep progressing on local reasoning only

## 2026-03-19 - standard entrypoint support files may be missing from the current workspace

- Symptom:
  - the standard remote entrypoint initially failed before benchmark execution
    because support files were missing
- Root cause:
  - this workspace lacked:
    - `scripts/arm/verify_pyperf_venv.py`
    - `scripts/arm/pyperf_env_hook/sitecustomize.py`
- Prevention rule:
  - before treating an entrypoint failure as a benchmark or JIT failure,
    confirm the entrypoint support files exist in the current source tree

## 2026-03-19 - separate the target-case pass from later benchmark-worker crashes

- Symptom:
  - the minimal `skip_chars` regression passed, but the benchmark still crashed
    later in autojit
- Root cause:
  - the first patch fixed the target loop, but the broader `tomli_loads`
    compile surface still contains unrelated blockers
- Prevention rule:
  - record target-case regressions and later benchmark-worker crashes as
    separate signals rather than collapsing them into one verdict

## 2026-03-19 - isolate remote workdirs and venvs before blaming a patch for wide autojit crashes

- Symptom:
  - the shared-environment autojit run crashed deep in unrelated stdlib compile
    paths
- Root cause:
  - shared workdirs and shared driver/pyperf environments let unrelated code and
    prior setup leak into the benchmark run
- Prevention rule:
  - when a case needs a narrow benchmark verdict, create an isolated workdir,
    isolated driver venv, and isolated pyperformance venv first
- Validation added:
  - round 2 isolated environment showed the issue48 patch itself does not crash
    under narrow autojit
