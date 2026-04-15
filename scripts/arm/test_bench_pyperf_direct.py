import importlib.util
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).with_name("bench_pyperf_direct.py")
SPEC = importlib.util.spec_from_file_location("bench_pyperf_direct", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def load_temp_module(source: str):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "temp_module.py"
        path.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("temp_module", path)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        return module


class BenchPyperfDirectTests(unittest.TestCase):
    def test_load_recipe_rejects_unknown_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recipe.json"
            path.write_text(
                json.dumps({"name": "bad", "unknown_key": 1}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                MODULE.load_recipe(path)

    def test_apply_recipe_defaults_fills_empty_cli_values(self):
        args = type(
            "Args",
            (),
            {
                "stub_pyperf": False,
                "compile_strategy": "none",
                "compile_names": "",
                "compile_exprs_json": "[]",
                "reprofile_exprs_json": "[]",
                "reprofile_warmup_runs": 0,
                "reprofile_warmup_expr": "",
                "prewarm_runs": 0,
                "specialized_opcodes": False,
            },
        )()
        recipe = {
            "name": "bm_go_board_useful",
            "stub_pyperf": True,
            "compile_strategy": "exprs",
            "compile_exprs": ["Board.useful"],
            "reprofile_exprs": ["Board.useful"],
            "reprofile_warmup_runs": 7,
            "reprofile_warmup_expr": "make_warmup()",
            "prewarm_runs": 3,
            "specialized_opcodes": True,
        }

        MODULE.apply_recipe_defaults(args, recipe)

        self.assertTrue(args.stub_pyperf)
        self.assertEqual(args.compile_strategy, "exprs")
        self.assertEqual(args.compile_exprs_json, '["Board.useful"]')
        self.assertEqual(args.reprofile_exprs_json, '["Board.useful"]')
        self.assertEqual(args.reprofile_warmup_runs, 7)
        self.assertEqual(args.reprofile_warmup_expr, "make_warmup()")
        self.assertEqual(args.prewarm_runs, 3)
        self.assertTrue(args.specialized_opcodes)

    def test_apply_recipe_defaults_preserves_explicit_cli_overrides(self):
        args = type(
            "Args",
            (),
            {
                "stub_pyperf": True,
                "compile_strategy": "names",
                "compile_names": "Board.useful",
                "compile_exprs_json": '["explicit"]',
                "reprofile_exprs_json": '["explicit"]',
                "reprofile_warmup_runs": 11,
                "reprofile_warmup_expr": "explicit_warmup()",
                "prewarm_runs": 2,
                "specialized_opcodes": True,
            },
        )()
        recipe = {
            "stub_pyperf": False,
            "compile_strategy": "exprs",
            "compile_names": "Board.other",
            "compile_exprs": ["recipe"],
            "reprofile_exprs": ["recipe"],
            "reprofile_warmup_runs": 1,
            "reprofile_warmup_expr": "recipe_warmup()",
            "prewarm_runs": 0,
            "specialized_opcodes": False,
        }

        MODULE.apply_recipe_defaults(args, recipe)

        self.assertTrue(args.stub_pyperf)
        self.assertEqual(args.compile_strategy, "names")
        self.assertEqual(args.compile_names, "Board.useful")
        self.assertEqual(args.compile_exprs_json, '["explicit"]')
        self.assertEqual(args.reprofile_exprs_json, '["explicit"]')
        self.assertEqual(args.reprofile_warmup_runs, 11)
        self.assertEqual(args.reprofile_warmup_expr, "explicit_warmup()")
        self.assertEqual(args.prewarm_runs, 2)
        self.assertTrue(args.specialized_opcodes)

    def test_resolve_compile_exprs_supports_functions_methods_and_lists(self):
        module = load_temp_module(
            textwrap.dedent(
                """
                def top():
                    return 1

                class C:
                    def method(self):
                        return 2

                targets = [top, C.method]
                """
            )
        )

        funcs = MODULE.resolve_compile_exprs(module, ["top", "C.method", "targets"])
        qualnames = [fn.__qualname__ for fn in funcs]
        self.assertEqual(qualnames, ["top", "C.method"])

    def test_resolve_compile_exprs_rejects_non_callable_values(self):
        module = load_temp_module(
            textwrap.dedent(
                """
                x = 42
                """
            )
        )

        with self.assertRaises(TypeError):
            MODULE.resolve_compile_exprs(module, ["x"])

    def test_resolve_compile_exprs_can_drive_reprofile_targets(self):
        module = load_temp_module(
            textwrap.dedent(
                """
                def warm():
                    return 1

                class C:
                    def method(self):
                        return 2

                reprofile_targets = [warm, C.method]
                """
            )
        )

        funcs = MODULE.resolve_compile_exprs(module, ["reprofile_targets"])
        qualnames = [fn.__qualname__ for fn in funcs]
        self.assertEqual(qualnames, ["warm", "C.method"])

    def test_install_pyperf_stub_supports_benchmark_imports(self):
        with patch.dict(sys.modules, {}, clear=False):
            MODULE.install_pyperf_stub()
            module = load_temp_module(
                textwrap.dedent(
                    """
                    import pyperf

                    runner = pyperf.Runner()

                    def bench():
                        return 1
                    """
                )
            )
            self.assertTrue(hasattr(module, "runner"))

    def test_reprofile_path_can_bootstrap_compile_profile(self):
        class FakeJit:
            def __init__(self):
                self.force_compile_calls = 0
                self.reprofile_calls = 0

            def force_compile(self, fn):
                self.force_compile_calls += 1
                return True

            def get_function_compile_profile_stats(self, fn):
                if self.force_compile_calls == 0:
                    return None
                return {"mwv_sites": 0}

            def reprofile_after_interpreter_warmup(self, fn, warmup, compiled_stats):
                self.reprofile_calls += 1
                warmup()
                return compiled_stats == {"mwv_sites": 0}

        fake = FakeJit()

        with patch.dict(sys.modules, {}, clear=False):
            MODULE.install_pyperf_stub()
            module = load_temp_module(
                textwrap.dedent(
                    """
                    import pyperf

                    def bench():
                        return 1
                    """
                )
            )

            funcs = MODULE.resolve_compile_exprs(module, ["bench"])
            reprofiled = []

            def warmup():
                return None

            for fn in funcs:
                compiled_stats = fake.get_function_compile_profile_stats(fn)
                compiled_stats = fake.get_function_compile_profile_stats(fn)
                if compiled_stats is None:
                    if not bool(fake.force_compile(fn)):
                        continue
                    compiled_stats = fake.get_function_compile_profile_stats(fn)
                if compiled_stats is None:
                    continue
                if fake.reprofile_after_interpreter_warmup(fn, warmup, compiled_stats):
                    reprofiled.append(fn.__qualname__)

        self.assertEqual(fake.force_compile_calls, 1)
        self.assertEqual(fake.reprofile_calls, 1)
        self.assertEqual(reprofiled, ["bench"])

    def test_resolve_callable_expr_returns_callable(self):
        module = load_temp_module(
            textwrap.dedent(
                """
                def make_warmup():
                    return lambda: 42
                """
            )
        )
        warmup = MODULE.resolve_callable_expr(module, "make_warmup()")
        self.assertTrue(callable(warmup))
        self.assertEqual(warmup(), 42)

    def test_resolve_callable_expr_rejects_non_callable(self):
        module = load_temp_module(
            textwrap.dedent(
                """
                x = 123
                """
            )
        )
        with self.assertRaises(TypeError):
            MODULE.resolve_callable_expr(module, "x")


if __name__ == "__main__":
    unittest.main()
