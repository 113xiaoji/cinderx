#!/usr/bin/env python3
"""Direct-run a pyperformance benchmark module under selectable JIT strategies."""

import argparse
import dis
import importlib.util
import inspect
import itertools
import json
import statistics
import sys
import time
import types
from pathlib import Path

RECIPE_SUPPORTED_KEYS = {
    "name",
    "description",
    "stub_pyperf",
    "compile_strategy",
    "compile_names",
    "compile_exprs",
    "reprofile_exprs",
    "reprofile_warmup_runs",
    "reprofile_warmup_expr",
    "prewarm_runs",
    "specialized_opcodes",
}


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_pyperf_stub():
    pyperf = types.ModuleType("pyperf")

    class _Runner:
        metadata = {}

        def bench_func(self, *args, **kwargs):
            return None

    pyperf.Runner = _Runner
    sys.modules.setdefault("pyperf", pyperf)


def load_recipe(path: Path):
    recipe = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(recipe, dict):
        raise TypeError(f"recipe must be a JSON object: {path}")
    unknown_keys = sorted(set(recipe) - RECIPE_SUPPORTED_KEYS)
    if unknown_keys:
        raise ValueError(
            f"recipe contains unsupported keys {unknown_keys}: {path}"
        )
    return recipe


def apply_recipe_defaults(args, recipe):
    if not recipe:
        return args

    def apply_if_default(arg_name, default_value, recipe_key=None, transform=None):
        key = recipe_key or arg_name
        if key not in recipe:
            return
        if getattr(args, arg_name) != default_value:
            return
        value = recipe[key]
        if transform is not None:
            value = transform(value)
        setattr(args, arg_name, value)

    apply_if_default("stub_pyperf", False)
    apply_if_default("compile_strategy", "none")
    apply_if_default("compile_names", "")
    apply_if_default("compile_exprs_json", "[]", "compile_exprs", json.dumps)
    apply_if_default("reprofile_exprs_json", "[]", "reprofile_exprs", json.dumps)
    apply_if_default("reprofile_warmup_runs", 0)
    apply_if_default("reprofile_warmup_expr", "")
    apply_if_default("prewarm_runs", 0)
    apply_if_default("specialized_opcodes", False)
    return args


def collect_functions(module):
    funcs = []
    seen = set()

    def add(fn):
        ident = id(fn)
        if ident not in seen:
            seen.add(ident)
            funcs.append(fn)

    for value in module.__dict__.values():
        if inspect.isfunction(value) and getattr(value, "__module__", None) == module.__name__:
            add(value)
        elif inspect.isclass(value) and getattr(value, "__module__", None) == module.__name__:
            for member in value.__dict__.values():
                if inspect.isfunction(member) and getattr(member, "__module__", None) == module.__name__:
                    add(member)
    return funcs


def _flatten_compile_values(value):
    if inspect.isfunction(value):
        yield value
        return
    if inspect.ismethod(value):
        yield value.__func__
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _flatten_compile_values(item)
        return
    raise TypeError(f"compile expression resolved to unsupported value: {value!r}")


def resolve_compile_exprs(module, expressions):
    funcs = []
    seen = set()
    globals_dict = module.__dict__
    for expr in expressions:
        value = eval(expr, globals_dict, globals_dict)
        for fn in _flatten_compile_values(value):
            ident = id(fn)
            if ident not in seen:
                seen.add(ident)
                funcs.append(fn)
    return funcs


def resolve_callable_expr(module, expression):
    globals_dict = module.__dict__
    value = eval(expression, globals_dict, globals_dict)
    if not callable(value):
        raise TypeError(f"warmup expression did not resolve to a callable: {value!r}")
    return value


def has_backedge(fn) -> bool:
    return any(ins.opname == "JUMP_BACKWARD" for ins in dis.get_instructions(fn))


def aggregate_deopts(events):
    grouped = {}
    for event in events:
        key = (
            event["normal"].get("func_qualname"),
            event["int"].get("lineno"),
            event["normal"].get("description"),
            event["normal"].get("reason"),
        )
        grouped[key] = grouped.get(key, 0) + int(event["int"].get("count", 0))

    rows = []
    for (qualname, lineno, description, reason), count in grouped.items():
        rows.append(
            {
                "qualname": qualname,
                "lineno": lineno,
                "description": description,
                "reason": reason,
                "count": count,
            }
        )
    rows.sort(key=lambda row: row["count"], reverse=True)
    return rows


def aggregate_hot_loop_skips(events):
    grouped = {}
    for event in events:
        key = (
            event["normal"].get("func_qualname"),
            event["normal"].get("reason"),
        )
        grouped[key] = grouped.get(key, 0) + int(event["int"].get("count", 0))

    rows = []
    for (qualname, reason), count in grouped.items():
        rows.append(
            {
                "qualname": qualname,
                "reason": reason,
                "count": count,
            }
        )
    rows.sort(key=lambda row: row["count"], reverse=True)
    return rows


