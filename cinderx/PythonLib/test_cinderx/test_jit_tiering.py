from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


PYTHONLIB = str(Path(__file__).resolve().parents[1])


class TieringApiTests(unittest.TestCase):
    def _run_tiering_script(self, body: str) -> list[str]:
        script = (
            textwrap.dedent(
                """
                import sys
                sys.path.insert(0, {!r})
                import cinderx.jit as jit
                jit.enable()
                if not jit.is_enabled():
                    print("__SKIP__:requires JIT")
                    raise SystemExit(0)
                """
            ).format(PYTHONLIB).strip()
            + "\n\n"
            + textwrap.dedent(body).strip()
            + "\n"
        )
        result = subprocess.run(
            [sys.executable, "-u", "-c", script],
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
            ["optimized", "interp", "baseline", "baseline", "optimized"],
        )


    def test_get_function_tier_info_reports_active_and_available_tiers(self) -> None:
        lines = self._run_tiering_script(
            """
            def helper(x):
                return x + 1

            info = jit.get_function_tier_info(helper)
            print(info["active_tier"])
            print(info["has_baseline"])
            print(info["has_optimized"])

            if not jit.force_compile_baseline(helper):
                raise AssertionError("force_compile_baseline() failed")
            info = jit.get_function_tier_info(helper)
            print(info["active_tier"])
            print(info["has_baseline"])
            print(info["has_optimized"])

            if not jit.force_compile(helper):
                raise AssertionError("force_compile() failed")
            info = jit.get_function_tier_info(helper)
            print(info["active_tier"])
            print(info["has_baseline"])
            print(info["has_optimized"])
            """
        )
        self.assertEqual(
            lines,
            [
                "interp",
                "False",
                "False",
                "baseline",
                "True",
                "False",
                "optimized",
                "True",
                "True",
            ],
        )

    def test_get_and_clear_tiering_stats_records_transitions(self) -> None:
        lines = self._run_tiering_script(
            """
            def helper(x):
                return x + 1

            stats = jit.get_and_clear_tiering_stats()
            print(len(stats["events"]))

            if not jit.force_compile_baseline(helper):
                raise AssertionError("force_compile_baseline() failed")
            if not jit.force_compile(helper):
                raise AssertionError("force_compile() failed")

            stats = jit.get_and_clear_tiering_stats()
            print(len(stats["events"]))
            for event in stats["events"]:
                print(event["from_tier"])
                print(event["to_tier"])

            stats = jit.get_and_clear_tiering_stats()
            print(len(stats["events"]))
            """
        )
        self.assertEqual(
            lines,
            ["0", "2", "interp", "baseline", "baseline", "optimized", "0"],
        )
