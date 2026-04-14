from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
SITECUSTOMIZE = ROOT / "scripts" / "arm" / "pyperf_env_hook" / "sitecustomize.py"


class _FakeCode:
    def __init__(self, filename: str, name: str) -> None:
        self.co_filename = filename
        self.co_name = name


class _FakeFrame:
    def __init__(
        self,
        module_name: str,
        filename: str,
        func_name: str,
        back: "_FakeFrame | None" = None,
    ) -> None:
        self.f_globals = {"__name__": module_name}
        self.f_code = _FakeCode(filename, func_name)
        self.f_back = back


class _StubJit(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("cinderjit")
        self.enable_calls = 0
        self.specialized_calls = 0
        self.compile_after = []
        self.jitlists = []

    def enable(self) -> None:
        self.enable_calls += 1

    def enable_specialized_opcodes(self) -> None:
        self.specialized_calls += 1

    def compile_after_n_calls(self, calls: int) -> None:
        self.compile_after.append(calls)

    def append_jit_list(self, entry: str) -> None:
        self.jitlists.append(entry)


class PyperfEnvHookSitecustomizeTests(unittest.TestCase):
    @contextmanager
    def _sitecustomize_module(self):
        saved_argv = list(sys.argv)
        saved_profile = sys.getprofile()
        had_orig_argv = hasattr(sys, "orig_argv")
        saved_orig_argv = list(getattr(sys, "orig_argv", []))
        saved_environ = os.environ
        saved_cinderjit = sys.modules.get("cinderjit")
        stub_jit = _StubJit()
        sys.modules["cinderjit"] = stub_jit
        try:
            yield stub_jit
        finally:
            sys.setprofile(saved_profile)
            sys.argv = saved_argv
            if had_orig_argv:
                sys.orig_argv = saved_orig_argv
            elif hasattr(sys, "orig_argv"):
                delattr(sys, "orig_argv")
            os.environ = saved_environ
            if saved_cinderjit is None:
                sys.modules.pop("cinderjit", None)
            else:
                sys.modules["cinderjit"] = saved_cinderjit

    def _load_sitecustomize(self, *, script_path: str, env: dict[str, str]):
        sys.argv = [script_path]
        sys.orig_argv = [sys.executable, script_path]
        os.environ = dict(env)
        spec = importlib.util.spec_from_file_location(
            "test_pyperf_sitecustomize",
            SITECUSTOMIZE,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_deferred_worker_jit_ignores_pyperf_calls_from_main(self) -> None:
        script_path = "/tmp/run_benchmark.py"
        with self._sitecustomize_module() as stub_jit:
            self._load_sitecustomize(
                script_path=script_path,
                env={
                    "PYPERFORMANCE_RUNID": "worker-1",
                    "CINDERX_DEFER_WORKER_JIT": "1",
                    "CINDERX_JITLIST_ENTRIES": "__main__:*",
                },
            )
            callback = sys.getprofile()
            self.assertIsNotNone(callback)

            main_top = _FakeFrame("__main__", script_path, "<module>")
            pyperf_call = _FakeFrame(
                "pyperf._runner",
                "/venv/lib/python3.14/site-packages/pyperf/_runner.py",
                "bench_func",
                back=main_top,
            )
            callback(pyperf_call, "call", None)

            self.assertEqual(stub_jit.enable_calls, 0)
            self.assertIs(sys.getprofile(), callback)

    def test_deferred_worker_jit_enables_for_main_benchmark_function(self) -> None:
        script_path = "/tmp/run_benchmark.py"
        with self._sitecustomize_module() as stub_jit:
            self._load_sitecustomize(
                script_path=script_path,
                env={
                    "PYPERFORMANCE_RUNID": "worker-1",
                    "CINDERX_DEFER_WORKER_JIT": "1",
                    "CINDERX_JITLIST_ENTRIES": "__main__:*",
                    "CINDERX_ENABLE_SPECIALIZED_OPCODES": "1",
                },
            )
            callback = sys.getprofile()
            self.assertIsNotNone(callback)

            main_top = _FakeFrame("__main__", script_path, "<module>")
            benchmark_call = _FakeFrame(
                "__main__",
                script_path,
                "versus_cpu",
                back=main_top,
            )
            callback(benchmark_call, "call", None)

            self.assertEqual(stub_jit.enable_calls, 1)
            self.assertEqual(stub_jit.specialized_calls, 1)
            self.assertEqual(stub_jit.compile_after, [0])
            self.assertIn("__main__:*", stub_jit.jitlists)
            self.assertIsNone(sys.getprofile())

    def test_worker_autojit_threshold_is_preserved_with_jitlist_filter(self) -> None:
        with self._sitecustomize_module() as stub_jit:
            self._load_sitecustomize(
                script_path="/tmp/run_benchmark.py",
                env={
                    "PYPERFORMANCE_RUNID": "worker-1",
                    "CINDERX_WORKER_PYTHONJITAUTO": "50",
                    "CINDERX_JITLIST_ENTRIES": "__main__:*",
                },
            )

            self.assertEqual(stub_jit.enable_calls, 1)
            self.assertEqual(stub_jit.compile_after, [50])
            self.assertIn("__main__:*", stub_jit.jitlists)
            self.assertIsNone(sys.getprofile())

    def test_jitlist_without_worker_threshold_stays_eager(self) -> None:
        with self._sitecustomize_module() as stub_jit:
            self._load_sitecustomize(
                script_path="/tmp/run_benchmark.py",
                env={
                    "PYPERFORMANCE_RUNID": "worker-1",
                    "CINDERX_JITLIST_ENTRIES": "__main__:*",
                },
            )

            self.assertEqual(stub_jit.enable_calls, 1)
            self.assertEqual(stub_jit.compile_after, [0])
            self.assertIn("__main__:*", stub_jit.jitlists)


if __name__ == "__main__":
    unittest.main()
