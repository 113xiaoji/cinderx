import importlib.util
import tempfile
import textwrap
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
