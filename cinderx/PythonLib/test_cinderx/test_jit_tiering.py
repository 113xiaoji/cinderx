import subprocess
import sys
import textwrap
import unittest


class TieringApiTests(unittest.TestCase):
    def _run_tiering_script(self, body: str) -> list[str]:
        script = (
            textwrap.dedent(
                """
                import cinderx.jit as jit

                jit.enable()
                if not jit.is_enabled():
                    print("__SKIP__:requires JIT")
                    raise SystemExit(0)
                """
            ).strip()
            + "\n\n"
            + textwrap.dedent(body).strip()
            + "\n"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-u", "-c", script],
            capture_output=True,
            check=False,
            text=True,
        )
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if result.returncode == 0 and lines == ["__SKIP__:requires JIT"]:
            self.skipTest("requires JIT")
        self.assertEqual(
            result.returncode,
            0,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return lines

    def test_force_compile_baseline_exposes_baseline_tier(self) -> None:
        lines = self._run_tiering_script(
            """
            def helper(x):
                return x + 1

            print(jit.get_function_tier(helper))
            if not jit.force_compile_baseline(helper):
                raise AssertionError("force_compile_baseline() failed")
            print(jit.get_function_tier(helper))
            """
        )
        self.assertEqual(lines, ["interp", "baseline"])

    def test_force_compile_promotes_baseline_function_to_optimized(self) -> None:
        lines = self._run_tiering_script(
            """
            def helper(x):
                return x + 1

            if not jit.force_compile_baseline(helper):
                raise AssertionError("force_compile_baseline() failed")
            print(jit.get_function_tier(helper))
            if not jit.force_compile(helper):
                raise AssertionError("force_compile() failed")
            print(jit.get_function_tier(helper))
            """
        )
        self.assertEqual(lines, ["baseline", "optimized"])

    def test_force_compile_promotes_baseline_function_with_cached_optimized_tier(
        self,
    ) -> None:
        lines = self._run_tiering_script(
            """
            def make_helper():
                def helper(x):
                    return x + 1
                return helper

            optimized = make_helper()
            if not jit.force_compile(optimized):
                raise AssertionError("force_compile(optimized) failed")
            print(jit.get_function_tier(optimized))

            baseline = make_helper()
            if not jit.force_compile_baseline(baseline):
                raise AssertionError("force_compile_baseline(baseline) failed")
            print(jit.get_function_tier(baseline))
            if not jit.force_compile(baseline):
                raise AssertionError("force_compile(baseline) failed")
            print(jit.get_function_tier(baseline))
            print(jit.get_function_tier(optimized))
            """
        )
        self.assertEqual(lines, ["optimized", "baseline", "optimized", "optimized"])

    def test_low_threshold_autocompiles_baseline_before_optimized(self) -> None:
        lines = self._run_tiering_script(
            """
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
        self.assertEqual(lines, ["interp", "interp", "baseline"])

    def test_low_threshold_prefers_baseline_over_cached_optimized_tier(self) -> None:
        lines = self._run_tiering_script(
            """
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
        self.assertEqual(
            lines,
            ["optimized", "interp", "interp", "baseline", "optimized"],
        )
