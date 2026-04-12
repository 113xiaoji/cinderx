import subprocess
import sys
import textwrap
import unittest

import cinderx.jit as jit
import cinderx.test_support as cinder_support


class TieringApiTests(unittest.TestCase):
    def setUp(self) -> None:
        jit.enable()
        if not jit.is_enabled():
            self.skipTest("requires JIT")
        self._compile_after_n_calls = jit.get_compile_after_n_calls()
        get_baseline = getattr(jit, "get_baseline_compile_after_n_calls", None)
        self._baseline_compile_after_n_calls = get_baseline() if get_baseline else 0

    def tearDown(self) -> None:
        jit.baseline_compile_after_n_calls(self._baseline_compile_after_n_calls or 0)
        jit.compile_after_n_calls(self._compile_after_n_calls or 0)

    def test_force_compile_baseline_exposes_baseline_tier(self) -> None:
        def helper(x):
            return x + 1

        self.assertEqual(jit.get_function_tier(helper), "interp")
        self.assertTrue(jit.force_compile_baseline(helper))
        self.assertEqual(jit.get_function_tier(helper), "baseline")

    def test_force_compile_promotes_baseline_function_to_optimized(self) -> None:
        def helper(x):
            return x + 1

        self.assertTrue(jit.force_compile_baseline(helper))
        self.assertEqual(jit.get_function_tier(helper), "baseline")
        self.assertTrue(jit.force_compile(helper))
        self.assertEqual(jit.get_function_tier(helper), "optimized")

    def test_low_threshold_autocompiles_baseline_before_optimized(self) -> None:
        script = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()

            def helper(x):
                return x + 1

            jit.baseline_compile_after_n_calls(1)
            jit.compile_after_n_calls(1000000)
            print(jit.get_function_tier(helper))
            helper(7)
            print(jit.get_function_tier(helper))
            helper(7)
            print(jit.get_function_tier(helper))
            """
        )
        result = subprocess.run(
            [sys.executable, "-S", "-u", "-c", script],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [line.strip() for line in result.stdout.splitlines() if line.strip()],
            ["interp", "interp", "baseline"],
        )

    def test_low_threshold_prefers_baseline_over_cached_optimized_tier(self) -> None:
        script = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()

            def make_helper():
                def helper(x):
                    return x + 1
                return helper

            jit.compile_after_n_calls(1)
            optimized = make_helper()
            optimized(7)
            optimized(7)
            print(jit.get_function_tier(optimized))

            jit.baseline_compile_after_n_calls(1)
            jit.compile_after_n_calls(1000000)
            baseline = make_helper()
            print(jit.get_function_tier(baseline))
            baseline(7)
            print(jit.get_function_tier(baseline))
            baseline(7)
            print(jit.get_function_tier(baseline))
            print(jit.get_function_tier(optimized))
            """
        )
        result = subprocess.run(
            [sys.executable, "-S", "-u", "-c", script],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [line.strip() for line in result.stdout.splitlines() if line.strip()],
            ["optimized", "interp", "interp", "baseline", "optimized"],
        )
