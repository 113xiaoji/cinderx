import importlib.util
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


if __name__ == "__main__":
    unittest.main()
