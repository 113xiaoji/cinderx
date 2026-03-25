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
# use an explicit worker marker we control rather than piggybacking on
# PYPERFORMANCE_RUNID, which interferes with JIT initialization.
worker = _has_token("--worker") or _is_truthy(
    os.environ.get("CINDERX_PYPERF_WORKER")
)


def _setenv(key: str, value: str) -> None:
    os.putenv(key, value)
    os.environ[key] = value


def _delenv(key: str) -> None:
    os.unsetenv(key)
    os.environ.pop(key, None)


def _install_pyperf_precompile_hook() -> None:
    if not _is_truthy(os.environ.get("CINDERX_PYPERF_PRECOMPILE_ALL")):
        return

    try:
        import pyperf  # type: ignore
        import cinderx.jit as jit
    except Exception:
        return

    runner_cls = getattr(pyperf, "Runner", None)
    if runner_cls is None:
        return

    orig = getattr(runner_cls, "bench_time_func", None)
    if orig is None or getattr(orig, "_cinderx_precompile_patch", False):
        return

    def patched(self, name, time_func, *args, **kwargs):
        did_precompile = False

        def wrapped(loops, *inner_args):
            nonlocal did_precompile
            if not did_precompile:
                did_precompile = True
                try:
                    jit.precompile_all(0)
                except Exception:
                    pass
            return time_func(loops, *inner_args)

        return orig(self, name, wrapped, *args, **kwargs)

    patched._cinderx_precompile_patch = True  # type: ignore[attr-defined]
    runner_cls.bench_time_func = patched

if worker and not skip and os.environ.get("CINDERX_DISABLE") in (None, "", "0"):
    if _is_truthy(os.environ.get("CINDERX_PYPERF_WORKER")):
        # pyperf metadata collection can trip over os._Environ methods after
        # JIT-enabled startup. A plain dict avoids that worker-only bug for the
        # worker processes we explicitly mark.
        os.environ = dict(os.environ)

    # Keep the pyperformance driver process on the safe side by allowing it to
    # start with PYTHONJITDISABLE=1. Workers can still opt back into JIT by
    # inheriting a dedicated worker-only autojit setting.
    worker_autojit = os.environ.get("CINDERX_WORKER_PYTHONJITAUTO")
    if worker_autojit not in (None, ""):
        # Keep the process environment in sync with the Python mapping. JIT
        # initialization reads getenv(), so mutating only a copied dict is not
        # enough once PYPERFORMANCE_RUNID has swapped out os.environ.
        _setenv("PYTHONJITAUTO", worker_autojit)
        _delenv("PYTHONJITDISABLE")

    try:
        if _is_truthy(os.environ.get("CINDERX_PYPERF_WORKER")):
            import platform

            platform.architecture = (
                lambda executable=None, bits="", linkage="": ("64bit", "ELF")
            )

        import cinderx.jit as jit

        _install_pyperf_precompile_hook()

        if os.environ.get("PYTHONJITDISABLE") in (None, "", "0"):
            jit.enable()
            if _is_truthy(os.environ.get("CINDERX_ENABLE_SPECIALIZED_OPCODES")):
                jit.enable_specialized_opcodes()
            entries = os.environ.get("CINDERX_JITLIST_ENTRIES", "")
            if entries:
                for entry in entries.split(","):
                    entry = entry.strip()
                    if entry:
                        jit.append_jit_list(entry)
    except Exception:
        pass
