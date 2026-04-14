import os
import sys


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
argv0_abspath = os.path.abspath(argv0) if argv0 not in ("", "-c") else argv0


def _has_token(name: str) -> bool:
    return any(t == name for t in tokens)


def _has_suffix(suffix: str) -> bool:
    return any(t.endswith(suffix) for t in tokens)


def _contains(substr: str) -> bool:
    return any(substr in t for t in tokens)


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


def _iter_jitlist_entries(raw: str):
    for entry in raw.split(","):
        entry = entry.strip()
        if entry:
            yield entry


def _worker_jit_api():
    try:
        import cinderjit as jit_ext

        return jit_ext
    except Exception:
        try:
            import cinderx.jit as jit_ext

            return jit_ext
        except Exception:
            return None


def _append_worker_jitlists(jit_ext, raw_entries: str) -> None:
    if not raw_entries:
        return

    script_main = argv0.endswith("run_benchmark.py")
    seen = set()
    for entry in _iter_jitlist_entries(raw_entries):
        if entry not in seen:
            jit_ext.append_jit_list(entry)
            seen.add(entry)
        if not script_main or ":" not in entry:
            continue
        module, qualname = entry.split(":", 1)
        if module == "__main__":
            continue
        main_entry = f"__main__:{qualname}"
        if main_entry not in seen:
            jit_ext.append_jit_list(main_entry)
            seen.add(main_entry)


def _enable_worker_jit(
    worker_autojit: str | None,
    raw_jitlist: str,
) -> None:
    if os.environ.get("PYPERFORMANCE_RUNID"):
        import platform

        platform.architecture = (
            lambda executable=None, bits="", linkage="": ("64bit", "ELF")
        )

    jit = _worker_jit_api()
    if jit is None:
        raise RuntimeError("unable to import cinderjit or cinderx.jit")

    jit.enable()
    if _is_truthy(os.environ.get("CINDERX_ENABLE_SPECIALIZED_OPCODES")):
        jit.enable_specialized_opcodes()

    if raw_jitlist:
        # When a worker auto-JIT threshold is present, treat the JIT list as a
        # filter on what may compile rather than forcing eager first-call
        # compilation of every matching function.
        threshold = 0
        if worker_autojit not in (None, ""):
            try:
                threshold = int(worker_autojit)
            except Exception:
                threshold = 0
        jit.compile_after_n_calls(threshold)
        _append_worker_jitlists(jit, raw_jitlist)
    elif worker_autojit not in (None, ""):
        try:
            jit.compile_after_n_calls(int(worker_autojit))
        except Exception:
            pass


if worker and not skip and os.environ.get("CINDERX_DISABLE") in (None, "", "0"):
    if os.environ.get("PYPERFORMANCE_RUNID"):
        # pyperf metadata collection can trip over os._Environ methods after
        # JIT-enabled startup. A plain dict avoids that worker-only bug.
        os.environ = dict(os.environ)

    worker_autojit = os.environ.get("CINDERX_WORKER_PYTHONJITAUTO")
    raw_jitlist = os.environ.get("CINDERX_JITLIST_ENTRIES", "")
    defer_worker_jit = _is_truthy(os.environ.get("CINDERX_DEFER_WORKER_JIT"))

    try:
        if defer_worker_jit and argv0 not in ("", "-c"):
            def _deferred_enable(frame, event, arg):
                if event != "call":
                    return None
                if frame.f_globals.get("__name__") != "__main__":
                    return None
                if frame.f_code.co_name == "<module>":
                    return None
                if (
                    argv0_abspath not in ("", "-c")
                    and os.path.abspath(frame.f_code.co_filename) != argv0_abspath
                ):
                    return None
                sys.setprofile(None)
                _enable_worker_jit(worker_autojit, raw_jitlist)
                return None

            sys.setprofile(_deferred_enable)
        else:
            _enable_worker_jit(worker_autojit, raw_jitlist)
    except Exception:
        pass
