import unittest

import cinderx.jit as jit
import cinderx.test_support as cinder_support


@cinder_support.skip_unless_jit("requires JIT")
class TieringApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._compile_after_n_calls = jit.get_compile_after_n_calls()
        get_baseline = getattr(jit, "get_baseline_compile_after_n_calls", None)
        self._baseline_compile_after_n_calls = get_baseline() if get_baseline else 0

    def tearDown(self) -> None:
        jit.baseline_compile_after_n_calls(self._baseline_compile_after_n_calls)
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
        def helper(x):
            return x + 1

        jit.baseline_compile_after_n_calls(1)
        jit.compile_after_n_calls(1000000)
        self.assertEqual(jit.get_function_tier(helper), "interp")
        helper(7)
        self.assertEqual(jit.get_function_tier(helper), "interp")
        helper(7)
        self.assertEqual(jit.get_function_tier(helper), "baseline")
