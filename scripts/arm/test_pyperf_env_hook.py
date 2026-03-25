from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import platform
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parent
SITECUSTOMIZE = ROOT / "pyperf_env_hook" / "sitecustomize.py"


class _FakeJit(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("cinderx.jit")
        self.events: list[tuple[str, object | None]] = []

    def enable(self) -> None:
        self.events.append(("enable", None))

    def enable_specialized_opcodes(self) -> None:
        self.events.append(("specialized", None))

    def append_jit_list(self, entry: str) -> None:
        self.events.append(("append_jit_list", entry))

    def precompile_all(self, workers: int = 0) -> bool:
        self.events.append(("precompile_all", workers))
        return True


class _FakeRunner:
    def bench_time_func(self, name, time_func, *args, **kwargs):
        return time_func(7, *args)


class _SitecustomizeHarness:
    ENV_KEYS = (
        "CINDERX_DISABLE",
        "CINDERX_ENABLE_SPECIALIZED_OPCODES",
        "CINDERX_JITLIST_ENTRIES",
        "CINDERX_PYPERF_PRECOMPILE_ALL",
        "CINDERX_PYPERF_WORKER",
        "CINDERX_WORKER_PYTHONJITAUTO",
        "PYPERFORMANCE_RUNID",
        "PYTHONJITAUTO",
        "PYTHONJITDISABLE",
    )

    def __init__(self, testcase: unittest.TestCase) -> None:
        self.testcase = testcase
        self.saved_env = {key: os.environ.get(key) for key in self.ENV_KEYS}
        self.saved_modules = {
            key: sys.modules.get(key)
            for key in ("cinderx", "cinderx.jit", "pyperf")
        }
        self.saved_architecture = platform.architecture
        self.fake_jit = _FakeJit()
        fake_cinderx = types.ModuleType("cinderx")
        fake_cinderx.jit = self.fake_jit
        fake_pyperf = types.ModuleType("pyperf")
        fake_pyperf.Runner = _FakeRunner
        sys.modules["cinderx"] = fake_cinderx
        sys.modules["cinderx.jit"] = self.fake_jit
        sys.modules["pyperf"] = fake_pyperf

    def close(self) -> None:
        for key, value in self.saved_env.items():
            if value is None:
                os.unsetenv(key)
                os.environ.pop(key, None)
            else:
                os.putenv(key, value)
                os.environ[key] = value

        for key, value in self.saved_modules.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value

        platform.architecture = self.saved_architecture

    def load(self) -> types.ModuleType:
        name = f"_issue63_sitecustomize_{id(self)}"
        spec = importlib.util.spec_from_file_location(name, SITECUSTOMIZE)
        self.testcase.assertIsNotNone(spec)
        self.testcase.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class SitecustomizeTests(unittest.TestCase):
    def _harness(self) -> _SitecustomizeHarness:
        harness = _SitecustomizeHarness(self)
        self.addCleanup(harness.close)
        return harness

    def test_worker_marker_rewrites_env_and_enables_jit(self) -> None:
        harness = self._harness()
        os.environ["CINDERX_PYPERF_WORKER"] = "1"
        os.environ["CINDERX_WORKER_PYTHONJITAUTO"] = "10"
        os.environ["PYTHONJITDISABLE"] = "1"

        harness.load()

        self.assertEqual(os.environ.get("PYTHONJITAUTO"), "10")
        self.assertNotIn("PYTHONJITDISABLE", os.environ)
        self.assertIn(("enable", None), harness.fake_jit.events)

    def test_runid_alone_no_longer_marks_worker(self) -> None:
        harness = self._harness()
        os.environ["PYPERFORMANCE_RUNID"] = "pyperf-probe"
        os.environ["PYTHONJITDISABLE"] = "1"

        harness.load()

        self.assertEqual(os.environ.get("PYTHONJITDISABLE"), "1")
        self.assertNotIn(("enable", None), harness.fake_jit.events)

    def test_precompile_hook_wraps_bench_time_func_once(self) -> None:
        harness = self._harness()
        os.environ["CINDERX_PYPERF_WORKER"] = "1"
        os.environ["CINDERX_PYPERF_PRECOMPILE_ALL"] = "1"

        harness.load()

        runner = sys.modules["pyperf"].Runner()
        calls: list[tuple[str, int]] = []

        def time_func(loops: int) -> int:
            calls.append(("time_func", loops))
            return loops + 1

        result = runner.bench_time_func("bench", time_func)

        self.assertEqual(result, 8)
        self.assertEqual(calls, [("time_func", 7)])
        self.assertTrue(
            getattr(sys.modules["pyperf"].Runner.bench_time_func, "_cinderx_precompile_patch", False)
        )
        self.assertIn(("precompile_all", 0), harness.fake_jit.events)
        self.assertEqual(
            harness.fake_jit.events.count(("precompile_all", 0)),
            1,
        )


if __name__ == "__main__":
    unittest.main()
