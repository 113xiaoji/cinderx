# Deliverable: issue-35 round/int float intrinsics

Implemented:
- new HIR opcodes for `DoubleToInt` and `DoubleRoundToInt`
- AArch64 LIR/codegen lowering via `Fcvtzs` and `Frintn`
- builtin-call rewrite from unary `int(float)` / `round(float)` away from generic `VectorCall`
- fallback frame-state reconstruction so slow-path interpreter fallback is safe for deopt cases
- ARM runtime regression coverage for both `int(float)` and `round(float)`

Remote ARM verification:
- host used: `124.70.162.35`
- targeted regressions passed:
  - `test_int_float_builtin_lowers_to_double_to_int`
  - `test_round_float_builtin_lowers_to_round_to_int`
- manual behavior checks passed for:
  - positive values
  - negative non-zero values
  - tie cases for `round()`
  - `NaN`, `inf`, `-inf`
  - large finite values that fall back to Python long creation

Final state:
- ready for normal code review / closeout
