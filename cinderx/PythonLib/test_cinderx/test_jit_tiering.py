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

    def test_baseline_auto_promotes_to_optimized_after_optimized_threshold(
        self,
    ) -> None:
        lines = self._run_tiering_script(
            """
            def helper(x):
                return x + 1

            jit.baseline_compile_after_n_calls(1)
            jit.compile_after_n_calls(3)

            print(jit.get_function_tier(helper))
            helper(7)
            print(jit.get_function_tier(helper))
            helper(7)
            print(jit.get_function_tier(helper))
            helper(7)
            print(jit.get_function_tier(helper))
            helper(7)
            print(jit.get_function_tier(helper))
            helper(7)
            print(jit.get_function_tier(helper))
            """
        )
        self.assertEqual(
            lines,
            ["interp", "interp", "baseline", "baseline", "optimized", "optimized"],
        )

    def test_tiering_stats_records_skipped_and_promoted_baseline_decisions(
        self,
    ) -> None:
        lines = self._run_tiering_script(
            """
            def helper(x):
                return x + 1

            jit.baseline_compile_after_n_calls(1)
            jit.compile_after_n_calls(3)
            jit.get_and_clear_tiering_stats()

            helper(7)
            helper(7)
            helper(7)
            helper(7)
            helper(7)

            stats = jit.get_and_clear_tiering_stats()
            decisions = [
                f"{item['action']}:{item['reason']}"
                for item in stats["decisions"]
                if item["func_qualname"].endswith("helper")
            ]
            event_reasons = [
                item["reason"]
                for item in stats["events"]
                if item["func_qualname"].endswith("helper")
            ]
            print("skip:optimized_threshold_not_reached" in decisions)
            print("promote:optimized_threshold_reached" in decisions)
            print("auto_threshold_baseline" in event_reasons)
            print("auto_threshold_optimized" in event_reasons)
            """
        )
        self.assertEqual(lines, ["True", "True", "True", "True"])

    def test_force_uncompile_records_fallback_transition(self) -> None:
        lines = self._run_tiering_script(
            """
            def helper(x):
                return x + 1

            if not jit.force_compile_baseline(helper):
                raise AssertionError("force_compile_baseline() failed")
            jit.get_and_clear_tiering_stats()
            if not jit.force_uncompile(helper):
                raise AssertionError("force_uncompile() failed")

            stats = jit.get_and_clear_tiering_stats()
            for event in stats["events"]:
                if event["func_qualname"].endswith("helper"):
                    print(event["from_tier"])
                    print(event["to_tier"])
                    print(event["reason"])
            """
        )
        self.assertEqual(lines, ["baseline", "interp", "force_uncompile"])

    def test_disable_deopt_all_records_fallback_transition(self) -> None:
        lines = self._run_tiering_script(
            """
            def helper(x):
                return x + 1

            if not jit.force_compile_baseline(helper):
                raise AssertionError("force_compile_baseline() failed")
            jit.get_and_clear_tiering_stats()
            jit.disable(deopt_all=True)

            stats = jit.get_and_clear_tiering_stats()
            print(jit.get_function_tier(helper))
            for event in stats["events"]:
                if event["func_qualname"].endswith("helper"):
                    print(event["from_tier"])
                    print(event["to_tier"])
                    print(event["reason"])
            """
        )
        self.assertEqual(lines, ["interp", "baseline", "interp", "disable_deopt_all"])

    def test_function_tier_info_reports_deopt_state(self) -> None:
        lines = self._run_tiering_script(
            """
            def helper(x):
                return x + 1

            if not jit.force_compile_baseline(helper):
                raise AssertionError("force_compile_baseline() failed")
            jit.get_and_clear_tiering_stats()
            jit.disable(deopt_all=True)
            jit.get_and_clear_tiering_stats()

            info = jit.get_function_tier_info(helper)
            print(info["active_tier"])
            print(info["has_baseline"])
            print(info["has_optimized"])
            print(info["is_deopted"])
            last_transition = info["last_transition"]
            print(last_transition["from_tier"])
            print(last_transition["to_tier"])
            print(last_transition["reason"])
            """
        )
        self.assertEqual(
            lines,
            [
                "interp",
                "True",
                "False",
                "True",
                "baseline",
                "interp",
                "disable_deopt_all",
            ],
        )

    def test_tiering_stats_records_type_dependency_invalidations(self) -> None:
        lines = self._run_tiering_script(
            """
            import ctypes
            import math
            import cinderjit

            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Point:
                def __init__(self, x=0.0, y=0.0, z=0.0):
                    self.x = x
                    self.y = y
                    self.z = z

                def dist(self, other):
                    return math.sqrt(
                        (self.x - other.x) ** 2
                        + (self.y - other.y) ** 2
                        + (self.z - other.z) ** 2
                    )

            a = Point(1.0, 2.0, 3.0)
            b = Point(4.0, 5.0, 6.0)
            for _ in range(20000):
                a.dist(b)

            if not jit.force_compile(Point.dist):
                raise AssertionError("force_compile(Point.dist) failed")
            counts = cinderjit.get_function_hir_opcode_counts(Point.dist)
            print(counts.get("DeoptPatchpoint", 0) > 0)
            jit.get_and_clear_tiering_stats()

            ctypes.pythonapi.PyType_Modified.argtypes = [ctypes.py_object]
            ctypes.pythonapi.PyType_Modified.restype = None
            ctypes.pythonapi.PyType_Modified(Point)

            stats = jit.get_and_clear_tiering_stats()
            invalidations = [
                item
                for item in stats.get("invalidations", [])
                if item["func_qualname"].endswith("Point.dist")
            ]
            print(len(invalidations) > 0)
            print(
                any(
                    item["action"] in {"patch", "skip"}
                    for item in invalidations
                )
            )
            print(
                len(invalidations) > 0
                and all(
                    item["watched_type"].endswith("Point")
                    and item["patcher_kind"]
                    and item["description"]
                    for item in invalidations
                )
            )
            """
        )
        self.assertEqual(lines, ["True", "True", "True", "True"])
