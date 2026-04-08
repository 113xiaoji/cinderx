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
# also recognize the worker-specific run id environment.
worker = _has_token("--worker") or os.environ.get("PYPERFORMANCE_RUNID") not in (
    None,
    "",
)

if worker and not skip and os.environ.get("CINDERX_DISABLE") in (None, "", "0"):
    # 从外层命令继承的环境变量读取 JIT 配置。
    # 必须在 os.environ = dict(os.environ) 之前读取，因为替换后
    # 虽然仍可读取已有值，但需要在这里处理 PYTHONJITAUTO 的特殊情况。

    # PYTHONJITAUTO: 控制 compile_after_n_calls 阈值。
    # 必须从 C environ 中移除，防止 module_exec 阶段过早设置
    # compile_after_n_calls 导致内部启动函数（如 frozen importlib）
    # 被编译引发崩溃。改为 JIT 初始化后从 Python 层面设置。
    auto_threshold = os.environ.get("PYTHONJITAUTO")
    os.environ.pop("PYTHONJITAUTO", None)

    # PYTHONJITDISABLE: 控制是否禁用 JIT。
    os.environ.pop("PYTHONJITDISABLE", None)

    # 以下环境变量保留在 C environ 中，让 module_exec 的
    # FlagProcessor 正常处理（只设配置标志，不触发编译）：
    # - PYTHONJITENABLEJITLISTWILDCARDS: 允许 JIT list 使用通配符
    # - CINDERX_ENABLE_SPECIALIZED_OPCODES: 启用特化操作码

    # CINDERX_JIT_LIST: 逗号分隔的 JIT list 条目（如 "__main__:*,mymod:*"）
    jit_list_str = os.environ.get("CINDERX_JIT_LIST", "")

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

            # 从 CINDERX_JIT_LIST 环境变量加载 JIT list 条目
            if jit_list_str:
                for entry in jit_list_str.split(","):
                    entry = entry.strip()
                    if entry:
                        jit.append_jit_list(entry)

            # 从 PYTHONJITAUTO 环境变量设置编译阈值
            if auto_threshold is not None and auto_threshold.isdigit():
                jit.compile_after_n_calls(int(auto_threshold))
    except Exception:
        pass
