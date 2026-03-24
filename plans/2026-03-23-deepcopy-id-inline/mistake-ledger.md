# Mistake Ledger: deepcopy builtin id inline

## Active guardrails

- Do not skip the audit-hook correctness check just because the fast path looks
  mechanically simple.
- Do not spend remote time before a local regression or exact HIR observation
  exists for the chosen shape.
- Do not widen beyond HIR until a concrete backend gap is observed.
