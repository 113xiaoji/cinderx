# Proposal

Lower guarded builtin `id()` calls to a direct pointer-to-int primitive path in
JIT-compiled hot code, starting with the `deepcopy` case. Keep the first round
as small as possible and validate audit-hook semantics before widening the
optimization.
