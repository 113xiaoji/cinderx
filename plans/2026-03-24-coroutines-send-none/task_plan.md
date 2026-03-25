# Task Plan: coroutines send(None) builder rewrite

## Goal
Fix pyperformance `coroutines` benchmark issue #65 by rewriting the narrow Python 3.14 `coro.send(None)` loop shape in the HIR builder so normal coroutine completion stays on compiled control flow instead of surfacing as `UnhandledException / CallMethod`.

## Workflow
1. Brainstorming
2. Writing-Plans
3. Test-Driven-Development
4. Verification-Before-Completion

## Scope
- Limit the optimization to a very narrow builder-layer pattern.
- Do not introduce a late HIR pass.
- Do not change LIR/codegen/runtime helpers unless the builder path proves insufficient.
- Use the shared remote entrypoint for meaningful validation.

## Questions
1. What exact bytecode shape can we safely match in Python 3.14?
2. What minimal builder rewrite produces `Send + GetSecondOutput<CInt64> + CondBranch`?
3. Can we prove the old `UnhandledException / CallMethod` disappears on the benchmark shape?

## Remote Execution
- Shared scheduler DB expected by skill: `plans/remote-scheduler.sqlite3`
- Scheduler helper script is not present in this repo, so this round will record that gap and continue with the standard remote entrypoint directly.
- Remote test entry: `scripts/arm/remote_update_build_test.sh`

## Status
- [x] Brainstorming
- [x] Writing-Plans
- [x] Test-Driven-Development
- [x] Verification-Before-Completion
