# Copyright (c) Meta Platforms, Inc. and affiliates.

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


JIT_PY = Path(__file__).resolve().parents[1] / "cinderx" / "jit.py"


class JitWrapperCompatibilityTests(unittest.TestCase):
    def _load_with_fake_cinderjit(self, fake_cinderjit: types.ModuleType):
        spec = importlib.util.spec_from_file_location(
            "jit_wrapper_under_test", JIT_PY
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"cinderjit": fake_cinderjit}):
            spec.loader.exec_module(module)
        return module

    def test_partial_cinderjit_keeps_core_bindings(self) -> None:
        fake = types.ModuleType("cinderjit")
        calls: list[object] = []

        def force_compile(func):
            calls.append(("force_compile", func.__name__))
            return True

        def enable():
            calls.append("enable")

        optional_missing = {
            "get_osr_entries",
            "get_deopt_entries",
            "run_osr_test_entry",
        }

        def dynamic_attr(name):
            if name in optional_missing:
                raise AttributeError(name)
            return lambda *args, **kwargs: None

        fake.force_compile = force_compile
        fake.enable = enable
        fake.__getattr__ = dynamic_attr

        wrapper = self._load_with_fake_cinderjit(fake)

        def target():
            return 42

        wrapper.enable()
        self.assertEqual(calls[0], "enable")
        self.assertTrue(wrapper.force_compile(target))
        self.assertEqual(calls[1], ("force_compile", "target"))

        self.assertEqual(wrapper.get_osr_entries(target), [])
        self.assertEqual(wrapper.get_deopt_entries(target), [])
        self.assertIsNone(wrapper.run_osr_test_entry(target, ()))


if __name__ == "__main__":
    unittest.main()
