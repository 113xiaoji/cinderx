import os
import sys
import inspect


def _argv_tokens():
    toks = []
    orig = getattr(sys, "orig_argv", None)
    if orig:
        toks.extend([str(x) for x in orig])
    toks.extend([str(x) for x in getattr(sys, "argv", [])])
    return toks


def _is_truthy(value: str | None) -> bool:
    return value in {"1", "true", "TRUE", "yes", "YES", "on", "ON"}


tokens = _argv_tokens()
argv = getattr(sys, "argv", [])
argv0 = argv[0] if argv else ""


def _has_token(name: str) -> bool:
    return any(t == name for t in tokens)


def _has_suffix(suffix: str) -> bool:
    return any(t.endswith(suffix) for t in tokens)


def _contains(substr: str) -> bool:
    return any(substr in t for t in tokens)


_PRECOMPILED_BENCH_FILES: set[tuple[int, str]] = set()


def _iter_local_functions(globals_dict: dict[str, object], script_str: str):
    result = []
    seen: set[int] = set()

    def add_obj(obj: object) -> None:
        if inspect.isfunction(obj):
            func = obj
            if func.__code__.co_filename != script_str:
                return
            ident = id(func)
            if ident in seen:
                return
            seen.add(ident)
            result.append(func)
            return
        if inspect.isclass(obj):
            for member in obj.__dict__.values():
                add_obj(member)

    for value in globals_dict.values():
        add_obj(value)
    return result


def _install_pyperf_precompile_hook(jit) -> None:
    if not _is_truthy(os.environ.get("CINDERX_PYPERF_PRECOMPILE_LOCALS")):
        return
    if not _has_suffix("run_benchmark.py"):
        return

    try:
        import pyperf
    except Exception:
        return

    if getattr(pyperf.Runner, "_cinderx_precompile_patched", False):
        return

    def _precompile_locals(func) -> None:
        globals_dict = getattr(func, "__globals__", None)
        code = getattr(func, "__code__", None)
        if not isinstance(globals_dict, dict) or code is None:
            return
        key = (id(globals_dict), code.co_filename)
        if key in _PRECOMPILED_BENCH_FILES:
            return
        for local in _iter_local_functions(globals_dict, code.co_filename):
            try:
                jit.force_compile(local)
            except Exception:
                pass
        _PRECOMPILED_BENCH_FILES.add(key)

    def _wrap(method):
        def inner(self, name, func, *args, **kwargs):
            _precompile_locals(func)
            return method(self, name, func, *args, **kwargs)

        return inner

    pyperf.Runner.bench_func = _wrap(pyperf.Runner.bench_func)
    pyperf.Runner.bench_time_func = _wrap(pyperf.Runner.bench_time_func)
    pyperf.Runner._cinderx_precompile_patched = True


skip = (
    _has_token("ensurepip")
    or _has_token("pip")
    or _has_suffix("get-pip.py")
    or argv0.endswith("get-pip.py")
    or _contains('run_module("pip"')
    or _contains("run_module('pip'")
)

# pyperformance 1.14 executes benchmark scripts directly and no longer passes
# the historical "--worker" argv token. Keep supporting the old shape, but
# also recognize the worker-specific run id environment.
worker = _has_token("--worker") or os.environ.get("PYPERFORMANCE_RUNID") not in (
    None,
    "",
)

if worker and not skip and os.environ.get("CINDERX_DISABLE") in (None, "", "0"):
    if os.environ.get("PYPERFORMANCE_RUNID"):
        # pyperf metadata collection can trip over os._Environ methods after
        # JIT-enabled startup. A plain dict avoids that worker-only bug.
        os.environ = dict(os.environ)

    try:
        if os.environ.get("PYPERFORMANCE_RUNID"):
            import platform

            platform.architecture = (
                lambda executable=None, bits="", linkage="": ("64bit", "ELF")
            )

        import cinderx.jit as jit

        if os.environ.get("PYTHONJITDISABLE") in (None, "", "0"):
            jit.enable()
            if _is_truthy(os.environ.get("CINDERX_ENABLE_SPECIALIZED_OPCODES")):
                jit.enable_specialized_opcodes()
            if _is_truthy(
                os.environ.get("CINDERX_ENABLE_TYPE_ANNOTATION_GUARDS")
            ):
                jit.enable_emit_type_annotation_guards()
            _install_pyperf_precompile_hook(jit)
            entries = os.environ.get("CINDERX_JITLIST_ENTRIES", "")
            if entries:
                for entry in entries.split(","):
                    entry = entry.strip()
                    if entry:
                        jit.append_jit_list(entry)
    except Exception:
        pass