def choose_candidates(
    module,
    functions,
    strategy: str,
    explicit_names: set[str],
    compile_exprs,
):
    if strategy == "none":
        return []
    if strategy == "all":
        return functions
    if strategy == "backedge":
        return [fn for fn in functions if has_backedge(fn)]
    if strategy == "names":
        return [fn for fn in functions if fn.__qualname__ in explicit_names]
    if strategy == "exprs":
        return resolve_compile_exprs(module, compile_exprs)
    raise ValueError(f"unsupported strategy: {strategy}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module-path", required=True)
    parser.add_argument("--module-name", default="bench_module")
    parser.add_argument("--bench-func", required=True)
    parser.add_argument("--bench-args-json", default="[]")
    parser.add_argument(
        "--recipe-json",
        default="",
        help="Path to a JSON recipe that fills default harness settings",
    )
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--prewarm-runs", type=int, default=0)
    parser.add_argument(
        "--compile-strategy",
        choices=["none", "all", "backedge", "names", "exprs"],
        default="none",
    )
    parser.add_argument(
        "--compile-names",
        default="",
        help="Comma-separated qualnames when --compile-strategy=names",
    )
    parser.add_argument(
        "--compile-exprs-json",
        default="[]",
        help="JSON list of Python expressions resolving to functions when --compile-strategy=exprs",
    )
    parser.add_argument(
        "--reprofile-exprs-json",
        default="[]",
        help="JSON list of Python expressions resolving to functions to reprofile after warmup",
    )
    parser.add_argument(
        "--reprofile-warmup-runs",
        type=int,
        default=0,
        help="Extra interpreted warmup runs before reprofile helper is invoked",
    )
    parser.add_argument(
        "--reprofile-warmup-expr",
        default="",
        help="Python expression evaluated in module globals that returns a zero-arg warmup callable",
    )
    parser.add_argument(
        "--stub-pyperf",
        action="store_true",
        help="Install a tiny pyperf stub before importing the benchmark module",
    )
    parser.add_argument("--specialized-opcodes", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    recipe = None
    recipe_path = ""
    if args.recipe_json:
        recipe_path = str(Path(args.recipe_json).resolve())
        recipe = load_recipe(Path(args.recipe_json))
        args = apply_recipe_defaults(args, recipe)

    module_path = Path(args.module_path)
    if args.stub_pyperf:
        install_pyperf_stub()
    module = load_module(module_path, args.module_name)
    bench = getattr(module, args.bench_func)
    bench_args = json.loads(args.bench_args_json)

    import cinderx.jit as jit

    jit.enable()
    if args.specialized_opcodes:
        jit.enable_specialized_opcodes()
    else:
        jit.disable_specialized_opcodes()
    jit.compile_after_n_calls(1000000)

    functions = collect_functions(module)
    explicit_names = {
        name.strip() for name in args.compile_names.split(",") if name.strip()
    }
    compile_exprs = json.loads(args.compile_exprs_json)
    reprofile_exprs = json.loads(args.reprofile_exprs_json)
    reprofile_warmup_expr = args.reprofile_warmup_expr.strip()
    candidates = choose_candidates(
        module,
        functions,
        args.compile_strategy,
        explicit_names,
        compile_exprs,
    )

    for _ in range(args.prewarm_runs):
        bench(*bench_args)

    compiled = []
    for fn in candidates:
        try:
            ok = bool(jit.force_compile(fn))
        except Exception:
            ok = False
        if ok:
            compiled.append(fn.__qualname__)

    reprofiled = []
    if reprofile_exprs:
        reprofile_funcs = resolve_compile_exprs(module, reprofile_exprs)
        if reprofile_warmup_expr:
            reprofile_warmup = resolve_callable_expr(module, reprofile_warmup_expr)
        else:
            def reprofile_warmup():
                for _ in range(args.reprofile_warmup_runs):
                    bench(*bench_args)

        for fn in reprofile_funcs:
            try:
                compiled_stats = jit.get_function_compile_profile_stats(fn)
                if compiled_stats is None:
                    if not bool(jit.force_compile(fn)):
                        continue
                    compiled_stats = jit.get_function_compile_profile_stats(fn)
                if compiled_stats is None:
                    continue
                if jit.reprofile_after_interpreter_warmup(
                    fn, reprofile_warmup, compiled_stats
                ):
                    reprofiled.append(fn.__qualname__)
            except Exception:
                pass

    samples = []
    all_deopts = []
    all_hot_loop_skips = []
    for _ in range(args.samples):
        jit.get_and_clear_runtime_stats()
        t0 = time.perf_counter()
        bench_return = bench(*bench_args)
        wall = time.perf_counter() - t0
        stats = jit.get_and_clear_runtime_stats()
        samples.append({"bench_return_sec": bench_return, "wall_sec": wall})
        all_deopts.extend(stats.get("deopt", []))
        all_hot_loop_skips.extend(stats.get("hot_loop_skip", []))

    payload = {
        "recipe_name": recipe.get("name") if recipe else "",
        "recipe_path": recipe_path,
        "module_path": str(module_path),
        "bench_func": args.bench_func,
        "bench_args": bench_args,
        "compile_strategy": args.compile_strategy,
        "compile_exprs": compile_exprs,
        "reprofile_exprs": reprofile_exprs,
        "reprofile_warmup_runs": args.reprofile_warmup_runs,
        "reprofile_warmup_expr": reprofile_warmup_expr,
        "stub_pyperf": args.stub_pyperf,
        "specialized_opcodes": args.specialized_opcodes,
        "prewarm_runs": args.prewarm_runs,
        "candidate_count": len(functions),
        "selected_compile_count": len(candidates),
        "compiled_count": len(compiled),
        "compiled_qualnames": compiled,
        "reprofiled_count": len(reprofiled),
        "reprofiled_qualnames": reprofiled,
        "samples": samples,
        "median_wall_sec": statistics.median(sample["wall_sec"] for sample in samples),
        "min_wall_sec": min(sample["wall_sec"] for sample in samples),
        "total_deopt_count": sum(int(event["int"].get("count", 0)) for event in all_deopts),
        "top_deopts": aggregate_deopts(all_deopts)[:12],
        "total_hot_loop_skip_count": sum(
            int(event["int"].get("count", 0)) for event in all_hot_loop_skips
        ),
        "top_hot_loop_skips": aggregate_hot_loop_skips(all_hot_loop_skips)[:12],
    }

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    print(text)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
