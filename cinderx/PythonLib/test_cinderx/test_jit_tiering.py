import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

import cinderx.jit as jit


class TieringApiTests(unittest.TestCase):
    def setUp(self) -> None:
        jit.enable()
        if not jit.is_enabled():
            self.skipTest("requires JIT")
        self._compile_after_n_calls = jit.get_compile_after_n_calls()
        get_baseline = getattr(jit, "get_baseline_compile_after_n_calls", None)
        self._baseline_compile_after_n_calls = get_baseline() if get_baseline else 0

    def tearDown(self) -> None:
        jit.baseline_compile_after_n_calls(self._baseline_compile_after_n_calls)
        if self._compile_after_n_calls is not None:
            jit.compile_after_n_calls(self._compile_after_n_calls)

    def run_tiering_script(
        self,
        name: str,
        code: str,
        env: dict[str, str] | None = None,
    ) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/{name}.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(textwrap.dedent(code))

            run_env = dict(os.environ)
            if env is not None:
                run_env.update(env)
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=run_env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

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
        self.assertEqual(jit.get_function_tier(helper), "interp")
        helper(7)
        self.assertEqual(jit.get_function_tier(helper), "baseline")

    def test_baseline_compile_after_none_disables_auto_baseline(self) -> None:
        jit.baseline_compile_after_n_calls(1)
        self.assertEqual(jit.get_baseline_compile_after_n_calls(), 1)

        jit.baseline_compile_after_n_calls(None)
        self.assertIsNone(jit.get_baseline_compile_after_n_calls())

    def test_disabling_baseline_auto_keeps_pending_function_interpreted(self) -> None:
        def helper(x):
            return x + 1

        jit.baseline_compile_after_n_calls(2)
        self.assertTrue(jit.get_function_tier_state(helper)["baseline_scheduled"])

        jit.baseline_compile_after_n_calls(None)

        state = jit.get_function_tier_state(helper)
        self.assertEqual(state["active_tier"], "interp")
        self.assertFalse(state["baseline_scheduled"])
        self.assertEqual(state["last_transition"], "baseline_auto_disabled")

        self.assertEqual(helper(7), 8)
        self.assertEqual(jit.get_function_tier(helper), "interp")

    def test_pause_deopt_all_clears_pending_baseline_tier(self) -> None:
        def helper(x):
            return x + 1

        jit.baseline_compile_after_n_calls(2)
        self.assertTrue(jit.get_function_tier_state(helper)["baseline_scheduled"])

        with jit.pause(deopt_all=True):
            self.assertEqual(helper(7), 8)
            state = jit.get_function_tier_state(helper)
            self.assertEqual(state["active_tier"], "interp")
            self.assertFalse(state["baseline_scheduled"])

        state = jit.get_function_tier_state(helper)
        self.assertEqual(state["active_tier"], "interp")
        self.assertFalse(state["baseline_scheduled"])

    def test_force_compile_baseline_does_not_reopt_shared_code(self) -> None:
        def make_helper():
            def helper(x):
                return x + 1

            return helper

        optimized = make_helper()
        baseline = make_helper()

        self.assertTrue(jit.force_compile(optimized))
        self.assertEqual(jit.get_function_tier(optimized), "optimized")

        self.assertTrue(jit.force_compile_baseline(baseline))
        self.assertEqual(jit.get_function_tier(baseline), "baseline")
        self.assertFalse(jit.is_jit_compiled(baseline))

    def test_force_uncompile_baseline_returns_to_interp(self) -> None:
        def helper(x):
            return x + 1

        self.assertTrue(jit.force_compile_baseline(helper))
        self.assertEqual(jit.get_function_tier(helper), "baseline")

        self.assertTrue(jit.force_uncompile(helper))
        self.assertFalse(jit.is_jit_compiled(helper))
        self.assertEqual(jit.get_function_tier(helper), "interp")

        self.assertEqual(helper(7), 8)
        self.assertEqual(jit.get_function_tier(helper), "interp")

    def test_pause_deopt_all_clears_baseline_tier(self) -> None:
        def helper(x):
            return x + 1

        self.assertTrue(jit.force_compile_baseline(helper))
        self.assertEqual(jit.get_function_tier(helper), "baseline")

        with jit.pause(deopt_all=True):
            self.assertEqual(jit.get_function_tier(helper), "interp")
            self.assertFalse(jit.is_jit_compiled(helper))

        self.assertEqual(jit.get_function_tier(helper), "interp")

    def test_auto_baseline_then_auto_optimized_clears_baseline_state(self) -> None:
        lines = self.run_tiering_script(
            "auto_baseline_to_optimized",
            """
            import faulthandler
            import cinderx.jit as jit

            faulthandler.enable()
            jit.enable()

            def helper(x):
                return x + 1

            jit.baseline_compile_after_n_calls(1)
            jit.compile_after_n_calls(3)

            for value in (7, 8, 9, 10):
                print(helper(value))
                print(jit.get_function_tier(helper))

            state = jit.get_function_tier_state(helper)
            print(state["last_transition"])
            print(state["baseline_scheduled"])
            print(jit.is_jit_compiled(helper))
            print(jit.force_uncompile(helper))
            print(jit.get_function_tier(helper))
            """,
        )
        self.assertEqual(
            lines[-13:],
            [
                "8",
                "baseline",
                "9",
                "baseline",
                "10",
                "baseline",
                "11",
                "optimized",
                "baseline_to_optimized",
                "False",
                "True",
                "True",
                "interp",
            ],
        )

    def test_function_tier_state_reports_lifecycle(self) -> None:
        def helper(x):
            return x + 1

        state = jit.get_function_tier_state(helper)
        self.assertEqual(state["active_tier"], "interp")
        self.assertFalse(state["baseline_scheduled"])
        self.assertFalse(state["compiled"])
        self.assertFalse(state["deopted"])
        self.assertEqual(state["last_transition"], "none")

        self.assertTrue(jit.force_compile_baseline(helper))
        state = jit.get_function_tier_state(helper)
        self.assertEqual(state["active_tier"], "baseline")
        self.assertFalse(state["baseline_scheduled"])
        self.assertFalse(state["compiled"])
        self.assertFalse(state["deopted"])
        self.assertEqual(state["last_transition"], "baseline")

        self.assertTrue(jit.force_compile(helper))
        state = jit.get_function_tier_state(helper)
        self.assertEqual(state["active_tier"], "optimized")
        self.assertTrue(state["compiled"])
        self.assertFalse(state["deopted"])
        self.assertEqual(state["last_transition"], "baseline_to_optimized")
        self.assertEqual(state["promotion_decisions"], 1)
        self.assertEqual(state["promotion_attempts"], 1)
        self.assertEqual(state["promotion_blocked_attempts"], 0)
        self.assertEqual(state["last_promotion_decision"], "attempt")
        self.assertEqual(state["last_policy_event"], "promotion_attempt")
        self.assertEqual(state["last_policy_reason"], "force_compile")

        self.assertTrue(jit.force_uncompile(helper))
        state = jit.get_function_tier_state(helper)
        self.assertEqual(state["active_tier"], "interp")
        self.assertFalse(state["compiled"])
        self.assertFalse(state["baseline_scheduled"])
        self.assertEqual(state["last_transition"], "uncompile")

    def test_compile_failure_updates_tier_state(self) -> None:
        lines = self.run_tiering_script(
            "compile_failure_tier_state",
            """
            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            original_limit = jit.get_allocator_stats()["max_bytes"]
            try:
                jit.set_max_code_size(0)

                def consumes_code_bytes():
                    return 42

                assert jit.force_compile(consumes_code_bytes)
                jit.set_max_code_size(5)

                def blocked_compile():
                    return 43

                try:
                    jit.force_compile(blocked_compile)
                except RuntimeError as exc:
                    print(str(exc))

                state = jit.get_function_tier_state(blocked_compile)
                print(state["active_tier"])
                print(state["compiled"])
                print(state["compile_failures"])
                print(state["last_compile_failure"])
                print(state["last_fallback_reason"])
                print(state["last_transition"])
                print(state["promotion_attempts"])
                print(state["last_promotion_reason"])
                print(state["promotion_blocked"])
                print(state["promotion_blocked_reason"])
                print(state["policy_state"])
            finally:
                jit.set_max_code_size(original_limit)
            """,
        )

        self.assertEqual(lines[-12:], [
            "PYJIT_OVER_MAX_CODE_SIZE",
            "interp",
            "False",
            "1",
            "over_max_code_size",
            "over_max_code_size",
            "compile_failed",
            "1",
            "force_compile",
            "True",
            "compile_failure_cooldown",
            "compile_failure_cooldown",
        ])

    def test_compile_failure_backoff_blocks_lazy_repromotion(self) -> None:
        lines = self.run_tiering_script(
            "compile_failure_backoff",
            """
            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            original_limit = jit.get_allocator_stats()["max_bytes"]
            try:
                jit.set_max_code_size(0)

                def consumes_code_bytes():
                    return 42

                assert jit.force_compile(consumes_code_bytes)
                jit.set_max_code_size(5)

                def blocked_compile():
                    return 43

                try:
                    jit.force_compile(blocked_compile)
                except RuntimeError:
                    pass

                jit.set_max_code_size(0)
                assert jit.lazy_compile(blocked_compile)
                print(blocked_compile())

                state = jit.get_function_tier_state(blocked_compile)
                print(state["active_tier"])
                print(state["compiled"])
                print(state["compile_failures"])
                print(state["promotion_attempts"])
                print(state["last_promotion_reason"])
                print(state["promotion_blocked"])
                print(state["promotion_blocked_reason"])
                print(state["last_transition"])
            finally:
                jit.set_max_code_size(original_limit)
            """,
        )

        self.assertEqual(lines[-9:], [
            "43",
            "interp",
            "False",
            "1",
            "1",
            "lazy_compile",
            "True",
            "compile_failure_cooldown",
            "promotion_blocked",
        ])

    def test_compile_failure_backoff_blocks_force_compile_repromotion(self) -> None:
        lines = self.run_tiering_script(
            "compile_failure_backoff_force",
            """
            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            original_limit = jit.get_allocator_stats()["max_bytes"]
            try:
                jit.set_max_code_size(0)

                def consumes_code_bytes():
                    return 42

                assert jit.force_compile(consumes_code_bytes)
                jit.set_max_code_size(5)

                def blocked_compile():
                    return 43

                try:
                    jit.force_compile(blocked_compile)
                except RuntimeError:
                    pass

                jit.set_max_code_size(0)
                print(jit.force_compile(blocked_compile))
                print(blocked_compile())

                state = jit.get_function_tier_state(blocked_compile)
                print(state["active_tier"])
                print(state["compiled"])
                print(state["compile_failures"])
                print(state["promotion_attempts"])
                print(state["last_promotion_reason"])
                print(state["promotion_blocked"])
                print(state["promotion_blocked_reason"])
                print(state["last_transition"])
            finally:
                jit.set_max_code_size(original_limit)
            """,
        )

        self.assertEqual(lines[-10:], [
            "False",
            "43",
            "interp",
            "False",
            "1",
            "1",
            "force_compile",
            "True",
            "compile_failure_cooldown",
            "promotion_blocked",
        ])

    def test_compile_failure_backoff_blocks_hot_loop_osr(self) -> None:
        lines = self.run_tiering_script(
            "compile_failure_backoff_osr",
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            original_limit = jit.get_allocator_stats()["max_bytes"]
            try:
                jit.set_max_code_size(0)

                def consumes_code_bytes():
                    return 42

                assert jit.force_compile(consumes_code_bytes)
                jit.set_max_code_size(5)

                def hot(n: int, acc: int) -> int:
                    while n > 0:
                        acc = acc + n
                        n = n - 1
                    return acc

                try:
                    jit.force_compile(hot)
                except RuntimeError:
                    pass

                jit.set_max_code_size(0)
                jit.get_and_clear_runtime_stats()
                print(hot(50000, 0))
                stats = jit.get_and_clear_runtime_stats()
                osr_entries = [
                    entry for entry in stats.get("osr", [])
                    if entry["normal"]["func_qualname"] == "hot"
                ]

                state = jit.get_function_tier_state(hot)
                print(len(osr_entries))
                print(sum(entry["int"]["count"] for entry in osr_entries))
                print(jit.is_jit_compiled(hot))
                print(state["active_tier"])
                print(state["compile_failures"])
                print(state["promotion_attempts"])
                print(state["last_promotion_reason"])
                print(state["promotion_blocked"])
                print(state["promotion_blocked_reason"])
                print(state["last_transition"])
            finally:
                jit.set_max_code_size(original_limit)
            """,
        )

        self.assertEqual(lines[-11:], [
            str((50000 * 50001) // 2),
            "0",
            "0",
            "False",
            "interp",
            "1",
            "1",
            "hot_loop_osr",
            "True",
            "compile_failure_cooldown",
            "promotion_blocked",
        ])

    def test_compile_failure_backoff_blocks_precompile_all_repromotion(self) -> None:
        lines = self.run_tiering_script(
            "compile_failure_backoff_precompile_all",
            """
            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            original_limit = jit.get_allocator_stats()["max_bytes"]
            try:
                jit.set_max_code_size(0)

                def consumes_code_bytes():
                    return 42

                assert jit.force_compile(consumes_code_bytes)
                jit.set_max_code_size(5)

                def blocked_compile():
                    return 43

                try:
                    jit.force_compile(blocked_compile)
                except RuntimeError:
                    pass

                jit.set_max_code_size(0)
                assert jit.lazy_compile(blocked_compile)
                print(jit.precompile_all(workers=2))

                state = jit.get_function_tier_state(blocked_compile)
                print(jit.is_jit_compiled(blocked_compile))
                print(state["active_tier"])
                print(state["compiled"])
                print(state["compile_failures"])
                print(state["promotion_attempts"])
                print(state["promotion_decisions"])
                print(state["promotion_blocked_attempts"])
                print(state["last_promotion_decision"])
                print(state["last_promotion_reason"])
                print(state["promotion_blocked"])
                print(state["promotion_blocked_reason"])
                print(state["last_policy_event"])
                print(state["last_policy_reason"])
                print(state["last_transition"])
            finally:
                jit.set_max_code_size(original_limit)
            """,
        )

        self.assertEqual(lines[-15:], [
            "True",
            "False",
            "interp",
            "False",
            "1",
            "1",
            "2",
            "1",
            "blocked",
            "precompile_all",
            "True",
            "compile_failure_cooldown",
            "promotion_blocked",
            "compile_failure_cooldown",
            "promotion_blocked",
        ])

    def test_successful_compile_without_failure_does_not_count_policy_reset(
        self,
    ) -> None:
        lines = self.run_tiering_script(
            "successful_compile_without_failure_reset",
            """
            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            def plain_compile():
                return 47

            print(jit.force_compile(plain_compile))
            state = jit.get_function_tier_state(plain_compile)
            print(state["policy_resets"])
            print(state["policy_state"])
            print(state["promotion_blocked"])
            print(state["compile_failure_streak"])
            print(state["compile_failure_backoff"])
            print(state["compile_failure_cooldown_remaining"])
            """,
        )

        self.assertEqual(lines[-7:], [
            "True",
            "0",
            "ready",
            "False",
            "0",
            "0",
            "0",
        ])

    def test_compile_failure_cooldown_expires_and_allows_repromotion(self) -> None:
        lines = self.run_tiering_script(
            "compile_failure_cooldown_expires",
            """
            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            original_limit = jit.get_allocator_stats()["max_bytes"]
            try:
                jit.set_max_code_size(0)

                def consumes_code_bytes():
                    return 42

                assert jit.force_compile(consumes_code_bytes)
                jit.set_max_code_size(5)

                def blocked_compile():
                    return 43

                try:
                    jit.force_compile(blocked_compile)
                except RuntimeError:
                    pass

                failed = jit.get_function_tier_state(blocked_compile)
                print(failed["compile_failure_backoff"])
                print(failed["compile_failure_cooldown_remaining"])
                print(failed["compile_failure_streak"])
                print(failed["policy_state"])
                print(failed["promotion_blocked"])

                jit.set_max_code_size(0)
                print(jit.force_compile(blocked_compile))
                first_block = jit.get_function_tier_state(blocked_compile)
                print(first_block["compile_failure_cooldown_remaining"])

                print(jit.force_compile(blocked_compile))
                second_block = jit.get_function_tier_state(blocked_compile)
                print(second_block["compile_failure_cooldown_remaining"])
                print(second_block["promotion_blocked"])
                print(second_block["policy_state"])

                print(jit.force_compile(blocked_compile))
                recovered = jit.get_function_tier_state(blocked_compile)
                print(recovered["active_tier"])
                print(recovered["compiled"])
                print(recovered["policy_state"])
                print(recovered["promotion_blocked"])
                print(recovered["compile_failure_cooldown_remaining"])
                print(recovered["compile_failure_backoff"])
                print(recovered["compile_failure_streak"])
                print(recovered["policy_resets"] > 0)
            finally:
                jit.set_max_code_size(original_limit)
            """,
        )

        self.assertEqual(lines[-20:], [
            "2",
            "2",
            "1",
            "compile_failure_cooldown",
            "True",
            "False",
            "1",
            "False",
            "0",
            "False",
            "ready",
            "True",
            "optimized",
            "True",
            "ready",
            "False",
            "0",
            "0",
            "0",
            "True",
        ])

    def test_hot_loop_osr_cooldown_ages_across_calls(self) -> None:
        lines = self.run_tiering_script(
            "hot_loop_osr_cooldown_ages",
            """
            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            original_limit = jit.get_allocator_stats()["max_bytes"]
            try:
                jit.set_max_code_size(0)

                def consumes_code_bytes():
                    return 42

                assert jit.force_compile(consumes_code_bytes)
                jit.set_max_code_size(5)

                def hot(n: int, acc: int) -> int:
                    while n > 0:
                        acc = acc + n
                        n = n - 1
                    return acc

                try:
                    jit.force_compile(hot)
                except RuntimeError:
                    pass

                jit.set_max_code_size(0)

                print(hot(50000, 0))
                first = jit.get_function_tier_state(hot)
                print(first["compile_failure_cooldown_remaining"])
                print(first["promotion_blocked"])
                print(jit.is_jit_compiled(hot))

                print(hot(50000, 0))
                second = jit.get_function_tier_state(hot)
                print(second["compile_failure_cooldown_remaining"])
                print(second["promotion_blocked"])
                print(second["policy_state"])
                print(jit.is_jit_compiled(hot))

                print(hot(50000, 0))
                recovered = jit.get_function_tier_state(hot)
                print(recovered["active_tier"])
                print(recovered["compiled"])
                print(recovered["policy_state"])
            finally:
                jit.set_max_code_size(original_limit)
            """,
        )

        total = str((50000 * 50001) // 2)
        self.assertEqual(lines[-13:], [
            total,
            "1",
            "True",
            "False",
            total,
            "0",
            "False",
            "ready",
            "False",
            total,
            "optimized",
            "True",
            "ready",
        ])

    def test_repeated_compile_failures_grow_policy_backoff(self) -> None:
        lines = self.run_tiering_script(
            "compile_failure_backoff_growth",
            """
            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            original_limit = jit.get_allocator_stats()["max_bytes"]
            try:
                jit.set_max_code_size(0)

                def consumes_code_bytes():
                    return 42

                assert jit.force_compile(consumes_code_bytes)
                jit.set_max_code_size(5)

                def blocked_compile():
                    return 43

                try:
                    jit.force_compile(blocked_compile)
                except RuntimeError:
                    pass

                first = jit.get_function_tier_state(blocked_compile)
                print(first["compile_failure_backoff"])
                print(first["compile_failure_cooldown_remaining"])
                print(first["compile_failure_streak"])

                print(jit.force_compile(blocked_compile))
                print(jit.force_compile(blocked_compile))
                try:
                    jit.force_compile(blocked_compile)
                except RuntimeError:
                    print("second_failure")

                second = jit.get_function_tier_state(blocked_compile)
                print(second["compile_failures"])
                print(second["compile_failure_backoff"])
                print(second["compile_failure_cooldown_remaining"])
                print(second["compile_failure_streak"])
                print(second["policy_state"])
                print(second["promotion_blocked"])
            finally:
                jit.set_max_code_size(original_limit)
            """,
        )

        self.assertEqual(lines[-12:], [
            "2",
            "2",
            "1",
            "False",
            "False",
            "second_failure",
            "2",
            "4",
            "4",
            "2",
            "compile_failure_cooldown",
            "True",
        ])

    def test_function_code_change_resets_policy_backoff(self) -> None:
        lines = self.run_tiering_script(
            "function_code_change_policy_reset",
            """
            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            original_limit = jit.get_allocator_stats()["max_bytes"]
            try:
                jit.set_max_code_size(0)

                def consumes_code_bytes():
                    return 42

                assert jit.force_compile(consumes_code_bytes)
                jit.set_max_code_size(5)

                def blocked_compile():
                    return 43

                try:
                    jit.force_compile(blocked_compile)
                except RuntimeError:
                    pass

                failed = jit.get_function_tier_state(blocked_compile)
                print(failed["policy_state"])
                print(failed["promotion_blocked"])

                def replacement():
                    return 44

                blocked_compile.__code__ = replacement.__code__
                changed = jit.get_function_tier_state(blocked_compile)
                print(changed["policy_state"])
                print(changed["promotion_blocked"])
                print(changed["deopt_budget"])
                print(changed["compile_failure_cooldown_remaining"])
                print(changed["policy_resets"] > 0)

                jit.set_max_code_size(0)
                print(jit.force_compile(blocked_compile))
                print(blocked_compile())
                recovered = jit.get_function_tier_state(blocked_compile)
                print(recovered["active_tier"])
                print(recovered["compiled"])
            finally:
                jit.set_max_code_size(original_limit)
            """,
        )

        self.assertEqual(lines[-11:], [
            "compile_failure_cooldown",
            "True",
            "ready",
            "False",
            "16",
            "0",
            "True",
            "True",
            "44",
            "optimized",
            "True",
        ])

    def test_threaded_precompile_worker_optional_python_api_guards(self) -> None:
        lines = self.run_tiering_script(
            "threaded_precompile_worker_guards",
            """
            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            class Probe:
                def __init__(self):
                    self.名字 = 7

                def value(self):
                    return self.名字

                def starts(self, text):
                    return text.startswith("pre")

                def add_one(self, values):
                    values.append(1)
                    return len(values)

            probe = Probe()

            def unicode_attr():
                return probe.value()

            def builtin_text_method():
                return probe.starts("precompile")

            def builtin_list_method():
                return probe.add_one([])

            for func in (unicode_attr, builtin_text_method, builtin_list_method):
                assert jit.lazy_compile(func)

            print(jit.precompile_all(workers=2))
            print(unicode_attr())
            print(builtin_text_method())
            print(builtin_list_method())
            print(jit.is_inline_cache_stats_collection_enabled())
            """,
            env={"PYTHONJITCOLLECTINLINECACHESTATS": "1"},
        )

        self.assertEqual(lines[-5:], [
            "True",
            "7",
            "True",
            "1",
            "True",
        ])

    def test_runtime_fallback_updates_tier_state(self) -> None:
        lines = self.run_tiering_script(
            "runtime_fallback_tier_state",
            """
            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            class Point:
                def __init__(self, x):
                    self.x = x

                def getx(self):
                    return self.x

            point = Point(1)
            for _ in range(20000):
                point.getx()

            assert jit.force_compile(Point.getx)

            class SubPoint(Point):
                pass

            jit.get_and_clear_runtime_stats()
            print(SubPoint(2).getx())
            state = jit.get_function_tier_state(Point.getx)
            print(state["active_tier"])
            print(state["compiled"])
            print(state["deopted"])
            print(state["runtime_fallbacks"])
            print(state["last_fallback_reason"])
            print(state["last_transition"])
            print(state["deopt_budget"])
            """,
        )

        self.assertEqual(lines[-8], "2")
        self.assertEqual(lines[-7], "optimized")
        self.assertEqual(lines[-6], "True")
        self.assertEqual(lines[-5], "False")
        self.assertGreaterEqual(int(lines[-4]), 1)
        self.assertEqual(lines[-3], "GuardFailure")
        self.assertEqual(lines[-2], "runtime_fallback")
        self.assertLess(int(lines[-1]), 16)

    def test_deopt_budget_exhaustion_blocks_repromotion(self) -> None:
        lines = self.run_tiering_script(
            "deopt_budget_exhaustion",
            """
            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            class Point:
                def __init__(self, x):
                    self.x = x

                def getx(self):
                    return self.x

            point = Point(1)
            for _ in range(20000):
                point.getx()

            assert jit.force_compile(Point.getx)

            class SubPoint(Point):
                pass

            for i in range(20):
                SubPoint(i).getx()

            exhausted = jit.get_function_tier_state(Point.getx)
            print(exhausted["runtime_fallbacks"] >= 16)
            print(exhausted["deopt_budget"])
            print(exhausted["promotion_blocked"])
            print(exhausted["promotion_blocked_reason"])
            print(exhausted["policy_state"])

            print(jit.force_uncompile(Point.getx))
            print(jit.force_compile(Point.getx))

            blocked = jit.get_function_tier_state(Point.getx)
            print(blocked["active_tier"])
            print(blocked["compiled"])
            print(blocked["deopted"])
            print(blocked["promotion_attempts"])
            print(blocked["last_promotion_reason"])
            print(blocked["promotion_blocked"])
            print(blocked["promotion_blocked_reason"])
            print(blocked["policy_state"])
            print(blocked["last_transition"])
            """,
        )

        self.assertEqual(lines[-16:], [
            "True",
            "0",
            "True",
            "deopt_budget_exhausted",
            "deopt_budget_exhausted",
            "True",
            "False",
            "interp",
            "False",
            "False",
            "1",
            "force_compile",
            "True",
            "deopt_budget_exhausted",
            "deopt_budget_exhausted",
            "promotion_blocked",
        ])

    def test_type_invalidation_updates_tier_state(self) -> None:
        lines = self.run_tiering_script(
            "type_invalidation_tier_state",
            """
            import math
            import types
            import cinderx.jit as jit

            jit.enable()
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

            assert jit.force_compile(Point.dist)
            before = jit.get_function_tier_state(Point.dist)
            print(before["invalidations"])

            class MovedPoint:
                pass

            a.__class__ = MovedPoint
            patched = jit.get_function_tier_state(Point.dist)
            print(patched["active_tier"])
            print(patched["compiled"])
            print(patched["invalidations"])
            print(patched["last_invalidation_reason"])
            print(patched["last_fallback_reason"])
            print(patched["last_transition"])

            jit.get_and_clear_runtime_stats()
            print(Point.dist(a, b))
            after_call = jit.get_function_tier_state(Point.dist)
            print(after_call["runtime_fallbacks"])
            print(after_call["last_fallback_reason"])
            print(after_call["last_transition"])
            """,
        )

        self.assertEqual(lines[-11], "0")
        self.assertEqual(lines[-10], "optimized")
        self.assertEqual(lines[-9], "True")
        self.assertGreaterEqual(int(lines[-8]), 1)
        self.assertEqual(lines[-7], "type_modified")
        self.assertEqual(lines[-6], "type_modified")
        self.assertEqual(lines[-5], "type_invalidation")
        self.assertEqual(float(lines[-4]), 5.196152422706632)
        self.assertGreaterEqual(int(lines[-3]), 1)
        self.assertEqual(lines[-2], "GuardFailure")
        self.assertEqual(lines[-1], "runtime_fallback")

    def test_shared_runtime_keeps_type_invalidation_after_one_owner_uncompiled(
        self,
    ) -> None:
        lines = self.run_tiering_script(
            "shared_runtime_type_invalidation",
            """
            import math
            import types
            import cinderx.jit as jit

            jit.enable()
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

            first = Point.dist
            second = types.FunctionType(Point.dist.__code__, globals())
            a = Point(1.0, 2.0, 3.0)
            b = Point(4.0, 5.0, 6.0)
            for _ in range(20000):
                a.dist(b)

            assert jit.force_compile(first)
            assert jit.force_compile(second)
            print(jit.is_jit_compiled(first))
            print(jit.is_jit_compiled(second))

            print(jit.force_uncompile(first))
            print(jit.is_jit_compiled(first))
            print(jit.is_jit_compiled(second))

            class MovedPoint:
                pass

            a.__class__ = MovedPoint
            state = jit.get_function_tier_state(second)
            print(state["active_tier"])
            print(state["compiled"])
            print(state["invalidations"])
            print(state["last_invalidation_reason"])
            print(state["last_transition"])
            """,
        )

        self.assertEqual(lines[-10:-3], [
            "True",
            "True",
            "True",
            "False",
            "True",
            "optimized",
            "True",
        ])
        self.assertGreater(int(lines[-3]), 0)
        self.assertEqual(lines[-2:], [
            "type_modified",
            "type_invalidation",
        ])
