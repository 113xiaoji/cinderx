# AGENTS.md

This file provides repository-level instructions for AI coding agents working
in this CinderX checkout.

## Mandatory pyperformance Method

All CinderX performance testing that uses pyperformance MUST follow:

`docs/pyperformance-cinderx-integration.md`

Do not invent or use an ad-hoc pyperformance setup unless the user explicitly
asks for a one-off diagnostic. In normal performance work, use the documented
method as the source of truth, including:

- the documented Python path detection flow;
- the driver venv with `--system-site-packages`;
- the patched pyperformance worker venv creation logic;
- the documented `jit_list`;
- inherited `LD_LIBRARY_PATH` and `PYTHONJIT*` environment variables;
- the documented benchmark command shape and affinity variable.

If the method needs to change, update
`docs/pyperformance-cinderx-integration.md` first, then record the reason and
verification evidence in `findings.md`.

For performance claims, record key benchmark inputs, command shape, result
files, and conclusions in `findings.md` before reporting completion.
