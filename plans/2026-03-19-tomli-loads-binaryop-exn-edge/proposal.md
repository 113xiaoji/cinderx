## Proposal

- Case: `tomli_loads`
- Issue: `#48`
- Symptom:
  - `BinaryOp<Subscript>` in `skip_chars()` raises `IndexError` at the string
    boundary, but the JIT-compiled path does not transfer control into the
    compiled `except IndexError` handler
- Primary hypothesis:
  - the HIR builder or later CFG cleanup loses the exception edge for
    `BINARY_SUBSCR`/`BinaryOp<Subscript>` in this shape, so runtime exception
    handling is forced to deopt as `UnhandledException`
- Planned order:
  - `HIR -> LIR -> codegen`
- Validation:
  - reproduce the minimal `skip_chars` shape
  - confirm the same failure mode in `tomli_loads`
  - first attempt a narrow HIR-side exception-edge fix before touching later
    lowering layers
- Exit criteria:
  - the target `BinaryOp<Subscript>` shape stops deopting on expected
    `IndexError`
  - `tomli_loads` shows a clear ARM improvement
  - no major regression appears across the requested benchmark matrix
