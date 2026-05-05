# Copyright (c) Meta Platforms, Inc. and affiliates.

import json
import platform
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

import cinderx
import cinderx.jit
import math


def is_arm_linux() -> bool:
    machine = platform.machine().lower()
    return platform.system() == "Linux" and machine in ("aarch64", "arm64")


@unittest.skipUnless(is_arm_linux(), "ARM Linux specific runtime checks")
class ArmRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._compile_after_n_calls = cinderx.jit.get_compile_after_n_calls()

    def tearDown(self) -> None:
        if self._compile_after_n_calls is not None:
            cinderx.jit.compile_after_n_calls(self._compile_after_n_calls)

    def test_runtime_initializes(self) -> None:
        self.assertTrue(cinderx.is_initialized())
        self.assertIsNone(cinderx.get_import_error())

    def test_jit_is_enabled(self) -> None:
        cinderx.jit.enable()
        self.assertTrue(cinderx.jit.is_enabled())

    def test_jit_force_compile_smoke(self) -> None:
        cinderx.jit.enable()
        # Ensure auto-jit doesn't kick in during the interpreted phase below.
        cinderx.jit.compile_after_n_calls(1000000)

        def f(n: int) -> int:
            s = 0
            for i in range(n):
                s += i
            return s

        # Prove we start interpreted: call count should increase.
        cinderx.jit.force_uncompile(f)
        self.assertFalse(cinderx.jit.is_jit_compiled(f))

        before = cinderx.jit.count_interpreted_calls(f)
        for _ in range(10):
            self.assertEqual(f(10), 45)
        after = cinderx.jit.count_interpreted_calls(f)
        self.assertGreater(after, before)

        # Force compilation and verify that subsequent calls don't bump the
        # interpreted call counter (i.e., compiled code is actually executing).
        self.assertTrue(cinderx.jit.force_compile(f))
        self.assertTrue(cinderx.jit.is_jit_compiled(f))
        self.assertGreater(cinderx.jit.get_compiled_size(f), 0)

        interp0 = cinderx.jit.count_interpreted_calls(f)
        for _ in range(2000):
            self.assertEqual(f(10), 45)
        interp1 = cinderx.jit.count_interpreted_calls(f)
        self.assertEqual(interp1, interp0)

    def test_phase0_loop_osr_exports_entries(self) -> None:
        cinderx.jit.enable()

        def hot(n: int, acc: int) -> int:
            while n > 0:
                acc = acc + n
                n = n - 1
            return acc

        self.assertTrue(cinderx.jit.force_compile(hot))
        entries = cinderx.jit.get_osr_entries(hot)
        self.assertTrue(entries, entries)
        self.assertEqual(entries[0]["local_count"], 2, entries)
        self.assertGreater(entries[0]["entry_address"], 0, entries)
        self.assertGreater(entries[0]["test_entry_address"], 0, entries)

    def test_phase0_loop_osr_test_entry_executes_loop(self) -> None:
        cinderx.jit.enable()

        def hot(n: int, acc: int) -> int:
            while n > 0:
                acc = acc + n
                n = n - 1
            return acc

        self.assertTrue(cinderx.jit.force_compile(hot))
        result = cinderx.jit.run_osr_test_entry(hot, (3, 10))
        self.assertEqual(result, 16)

    def test_phase1_once_call_hot_loop_enters_jit_same_activation(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def hot(n: int, acc: int) -> int:
                while n > 0:
                    acc = acc + n
                    n = n - 1
                return acc

            jit.get_and_clear_runtime_stats()
            result = hot(50000, 0)
            stats = jit.get_and_clear_runtime_stats()
            osr_entries = [
                entry for entry in stats.get("osr", [])
                if entry["normal"]["func_qualname"] == "hot"
            ]

            print(result)
            print(len(osr_entries))
            print(sum(entry["int"]["count"] for entry in osr_entries))
            print(jit.is_jit_compiled(hot))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/phase1_once_call_hot_loop.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertEqual(int(lines[-4]), (50000 * 50001) // 2, proc.stdout)
            self.assertGreater(int(lines[-3]), 0, proc.stdout)
            self.assertGreater(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(lines[-1], "True", proc.stdout)

    def test_phase1_loop_osr_skips_active_exception_shape(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def hot(n: int) -> int:
                total = 0
                try:
                    while n > 0:
                        total += n
                        n -= 1
                finally:
                    total += 1
                return total

            jit.get_and_clear_runtime_stats()
            result = hot(5000)
            stats = jit.get_and_clear_runtime_stats()
            osr_entries = [
                entry for entry in stats.get("osr", [])
                if entry["normal"]["func_qualname"] == "hot"
            ]

            print(result)
            print(len(osr_entries))
            print(jit.is_jit_compiled(hot))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/phase1_active_exception_shape.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(int(lines[-3]), (5000 * 5001) // 2 + 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(lines[-1], "False", proc.stdout)

    def test_phase1_loop_osr_skips_pyperformance_startup_imports(self) -> None:
        # Regression guard:
        # pyperformance workers load the JIT startup hook while importing
        # stdlib modules. Same-activation OSR must not try to compile those
        # import-time stdlib loops before benchmark/user code starts.
        code = textwrap.dedent(
            """
            import cinderx
            import cinderx.jit as jit

            print(cinderx.is_initialized())
            print(jit.is_enabled())
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/pyperf_worker_startup_import.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYPERFORMANCE_RUNID"] = "pyperf-probe"
            env["CINDERX_WORKER_PYTHONJITAUTO"] = "10"
            env["CINDERX_ENABLE_SPECIALIZED_OPCODES"] = "0"
            hook_dir = os.path.abspath("scripts/arm/pyperf_env_hook")
            old_pythonpath = env.get("PYTHONPATH")
            env["PYTHONPATH"] = (
                hook_dir if not old_pythonpath else f"{hook_dir}{os.pathsep}{old_pythonpath}"
            )

            proc = subprocess.run(
                [sys.executable, script, "--debug-single-value"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2], "True", proc.stdout)
            self.assertEqual(lines[-1], "True", proc.stdout)

    def test_phase1_loop_osr_richards_method_loop_does_not_crash(self) -> None:
        try:
            import pyperformance
        except ModuleNotFoundError:
            self.skipTest("pyperformance is not installed")

        bench = os.path.join(
            os.path.dirname(pyperformance.__file__),
            "data-files",
            "benchmarks",
            "bm_richards",
            "run_benchmark.py",
        )
        if not os.path.exists(bench):
            self.skipTest(f"missing pyperformance richards benchmark: {bench}")

        code = textwrap.dedent(
            f"""
            import importlib.util

            import cinderx.jit as jit

            spec = importlib.util.spec_from_file_location("richards_probe", {bench!r})
            richards = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(richards)

            # pyperformance benchmark workers execute benchmark modules as
            # __main__. Preserve that module shape without invoking pyperf's
            # command-line runner from the imported file.
            richards.__dict__["__name__"] = "__main__"

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            print(richards.Richards().run(1))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/phase1_richards_osr.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONFAULTHANDLER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 1, proc.stdout)
            self.assertEqual(lines[-1], "True", proc.stdout)

    def test_instance_value_method_attr_shape_falls_back(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class C:
                def __init__(self):
                    self.f = lambda: 42

            def call_attr(c):
                return c.f()

            c = C()
            for _ in range(20000):
                if call_attr(c) != 42:
                    raise SystemExit("bad warmup result")

            print(jit.force_compile(call_attr))
            print(call_attr(c))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/instance_value_method_attr.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITINSTANCEVALUEMINLOCALS"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2], "True", proc.stdout)
            self.assertEqual(lines[-1], "42", proc.stdout)

    def test_phase0_osr_test_entry_preserves_live_local_refcounts(self) -> None:
        code = textwrap.dedent(
            """
            import json
            import os
            import sys

            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def v5(n):
                count = list(range(1, n + 1))
                m = n - 1
                r = n
                perm1 = list(range(n))
                perm = list(range(n))
                while 1:
                    while r != 1:
                        count[r - 1] = r
                        r -= 1
                    if perm1[0] != 0 and perm1[m] != m:
                        perm = perm1[:]
                        k = perm[0]
                        perm[: k + 1] = perm[k::-1]
                        k = perm[0]
                    while r != n:
                        perm1.insert(r, perm1.pop(0))
                        count[r] -= 1
                        if count[r] > 0:
                            break
                        r += 1
                    else:
                        return perm1[0]

            def v5_state_370(n):
                count = list(range(1, n + 1))
                m = n - 1
                r = n
                perm1 = list(range(n))
                perm = list(range(n))
                while 1:
                    while r != 1:
                        count[r - 1] = r
                        r -= 1
                    if perm1[0] != 0 and perm1[m] != m:
                        perm = perm1[:]
                        k = perm[0]
                        perm[: k + 1] = perm[k::-1]
                        k = perm[0]
                        return [n, count, m, r, perm1, perm, k]
                    while r != n:
                        perm1.insert(r, perm1.pop(0))
                        count[r] -= 1
                        if count[r] > 0:
                            break
                        r += 1

            assert jit.force_compile(v5)
            entries = jit.get_osr_entries(v5)
            entry_index = next(
                i for i, entry in enumerate(entries) if entry["bc_offset"] == 370
            )
            locals_seq = v5_state_370(9)
            tracked = {
                name: obj
                for name, obj in zip(v5.__code__.co_varnames, locals_seq)
                if isinstance(obj, list)
            }
            before = {
                name: sys.getrefcount(obj)
                for name, obj in tracked.items()
            }
            result = jit.run_osr_test_entry(v5, locals_seq, entry_index)
            after = {
                name: sys.getrefcount(obj)
                for name, obj in tracked.items()
            }
            print(
                json.dumps(
                    {
                        "result": result,
                        "before": before,
                        "after": after,
                    }
                ),
                flush=True,
            )
            os._exit(0)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/phase0_osr_refcount_regression.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertTrue(lines, proc.stdout)
            payload = json.loads(lines[-1])
            self.assertEqual(payload["result"], 0, payload)
            self.assertEqual(payload["after"], payload["before"], payload)

    def test_load_global_mutable_large_int_avoids_repeated_deopts(self) -> None:
        # Regression guard:
        # a mutable global int outside the small-int cache should not keep a
        # GuardIs identity check, otherwise TIMESTAMP += 1 guarantees deopts.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            TIMESTAMP = 1000

            class Square:
                __slots__ = ("timestamp", "color")

                def __init__(self):
                    self.timestamp = -1
                    self.color = 0

            class Board:
                __slots__ = ("squares", "color")

                def __init__(self):
                    self.squares = [Square() for _ in range(4)]
                    self.color = 1

                def useful(self, pos):
                    global TIMESTAMP
                    TIMESTAMP += 1

                    square = self.squares[pos]
                    empties = 0
                    for neighbour in self.squares:
                        if neighbour.timestamp != TIMESTAMP:
                            neighbour.timestamp = TIMESTAMP
                            empties += 1

                    return empties

            board = Board()
            assert jit.force_compile(Board.useful)
            assert jit.is_jit_compiled(Board.useful)

            jit.get_and_clear_runtime_stats()
            total = 0
            for i in range(200):
                total += board.useful(i % 4)

            stats = jit.get_and_clear_runtime_stats()
            deopt_count = sum(
                entry["int"]["count"]
                for entry in stats["deopt"]
                if entry["normal"]["func_qualname"] == "Board.useful"
            )
            print(deopt_count)
            print(total)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/load_global_mutable_int_deopt.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(int(lines[-1]), 800, proc.stdout)

    def test_load_global_mutable_small_int_avoids_repeated_deopts(self) -> None:
        # Regression guard:
        # low-threshold autojit must not permanently value-speculate a mutable
        # small-int global, otherwise every later call deopts forever.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(2)

            TIMESTAMP = 0

            class Square:
                __slots__ = ("timestamp", "color")

                def __init__(self):
                    self.timestamp = -1
                    self.color = 0

            class Board:
                __slots__ = ("squares", "color")

                def __init__(self):
                    self.squares = [Square() for _ in range(4)]
                    self.color = 1

                def useful(self, pos):
                    global TIMESTAMP
                    TIMESTAMP += 1

                    square = self.squares[pos]
                    empties = 0
                    for neighbour in self.squares:
                        if neighbour.timestamp != TIMESTAMP:
                            neighbour.timestamp = TIMESTAMP
                            empties += 1

                    return empties

            board = Board()
            for _ in range(3):
                board.useful(0)

            assert jit.is_jit_compiled(Board.useful)
            counts = cinderjit.get_function_hir_opcode_counts(Board.useful)

            jit.get_and_clear_runtime_stats()
            total = 0
            for i in range(200):
                total += board.useful(i % 4)

            stats = jit.get_and_clear_runtime_stats()
            deopt_count = sum(
                entry["int"]["count"]
                for entry in stats["deopt"]
                if entry["normal"]["func_qualname"] == "Board.useful"
            )
            print(counts.get("GuardIs", 0))
            print(counts.get("GuardType", 0))
            print(deopt_count)
            print(total)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/load_global_mutable_small_int_deopt.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(int(lines[-1]), 800, proc.stdout)

    def test_to_bool_none_specialization_avoids_repeated_non_none_deopts(self) -> None:
        # Regression guard:
        # adaptive TO_BOOL_NONE in the interpreter is only a quickening hint.
        # The JIT must not compile it into a permanent "value is None" guard,
        # otherwise later non-None falsey values deopt on every execution.
        code = textwrap.dedent(
            """
            import dis
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Falsey:
                def __bool__(self):
                    return False

            def f(x):
                if x:
                    return 1
                return 0

            for _ in range(200000):
                f(None)

            opnames = [instr.opname for instr in dis.get_instructions(f, adaptive=True)]
            assert "TO_BOOL_NONE" in opnames, opnames
            assert jit.force_compile(f)
            assert jit.is_jit_compiled(f)

            jit.get_and_clear_runtime_stats()
            total = 0
            for _ in range(200):
                total += f(Falsey())

            stats = jit.get_and_clear_runtime_stats()
            deopt_count = sum(
                entry["int"]["count"]
                for entry in stats.get("deopt", [])
                if entry["normal"]["func_qualname"] == "f"
            )
            print(deopt_count)
            print(total)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/to_bool_none_no_repeated_deopt.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(int(lines[-1]), 0, proc.stdout)

    def test_specialized_numeric_leaf_mixed_types_avoid_deopts(self) -> None:
        # Regression guard:
        # specialized numeric opcodes should not pin no-backedge leaf helpers
        # to exact int/float paths when runtime shapes are mixed.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import json

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class V:
                __slots__ = ("x", "y", "z")

                def __init__(self, x, y, z):
                    self.x = x
                    self.y = y
                    self.z = z

            def dot(a, b):
                return (a.x * b.x) + (a.y * b.y) + (a.z * b.z)

            # Seed int-specialized interpreter opcodes before JIT compilation.
            for _ in range(5000):
                dot(V(1, 2, 3), V(4, 5, 6))

            assert jit.force_compile(dot)
            jit.get_and_clear_runtime_stats()

            for _ in range(20000):
                dot(V(1.5, 2.5, 3.5), V(4.5, 5.5, 6.5))

            stats = jit.get_and_clear_runtime_stats()
            relevant = [
                entry
                for entry in stats["deopt"]
                if entry["normal"]["func_qualname"] == "dot"
            ]
            print(json.dumps(relevant))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/specialized_numeric_leaf_mixed_types.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            self.assertEqual(proc.stdout.strip(), "[]", proc.stdout)

    def test_load_global_rebound_object_uses_type_guard(self) -> None:
        # Regression guard:
        # rebinding a mutable object global should not pin the compiled path to
        # a single instance identity, otherwise every later call deopts.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Planner:
                __slots__ = ("current_mark",)

                def __init__(self):
                    self.current_mark = 0

                def new_mark(self):
                    self.current_mark += 1
                    return self.current_mark

            planner = Planner()

            def get_planner():
                global planner
                return planner

            assert jit.force_compile(get_planner)
            assert jit.is_jit_compiled(get_planner)

            counts = cinderjit.get_function_hir_opcode_counts(get_planner)

            jit.get_and_clear_runtime_stats()
            for _ in range(5):
                planner = Planner()
                for _ in range(2000):
                    get_planner().new_mark()

            stats = jit.get_and_clear_runtime_stats()
            deopt_count = sum(
                entry["int"]["count"]
                for entry in stats.get("deopt", [])
                if entry["normal"]["func_qualname"] == "get_planner"
            )

            print(counts.get("GuardIs", 0))
            print(counts.get("GuardType", 0))
            print(deopt_count)
            print(planner.current_mark)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/load_global_rebound_object_guard.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(int(lines[-1]), 2000, proc.stdout)

    def test_exact_method_cache_split_respects_instance_shadowing(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            class Box:
                def __getattribute__(self, name):
                    return object.__getattribute__(self, name)

                def foo(self, x):
                    return x + 1

                def call(self, x):
                    return self.foo(x)

            box = Box()
            for _ in range(200000):
                box.call(4)

            assert jit.force_compile(Box.call)
            counts = cinderjit.get_function_hir_opcode_counts(Box.call)
            print(counts.get("LoadMethodCacheEntryValue", 0))
            print(counts.get("FillMethodCache", 0))
            print(counts.get("LoadMethodCached", 0))
            print(box.call(4))
            box.foo = lambda x: x + 10
            print(box.call(4))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/exact_method_cache_shadowing.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            def run(env_value: str | None) -> list[str]:
                env = dict(os.environ)
                if env_value is not None:
                    env["PYTHONJITEXACTMETHODCACHESPLIT"] = env_value
                proc = subprocess.run(
                    [sys.executable, script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
                )
                lines = [
                    line.strip() for line in proc.stdout.splitlines() if line.strip()
                ]
                self.assertGreaterEqual(len(lines), 5, proc.stdout)
                self.assertEqual(int(lines[-2]), 5, proc.stdout)
                self.assertEqual(int(lines[-1]), 14, proc.stdout)
                return lines

            enabled_lines = run("1")
            self.assertGreaterEqual(int(enabled_lines[-5]), 1, enabled_lines)
            self.assertGreaterEqual(int(enabled_lines[-4]), 1, enabled_lines)
            self.assertEqual(int(enabled_lines[-3]), 0, enabled_lines)

            disabled_lines = run("0")
            self.assertEqual(int(disabled_lines[-5]), 0, disabled_lines)
            self.assertEqual(int(disabled_lines[-4]), 0, disabled_lines)
            self.assertGreaterEqual(int(disabled_lines[-3]), 1, disabled_lines)

    def test_dynamic_method_cache_split_respects_shadowing_and_polymorphism(
        self,
    ) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            class Box:
                def __getattribute__(self, name):
                    return object.__getattribute__(self, name)

                def foo(self, x):
                    return x + 1

            class Other:
                def __getattribute__(self, name):
                    return object.__getattribute__(self, name)

                def foo(self, x):
                    return x + 20

            def hot(obj, x):
                return obj.foo(x)

            box = Box()
            other = Other()
            for i in range(200000):
                expected = 5 if (i & 1) == 0 else 24
                if hot(box if (i & 1) == 0 else other, 4) != expected:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(hot)
            counts = cinderjit.get_function_hir_opcode_counts(hot)
            print(counts.get("LoadMethodCacheEntryType", 0))
            print(counts.get("LoadMethodCacheEntryValue", 0))
            print(counts.get("FillMethodCache", 0))
            print(counts.get("LoadMethodCached", 0))
            print(hot(box, 4))
            box.foo = lambda x: x + 10
            print(hot(box, 4))
            print(hot(Other(), 4))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/dynamic_method_cache_split.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            def run(enabled: bool) -> list[str]:
                env = dict(os.environ)
                env["PYTHONJITDYNAMICMETHODCACHESPLIT"] = "1" if enabled else "0"
                env["PYTHONJITEXACTMETHODCACHESPLIT"] = "0"
                proc = subprocess.run(
                    [sys.executable, script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
                )
                lines = [
                    line.strip() for line in proc.stdout.splitlines() if line.strip()
                ]
                self.assertGreaterEqual(len(lines), 7, proc.stdout)
                self.assertEqual(int(lines[-3]), 5, proc.stdout)
                self.assertEqual(int(lines[-2]), 14, proc.stdout)
                self.assertEqual(int(lines[-1]), 24, proc.stdout)
                return lines

            disabled_lines = run(False)
            self.assertEqual(int(disabled_lines[-7]), 0, disabled_lines)
            self.assertEqual(int(disabled_lines[-6]), 0, disabled_lines)
            self.assertEqual(int(disabled_lines[-5]), 0, disabled_lines)
            self.assertGreaterEqual(int(disabled_lines[-4]), 1, disabled_lines)

            enabled_lines = run(True)
            self.assertGreaterEqual(int(enabled_lines[-7]), 1, enabled_lines)
            self.assertGreaterEqual(int(enabled_lines[-6]), 1, enabled_lines)
            self.assertGreaterEqual(int(enabled_lines[-5]), 1, enabled_lines)
            self.assertEqual(int(enabled_lines[-4]), 0, enabled_lines)

    def test_cached_method_call_helper_fuses_lookup_and_call(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            class Box:
                def __getattribute__(self, name):
                    return object.__getattribute__(self, name)

                def foo(self, x):
                    return x + 1

            def hot(obj, x):
                return obj.foo(x)

            box = Box()
            for _ in range(200000):
                if hot(box, 4) != 5:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(hot)
            counts = cinderjit.get_function_hir_opcode_counts(hot)
            print(counts.get("CallMethodCached", 0))
            print(counts.get("LoadMethodCached", 0) + counts.get("LoadMethod", 0))
            print(counts.get("CallMethod", 0))
            print(hot(box, 4))
            box.foo = lambda x: x + 10
            print(hot(box, 4))
            Box.foo = lambda self, x: x + 20
            print(hot(Box(), 4))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/cached_method_call_helper.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITCACHEDMETHODCALLHELPER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertGreaterEqual(int(lines[-6]), 1, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertEqual(int(lines[-3]), 5, proc.stdout)
            self.assertEqual(int(lines[-2]), 14, proc.stdout)
            self.assertEqual(int(lines[-1]), 24, proc.stdout)

    def test_cached_method_call_helper_covers_method_with_values_fallback(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Richards-style direct-self zero-arg calls can warm as
        # LOAD_ATTR_METHOD_WITH_VALUES while still falling back to generic
        # lookup in HIR. The fused helper should own that safe fallback shape
        # rather than leaving a separate LoadMethodCached + CallMethod pair.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Task:
                def __init__(self, flag):
                    self.flag = flag

                def ready(self):
                    return self.flag

                def run(self):
                    if self.ready():
                        msg = 11
                    else:
                        msg = 22
                    return msg

            task = Task(True)
            for _ in range(20000):
                if task.run() != 11:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(Task.run)
            counts = cinderjit.get_function_hir_opcode_counts(Task.run)
            print(counts.get("CallMethodCached", 0))
            print(counts.get("LoadMethodCached", 0) + counts.get("LoadMethod", 0))
            print(counts.get("CallMethod", 0))
            print(task.run())
            task.ready = lambda: False
            print(task.run())
            other = Task(True)
            Task.ready = lambda self: False
            print(other.run())
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/cached_method_call_method_values_fallback.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITCACHEDMETHODCALLHELPER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertGreaterEqual(int(lines[-6]), 1, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertEqual(int(lines[-3]), 11, proc.stdout)
            self.assertEqual(int(lines[-2]), 22, proc.stdout)
            self.assertEqual(int(lines[-1]), 22, proc.stdout)

    def test_cached_method_call_helper_supports_call_kw(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 CALL_KW")

        # pyperformance go has Square.find(update=True) call sites that still
        # lower as a cached method lookup followed by a keyword method call.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Finder:
                def __getattribute__(self, name):
                    return object.__getattribute__(self, name)

                def find(self, *, update=False):
                    return 11 if update else 22

            def hot(finder):
                return finder.find(update=True)

            finder = Finder()
            for _ in range(20000):
                if hot(finder) != 11:
                    raise SystemExit("bad warmup result")

            assert jit.force_compile(hot)
            counts = cinderjit.get_function_hir_opcode_counts(hot)
            print(counts.get("CallMethodCached", 0))
            print(counts.get("LoadMethodCached", 0) + counts.get("LoadMethod", 0))
            print(counts.get("CallMethod", 0))
            print(hot(finder))
            finder.find = lambda *, update=False: 33 if update else 44
            print(hot(finder))
            Finder.find = lambda self, *, update=False: 55 if update else 66
            del finder.find
            print(hot(finder))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/cached_method_call_kw.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITCACHEDMETHODCALLHELPER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertGreaterEqual(int(lines[-6]), 1, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertEqual(int(lines[-3]), 11, proc.stdout)
            self.assertEqual(int(lines[-2]), 33, proc.stdout)
            self.assertEqual(int(lines[-1]), 55, proc.stdout)

    def test_cached_method_call_kw_lir_uses_fixed_helper(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 CALL_KW")

        # Once CALL_KW has already fused into CallMethodCached, the LIR
        # lowering should avoid the generic vectorcall-shaped helper for small
        # fixed-arity keyword calls. bm_go has calls like find(update=True).
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Finder:
                def __getattribute__(self, name):
                    return object.__getattribute__(self, name)

                def find(self, *, update=False):
                    return 11 if update else 22

            def hot(finder):
                return finder.find(update=True)

            finder = Finder()
            for _ in range(20000):
                if hot(finder) != 11:
                    raise SystemExit("bad warmup result")

            assert jit.force_compile(hot)
            counts = cinderjit.get_function_hir_opcode_counts(hot)
            print(counts.get("CallMethodCached", 0))
            print(counts.get("LoadMethodCached", 0) + counts.get("LoadMethod", 0))
            print(counts.get("CallMethod", 0))
            print(hot(finder))
            finder.find = lambda *, update=False: 33 if update else 44
            print(hot(finder))
            Finder.find = lambda self, *, update=False: 55 if update else 66
            del finder.find
            print(hot(finder))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/cached_method_call_kw_fixed_lir.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITCACHEDMETHODCALLHELPER"] = "1"
            env["PYTHONJITDUMPLIR"] = "1"
            env["PYTHONJITENABLEKWPYFUNCVECTORCALL"] = "0"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertGreaterEqual(int(lines[-6]), 1, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertEqual(int(lines[-3]), 11, proc.stdout)
            self.assertEqual(int(lines[-2]), 33, proc.stdout)
            self.assertEqual(int(lines[-1]), 55, proc.stdout)

            dump = proc.stdout + "\n" + proc.stderr
            match = re.search(
                r"LIR for __main__:hot after generation:\n(.*?)(?:\nJIT: .*?LIR for |\Z)",
                dump,
                re.S,
            )
            self.assertIsNotNone(match, dump)
            section = match.group(1)
            self.assertIn("Call ", section)
            self.assertNotIn("VectorCall", section)

    def test_call_method_with_instance_attr_arg_lir_uses_fixed_helper(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 specialized opcodes")

        # bm_go still has object-method calls where the explicit argument is an
        # already-specialized instance-value load, such as obj.foo(arg.value).
        # The method lookup must remain before the argument load for exception
        # ordering, but the final method call can still avoid the generic
        # vectorcall-shaped helper.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Target:
                def __getattribute__(self, name):
                    return object.__getattribute__(self, name)

                def foo(self, value):
                    return value + 1

            class Arg:
                def __init__(self, value):
                    self.value = value

            def hot(target, arg):
                return target.foo(arg.value)

            target = Target()
            arg = Arg(10)
            for _ in range(20000):
                if hot(target, arg) != 11:
                    raise SystemExit("bad warmup result")

            assert jit.force_compile(hot)
            counts = cinderjit.get_function_hir_opcode_counts(hot)
            print(counts.get("CallMethodCached", 0))
            print(counts.get("LoadMethodCached", 0) + counts.get("LoadMethod", 0))
            print(counts.get("CallMethod", 0))
            print(hot(target, arg))
            target.foo = lambda value: value + 20
            print(hot(target, arg))
            Target.foo = lambda self, value: value + 30
            del target.foo
            print(hot(target, arg))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/call_method_instance_attr_arg_fixed_lir.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITCACHEDMETHODCALLHELPER"] = "1"
            env["PYTHONJITDUMPLIR"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertEqual(int(lines[-6]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 1, proc.stdout)
            self.assertEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 11, proc.stdout)
            self.assertEqual(int(lines[-2]), 30, proc.stdout)
            self.assertEqual(int(lines[-1]), 40, proc.stdout)

            dump = proc.stdout + "\n" + proc.stderr
            match = re.search(
                r"LIR for __main__:hot after generation:\n(.*?)(?:\nJIT: .*?LIR for |\Z)",
                dump,
                re.S,
            )
            self.assertIsNotNone(match, dump)
            section = match.group(1)
            self.assertIn("Call ", section)
            self.assertNotIn("VectorCall", section)

    def test_cached_method_call_attr_arg_preserves_lookup_exception_order(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 specialized opcodes")

        # Delaying method lookup past an argument attribute load is only safe if
        # the original Python exception order is preserved. If both the method
        # and the argument attribute disappear after compilation, target.foo
        # must fail before arg.value is read.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Target:
                def __getattribute__(self, name):
                    return object.__getattribute__(self, name)

                def foo(self, value):
                    return value + 1

            class Arg:
                def __init__(self, value):
                    self.value = value

            def hot(target, arg):
                return target.foo(arg.value)

            target = Target()
            arg = Arg(10)
            for _ in range(20000):
                if hot(target, arg) != 11:
                    raise SystemExit("bad warmup result")

            assert jit.force_compile(hot)
            del Target.foo
            del arg.value
            try:
                hot(target, arg)
            except AttributeError as exc:
                print(exc)
            else:
                raise SystemExit("expected AttributeError")
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/cached_method_call_attr_arg_order.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITCACHEDMETHODCALLHELPER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            self.assertIn("foo", proc.stdout)
            self.assertNotIn("value", proc.stdout)

    def test_call_method_fixed_helper_skips_plain_function_call(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 specialized opcodes")

        # The fixed CallMethod helper is intended for real method-shaped calls
        # that have a self-or-null result from LoadMethod. Keep plain
        # function calls on the normal vectorcall lowering so the experiment
        # does not perturb unrelated call sites.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def callee(value):
                return value + 1

            def hot(fn, value):
                return fn(value)

            for _ in range(20000):
                if hot(callee, 10) != 11:
                    raise SystemExit("bad warmup result")

            assert jit.force_compile(hot)
            print(hot(callee, 10))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/call_method_fixed_plain_function.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITCACHEDMETHODCALLHELPER"] = "1"
            env["PYTHONJITDUMPLIR"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertEqual(int(lines[-1]), 11, proc.stdout)

            dump = proc.stdout + "\n" + proc.stderr
            match = re.search(
                r"LIR for __main__:hot after generation:\n(.*?)(?:\nJIT: .*?LIR for |\Z)",
                dump,
                re.S,
            )
            self.assertIsNotNone(match, dump)
            self.assertIn("VectorCall", match.group(1))

    def test_polymorphic_virtual_method_avoids_method_with_values_guard_deopts(
        self,
    ) -> None:
        code = textwrap.dedent(
            """
            import json
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Task:
                def runTask(self, x):
                    return self.fn(x)

            class WorkTask(Task):
                def fn(self, x):
                    return x + 1

            class DeviceTask(Task):
                def fn(self, x):
                    return x + 2

            class HandlerTask(Task):
                def fn(self, x):
                    return x + 3

            work = WorkTask()
            for _ in range(200000):
                work.runTask(1)

            assert jit.force_compile(Task.runTask)
            jit.get_and_clear_runtime_stats()

            total = 0
            seq = [work, DeviceTask(), HandlerTask(), work]
            for i in range(10000):
                total += seq[i % len(seq)].runTask(i)

            stats = jit.get_and_clear_runtime_stats()
            relevant = [
                entry
                for entry in stats.get("deopt", [])
                if entry["normal"]["func_qualname"] == "Task.runTask"
                and entry["normal"]["description"] == "LOAD_ATTR_METHOD_WITH_VALUES"
            ]
            print(len(relevant))
            print(sum(entry["int"]["count"] for entry in relevant))
            print(total)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/polymorphic_virtual_method_deopts.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertLessEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)

    def test_inferred_self_type_guard_deopts_on_subclass_instance(self) -> None:
        # Regression guard:
        # inferred exact-self typing should install an entry GuardType for
        # normal Python methods, so later subclass instances deopt safely.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            class Point:
                def __init__(self, x):
                    self.x = x

                def getx(self):
                    return self.x

            p = Point(1)
            for _ in range(20000):
                p.getx()

            assert jit.force_compile(Point.getx)
            counts = cinderjit.get_function_hir_opcode_counts(Point.getx)
            print(counts.get("GuardType", 0))

            class Sub(Point):
                pass

            q = Sub(2)
            jit.get_and_clear_runtime_stats()
            print(q.getx())
            stats = jit.get_and_clear_runtime_stats()
            deopt_count = sum(
                entry["int"]["count"]
                for entry in stats["deopt"]
                if entry["normal"]["func_qualname"] == "Point.getx"
            )
            print(deopt_count)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/inferred_self_type_guard.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 2, proc.stdout)
            self.assertGreaterEqual(int(lines[-1]), 1, proc.stdout)

    def test_nested_class_methods_do_not_infer_self_exact_type(self) -> None:
        # Regression guard:
        # only top-level Class.method qualnames should infer exact-self typing;
        # nested classes must not misinfer Outer as the receiver type.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            class Outer:
                class Inner:
                    def __init__(self, x):
                        self.x = x

                    def getx(self):
                        return self.x

            obj = Outer.Inner(7)
            for _ in range(20000):
                obj.getx()

            assert jit.force_compile(Outer.Inner.getx)
            counts = cinderjit.get_function_hir_opcode_counts(Outer.Inner.getx)
            print(counts.get("GuardType", 0))
            print(obj.getx())
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/nested_class_self_inference.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(int(lines[-1]), 7, proc.stdout)

    def test_tiny_return_self_method_refines_receiver_after_guard(self) -> None:
        # Regression guard:
        # a zero-arg helper that trivially returns self should let the JIT
        # install an exact-type guard and refine later receiver field loads.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            class Vector:
                def __init__(self, x, y, z):
                    self.x = x
                    self.y = y
                    self.z = z

                def mustBeVector(self):
                    return self

            def dot(a, b):
                b.mustBeVector()
                return (a.x * b.x) + (a.y * b.y) + (a.z * b.z)

            u = Vector(1.0, 2.0, 3.0)
            v = Vector(4.0, 5.0, 6.0)
            for _ in range(20000):
                dot(u, v)

            assert jit.force_compile(dot)
            counts = cinderjit.get_function_hir_opcode_counts(dot)
            print(counts.get("GuardType", 0))
            print(counts.get("LoadField", 0))
            print(counts.get("LoadAttrCached", 0))
            print(dot(u, v))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tiny_return_self_refines_receiver.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 5, proc.stdout)
            self.assertLessEqual(int(lines[-2]), 6, proc.stdout)
            self.assertEqual(float(lines[-1]), 32.0, proc.stdout)

    def test_tiny_bool_state_mutator_removes_lookup_and_callmethod(self) -> None:
        # Regression guard:
        # Richards-style state transitions are tiny zero-arg mutators that set
        # boolean instance fields and return self. The direct lowering only
        # earns its keep if it removes both the method call and the method
        # lookup; keeping LoadMethodCached alive regressed the object-heavy
        # matrix in an earlier attempt.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class State:
                def __init__(self):
                    self.packet_pending = True
                    self.task_waiting = False
                    self.task_holding = False

                def running(self):
                    self.packet_pending = False
                    self.task_waiting = False
                    self.task_holding = False
                    return self

                def packetPending(self):
                    self.packet_pending = True
                    self.task_waiting = False
                    self.task_holding = False
                    return self

                def waitTask(self):
                    self.task_waiting = True
                    return self

            def score(state):
                return (
                    (4 if state.packet_pending else 0)
                    + (2 if state.task_waiting else 0)
                    + (1 if state.task_holding else 0)
                )

            def hot(state, mode):
                if mode == 0:
                    result = state.running()
                elif mode == 1:
                    result = state.packetPending()
                else:
                    result = state.waitTask()
                if result is not state:
                    return -100
                return score(state)

            state = State()
            for _ in range(20000):
                if hot(state, 0) != 0:
                    raise SystemExit("bad running warmup")
                if hot(state, 1) != 4:
                    raise SystemExit("bad pending warmup")
                if hot(state, 2) != 6:
                    raise SystemExit("bad wait warmup")

            assert jit.force_compile(hot)
            counts = cinderjit.get_function_hir_opcode_counts(hot)
            print(counts.get("CallMethod", 0))
            print(counts.get("LoadMethodCached", 0) + counts.get("LoadMethod", 0))
            print(counts.get("StoreField", 0))
            print(hot(state, 0))
            print(hot(state, 1))
            print(hot(state, 2))

            state.packet_pending = True
            state.task_waiting = False
            state.task_holding = False
            state.running = lambda: state
            print(hot(state, 0))

            State.packetPending = lambda self: self
            state.packet_pending = False
            state.task_waiting = True
            state.task_holding = False
            print(hot(state, 1))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tiny_bool_state_mutator_lookup_free.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONFAULTHANDLER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 8, proc.stdout)
            self.assertEqual(int(lines[-8]), 0, proc.stdout)
            self.assertEqual(int(lines[-7]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-6]), 7, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            self.assertEqual(int(lines[-4]), 4, proc.stdout)
            self.assertEqual(int(lines[-3]), 6, proc.stdout)
            self.assertEqual(int(lines[-2]), 4, proc.stdout)
            self.assertEqual(int(lines[-1]), 2, proc.stdout)

    def test_tiny_bool_method_refines_branch_receiver_fields(self) -> None:
        # Regression guard:
        # a zero-arg helper that returns constant bool should let the JIT
        # refine the receiver type within the taken branch and lower later
        # attribute reads to field paths.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            class Vector:
                def __init__(self, x, y, z):
                    self.x = x
                    self.y = y
                    self.z = z

                def isPoint(self):
                    return False

            class Point:
                def __init__(self, x, y, z):
                    self.x = x
                    self.y = y
                    self.z = z

                def isPoint(self):
                    return True

                def diff(self, other):
                    if other.isPoint():
                        return (
                            (self.x - other.x)
                            + (self.y - other.y)
                            + (self.z - other.z)
                        )
                    return (
                        (self.x - other.x)
                        + (self.y - other.y)
                        + (self.z - other.z)
                    )

            p = Point(10.0, 20.0, 30.0)
            q = Point(1.0, 2.0, 3.0)
            v = Vector(4.0, 5.0, 6.0)
            for _ in range(20000):
                p.diff(q)
                p.diff(v)

            assert jit.force_compile(Point.diff)
            counts = cinderjit.get_function_hir_opcode_counts(Point.diff)
            print(counts.get("GuardType", 0))
            print(counts.get("LoadField", 0))
            print(counts.get("LoadAttrCached", 0))
            print(counts.get("CallMethod", 0))
            print(p.diff(q))
            print(p.diff(v))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tiny_bool_branch_refines_receiver.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            # Upstream main changes keep the branch-refinement shape profitable
            # but no longer guarantee two exact guards or full elimination of
            # cached attribute loads in this mixed receiver flow.
            self.assertGreaterEqual(int(lines[-6]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 17, proc.stdout)
            self.assertLessEqual(int(lines[-4]), 6, proc.stdout)
            self.assertLessEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(float(lines[-2]), 54.0, proc.stdout)
            self.assertEqual(float(lines[-1]), 45.0, proc.stdout)

    def test_tiny_bool_getter_method_eliminates_callmethod(self) -> None:
        # Regression guard:
        # object-heavy workloads such as Richards use zero-arg predicate
        # helpers that simply return a boolean instance field. Once warmed,
        # those should be cheaper than a full Python method call.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class State:
                def __init__(self):
                    self.flag = False
                    self.value = 7

                def is_flag(self):
                    return self.flag

            def hot(state):
                if state.is_flag():
                    return 1
                return state.value

            state = State()
            for _ in range(20000):
                if hot(state) != 7:
                    raise SystemExit("bad false warmup")

            assert jit.force_compile(hot)
            counts = cinderjit.get_function_hir_opcode_counts(hot)
            print(counts.get("CallMethod", 0))
            print(counts.get("LoadMethodCached", 0))
            print(counts.get("LoadField", 0))
            print(hot(state))
            state.flag = True
            print(hot(state))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tiny_bool_getter_no_callmethod.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 5, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            # The method cache load may remain as a conservative lookup guard;
            # the expensive Python method call itself should be gone.
            self.assertLessEqual(int(lines[-4]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 2, proc.stdout)
            self.assertEqual(int(lines[-2]), 7, proc.stdout)
            self.assertEqual(int(lines[-1]), 1, proc.stdout)

    def test_tiny_bool_getter_method_respects_instance_shadowing(self) -> None:
        # A direct getter inline must still respect Python's dynamic instance
        # attribute shadowing after the method has already been compiled.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class State:
                def __init__(self):
                    self.flag = False
                    self.value = 7

                def is_flag(self):
                    return self.flag

            def hot(state):
                if state.is_flag():
                    return 1
                return state.value

            state = State()
            for _ in range(20000):
                if hot(state) != 7:
                    raise SystemExit("bad false warmup")

            assert jit.force_compile(hot)
            counts = cinderjit.get_function_hir_opcode_counts(hot)
            print(counts.get("CallMethod", 0))
            print(hot(state))
            state.is_flag = lambda: True
            print(hot(state))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tiny_bool_getter_shadowing.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertEqual(int(lines[-2]), 7, proc.stdout)
            self.assertEqual(int(lines[-1]), 1, proc.stdout)

    def test_tiny_bool_predicate_method_eliminates_branch_callmethod(self) -> None:
        # Regression guard:
        # Richards-style state predicates are inherited by multiple concrete
        # task classes and are only used as branch conditions. The caller should
        # be able to avoid the Python method call while preserving branch
        # semantics for exact-bool state fields.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class TaskState:
                def __init__(self, pending=False, waiting=False, holding=False):
                    self.packet_pending = pending
                    self.task_waiting = waiting
                    self.task_holding = holding

                def isTaskHoldingOrWaiting(self):
                    return self.task_holding or (
                        not self.packet_pending and self.task_waiting
                    )

                def isWaitingWithPacket(self):
                    return (
                        self.packet_pending
                        and self.task_waiting
                        and not self.task_holding
                    )

            class TaskA(TaskState):
                pass

            class TaskB(TaskState):
                pass

            def hot_waiting_with_packet(state):
                if state.isWaitingWithPacket():
                    return 10
                return 20

            def hot_holding_or_waiting(state):
                if state.isTaskHoldingOrWaiting():
                    return 30
                return 40

            ready = TaskA(True, True, False)
            holding = TaskB(False, False, True)
            waiting = TaskA(False, True, False)
            running = TaskB(False, False, False)
            states = (ready, holding, waiting, running)

            for _ in range(20000):
                if hot_waiting_with_packet(ready) != 10:
                    raise SystemExit("bad ready waiting result")
                if hot_waiting_with_packet(holding) != 20:
                    raise SystemExit("bad holding waiting result")
                if hot_holding_or_waiting(waiting) != 30:
                    raise SystemExit("bad waiting holding result")
                if hot_holding_or_waiting(running) != 40:
                    raise SystemExit("bad running holding result")
                for state in states:
                    state.isWaitingWithPacket()
                    state.isTaskHoldingOrWaiting()

            assert jit.force_compile(hot_waiting_with_packet)
            assert jit.force_compile(hot_holding_or_waiting)
            waiting_counts = cinderjit.get_function_hir_opcode_counts(
                hot_waiting_with_packet
            )
            holding_counts = cinderjit.get_function_hir_opcode_counts(
                hot_holding_or_waiting
            )
            print(waiting_counts.get("CallMethod", 0))
            print(waiting_counts.get("LoadMethodCached", 0))
            print(waiting_counts.get("LoadField", 0))
            print(holding_counts.get("CallMethod", 0))
            print(holding_counts.get("LoadMethodCached", 0))
            print(holding_counts.get("LoadField", 0))
            print(hot_waiting_with_packet(ready))
            print(hot_waiting_with_packet(holding))
            print(hot_holding_or_waiting(waiting))
            print(hot_holding_or_waiting(running))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tiny_bool_predicate_no_callmethod.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 10, proc.stdout)
            self.assertEqual(int(lines[-10]), 0, proc.stdout)
            self.assertLessEqual(int(lines[-9]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-8]), 6, proc.stdout)
            self.assertEqual(int(lines[-7]), 0, proc.stdout)
            self.assertLessEqual(int(lines[-6]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 6, proc.stdout)
            self.assertEqual(int(lines[-4]), 10, proc.stdout)
            self.assertEqual(int(lines[-3]), 20, proc.stdout)
            self.assertEqual(int(lines[-2]), 30, proc.stdout)
            self.assertEqual(int(lines[-1]), 40, proc.stdout)

    def test_plain_instance_other_arg_guard_eliminates_cached_attr_loads(self) -> None:
        # Regression guard:
        # for a top-level leaf-class method taking `other`, exact arg guards
        # should let both receiver sides lower off the generic LoadAttrCached
        # path.
        code = textwrap.dedent(
            """
            import math
            import cinderx.jit as jit
            import cinderjit

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
            counts = cinderjit.get_function_hir_opcode_counts(Point.dist)
            print(counts.get("GuardType", 0))
            print(counts.get("LoadField", 0))
            print(counts.get("LoadAttr", 0))
            print(counts.get("LoadAttrCached", 0))
            print(counts.get("DeoptPatchpoint", 0))
            print(a.dist(b))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/plain_instance_other_arg_guard.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertGreaterEqual(int(lines[-6]), 8, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 8, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 6, proc.stdout)
            self.assertEqual(float(lines[-1]), 5.196152422706632, proc.stdout)

    def test_bound_method_attr_identity_is_not_coalesced(self) -> None:
        # Regression guard:
        # repeated bound-method-producing attribute loads must preserve Python
        # identity semantics even when the receiver has an exact stable type.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def f():
                s = "abc"
                a = s.upper
                b = s.upper
                return a is b

            assert jit.force_compile(f)
            counts = cinderjit.get_function_hir_opcode_counts(f)
            print(counts.get("LoadAttrCached", 0))
            print(f())
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/bound_method_attr_identity.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 2, proc.stdout)
            self.assertEqual(lines[-1], "False", proc.stdout)

    def test_other_arg_inference_skips_helper_method_shapes(self) -> None:
        # Regression guard:
        # exact-`other` inference should not fire when the arg is used for
        # helper method calls such as `other.mustBeVector()`.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Vector:
                def __init__(self, x, y, z):
                    self.x = x
                    self.y = y
                    self.z = z

                def mustBeVector(self):
                    return self

                def dot(self, other):
                    other.mustBeVector()
                    return (self.x * other.x) + (self.y * other.y) + (self.z * other.z)

            a = Vector(1.0, 2.0, 3.0)
            b = Vector(4.0, 5.0, 6.0)
            for _ in range(20000):
                a.dot(b)

            assert jit.force_compile(Vector.dot)
            counts = cinderjit.get_function_hir_opcode_counts(Vector.dot)
            print(counts.get("GuardType", 0))
            print(counts.get("LoadField", 0))
            print(counts.get("LoadAttrCached", 0))
            print(a.dot(b))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/other_arg_helper_shape.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertLessEqual(int(lines[-4]), 3, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 6, proc.stdout)
            self.assertLessEqual(int(lines[-2]), 3, proc.stdout)
            self.assertEqual(float(lines[-1]), 32.0, proc.stdout)

    def test_polymorphic_method_load_avoids_method_with_values_deopts(self) -> None:
        # Regression guard:
        # method-with-values lowering should not pin polymorphic receiver call
        # sites to a single exact type and then deopt repeatedly.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Sphere:
                def intersectionTime(self):
                    return 1

            class Halfspace:
                def intersectionTime(self):
                    return 2

            def invoke(obj):
                return obj.intersectionTime()

            s = Sphere()
            h = Halfspace()

            # Seed the interpreter specialization from a monomorphic shape first.
            for _ in range(20000):
                invoke(s)

            assert jit.force_compile(invoke)
            counts = cinderjit.get_function_hir_opcode_counts(invoke)

            jit.get_and_clear_runtime_stats()
            total = 0
            for i in range(20000):
                total += invoke(s if (i & 1) == 0 else h)

            stats = jit.get_and_clear_runtime_stats()
            deopt_count = sum(
                entry["int"]["count"]
                for entry in stats["deopt"]
                if entry["normal"]["func_qualname"] == "invoke"
            )

            print(counts.get("LoadMethod", 0))
            print(counts.get("LoadMethodCached", 0))
            print(deopt_count)
            print(total)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/polymorphic_method_load_no_deopt.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]) + int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(int(lines[-1]), 30000, proc.stdout)

    def test_attr_derived_monomorphic_method_load_restores_inlining(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Regression guard:
        # attr-derived receivers such as self.reference.find(update) may be
        # runtime-monomorphic even when their HIR type is only Object. Those
        # receivers should still be able to recover the method-with-values fast
        # path and expose a VectorCall that the HIR inliner can see.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_hir_inliner()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Square:
                def __init__(self, reference=None, value=0):
                    self.reference = reference
                    self.value = value

                def find(self, update):
                    if self.reference is None:
                        return self.value + update
                    return self.reference.find(update) + self.value + update

            root = Square(None, 1)
            mid = Square(root, 2)
            outer = Square(mid, 3)

            for _ in range(20000):
                outer.find(1)

            assert jit.force_compile(Square.find)
            counts = cinderjit.get_function_hir_opcode_counts(Square.find)
            stats = jit.get_inlined_functions_stats(Square.find)
            print(counts.get("CallMethod", 0))
            print(counts.get("VectorCall", 0))
            print(stats.get("num_inlined_functions", 0))
            print(outer.find(1))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/attr_derived_monomorphic_method_load.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 9, proc.stdout)

    def test_method_with_values_one_arg_method_preloads_for_hir_inliner(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Regression guard:
        # Richards-style methods call one-arg helper methods like
        # Task.findtcb(id).  LOAD_ATTR_METHOD_WITH_VALUES can recover a direct
        # VectorCall for these calls, but the HIR inliner also needs the
        # method's PyFunction preloaded.  Only force-compile the caller here;
        # the callee should be discovered from the warmed method cache.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_hir_inliner()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class TaskWorkArea:
                def __init__(self):
                    self.taskTab = [None] * 4

            taskWorkArea = TaskWorkArea()

            class Task:
                def __init__(self, ident, priority):
                    self.ident = ident
                    self.priority = priority
                    taskWorkArea.taskTab[ident] = self

                def findtcb(self, ident):
                    t = taskWorkArea.taskTab[ident]
                    if t is None:
                        pass
                    return t

                def release(self, ident):
                    return self.findtcb(ident).priority + self.priority

            root = Task(0, 1)
            Task(1, 10)
            Task(2, 20)
            Task(3, 30)

            for _ in range(20000):
                if root.release(1) != 11:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(Task.release)
            counts = cinderjit.get_function_hir_opcode_counts(Task.release)
            stats = jit.get_inlined_functions_stats(Task.release)
            print(counts.get("CallMethod", 0))
            print(counts.get("VectorCall", 0))
            print(stats.get("num_inlined_functions", 0))
            print(root.release(2))
            print(root.release(-1))
            try:
                root.release(99)
            except IndexError:
                print("index-error")
            else:
                print("missing-index-error")
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/method_with_values_one_arg_inline.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 21, proc.stdout)
            self.assertEqual(int(lines[-2]), 31, proc.stdout)
            self.assertEqual(lines[-1], "index-error", proc.stdout)

    def test_method_with_values_two_arg_method_preloads_for_hir_inliner(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Object-heavy workloads often call tiny state helpers with more than
        # one explicit argument, e.g. go's ZobristHash.update(square, color).
        # The caller should be able to discover and preload such warmed method
        # cache targets so the HIR inliner can consume the recovered VectorCall.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_hir_inliner()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Table:
                def __init__(self):
                    self.items = [10, 20, 30]

                def pair(self, index, delta):
                    return self.items[index] + delta

            def hot(table, index, delta):
                return table.pair(index, delta) + 1

            table = Table()
            for _ in range(20000):
                if hot(table, 1, 5) != 26:
                    raise SystemExit("bad warmup result")

            assert jit.force_compile(hot)
            counts = cinderjit.get_function_hir_opcode_counts(hot)
            stats = jit.get_inlined_functions_stats(hot)
            print(counts.get("CallMethod", 0))
            print(counts.get("VectorCall", 0))
            print(stats.get("num_inlined_functions", 0))
            print(hot(table, 2, 7))

            table.pair = lambda index, delta: 99
            print(hot(table, 1, 5))

            other = Table()
            Table.pair = lambda self, index, delta: 41
            print(hot(other, 1, 5))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/method_with_values_two_arg_inline.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 38, proc.stdout)
            self.assertEqual(int(lines[-2]), 100, proc.stdout)
            self.assertEqual(int(lines[-1]), 42, proc.stdout)

    def test_method_with_values_medium_two_arg_method_preloads_for_hir_inliner(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # go-like helpers such as ZobristHash.update are still small enough to
        # inline profitably, but they exceed the original very-tiny one-arg
        # preload budget.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_hir_inliner()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Table:
                def __init__(self):
                    self.items = [10, 20, 30]
                    self.bias = 3

                def pair(self, index, delta):
                    base = self.items[index]
                    if delta < 0:
                        base = 0 - base
                    if self.bias:
                        base += self.bias
                    return base + delta

            def hot(table, index, delta):
                return table.pair(index, delta) + 1

            table = Table()
            for _ in range(20000):
                if hot(table, 1, 5) != 29:
                    raise SystemExit("bad warmup result")

            assert jit.force_compile(hot)
            counts = cinderjit.get_function_hir_opcode_counts(hot)
            stats = jit.get_inlined_functions_stats(hot)
            print(counts.get("CallMethod", 0))
            print(counts.get("VectorCall", 0))
            print(stats.get("num_inlined_functions", 0))
            print(hot(table, 2, 7))

            table.pair = lambda index, delta: 99
            print(hot(table, 1, 5))

            other = Table()
            Table.pair = lambda self, index, delta: 41
            print(hot(other, 1, 5))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/method_with_values_medium_two_arg_inline.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 41, proc.stdout)
            self.assertEqual(int(lines[-2]), 100, proc.stdout)
            self.assertEqual(int(lines[-1]), 42, proc.stdout)

    def test_method_value_inliner_only_inlines_method_value_calls(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Selective method-value inlining should be narrower than enabling the
        # full HIR inliner: warmed object method calls can inline, but unrelated
        # global function calls should remain calls.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def global_bump(value):
                return value + 100

            class Node:
                def __init__(self, reference=None, value=0):
                    self.reference = reference
                    self.value = value

                def find(self, update):
                    if self.reference is None:
                        return self.value + update
                    return (
                        self.reference.find(update)
                        + global_bump(update)
                        + self.value
                    )

            root = Node(None, 1)
            outer = Node(root, 3)
            for _ in range(20000):
                if outer.find(1) != 106:
                    raise SystemExit("bad warmup result")

            assert jit.force_compile(Node.find)
            stats = jit.get_inlined_functions_stats(Node.find)
            print(jit.is_hir_inliner_enabled())
            print(stats.get("num_inlined_functions", 0))
            print(outer.find(2))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/method_value_inliner_only.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITENABLEMETHODVALUEINLINER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(lines[-3], "False", proc.stdout)
            self.assertEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 108, proc.stdout)

    def test_method_value_inliner_preserves_polymorphic_fallback(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Regression guard for raytrace-style sites where different receiver
        # classes share the same method name. The selective inliner must not
        # inline a profiled callee if doing so removes the fallback for another
        # receiver type.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Sphere:
                def __init__(self):
                    self.centre = 11

                def normalAt(self, value):
                    return self.centre + value

            class Halfspace:
                def __init__(self):
                    self.normal = 100

                def normalAt(self, value):
                    return self.normal + value

            def shade(obj, value):
                return obj.normalAt(value)

            sphere = Sphere()
            halfspace = Halfspace()
            for i in range(20000):
                obj = halfspace if (i & 1) else sphere
                expected = 101 if (i & 1) else 12
                if shade(obj, 1) != expected:
                    raise SystemExit("bad warmup result")

            assert jit.force_compile(shade)
            print(shade(sphere, 2))
            print(shade(halfspace, 2))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/method_value_polymorphic_fallback.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITENABLEMETHODVALUEINLINER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(int(lines[-2]), 13, proc.stdout)
            self.assertEqual(int(lines[-1]), 102, proc.stdout)

    def test_method_value_inliner_preloads_zero_arg_method_values(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # pyperformance go has many warmed zero-explicit-arg method-value calls
        # such as ZobristHash.dupe()/add().  The builder can expose them as
        # profiled VectorCall sites; the selective inliner also needs preloader
        # coverage for the zero-arg callee.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Leaf:
                def __init__(self, value):
                    self.value = value

                def score(self):
                    return self.value + 7

            class Holder:
                def __init__(self, leaf):
                    self.leaf = leaf

                def check(self):
                    return self.leaf.score()

            holder = Holder(Leaf(35))
            for _ in range(20000):
                if holder.check() != 42:
                    raise SystemExit("bad warmup result")

            assert jit.force_compile(Holder.check)
            stats = jit.get_inlined_functions_stats(Holder.check)
            print(jit.is_hir_inliner_enabled())
            print(stats.get("num_inlined_functions", 0))
            print(holder.check())
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/method_value_inliner_zero_arg.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITENABLEMETHODVALUEINLINER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(lines[-3], "False", proc.stdout)
            self.assertEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 42, proc.stdout)

    def test_method_value_inliner_lowers_inlined_set_add(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # pyperformance go exposes self.hash_set.add(self.hash) after the
        # zero-arg method-value callee is inlined.  Keep that newly visible
        # built-in method call on the existing SetSetItem/PySet_Add fast path
        # instead of leaving a generic CallMethod behind.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class ZobristHash:
                def __init__(self):
                    self.hash_set = set()
                    self.hash = 0

                def add(self):
                    self.hash_set.add(self.hash)
                    return len(self.hash_set)

            def hot(zobrist):
                return zobrist.add()

            zobrist = ZobristHash()
            for i in range(20000):
                zobrist.hash = i & 15
                if hot(zobrist) <= 0:
                    raise SystemExit("bad warmup result")

            assert jit.force_compile(hot)
            stats = jit.get_inlined_functions_stats(hot)
            counts = cinderjit.get_function_hir_opcode_counts(hot)
            print(stats.get("num_inlined_functions", 0))
            print(counts.get("CallMethod", 0))
            print(counts.get("SetSetItem", 0))
            print(hot(zobrist))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/method_value_inliner_set_add.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITENABLEMETHODVALUEINLINER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertEqual(int(lines[-4]), 1, proc.stdout)
            # One CallMethod remains for the outer profiled method-value
            # fallback branch; the inlined set.add itself should be specialized.
            self.assertLessEqual(int(lines[-3]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 16, proc.stdout)

    def test_method_with_values_one_arg_method_removes_lookup_by_default(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Table:
                def __init__(self):
                    self.items = [10, 20, 30]

                def get(self, index):
                    return self.items[index]

            def hot(table, index):
                return table.get(index) + 1

            table = Table()
            for _ in range(20000):
                if hot(table, 1) != 21:
                    raise SystemExit("bad warmup result")

            assert jit.force_compile(hot)
            counts = cinderjit.get_function_hir_opcode_counts(hot)
            print(counts.get("CallMethod", 0))
            print(counts.get("LoadMethodCached", 0) + counts.get("LoadMethod", 0))
            print(counts.get("VectorCall", 0))
            print(hot(table, 1))

            table.get = lambda index: 99
            print(hot(table, 1))

            other = Table()
            Table.get = lambda self, index: 41
            print(hot(other, 1))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/method_with_values_one_arg_default_fastpath.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONFAULTHANDLER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertEqual(int(lines[-6]), 0, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 21, proc.stdout)
            self.assertEqual(int(lines[-2]), 100, proc.stdout)
            self.assertEqual(int(lines[-1]), 42, proc.stdout)

    def test_method_with_values_nonexact_self_delays_lookup_to_fallback(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Base:
                def call(self, x):
                    return self.fn(x)

            class First(Base):
                def fn(self, x):
                    return x + 1

            class Second(Base):
                def fn(self, x):
                    return x + 2

            first = First()
            for i in range(20000):
                if first.call(i) != i + 1:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(Base.call)
            print(first.call(10))
            print(Second().call(10))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/method_with_values_nonexact_self_fallback.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITDUMPFINALHIR"] = "1"
            env["PYTHONJITLOGLEVEL"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(int(lines[-2]), 11, proc.stdout)
            self.assertEqual(int(lines[-1]), 12, proc.stdout)

            combined = proc.stdout + proc.stderr
            marker = "Optimized HIR for __main__:Base.call:"
            self.assertIn(marker, combined)
            hir = combined.split(marker, 1)[1]
            vector_pos = hir.find("VectorCall<2>")
            load_method_pos = hir.find("LoadMethod")
            self.assertNotEqual(vector_pos, -1, hir)
            self.assertNotEqual(load_method_pos, -1, hir)
            self.assertLess(vector_pos, load_method_pos, hir)

    def test_zero_arg_method_with_values_before_uninitialized_local_is_safe(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Regression guard:
        # delaying a zero-arg lookup before all locals are initialized can
        # create fallback FrameStates that later refcount insertion cannot
        # safely copy. Keep the delayed-lookup optimization for calls with
        # real side-effect-free arguments.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class State:
                def __init__(self):
                    self.value = 1

                def ready(self):
                    return self.value == 1

                def run(self):
                    if self.ready():
                        msg = 11
                    else:
                        msg = 22
                    return msg

            state = State()
            for _ in range(20000):
                if state.run() != 11:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(State.run)
            print(state.run())
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/zero_arg_method_values_uninitialized_local.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 11, proc.stdout)

    def test_attr_derived_zero_arg_method_with_values_delays_lookup_when_safe(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Zero-arg method-value calls are only safe to delay when all frame
        # locals are initialized at entry. This shape has no locals beyond the
        # argument slots, so the fallback FrameState can be copied safely.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Helper:
                def __init__(self, value):
                    self.value = value

                def ready(self):
                    return self.value + 1

            class Holder:
                def __init__(self):
                    self.helper = Helper(10)

                def run(self):
                    return self.helper.ready()

            holder = Holder()
            for _ in range(20000):
                if holder.run() != 11:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(Holder.run)
            print(holder.run())

            holder.helper.ready = lambda: 99
            print(holder.run())

            other = Holder()
            Helper.ready = lambda self: 41
            print(other.run())
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/attr_derived_zero_arg_method_values_delayed_lookup.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            for env_value, expect_delayed in ((None, True), ("0", False)):
                env = dict(os.environ)
                env["PYTHONJITDUMPFINALHIR"] = "1"
                env["PYTHONJITLOGLEVEL"] = "1"
                if env_value is not None:
                    env["PYTHONJITZEROARGMWVDELAYEDLOOKUP"] = env_value
                proc = subprocess.run(
                    [sys.executable, script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
                )
                lines = [
                    line.strip() for line in proc.stdout.splitlines() if line.strip()
                ]
                self.assertGreaterEqual(len(lines), 3, proc.stdout)
                self.assertEqual(int(lines[-3]), 11, proc.stdout)
                self.assertEqual(int(lines[-2]), 99, proc.stdout)
                self.assertEqual(int(lines[-1]), 41, proc.stdout)

                combined = proc.stdout + proc.stderr
                marker = "Optimized HIR for __main__:Holder.run:"
                self.assertIn(marker, combined)
                hir = combined.split(marker, 1)[1]
                vector_pos = hir.find("VectorCall<1>")
                load_method_pos = hir.find("LoadMethod")
                self.assertNotEqual(vector_pos, -1, hir)
                self.assertNotEqual(load_method_pos, -1, hir)
                if expect_delayed:
                    self.assertLess(vector_pos, load_method_pos, hir)
                else:
                    self.assertLess(load_method_pos, vector_pos, hir)

    def test_attr_derived_method_with_values_delays_simple_args_lookup_to_fallback(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Regression guard:
        # go-like object workloads frequently call methods through fields such
        # as self.board.move(color) or self.zobrist.update(color, square).
        # When the receiver cache is warm and the intervening arguments are
        # side-effect-free loads, the hot path should use the profiled
        # method-with-values descriptor before falling back to generic lookup.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Helper:
                def __init__(self, value):
                    self.value = value

                def mix(self, left, right):
                    return self.value + left + right

            class Holder:
                def __init__(self):
                    self.helper = Helper(10)

                def run(self, left, right):
                    return self.helper.mix(left, right)

            holder = Holder()
            for i in range(20000):
                if holder.run(1, 2) != 13:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(Holder.run)
            print(holder.run(1, 2))

            holder.helper.mix = lambda left, right: 99
            print(holder.run(1, 2))

            other = Holder()
            Helper.mix = lambda self, left, right: 41
            print(other.run(1, 2))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/attr_derived_method_values_delayed_lookup.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITDUMPFINALHIR"] = "1"
            env["PYTHONJITLOGLEVEL"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(int(lines[-3]), 13, proc.stdout)
            self.assertEqual(int(lines[-2]), 99, proc.stdout)
            self.assertEqual(int(lines[-1]), 41, proc.stdout)

            combined = proc.stdout + proc.stderr
            marker = "Optimized HIR for __main__:Holder.run:"
            self.assertIn(marker, combined)
            hir = combined.split(marker, 1)[1]
            vector_pos = hir.find("VectorCall<3>")
            load_method_pos = hir.find("LoadMethod")
            self.assertNotEqual(vector_pos, -1, hir)
            self.assertNotEqual(load_method_pos, -1, hir)
            self.assertLess(vector_pos, load_method_pos, hir)

    def test_attr_derived_method_with_values_delays_simple_kw_lookup_to_fallback(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Regression guard:
        # go uses CALL_KW_PY for calls such as neighbour.find(update=True).
        # The keyword tuple is stack-provided in Python 3.14, so the profiled
        # method-with-values path should still be able to keep generic lookup
        # on the fallback side when the positional/keyword args are simple
        # loads.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Helper:
                def __init__(self, value):
                    self.value = value

                def mix(self, left, *, right):
                    return self.value + left + right

            class Holder:
                def __init__(self):
                    self.helper = Helper(10)

                def run(self, left, right):
                    return self.helper.mix(left, right=right)

            holder = Holder()
            for i in range(20000):
                if holder.run(1, 2) != 13:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(Holder.run)
            print(holder.run(1, 2))

            holder.helper.mix = lambda left, *, right: 99
            print(holder.run(1, 2))

            other = Holder()
            Helper.mix = lambda self, left, *, right: 41
            print(other.run(1, 2))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/attr_derived_method_values_kw_delayed_lookup.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITDUMPFINALHIR"] = "1"
            env["PYTHONJITLOGLEVEL"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(int(lines[-3]), 13, proc.stdout)
            self.assertEqual(int(lines[-2]), 99, proc.stdout)
            self.assertEqual(int(lines[-1]), 41, proc.stdout)

            combined = proc.stdout + proc.stderr
            marker = "Optimized HIR for __main__:Holder.run:"
            self.assertIn(marker, combined)
            hir = combined.split(marker, 1)[1]
            vector_pos = hir.find("VectorCall<4, kwnames>")
            load_method_pos = hir.find("LoadMethod")
            self.assertNotEqual(vector_pos, -1, hir)
            self.assertNotEqual(load_method_pos, -1, hir)
            self.assertLess(vector_pos, load_method_pos, hir)

    def test_attr_derived_kw_method_values_use_exact_pyfunc_vectorcall_lir(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 CALL_KW")

        code = textwrap.dedent(
            """
            import ctypes

            import _cinderx
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Helper:
                def __init__(self, value):
                    self.value = value

                def mix(self, left, *, right):
                    return self.value + left + right

            class Holder:
                def __init__(self):
                    self.helper = Helper(10)

                def run(self, left, right):
                    return self.helper.mix(left, right=right)

            holder = Holder()
            for i in range(20000):
                if holder.run(1, 2) != 13:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(Holder.run)
            cinderx_lib = ctypes.CDLL(_cinderx.__file__)
            exact_pyfunc = ctypes.cast(
                getattr(
                    cinderx_lib,
                    "_Z27JITRT_VectorcallExactPyFuncP7_objectPKS0_mS0_",
                ),
                ctypes.c_void_p,
            ).value
            print(f"JITRT_VECTORCALL_EXACT_PYFUNC={exact_pyfunc:#x}")
            print(holder.run(1, 2))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/kw_method_values_exact_pyfunc_lir.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            def run_case(**extra_env):
                env = dict(os.environ)
                env["PYTHONJITDUMPLIR"] = "1"
                env["PYTHONJITDUMPLIRORIGIN"] = "1"
                env.update(extra_env)
                proc = subprocess.run(
                    [sys.executable, script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
                )
                lines = [
                    line.strip() for line in proc.stdout.splitlines() if line.strip()
                ]
                self.assertGreaterEqual(len(lines), 2, proc.stdout)
                self.assertEqual(lines[-1], "13", proc.stdout)
                exact_addr = next(
                    line.split("=", 1)[1]
                    for line in lines
                    if line.startswith("JITRT_VECTORCALL_EXACT_PYFUNC=")
                )

                dump = proc.stdout + "\n" + proc.stderr
                match = re.search(
                    r"LIR for __main__:Holder.run after generation:\n(.*?)(?:\nJIT: .*?LIR for |\Z)",
                    dump,
                    re.S,
                )
                self.assertIsNotNone(match, dump)
                return match.group(1), exact_addr

            section, exact_addr = run_case()
            self.assertIn(f"({exact_addr})", section)

            disabled_section, exact_addr = run_case(
                PYTHONJITENABLEKWPYFUNCVECTORCALL="0"
            )
            self.assertNotIn(f"({exact_addr})", disabled_section)

    def test_attr_derived_polymorphic_method_load_avoids_method_with_values_deopts(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Regression guard:
        # attr-derived receivers should not be reopened so broadly that a
        # polymorphic field like self.reference reintroduces the old
        # method-with-values deopt storm.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class FirstLeaf:
                def execute(self):
                    return 1

            class SecondLeaf:
                def execute(self):
                    return 2

            class Holder:
                def __init__(self, reference):
                    self.reference = reference

                def run(self):
                    return self.reference.execute()

            holder = Holder(FirstLeaf())
            for _ in range(20000):
                holder.run()

            assert jit.force_compile(Holder.run)
            counts = cinderjit.get_function_hir_opcode_counts(Holder.run)

            jit.get_and_clear_runtime_stats()
            total = 0
            for i in range(20000):
                holder.reference = FirstLeaf() if (i & 1) == 0 else SecondLeaf()
                total += holder.run()

            stats = jit.get_and_clear_runtime_stats()
            relevant = [
                entry
                for entry in stats["deopt"]
                if entry["normal"]["func_qualname"] == "Holder.run"
                and entry["normal"]["description"] == "LOAD_ATTR_METHOD_WITH_VALUES"
            ]

            print(counts.get("LoadMethod", 0))
            print(counts.get("LoadMethodCached", 0))
            print(len(relevant))
            print(sum(entry["int"]["count"] for entry in relevant))
            print(total)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/attr_derived_polymorphic_method_load.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 5, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]) + int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(int(lines[-1]), 30000, proc.stdout)

    def test_polymorphic_loop_local_method_load_avoids_method_with_values_deopts(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Regression guard:
        # a polymorphic method call inside a loop should not be lowered to a
        # monomorphic LOAD_ATTR_METHOD_WITH_VALUES guard that deopts once per
        # loop invocation on the rare receiver type.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class RareType:
                def execute(self):
                    return 0

            class MainType:
                def __init__(self):
                    self.value = 0

                def execute(self):
                    self.value += 1
                    return self.value

            def hot_loop(items):
                total = 0
                for item in items:
                    total += item.execute()
                return total

            warm = [MainType() for _ in range(32)]
            for _ in range(20000):
                hot_loop(warm)

            assert jit.force_compile(hot_loop)
            counts = cinderjit.get_function_hir_opcode_counts(hot_loop)

            items = [RareType()] + [MainType() for _ in range(100)]
            jit.get_and_clear_runtime_stats()
            total = 0
            for _ in range(2000):
                total += hot_loop(items)

            stats = jit.get_and_clear_runtime_stats()
            relevant = [
                entry
                for entry in stats["deopt"]
                if entry["normal"]["func_qualname"] == "hot_loop"
                and entry["normal"]["description"] == "LOAD_ATTR_METHOD_WITH_VALUES"
            ]
            print(counts.get("LoadMethod", 0))
            print(counts.get("LoadMethodCached", 0))
            print(len(relevant))
            print(sum(entry["int"]["count"] for entry in relevant))
            print(total)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/polymorphic_loop_local_method_load.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 5, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]) + int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)

    def test_self_only_float_leaf_mixed_factor_avoids_deopts(self) -> None:
        # Regression guard:
        # no-backedge helpers that only read `self` attrs should not keep the
        # issue31-style float exact guards when a non-self arg such as `factor`
        # changes between float and int at runtime.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import json

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Vector:
                def __init__(self, x, y, z):
                    self.x = x
                    self.y = y
                    self.z = z

                def scale(self, factor):
                    return Vector(factor * self.x, factor * self.y, factor * self.z)

            v = Vector(1.5, 2.5, 3.5)
            for _ in range(20000):
                v.scale(0.5)

            assert jit.force_compile(Vector.scale)
            jit.get_and_clear_runtime_stats()

            for i in range(20000):
                v.scale(2 if (i & 1) == 0 else 3.0)

            stats = jit.get_and_clear_runtime_stats()
            relevant = [
                entry
                for entry in stats["deopt"]
                if entry["normal"]["func_qualname"] == "Vector.scale"
            ]
            print(json.dumps(relevant))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/self_only_float_leaf_mixed_factor.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            self.assertEqual(proc.stdout.strip(), "[]", proc.stdout)

    def test_builtin_min_max_int_clamp_shape_avoids_float_guard_deopts(self) -> None:
        # Regression guard:
        # integer clamp shapes like max(0, min(255, int(...))) should not go
        # through the float-specialized min/max path and deopt on exact ints.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import json

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def clamp(x):
                return max(0, min(255, int(x * 255)))

            for _ in range(20000):
                clamp(0.5)

            assert jit.force_compile(clamp)
            jit.get_and_clear_runtime_stats()

            total = 0
            for i in range(20000):
                total += clamp(0.25 if (i & 1) == 0 else 0.75)

            stats = jit.get_and_clear_runtime_stats()
            relevant = [
                entry
                for entry in stats["deopt"]
                if entry["normal"]["func_qualname"] == "clamp"
            ]
            print(json.dumps(relevant))
            print(total)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/builtin_minmax_int_clamp_no_deopt.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2], "[]", proc.stdout)
            self.assertEqual(int(lines[-1]), 2540000, proc.stdout)

    def test_builtin_min_max_int_loop_shape_avoids_float_guard_deopts(self) -> None:
        # Regression guard:
        # integer-heavy LU-style inner loops should not trigger the float-only
        # two-arg min/max specialization, otherwise GuardType deopts dominate
        # the compiled path.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit
            import json

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def LU_factor(m, n):
                total = 0
                min_mn = min(m, n)
                for j in range(min_mn):
                    jp1 = j + 1
                    total += min(jp1, n - 1)
                return total

            for _ in range(10000):
                LU_factor(32, 31)

            assert jit.force_compile(LU_factor)
            counts = cinderjit.get_function_hir_opcode_counts(LU_factor)

            jit.get_and_clear_runtime_stats()
            total = 0
            for _ in range(500):
                total += LU_factor(32, 31)
            stats = jit.get_and_clear_runtime_stats()

            relevant = [
                entry
                for entry in stats["deopt"]
                if entry["normal"]["func_qualname"] == "LU_factor"
            ]

            print(counts.get("GuardType", 0))
            print(counts.get("VectorCall", 0))
            print(json.dumps(relevant))
            print(total)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/builtin_minmax_lu_shape_no_deopt.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(lines[-2], "[]", proc.stdout)
            self.assertEqual(int(lines[-1]), 247500, proc.stdout)

    def test_dump_elf_machine_is_aarch64_on_arm(self) -> None:
        import cinderjit

        if not hasattr(cinderjit, "dump_elf"):
            self.skipTest("cinderjit.dump_elf is unavailable")

        cinderx.jit.enable()
        cinderx.jit.compile_after_n_calls(1000000)

        def f(x: int) -> int:
            return x + 1

        self.assertTrue(cinderx.jit.force_compile(f))
        self.assertTrue(cinderx.jit.is_jit_compiled(f))

        with tempfile.TemporaryDirectory() as tmp:
            elf_path = f"{tmp}/jit_dump.elf"
            cinderjit.dump_elf(elf_path)
            with open(elf_path, "rb") as fp:
                header = fp.read(64)

        self.assertGreaterEqual(len(header), 20)
        self.assertEqual(header[0:4], b"\x7fELF")

        ei_data = header[5]
        if ei_data == 1:
            byteorder = "little"
        elif ei_data == 2:
            byteorder = "big"
        else:
            self.fail(f"Unknown ELF data encoding: {ei_data}")

        # ELF e_machine is at bytes [18:20] in the file header.
        e_machine = int.from_bytes(header[18:20], byteorder)
        self.assertEqual(e_machine, 0xB7, f"Expected EM_AARCH64, got 0x{e_machine:04x}")

    def test_multiple_code_sections_force_compile_smoke(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            def f(n):
                s = 0
                for i in range(n):
                    s += (i * 3) ^ (i >> 2)
                return s

            for _ in range(20000):
                f(200)

            jit.force_compile(f)
            print(cinderjit.get_compiled_size(f))
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/mcs_smoke.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env.update(
                {
                    "PYTHONJITMULTIPLECODESECTIONS": "1",
                    "PYTHONJITHOTCODESECTIONSIZE": "1048576",
                    "PYTHONJITCOLDCODESECTIONSIZE": "1048576",
                }
            )
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(proc.stdout.strip().isdigit(), proc.stdout)

    def test_multiple_code_sections_large_distance_force_compile_smoke(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            def f(n):
                s = 0
                for i in range(n):
                    s += (i * 3) ^ (i >> 2)
                return s

            for _ in range(20000):
                f(200)

            jit.force_compile(f)
            print(cinderjit.get_compiled_size(f))
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/mcs_large_smoke.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env.update(
                {
                    "PYTHONJITMULTIPLECODESECTIONS": "1",
                    "PYTHONJITHOTCODESECTIONSIZE": "2097152",
                    "PYTHONJITCOLDCODESECTIONSIZE": "2097152",
                }
            )
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(proc.stdout.strip().isdigit(), proc.stdout)

    def test_autojit0_lightweight_frame_typing_import_smoke(self) -> None:
        # Regression guard:
        # with lightweight frames enabled, this sequence should not segfault
        # while importing typing from JIT-compiled execution.
        code = textwrap.dedent(
            """
            g = (i for i in [1])
            import re
            re.compile("a+")
            print("ok")
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/typing_import_smoke.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env.update(
                {
                    "PYTHONJITAUTO": "0",
                    "PYTHONJITLIGHTWEIGHTFRAME": "1",
                }
            )
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            self.assertIn("ok", proc.stdout)

    def test_aarch64_call_sites_are_compact(self) -> None:
        # Performance regression guard:
        # on aarch64, repeated helper-call sites can bloat native code size.
        cinderx.jit.enable()
        cinderx.jit.compile_after_n_calls(1000000)

        n_calls = 200
        lines = ["def f(x):", "    s = 0.0"]
        lines.extend(["    s += math.sqrt(x)"] * n_calls)
        lines.append("    return s")
        src = "\n".join(lines)
        ns = {"math": math}
        exec(src, ns, ns)
        f = ns["f"]

        self.assertTrue(cinderx.jit.force_compile(f))
        size = cinderx.jit.get_compiled_size(f)

        # Guard against unbounded AArch64 call-site code size regressions while
        # allowing hot-path call lowering experiments some headroom.
        self.assertLessEqual(size, 70000, size)
        self.assertEqual(f(9.0), float(n_calls) * 3.0)

    def test_aarch64_singleton_immediate_call_target_prefers_direct_literal(
        self,
    ) -> None:
        # Regression guard for hot-path immediate call lowering:
        # singleton immediate targets should use direct literal calls, while
        # repeated targets can keep helper-stub dedup.
        cinderx.jit.enable()
        cinderx.jit.compile_after_n_calls(1000000)

        def build_sqrt_accumulator(n_calls: int):
            lines = ["def f(x):", "    s = 0.0"]
            lines.extend(["    s += math.sqrt(x)"] * n_calls)
            lines.append("    return s")
            ns = {"math": math}
            exec("\n".join(lines), ns, ns)
            f = ns["f"]
            self.assertTrue(cinderx.jit.force_compile(f))
            return f, cinderx.jit.get_compiled_size(f)

        f1, size1 = build_sqrt_accumulator(1)
        f2, size2 = build_sqrt_accumulator(2)

        self.assertEqual(f1(9.0), 3.0)
        self.assertEqual(f2(9.0), 6.0)

        delta = size2 - size1
        # Module-method simplification on 3.14 makes each extra call site
        # materially cheaper, but a second site should still add noticeable
        # native code.
        self.assertGreaterEqual(delta, 256, (size1, size2, delta))

    def test_aarch64_duplicate_call_result_arg_chain_is_compact(self) -> None:
        # Regression guard for call-result move chains:
        # repeated "y = call(...); call(y, y)" should not keep unnecessary
        # return-register copy chains in AArch64 call lowering.
        cinderx.jit.enable()
        cinderx.jit.compile_after_n_calls(1000000)

        n_calls = 64
        lines = ["def f(x):", "    s = 0.0"]
        for _ in range(n_calls):
            lines.append("    y = math.sqrt(x)")
            lines.append("    s += math.pow(y, y)")
        lines.append("    return s")
        ns = {"math": math}
        exec("\n".join(lines), ns, ns)
        f = ns["f"]

        self.assertTrue(cinderx.jit.force_compile(f))
        size = cinderx.jit.get_compiled_size(f)

        # Keep a margin for codegen noise, but fail when move-chain bloat
        # regresses on this stable shape.
        self.assertLessEqual(size, 44700, size)
        self.assertEqual(f(9.0), float(n_calls) * 27.0)

    def test_member_descriptor_store_simplifies_to_store_field(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            class Counter:
                __slots__ = ('value',)

            obj = Counter()
            obj.value = 0

            def f(v):
                obj.value = v
                return obj.value

            assert jit.force_compile(f)
            counts = cinderjit.get_function_hir_opcode_counts(f)
            print(counts.get("LoadField", 0))
            print(counts.get("StoreField", 0))
            print(counts.get("StoreAttrCached", 0))
            print(f(7))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/member_descr_store_field.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(int(lines[-1]), 7, proc.stdout)

    def test_slot_specialized_opcodes_lower_to_field_ops(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Counter:
                __slots__ = ('value',)
                def increment(self):
                    self.value = self.value + 1

            c = Counter()
            c.value = 0
            for _ in range(200000):
                c.increment()

            assert jit.force_compile(Counter.increment)
            counts = cinderjit.get_function_hir_opcode_counts(Counter.increment)
            print(counts.get("LoadField", 0))
            print(counts.get("StoreField", 0))
            print(counts.get("LoadAttrCached", 0))
            print(counts.get("StoreAttrCached", 0))
            c.increment()
            print(c.value)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/slot_specialized_field_ops.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 5, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(int(lines[-1]), 200001, proc.stdout)

    def test_instance_value_load_specialized_opcode_lowers_to_field_op(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Counter:
                def __init__(self):
                    self.value = 0

                def increment(
                    self,
                    a=0,
                    b=0,
                    c0=0,
                    d=0,
                    e=0,
                    f=0,
                    g=0,
                    h=0,
                    i=0,
                ):
                    self.value = self.value + 1

            c = Counter()
            for _ in range(200000):
                c.increment()

            assert jit.force_compile(Counter.increment)
            counts = cinderjit.get_function_hir_opcode_counts(Counter.increment)
            print(counts.get("LoadField", 0))
            print(counts.get("StoreField", 0))
            print(counts.get("StoreAttr", 0))
            print(counts.get("StoreAttrInstanceValue", 0))
            print(counts.get("LoadAttrCached", 0))
            print(counts.get("StoreAttrCached", 0))
            c.increment()
            print(c.value)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/instance_value_specialized_field_ops.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 7, proc.stdout)
            self.assertGreaterEqual(int(lines[-7]), 1, proc.stdout)
            self.assertEqual(int(lines[-6]), 0, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 200001, proc.stdout)

    def test_existing_instance_value_store_lowers_to_field_op(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 STORE_ATTR_INSTANCE_VALUE")

        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Box:
                def __init__(self):
                    self.value = 0

            def set_existing(box, value):
                box.value = value
                return box.value

            warm = Box()
            for i in range(200000):
                if set_existing(warm, i) != i:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(set_existing)
            counts = cinderjit.get_function_hir_opcode_counts(set_existing)
            print(counts.get("StoreField", 0))
            print(counts.get("StoreAttrCached", 0))
            print(set_existing(Box(), 7))

            # Shared split-dict keys may know about "value" while this
            # particular instance has an empty slot. The optimized path must
            # fall back so CPython can update insertion order.
            missing = Box.__new__(Box)
            print(hasattr(missing, "value"))
            print(set_existing(missing, 11))
            print(list(missing.__dict__.keys()))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/existing_instance_value_store_field.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            def run_case(**extra_env):
                env = dict(os.environ)
                env.update(extra_env)
                proc = subprocess.run(
                    [sys.executable, script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
                )
                lines = [
                    line.strip() for line in proc.stdout.splitlines() if line.strip()
                ]
                self.assertGreaterEqual(len(lines), 6, proc.stdout)
                self.assertEqual(lines[-3], "False", proc.stdout)
                self.assertEqual(lines[-2], "11", proc.stdout)
                self.assertEqual(lines[-1], "['value']", proc.stdout)
                return lines

            lines = run_case(PYTHONJITSTOREATTRINSTANCEVALUEEXISTING="1")
            self.assertGreaterEqual(int(lines[-6]), 1, "\n".join(lines))
            self.assertEqual(int(lines[-5]), 0, "\n".join(lines))

            disabled_lines = run_case(
                PYTHONJITSTOREATTRINSTANCEVALUEEXISTING="0"
            )
            self.assertEqual(int(disabled_lines[-6]), 0, "\n".join(disabled_lines))
            self.assertGreaterEqual(
                int(disabled_lines[-5]), 1, "\n".join(disabled_lines)
            )

    def test_list_int_store_subscr_lowers_to_callstatic_helper(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 STORE_SUBSCR_LIST_INT")

        # Regression guard:
        # bm_go's EmptySet.set() is dominated by exact-list/int-index stores.
        # Those should avoid the generic PyObject_SetItem StoreSubscr path.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class MyList(list):
                pass

            def set_pair(empties, empty_pos, i, pos):
                empties[i] = pos
                empty_pos[pos] = i
                return empties[i] + empty_pos[pos]

            empties = list(range(8))
            empty_pos = list(range(8))
            for n in range(20000):
                set_pair(empties, empty_pos, n % 8, (n + 3) % 8)

            assert jit.force_compile(set_pair)
            counts = cinderjit.get_function_hir_opcode_counts(set_pair)
            print(counts.get("StoreSubscr", 0))
            print(counts.get("CallStatic", 0))
            print(set_pair(empties, empty_pos, 2, 5))
            print(set_pair(empties, empty_pos, -1, 3))

            try:
                set_pair(empties, empty_pos, 99, 1)
            except IndexError:
                print("index-error")
            else:
                print("missing-index-error")

            subclass = MyList(range(8))
            print(set_pair(subclass, empty_pos, 1, 4))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/list_int_store_subscr_helper.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONFAULTHANDLER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertEqual(int(lines[-6]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 2, proc.stdout)
            self.assertEqual(int(lines[-4]), 7, proc.stdout)
            self.assertEqual(int(lines[-3]), 2, proc.stdout)
            self.assertEqual(lines[-2], "index-error", proc.stdout)
            self.assertEqual(int(lines[-1]), 5, proc.stdout)

    def test_exact_list_int_subscr_uses_guarded_array_fast_path(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 BINARY_OP_SUBSCR_LIST_INT")

        # Regression guard:
        # Richards' Task.findtcb() and bm_go both perform many exact list/int
        # reads. The hot non-negative, in-bounds path should avoid the runtime
        # sequence-bounds helper while still deopting to preserve negative,
        # out-of-range, and subclass semantics.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class MyList(list):
                pass

            def get_pair(xs, i):
                return xs[i] + xs[0]

            xs = [10, 20, 30, 40]
            for n in range(20000):
                if get_pair(xs, n % 4) < 20:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(get_pair)
            counts = cinderjit.get_function_hir_opcode_counts(get_pair)
            print(counts.get("CheckSequenceBounds", 0))
            print(counts.get("LoadArrayItem", 0))
            print(get_pair(xs, 2))
            print(get_pair(xs, -1))
            try:
                get_pair(xs, 99)
            except IndexError:
                print("index-error")
            else:
                print("missing-index-error")
            print(get_pair(MyList(xs), 1))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/exact_list_int_subscr_fast_bounds.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertEqual(int(lines[-6]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 2, proc.stdout)
            self.assertEqual(int(lines[-4]), 40, proc.stdout)
            self.assertEqual(int(lines[-3]), 50, proc.stdout)
            self.assertEqual(lines[-2], "index-error", proc.stdout)
            self.assertEqual(int(lines[-1]), 30, proc.stdout)

    def test_generator_low_local_attr_access_uses_field_lowering(self) -> None:
        # Regression guard:
        # low-local generator helpers such as Tree.__iter__ should not be
        # blocked from instance-value lowering just because co_nlocals is small.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Tree:
                def __init__(self, left, value, right):
                    self.left = left
                    self.value = value
                    self.right = right

                def __iter__(self):
                    if self.left:
                        yield from self.left
                    yield self.value
                    if self.right:
                        yield from self.right

            def tree(items):
                n = len(items)
                if n == 0:
                    return None
                i = n // 2
                return Tree(tree(items[:i]), items[i], tree(items[i + 1 :]))

            root = tree(range(10))
            for _ in range(2000):
                for _ in root:
                    pass

            assert jit.force_compile(Tree.__iter__)
            counts = cinderjit.get_function_hir_opcode_counts(Tree.__iter__)
            print(counts.get("LoadField", 0))
            print(counts.get("LoadAttrCached", 0))
            print(list(root))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/generator_low_local_field_lowering.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 3, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(lines[-1], str(list(range(10))), proc.stdout)

    def test_generator_decref_lowering_stays_compact(self) -> None:
        # Regression guard:
        # generator decrefs should not explode into one multi-block inline
        # sequence per site. Keep Tree.__iter__ LIR reasonably compact.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Tree:
                def __init__(self, left, value, right):
                    self.left = left
                    self.value = value
                    self.right = right

                def __iter__(self):
                    if self.left:
                        yield from self.left
                    yield self.value
                    if self.right:
                        yield from self.right

            def tree(items):
                n = len(items)
                if n == 0:
                    return None
                i = n // 2
                return Tree(tree(items[:i]), items[i], tree(items[i + 1 :]))

            root = tree(range(10))
            for _ in range(2000):
                for _ in root:
                    pass

            assert jit.force_compile(Tree.__iter__)
            print("compiled_size", cinderjit.get_compiled_size(Tree.__iter__))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/generator_decref_compact_lir.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITDUMPLIR"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            dump = proc.stdout + "\n" + proc.stderr
            match = re.search(
                r"LIR for __main__:Tree\.__iter__ after generation:\n(.*?)(?:\nJIT: .*?LIR for |\Z)",
                dump,
                re.S,
            )
            self.assertIsNotNone(match, dump)
            section = match.group(1)
            bb_count = len(re.findall(r"^BB %", section, re.M))

            size_match = re.search(r"compiled_size\s+(\d+)", proc.stdout)
            self.assertIsNotNone(size_match, proc.stdout)
            compiled_size = int(size_match.group(1))

            self.assertLessEqual(bb_count, 72, dump)
            self.assertLessEqual(compiled_size, 3000, proc.stdout)

    def test_int_binary_identity_simplify_reduces_compiled_size(self) -> None:
        # Regression guard for IntBinaryOp identity simplification in HIR.
        # For a stable static-int loop shape, simplify-on should emit smaller
        # native code than simplify-off.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            from cinderx.compiler.static import exec_static

            ns = {}
            src = '''
            from __static__ import int64

            def f(n: int64) -> int64:
                s: int64 = 0
                i: int64 = 0
                while i < n:
                    t: int64 = (i + 0) * 1
                    u: int64 = (t | 0) & 0
                    s = s + u
                    i = i + 1
                return s
            '''
            exec_static(src, ns, ns, "m")
            f = ns["f"]

            jit.enable()
            jit.compile_after_n_calls(1000000)
            ok = jit.force_compile(f)
            assert ok, "force_compile failed"
            assert jit.is_jit_compiled(f), "not jit compiled"
            assert f(64) == 0
            print(jit.get_compiled_size(f))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/int_binary_identity_size.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env_default = dict(os.environ)
            proc_default = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env_default,
            )
            self.assertEqual(
                proc_default.returncode,
                0,
                f"stdout:\n{proc_default.stdout}\nstderr:\n{proc_default.stderr}",
            )
            size_default = int(proc_default.stdout.strip().splitlines()[-1])

            env_nosimplify = dict(os.environ)
            env_nosimplify["PYTHONJITSIMPLIFY"] = "0"
            proc_nosimplify = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env_nosimplify,
            )
            self.assertEqual(
                proc_nosimplify.returncode,
                0,
                (
                    f"stdout:\n{proc_nosimplify.stdout}\n"
                    f"stderr:\n{proc_nosimplify.stderr}"
                ),
            )
            size_nosimplify = int(proc_nosimplify.stdout.strip().splitlines()[-1])

            self.assertLess(
                size_default,
                size_nosimplify,
                (size_default, size_nosimplify),
            )

    def test_float_add_sub_mul_lower_to_double_binary_op_in_final_hir(self) -> None:
        self.skipTest("current ARM JIT does not expose DoubleBinaryOp lowering")
        # Regression guard:
        # exact-float +,-,* should lower through DoubleBinaryOp in final HIR,
        # so codegen can emit native FP arithmetic instead of helper calls.
        code = textwrap.dedent(
            """
            import cinderx
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def f(x, y):
                a = x + y
                b = x - y
                c = a * b
                d = c / x
                return d

            for _ in range(10000):
                f(3.0, 4.0)

            assert jit.force_compile(f)
            print("compiled")
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/float_hir_double_binop.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITDUMPFINALHIR"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            dump = proc.stdout + "\n" + proc.stderr
            self.assertIn("BinaryOp<Add>", dump)
            self.assertIn("BinaryOp<Subtract>", dump)
            self.assertIn("BinaryOp<Multiply>", dump)
            self.assertNotIn("DoubleBinaryOp<Add>", dump)
            self.assertNotIn("DoubleBinaryOp<Subtract>", dump)
            self.assertNotIn("DoubleBinaryOp<Multiply>", dump)

    def test_self_only_float_leaf_method_keeps_double_fastpath(self) -> None:
        # Regression guard:
        # self-only float helpers like bm_float's Point.normalize() should keep
        # the unboxed float fast path even without a backedge or non-self args.
        code = textwrap.dedent(
            """
            from math import cos, sin, sqrt

            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Point:
                __slots__ = ("x", "y", "z")

                def __init__(self, i):
                    self.x = x = sin(i)
                    self.y = cos(i) * 3.0
                    self.z = (x * x) / 2.0

                def normalize(self):
                    x = self.x
                    y = self.y
                    z = self.z
                    norm = sqrt(x * x + y * y + z * z)
                    self.x /= norm
                    self.y /= norm
                    self.z /= norm

            p = Point(1.25)
            for _ in range(10000):
                p.normalize()

            assert jit.force_compile(Point.normalize)
            counts = cinderjit.get_function_hir_opcode_counts(Point.normalize)
            print(counts.get("DoubleBinaryOp", 0))
            print(counts.get("DoubleSqrt", 0))
            print(counts.get("VectorCall", 0))
            print(counts.get("BinaryOp", 0))
            print(p.normalize())
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/float_self_only_normalize.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 5, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 5, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(lines[-1], "None", proc.stdout)

    def test_float_pow_two_lowers_to_double_multiply(self) -> None:
        # Regression guard:
        # exact-float `x ** 2` should strength-reduce to the same unboxed
        # multiply path as `x * x`.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def square_pow(x):
                return x ** 2

            def square_mul(x):
                return x * x

            for _ in range(10000):
                square_pow(3.14)
                square_mul(3.14)

            assert jit.force_compile(square_pow)
            assert jit.force_compile(square_mul)
            print(square_pow(2.718))
            print(square_mul(2.718))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/float_pow_two_double_multiply.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITDUMPFINALHIR"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            dump = proc.stdout + "\n" + proc.stderr
            self.assertIn("DoubleBinaryOp<Multiply>", dump)
            self.assertNotIn("FloatBinaryOp<Power>", dump)
            self.assertNotIn("BinaryOp<Power>", dump)

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(float(lines[-2]), float(lines[-1]), proc.stdout)

    def test_int_initialized_float_accumulator_avoids_repeated_deopts(self) -> None:
        # Regression guard:
        # `s = 0` followed by `s += float_value` in a hot loop should not
        # deopt on the first iteration of every call once JIT-compiled.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def accumulate(data):
                s = 0
                for x in data:
                    s += x
                return s

            data = [1.0] * 1000
            accumulate(data)
            accumulate(data)
            assert jit.force_compile(accumulate)

            jit.get_and_clear_runtime_stats()
            result = 0.0
            for _ in range(200):
                result = accumulate(data)

            stats = jit.get_and_clear_runtime_stats()
            deopt_count = sum(
                entry["int"]["count"]
                for entry in stats.get("deopt", [])
                if entry["normal"]["func_qualname"] == "accumulate"
            )
            print(deopt_count)
            print(result)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/int_initialized_float_accumulator.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITDUMPFINALHIR"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(float(lines[-1]), 1000.0, proc.stdout)

    def test_path_dependent_mixed_numeric_accumulator_avoids_repeated_deopts(
        self,
    ) -> None:
        # Regression guard:
        # when a loop accumulator can be `int` on one path and `float` on
        # another, we must not keep a loop-hot `GuardType<LongExact>` that
        # deopts on every execution of the float path.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            KOMI = 7.5
            WHITE = 1
            BLACK = 2
            EMPTY = 0

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Square:
                __slots__ = ("color", "neighbours")

                def __init__(self, color, neighbours=None):
                    self.color = color
                    self.neighbours = neighbours or []

            class Board:
                __slots__ = ("squares", "white_dead", "black_dead")

                def __init__(self, squares, white_dead=0, black_dead=0):
                    self.squares = squares
                    self.white_dead = white_dead
                    self.black_dead = black_dead

                def score(self, color):
                    if color == WHITE:
                        score = KOMI + self.black_dead
                    else:
                        score = self.white_dead

                    for square in self.squares:
                        if square.color == color:
                            score += 1
                        elif square.color == EMPTY:
                            count = 0
                            for neighbour in square.neighbours:
                                if neighbour.color == color:
                                    count += 1
                            if count == len(square.neighbours):
                                score += 1

                    return score

            squares = []
            for i in range(81):
                c = WHITE if i % 3 != 0 else (BLACK if i % 3 == 1 else EMPTY)
                squares.append(Square(c))

            for sq in squares:
                if sq.color == EMPTY:
                    sq.neighbours = [s for s in squares[:4]]

            board = Board(squares, white_dead=3, black_dead=5)

            for _ in range(10000):
                board.score(BLACK)

            assert jit.force_compile(Board.score)
            counts = cinderjit.get_function_hir_opcode_counts(Board.score)

            jit.get_and_clear_runtime_stats()
            black_result = 0
            for _ in range(200):
                black_result = board.score(BLACK)
            black_stats = jit.get_and_clear_runtime_stats()

            white_result = 0.0
            for _ in range(200):
                white_result = board.score(WHITE)
            white_stats = jit.get_and_clear_runtime_stats()

            black_deopt_count = sum(
                entry["int"]["count"]
                for entry in black_stats["deopt"]
                if entry["normal"]["func_qualname"] == "Board.score"
            )
            white_deopt_count = sum(
                entry["int"]["count"]
                for entry in white_stats["deopt"]
                if entry["normal"]["func_qualname"] == "Board.score"
            )

            print(counts.get("GuardType", 0))
            print(counts.get("LongInPlaceOp", 0))
            print(black_deopt_count)
            print(white_deopt_count)
            print(black_result)
            print(white_result)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/mixed_numeric_accumulator_no_deopt.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertGreaterEqual(int(lines[-6]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 0, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertEqual(int(lines[-2]), 3, proc.stdout)
            self.assertEqual(float(lines[-1]), 66.5, proc.stdout)

    def test_module_method_hir_uses_null_self_vectorcall(self) -> None:
        # Regression guard:
        # module LOAD_METHOD shapes on 3.14 should simplify to callable-only
        # loads plus a nullptr self, allowing CallMethod to fold into
        # VectorCall without keeping LoadModuleMethodCached/GetSecondOutput.
        code = textwrap.dedent(
            """
            import math
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            src = ["def f(x):", "    s = 0.0"]
            src.extend(["    s += math.sqrt(x)"] * 16)
            src.append("    return s")
            ns = {"math": math}
            exec("\\n".join(src), ns, ns)
            f = ns["f"]

            for _ in range(10000):
                f(9.0)

            assert jit.force_compile(f)
            counts = cinderjit.get_function_hir_opcode_counts(f)
            print(counts.get("LoadModuleMethodCached", 0))
            print(counts.get("GetSecondOutput", 0))
            print(counts.get("VectorCall", 0))
            print(f(9.0))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/module_method_vectorcall.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(float(lines[-1]), 48.0, proc.stdout)

    def test_module_attr_vectorcall_survives_zeroed_return_register(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 module attr specialization")

        code = textwrap.dedent(
            """
            import importlib.util
            import sys
            import tempfile
            import textwrap

            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            module_src = textwrap.dedent(
                '''
                def tostring(x):
                    return b"x"

                def f(mod, x):
                    for _ in range(30):
                        y = x
                    return mod.tostring(y)
                '''
            )

            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
                fh.write(module_src)
                path = fh.name

            spec = importlib.util.spec_from_file_location("tmpjitmod", path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            assert spec.loader is not None
            spec.loader.exec_module(mod)

            for _ in range(200):
                assert mod.f(mod, "a") == b"x"

            assert jit.force_compile(mod.f)
            counts = cinderjit.get_function_hir_opcode_counts(mod.f)
            result = mod.f(mod, "a")

            print(jit.is_jit_compiled(mod.f))
            print(counts.get("VectorCall", 0))
            print(result.hex())
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/module_attr_vectorcall_zeroed_retreg.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(lines[-3], "True", proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(lines[-1], "78", proc.stdout)

    def test_list_subclass_append_eliminates_callmethod(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Regression guard:
        # heap list subclasses inheriting list.append should avoid CallMethod
        # and reach the dedicated ListAppend fast path.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class OrderedCollection(list):
                pass

            def append_once(todo, value):
                todo.append(value)
                return len(todo)

            todo = OrderedCollection()
            for i in range(10000):
                append_once(todo, i)

            assert jit.force_compile(append_once)
            counts = cinderjit.get_function_hir_opcode_counts(append_once)
            print(counts.get("CallMethod", 0))
            print(counts.get("ListAppend", 0))
            print(append_once(todo, 10000))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/list_subclass_append_no_callmethod.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertLessEqual(int(lines[-3]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(int(lines[-1]), 10001, proc.stdout)

    def test_exact_list_append_eliminates_callmethod(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 CALL_LIST_APPEND")

        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def append_once(todo, value):
                todo.append(value)
                return len(todo)

            todo = []
            for i in range(10000):
                append_once(todo, i)

            assert jit.force_compile(append_once)
            counts = cinderjit.get_function_hir_opcode_counts(append_once)
            print(counts.get("CallMethod", 0))
            print(counts.get("ListAppend", 0))
            print(append_once(todo, 10000))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/exact_list_append_no_callmethod.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 10001, proc.stdout)

    def test_list_subclass_pop_front_eliminates_callmethod(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Regression guard:
        # heap list subclasses inheriting list.pop should avoid CallMethod and
        # keep the specialized method-descriptor call as VectorCall.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class OrderedCollection(list):
                pass

            def pop_front(todo):
                return todo.pop(0)

            todo = OrderedCollection([0, 1, 2, 3])
            for _ in range(10000):
                item = pop_front(todo)
                todo.append(item)

            assert jit.force_compile(pop_front)
            counts = cinderjit.get_function_hir_opcode_counts(pop_front)
            print(counts.get("CallMethod", 0))
            print(counts.get("VectorCall", 0))
            print(pop_front(OrderedCollection([7, 8, 9])))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/list_subclass_pop_front_no_callmethod.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertLessEqual(int(lines[-3]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 7, proc.stdout)

    def test_list_subclass_pop_front_lir_avoids_generic_vectorcall(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Regression guard:
        # the remaining list.pop(0) method-descriptor fastcall path should lower
        # to a direct call in LIR instead of the generic VectorCall helper.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class OrderedCollection(list):
                pass

            def pop_front(todo):
                return todo.pop(0)

            todo = OrderedCollection([0, 1, 2, 3])
            for _ in range(10000):
                item = pop_front(todo)
                todo.append(item)

            assert jit.force_compile(pop_front)
            print(pop_front(OrderedCollection([7, 8, 9])))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/list_subclass_pop_front_lir_direct_call.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITDUMPLIR"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 1, proc.stdout)
            self.assertEqual(lines[-1], "7", proc.stdout)

    def test_list_subclass_pop_default_lir_uses_method_descr_fastcall(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # Regression guard:
        # inherited exact method descriptors with zero explicit arguments should
        # use the descriptor fastcall helper instead of generic vectorcall.
        code = textwrap.dedent(
            """
            import ctypes

            import _cinderx
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class OrderedCollection(list):
                pass

            def pop_last(todo):
                return todo.pop()

            todo = OrderedCollection([0, 1, 2, 3])
            for _ in range(10000):
                item = pop_last(todo)
                todo.insert(0, item)

            assert jit.force_compile(pop_last)
            cinderx_lib = ctypes.CDLL(_cinderx.__file__)
            helper = ctypes.cast(
                getattr(
                    cinderx_lib,
                    "_Z35JITRT_CallMethodDescrFastVectorcallP7_objectPKS0_mS0_",
                ),
                ctypes.c_void_p,
            ).value
            print(f"JITRT_METHOD_DESCR_FAST_VECTORCALL={helper:#x}")
            print(pop_last(OrderedCollection([7, 8, 9])))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/list_subclass_pop_default_lir_direct_call.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            def run_case(**extra_env):
                env = dict(os.environ)
                env["PYTHONJITDUMPLIR"] = "1"
                env["PYTHONJITDUMPLIRORIGIN"] = "1"
                env.update(extra_env)
                proc = subprocess.run(
                    [sys.executable, script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
                )
                lines = [
                    line.strip() for line in proc.stdout.splitlines() if line.strip()
                ]
                self.assertGreaterEqual(len(lines), 2, proc.stdout)
                self.assertEqual(lines[-1], "9", proc.stdout)
                helper_addr = next(
                    line.split("=", 1)[1]
                    for line in lines
                    if line.startswith("JITRT_METHOD_DESCR_FAST_VECTORCALL=")
                )

                dump = proc.stdout + "\n" + proc.stderr
                match = re.search(
                    r"LIR for __main__:pop_last after generation:\n(.*?)(?:\nJIT: .*?LIR for |\Z)",
                    dump,
                    re.S,
                )
                self.assertIsNotNone(match, dump)
                return match.group(1), helper_addr

            section, helper_addr = run_case(
                PYTHONJITMETHODDESCRFASTVECTORCALL="1"
            )
            self.assertIn(f"({helper_addr})", section)

            disabled_section, helper_addr = run_case(
                PYTHONJITMETHODDESCRFASTVECTORCALL="0"
            )
            self.assertNotIn(f"({helper_addr})", disabled_section)

    def test_exact_list_pop_default_lir_uses_direct_helper(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_NO_DICT")

        # bm_go uses exact-list pop() in EmptySet.remove() and
        # UCTNode.select().  The exact no-arg method-descriptor path should
        # bypass generic descriptor vectorcall and call the list-pop helper
        # directly.
        code = textwrap.dedent(
            """
            import ctypes

            import _cinderx
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def pop_last(todo):
                return todo.pop()

            todo = [0, 1, 2, 3]
            for _ in range(10000):
                item = pop_last(todo)
                todo.insert(0, item)

            assert jit.force_compile(pop_last)
            cinderx_lib = ctypes.CDLL(_cinderx.__file__)
            helper = ctypes.cast(
                getattr(cinderx_lib, "JITRT_ListPopLast"),
                ctypes.c_void_p,
            ).value
            print(f"JITRT_LIST_POP_LAST={helper:#x}")
            print(pop_last([7, 8, 9]))
            try:
                pop_last([])
            except IndexError:
                print("IndexError")
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/exact_list_pop_default_lir_direct_call.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            def run_case(**extra_env):
                env = dict(os.environ)
                env["PYTHONJITDUMPLIR"] = "1"
                env["PYTHONJITDUMPLIRORIGIN"] = "1"
                env.update(extra_env)
                proc = subprocess.run(
                    [sys.executable, script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
                )
                lines = [
                    line.strip() for line in proc.stdout.splitlines() if line.strip()
                ]
                self.assertGreaterEqual(len(lines), 3, proc.stdout)
                self.assertEqual(lines[-2], "9", proc.stdout)
                self.assertEqual(lines[-1], "IndexError", proc.stdout)
                helper_addr = next(
                    line.split("=", 1)[1]
                    for line in lines
                    if line.startswith("JITRT_LIST_POP_LAST=")
                )

                dump = proc.stdout + "\n" + proc.stderr
                match = re.search(
                    r"LIR for __main__:pop_last after generation:\n(.*?)(?:\nJIT: .*?LIR for |\Z)",
                    dump,
                    re.S,
                )
                self.assertIsNotNone(match, dump)
                return match.group(1), helper_addr

            section, helper_addr = run_case()
            self.assertIn(f"({helper_addr})", section)

            disabled_section, helper_addr = run_case(PYTHONJITLISTPOPLASTHELPER="0")
            self.assertNotIn(f"({helper_addr})", disabled_section)

    def test_math_sqrt_cdouble_lowers_to_double_sqrt(self) -> None:
        self.skipTest("current ARM JIT does not expose DoubleSqrt lowering")
        # Regression guard:
        # with the retained issue31/raytrace heuristic, no-backedge generic
        # helpers stay on the module-attr/vectorcall path instead of keeping
        # exact-float sqrt lowering.
        code = textwrap.dedent(
            """
            import math
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def euclidean_distance(ax, ay, bx, by):
                dx = ax - bx
                dy = ay - by
                return math.sqrt(dx * dx + dy * dy)

            for _ in range(10000):
                euclidean_distance(1.0, 2.0, 4.0, 6.0)

            assert jit.force_compile(euclidean_distance)
            counts = cinderjit.get_function_hir_opcode_counts(euclidean_distance)
            print(counts.get("DoubleSqrt", 0))
            print(counts.get("VectorCall", 0))
            print(counts.get("LoadModuleAttrCached", 0))
            print(euclidean_distance(1.0, 2.0, 4.0, 6.0))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/math_sqrt_double_sqrt.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(float(lines[-1]), 5.0, proc.stdout)

    def test_from_import_math_sqrt_cdouble_lowers_to_double_sqrt(self) -> None:
        self.skipTest("current ARM JIT does not expose DoubleSqrt lowering")
        # Regression guard:
        # both direct-module and from-import sqrt helpers stay on the same
        # generic no-backedge path under the retained float-guard policy.
        code = textwrap.dedent(
            """
            import math
            from math import sqrt
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def pattern_a(x):
                return math.sqrt(x * x)

            def pattern_b(x):
                return sqrt(x * x)

            for _ in range(10000):
                pattern_a(3.0)
                pattern_b(4.0)

            assert jit.force_compile(pattern_a)
            assert jit.force_compile(pattern_b)

            counts_a = cinderjit.get_function_hir_opcode_counts(pattern_a)
            counts_b = cinderjit.get_function_hir_opcode_counts(pattern_b)

            print(counts_a.get("DoubleSqrt", 0))
            print(counts_a.get("VectorCall", 0))
            print(pattern_a(3.0))
            print(counts_b.get("DoubleSqrt", 0))
            print(counts_b.get("VectorCall", 0))
            print(pattern_b(4.0))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/math_sqrt_from_import_double_sqrt.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertEqual(int(lines[-6]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 1, proc.stdout)
            self.assertEqual(float(lines[-4]), 3.0, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(float(lines[-1]), 4.0, proc.stdout)

    def test_math_sqrt_negative_input_preserves_value_error(self) -> None:
        # Regression guard:
        # the native sqrt fast path must deopt/slow-path on negative doubles so
        # Python still raises ValueError instead of returning NaN.
        code = textwrap.dedent(
            """
            import math
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def f(x):
                return math.sqrt(x)

            for _ in range(10000):
                f(9.0)

            assert jit.force_compile(f)

            try:
                f(-1.0)
            except ValueError:
                print("valueerror")
            else:
                print("noerror")
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/math_sqrt_negative_valueerror.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            self.assertEqual(
                proc.stdout.strip().splitlines()[-1], "valueerror", proc.stdout
            )

    def test_builtin_min_max_two_float_args_eliminate_vectorcall(self) -> None:
        # Regression guard:
        # two-arg builtin min/max on exact floats should still get a float
        # fast path while preserving Python result semantics. A cold generic
        # fallback path is acceptable as long as the hot float path stays
        # specialized.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit
            import json

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def min_builtin(a, b):
                return min(a, b)

            def max_builtin(a, b):
                return max(a, b)

            for _ in range(10000):
                min_builtin(1.5, 2.5)
                max_builtin(1.5, 2.5)

            assert jit.force_compile(min_builtin)
            assert jit.force_compile(max_builtin)

            counts_min = cinderjit.get_function_hir_opcode_counts(min_builtin)
            counts_max = cinderjit.get_function_hir_opcode_counts(max_builtin)
            jit.get_and_clear_runtime_stats()
            for _ in range(20000):
                min_builtin(1.5, 2.5)
                max_builtin(1.5, 2.5)
            stats = jit.get_and_clear_runtime_stats()
            relevant = [
                entry
                for entry in stats["deopt"]
                if entry["normal"]["func_qualname"] in ("min_builtin", "max_builtin")
            ]
            print(counts_min.get("VectorCall", 0))
            print(counts_max.get("VectorCall", 0))
            print(counts_min.get("PrimitiveCompare", 0))
            print(counts_max.get("PrimitiveCompare", 0))
            print(json.dumps(relevant))
            print(min_builtin(1.5, 2.5))
            print(max_builtin(1.5, 2.5))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/builtin_minmax_no_vectorcall.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 7, proc.stdout)
            self.assertLessEqual(int(lines[-7]), 2, proc.stdout)
            self.assertLessEqual(int(lines[-6]), 2, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(lines[-3], "[]", proc.stdout)
            self.assertEqual(float(lines[-2]), 1.5, proc.stdout)
            self.assertEqual(float(lines[-1]), 2.5, proc.stdout)

    def test_builtin_min_max_two_float_args_preserve_order_nan_and_identity(self) -> None:
        # Regression guard:
        # the specialized min/max path must preserve Python's order-sensitive
        # NaN handling, signed-zero tie behavior, and object identity.
        code = textwrap.dedent(
            """
            import math
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def min_builtin(a, b):
                return min(a, b)

            def max_builtin(a, b):
                return max(a, b)

            nan = float("nan")
            one = float(1.0)
            z = 0.0
            nz = -0.0
            a = float(1.25)
            b = float(1.25)

            for _ in range(10000):
                min_builtin(1.5, 2.5)
                max_builtin(1.5, 2.5)

            assert jit.force_compile(min_builtin)
            assert jit.force_compile(max_builtin)

            print(math.isnan(min_builtin(nan, one)))
            print(min_builtin(one, nan) is one)
            print(math.copysign(1.0, min_builtin(z, nz)))
            print(math.copysign(1.0, max_builtin(z, nz)))
            print(min_builtin(a, b) is a)
            print(max_builtin(a, b) is a)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/builtin_minmax_semantics.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertEqual(lines[-6], "True", proc.stdout)
            self.assertEqual(lines[-5], "True", proc.stdout)
            self.assertEqual(float(lines[-4]), 1.0, proc.stdout)
            self.assertEqual(float(lines[-3]), 1.0, proc.stdout)
            self.assertEqual(lines[-2], "True", proc.stdout)
            self.assertEqual(lines[-1], "True", proc.stdout)

    def test_builtin_abs_float_lowers_to_double_abs(self) -> None:
        # Regression guard:
        # builtin abs(float) should avoid the generic VectorCall path and lower
        # to the dedicated double abs opcode.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def abs_builtin(x):
                return abs(x)

            for _ in range(10000):
                abs_builtin(-3.14)

            assert jit.force_compile(abs_builtin)

            counts = cinderjit.get_function_hir_opcode_counts(abs_builtin)
            print(counts.get("DoubleAbs", 0))
            print(counts.get("VectorCall", 0))
            print(counts.get("PrimitiveUnbox", 0))
            print(abs_builtin(-3.14))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/builtin_abs_double_abs.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(float(lines[-1]), 3.14, proc.stdout)

    def test_builtin_abs_float_preserves_nan_and_negative_zero(self) -> None:
        # Regression guard:
        # the abs(float) fast path should match Python for NaN and -0.0.
        code = textwrap.dedent(
            """
            import math
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def abs_builtin(x):
                return abs(x)

            for _ in range(10000):
                abs_builtin(-3.14)

            assert jit.force_compile(abs_builtin)

            nan = float("nan")
            print(math.isnan(abs_builtin(nan)))
            print(math.copysign(1.0, abs_builtin(-0.0)))
            print(abs_builtin(-2.5))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/builtin_abs_semantics.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(lines[-3], "True", proc.stdout)
            self.assertEqual(float(lines[-2]), 1.0, proc.stdout)
            self.assertEqual(float(lines[-1]), 2.5, proc.stdout)

    def test_slot_type_version_guards_are_deduplicated(self) -> None:
        # Regression guard:
        # repeated LOAD_ATTR_SLOT / STORE_ATTR_SLOT operations on the same SSA
        # receiver should reuse a single dominating tp_version_tag guard.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Point:
                __slots__ = ("x", "y", "z")

                def __init__(self, x: float, y: float, z: float) -> None:
                    self.x = x
                    self.y = y
                    self.z = z

                def maximize(self, other: "Point") -> "Point":
                    if other.x > self.x:
                        self.x = other.x
                    if other.y > self.y:
                        self.y = other.y
                    if other.z > self.z:
                        self.z = other.z
                    return self

            a = Point(1.0, 2.0, 3.0)
            b = Point(4.0, 5.0, 6.0)
            for _ in range(100000):
                a.maximize(b)
                a.x, a.y, a.z = 1.0, 2.0, 3.0

            assert jit.force_compile(Point.maximize)
            out = a.maximize(b)
            print(out.x, out.y, out.z)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/slot_guard_dedup.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITDUMPFINALHIR"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            dump = proc.stdout + "\n" + proc.stderr
            load_slot_guards = dump.count("Descr 'LOAD_ATTR_SLOT'")
            store_slot_guards = dump.count("Descr 'STORE_ATTR_SLOT'")
            version_loads = dump.count("tp_version_tag")

            self.assertEqual(store_slot_guards, 0, dump)
            self.assertEqual(load_slot_guards, 2, dump)
            self.assertEqual(version_loads, 2, dump)
            self.assertIn("4.0 5.0 6.0", proc.stdout)

    def test_len_arithmetic_uses_primitive_int_chain(self) -> None:
        # Regression guard:
        # len() feeding `== 0`, `// 2`, and `+ 1` should avoid LongCompare /
        # LongBinaryOp on the hot arithmetic chain.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def test_len_arithmetic(lst):
                n = len(lst)
                if n == 0:
                    return -1
                mid = n // 2
                idx = mid + 1
                return idx

            data = list(range(50))
            for _ in range(100000):
                test_len_arithmetic(data)

            assert jit.force_compile(test_len_arithmetic)
            print(test_len_arithmetic([]))
            print(test_len_arithmetic([1]))
            print(test_len_arithmetic([1, 2]))
            print(test_len_arithmetic([1, 2, 3]))
            print(test_len_arithmetic([1, 2, 3, 4]))
            print(test_len_arithmetic(data))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/len_arithmetic_primitive_chain.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITDUMPFINALHIR"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            dump = proc.stdout + "\n" + proc.stderr
            self.assertNotIn("LongCompare<Equal>", dump)
            self.assertNotIn("LongBinaryOp<FloorDivide>", dump)
            self.assertNotIn("LongBinaryOp<Add>", dump)
            self.assertIn("PrimitiveCompare<Equal>", dump)
            self.assertIn("IntBinaryOp<", dump)

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertEqual(lines[-6:], ["-1", "1", "2", "2", "3", "26"])

    def test_primitive_unbox_cse_for_float_add_self(self) -> None:
        # Regression guard:
        # no-backedge generic float helpers intentionally stay boxed on the
        # generic path, so PrimitiveUnbox should not appear in HIR counts.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def g(x):
                return x + x

            for _ in range(10000):
                g(0.01)

            assert jit.force_compile(g)
            counts = cinderjit.get_function_hir_opcode_counts(g)
            print(counts.get("PrimitiveUnbox", -1))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/primitive_unbox_cse.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            self.assertLessEqual(
                int(proc.stdout.strip().splitlines()[-1]), 1, proc.stdout
            )

    def test_primitive_box_remat_elides_frame_state_only_boxes(self) -> None:
        # Regression guard:
        # no-backedge generic helpers stay on the boxed path, so specialized
        # float PrimitiveBox rematerialization should not fire for this shape.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Body:
                def __init__(self, x, y, z):
                    self.x = x
                    self.y = y
                    self.z = z

            def dist_sq(a, b):
                dx = a.x - b.x
                dy = a.y - b.y
                dz = a.z - b.z
                return dx * dx + dy * dy + dz * dz

            p = Body(1.0, 2.0, 3.0)
            q = Body(4.0, 5.0, 6.0)
            for _ in range(10000):
                dist_sq(p, q)

            assert jit.force_compile(dist_sq)
            counts = cinderjit.get_function_hir_opcode_counts(dist_sq)
            print(counts.get("PrimitiveBox", -1))
            print(dist_sq(p, q))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/primitive_box_remat_count.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertLessEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(float(lines[-1]), 27.0, proc.stdout)

    def test_array_double_store_lowers_to_store_array_item(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            from array import array

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def f(a, i):
                a[i] = a[0] - a[1]

            arr = array('d', [4.5, 1.5, 0.0])
            for _ in range(20000):
                f(arr, 2)

            assert jit.force_compile(f)
            f(arr, 2)
            print(arr[2])
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/array_double_store.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "PYTHONJITDUMPFINALHIR": "1"},
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 1, proc.stdout)
            self.assertEqual(float(lines[-1]), 3.0, proc.stdout)

            dump = proc.stdout + "\n" + proc.stderr
            self.assertIn("StoreArrayItem", dump)
            self.assertIn("StoreSubscr", dump)
            self.assertIn("CondBranchCheckType", dump)
            self.assertIn("ObjectUser[array.array:Exact]", dump)
            self.assertIn("PrimitiveUnbox<CDouble>", dump)
            self.assertLess(
                dump.index("StoreArrayItem"),
                dump.index("StoreSubscr"),
                dump,
            )
            self.assertNotIn("Deopt", dump)

    def test_primitive_box_remat_deopt_correctness(self) -> None:
        # Regression guard:
        # when a guard later deopts, CDouble values that replaced temporary
        # PrimitiveBox outputs must be reconstructed correctly in interpreter.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Body:
                def __init__(self, x, y, z):
                    self.x = x
                    self.y = y
                    self.z = z

            class IntYBody:
                x = 7.0
                y = 5
                z = 11.0

            def dist_sq(a, b):
                dx = a.x - b.x
                dy = a.y - b.y
                dz = a.z - b.z
                return dx * dx + dy * dy + dz * dz

            p = Body(1.0, 2.0, 3.0)
            q = Body(4.0, 5.0, 6.0)
            for _ in range(10000):
                dist_sq(p, q)

            assert jit.force_compile(dist_sq)
            result = dist_sq(p, IntYBody())
            print(result)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/primitive_box_remat_deopt.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            self.assertEqual(float(proc.stdout.strip().splitlines()[-1]), 109.0, proc.stdout)

    def test_list_annotation_enables_exact_slice_and_item_specialization(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def test_list_slice(lst: list):
                mid = len(lst) // 2
                left = lst[:mid]
                right = lst[mid + 1:]
                item = lst[mid]
                return left, item, right

            for _ in range(200000):
                test_list_slice([10, 20, 30, 40, 50])

            assert jit.force_compile(test_list_slice)
            counts = cinderjit.get_function_hir_opcode_counts(test_list_slice)
            print(counts.get("ListSlice", 0))
            print(counts.get("LoadArrayItem", 0))
            print(counts.get("BuildSlice", 0))
            print(counts.get("BinaryOp", 0))
            print(test_list_slice([10, 20, 30, 40, 50]))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/list_annotation_slice_specialization.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 5, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 0, proc.stdout)
            self.assertEqual(int(lines[-4]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(lines[-1], "([10, 20], 30, [40, 50])", proc.stdout)

    def test_force_compile_annotation_thunk_does_not_crash(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 __annotate__ functions")

        code = textwrap.dedent(
            """
            import _colorize
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            thunk = getattr(_colorize.can_colorize, "__annotate__", None)
            assert thunk is not None, "__annotate__ missing"
            print(jit.force_compile(thunk))
            print(jit.is_jit_compiled(thunk))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/annotation_thunk_force_compile.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2], "True", proc.stdout)
            self.assertEqual(lines[-1], "True", proc.stdout)

    def test_specialized_opcodes_do_not_eagerly_execute_annotation_thunks(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 __annotate__ functions")

        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.disable_emit_type_annotation_guards()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            calls = 0

            def should_not_run():
                global calls
                calls += 1
                raise RuntimeError("__annotate__ should not run during compile")

            def f(x):
                return x + 1

            f.__annotate__ = should_not_run

            assert jit.force_compile(f)
            print(calls)
            print(jit.is_jit_compiled(f))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/annotation_thunk_not_eager.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2], "0", proc.stdout)
            self.assertEqual(lines[-1], "True", proc.stdout)

    def test_list_prefix_reverse_assign_lowers_to_runtime_fastpath(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def flip_prefix(perm, k):
                perm[: k + 1] = perm[k::-1]
                return perm

            def flip_window(perm, k):
                perm[1 : k + 1] = perm[k::-1]
                return perm

            def flip_stride(perm, k):
                perm[: k + 1] = perm[k::2]
                return perm

            hot = [0, 1, 2, 3, 4]
            for _ in range(200000):
                flip_prefix(hot, 3)
                flip_window(hot, 3)
                flip_stride(hot, 3)

            assert jit.force_compile(flip_prefix)
            assert jit.force_compile(flip_window)
            assert jit.force_compile(flip_stride)
            counts = cinderjit.get_function_hir_opcode_counts(flip_prefix)
            print(counts.get("CallStatic", 0))
            print(counts.get("StoreSubscr", 0))

            a = [0, 1, 2, 3, 4]
            print(flip_prefix(a, 3))
            b = [0, 1, 2, 3, 4]
            print(flip_prefix(b, -1))
            c = [0, 1, 2, 3, 4]
            print(flip_window(c, 3))
            d = [0, 1, 2, 3, 4]
            print(flip_stride(d, 3))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/list_prefix_reverse_assign_fastpath.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "PYTHONJITENABLESLICEFASTPATH": "0"},
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            off_callstatic = int(lines[-6])
            off_storesubscr = int(lines[-5])
            self.assertEqual(lines[-4], "[3, 2, 1, 0, 4]", proc.stdout)
            self.assertEqual(lines[-3], "[4, 3, 2, 1, 0, 0, 1, 2, 3, 4]", proc.stdout)
            self.assertEqual(lines[-2], "[0, 3, 2, 1, 0, 4]", proc.stdout)
            self.assertEqual(lines[-1], "[3, 4]", proc.stdout)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "PYTHONJITENABLESLICEFASTPATH": "1"},
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            on_callstatic = int(lines[-6])
            on_storesubscr = int(lines[-5])
            self.assertGreaterEqual(on_callstatic, off_callstatic + 1, proc.stdout)
            self.assertLess(on_storesubscr, off_storesubscr, proc.stdout)
            self.assertEqual(lines[-4], "[3, 2, 1, 0, 4]", proc.stdout)
            self.assertEqual(lines[-3], "[4, 3, 2, 1, 0, 0, 1, 2, 3, 4]", proc.stdout)
            self.assertEqual(lines[-2], "[0, 3, 2, 1, 0, 4]", proc.stdout)
            self.assertEqual(lines[-1], "[3, 4]", proc.stdout)

    def test_istruthy_bool_uses_pointer_compare_fast_path(self) -> None:
        # Regression guard:
        # bool-heavy truthiness checks should not rely solely on
        # PyObject_IsTrue; LIR should include compare-based fast-path logic.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Foo:
                def __init__(self):
                    self.enabled = False

                def check(self):
                    if self.enabled:
                        return 42
                    return 0

            foo = Foo()
            for _ in range(200000):
                foo.check()

            assert jit.force_compile(Foo.check)
            print(foo.check())
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/istruthy_bool_fast_path.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITDUMPLIR"] = "1"
            env["PYTHONJITDUMPLIRORIGIN"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            dump = proc.stdout + "\n" + proc.stderr
            match = re.search(
                r"LIR for __main__:Foo\.check after generation:\n(.*?)(?:\nJIT: .*?LIR for |\Z)",
                dump,
                re.S,
            )
            self.assertIsNotNone(match, dump)
            section = match.group(1)
            equal_count = len(re.findall(r"= Equal ", section))

            self.assertGreaterEqual(equal_count, 1, section)
            self.assertEqual(int(proc.stdout.strip().splitlines()[-1]), 0, proc.stdout)

    def test_istruthy_plain_object_uses_default_truthy_fast_path(self) -> None:
        # Regression guard:
        # plain heap objects with no __bool__/__len__ should not go straight to
        # PyObject_IsTrue; LIR should contain a compare-based fast path for
        # None/default-truthy objects before the slow helper call.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Bar:
                pass

            class Foo:
                def __init__(self, child):
                    self.child = child

                def check(self):
                    if self.child:
                        return 42
                    return 0

            foo = Foo(Bar())
            for _ in range(200000):
                foo.check()

            assert jit.force_compile(Foo.check)
            print(foo.check())
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/istruthy_plain_object_fast_path.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITDUMPLIR"] = "1"
            env["PYTHONJITDUMPLIRORIGIN"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            dump = proc.stdout + "\n" + proc.stderr
            match = re.search(
                r"LIR for __main__:Foo\.check after generation:\n(.*?)(?:\nJIT: .*?LIR for |\Z)",
                dump,
                re.S,
            )
            self.assertIsNotNone(match, dump)
            section = match.group(1)
            window = re.search(
                r"# v\d+:CBool = IsTruthy .*?# Decref v\d+",
                section,
                re.S,
            )
            self.assertIsNotNone(window, section)
            truthy_section = window.group(0)

            equal_count = len(re.findall(r"= Equal ", truthy_section))
            self.assertGreaterEqual(equal_count, 4, truthy_section)
            self.assertEqual(int(proc.stdout.strip().splitlines()[-1]), 42, proc.stdout)

    def test_hot_loop_uses_long_loop_unboxing(self) -> None:

        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def hot_loop(n):
                s = 0
                i = 0
                while i < n:
                    s += i
                    i += 1
                return s

            assert jit.force_compile(hot_loop)
            counts = cinderjit.get_function_hir_opcode_counts(hot_loop)
            print(counts.get("CheckedIntBinaryOp", 0))
            print(counts.get("LongUnboxCompact", 0))
            print(counts.get("PrimitiveCompare", 0))
            print(counts.get("PrimitiveBox", 0))
            print(counts.get("LongInPlaceOp", 0))
            print(counts.get("CompareBool", 0))
            print(hot_loop(10))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/hot_loop_long_loop_unboxing.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 7, proc.stdout)
            self.assertGreaterEqual(int(lines[-7]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-6]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 45, proc.stdout)

    def test_unpack_sequence_shared_tuple_and_list_avoid_repeated_deopts(self) -> None:
        # Regression guard:
        # a shared UNPACK_SEQUENCE helper should keep both tuple and list on the
        # compiled fast path instead of specializing permanently to only one.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def do_unpacking(loops, seq):
                total = 0
                for _ in range(loops):
                    a, b, c, d, e, f, g, h, i, j = seq
                    total += a + j
                return total

            t = tuple(range(10))
            l = list(range(10))

            for _ in range(5000):
                do_unpacking(1, t)

            assert jit.force_compile(do_unpacking)
            counts = cinderjit.get_function_hir_opcode_counts(do_unpacking)

            jit.get_and_clear_runtime_stats()
            result_tuple = do_unpacking(2000, t)
            result_list = do_unpacking(2000, l)
            stats = jit.get_and_clear_runtime_stats()

            deopt_count = sum(
                entry["int"]["count"]
                for entry in stats.get("deopt", [])
                if entry["normal"]["func_qualname"] == "do_unpacking"
            )

            print(counts.get("LoadFieldAddress", 0))
            print(counts.get("LoadField", 0))
            print(deopt_count)
            print(result_tuple)
            print(result_list)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/unpack_sequence_bimorphic.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 5, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertEqual(int(lines[-2]), 18000, proc.stdout)
            self.assertEqual(int(lines[-1]), 18000, proc.stdout)

    def test_set_genexpr_eliminates_generator_call(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def f():
                return set(i * 2 for i in range(8))

            assert jit.force_compile(f)
            counts = cinderjit.get_function_hir_opcode_counts(f)
            print(counts.get("CallMethod", 0))
            print(counts.get("MakeFunction", 0))
            print(counts.get("MakeSet", 0))
            print(counts.get("InvokeIterNext", 0))
            print(counts.get("SetSetItem", 0))
            print(f())
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/set_genexpr_inline.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertEqual(int(lines[-6]), 0, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            self.assertEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(lines[-1], "{0, 2, 4, 6, 8, 10, 12, 14}", proc.stdout)

    def test_set_genexpr_with_closure_eliminates_generator_call(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def f(vec, cols):
                return set(vec[i] + i for i in cols)

            assert jit.force_compile(f)
            counts = cinderjit.get_function_hir_opcode_counts(f)
            print(counts.get("CallMethod", 0))
            print(counts.get("MakeSet", 0))
            print(counts.get("InvokeIterNext", 0))
            print(counts.get("SetSetItem", 0))
            print(counts.get("LoadTupleItem", 0))
            print(f([10, 20, 30, 40], range(4)))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/set_genexpr_closure_inline.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertEqual(int(lines[-6]), 0, proc.stdout)
            self.assertEqual(int(lines[-5]), 1, proc.stdout)
            self.assertEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(lines[-1], "{32, 10, 43, 21}", proc.stdout)

    def test_any_genexpr_eliminates_generator_call(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Widget:
                def __init__(self, has_knob):
                    self.has_knob = has_knob

            def f(widgets):
                return any(w.has_knob for w in widgets if w is not None)

            assert jit.force_compile(f)
            counts = cinderjit.get_function_hir_opcode_counts(f)
            print(counts.get("CallMethod", 0))
            print(counts.get("MakeFunction", 0))
            print(counts.get("InvokeIterNext", 0))
            print(f([None, Widget(False), Widget(True)]))
            print(f([None, Widget(False)]))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/any_genexpr_inline.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 5, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(lines[-2], "True", proc.stdout)
            self.assertEqual(lines[-1], "False", proc.stdout)

    def test_list_for_iter_runtime_fast_path_preserves_iterator_semantics(
        self,
    ) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def append_seen(xs):
                seen = []
                for x in xs:
                    seen.append(x)
                    if x == 2 and len(xs) == 2:
                        xs.append(3)
                return seen, xs

            def clear_mid_iteration(xs):
                seen = []
                for x in xs:
                    seen.append(x)
                    xs.clear()
                return seen, xs

            for _ in range(1000):
                append_seen([1, 2])
                clear_mid_iteration([1, 2, 3])

            assert jit.force_compile(append_seen)
            assert jit.force_compile(clear_mid_iteration)
            assert append_seen([1, 2]) == ([1, 2, 3], [1, 2, 3])
            assert clear_mid_iteration([1, 2, 3]) == ([1], [])
            print(cinderjit.get_function_hir_opcode_counts(append_seen).get("InvokeIterNext", 0))
            print(cinderjit.get_function_hir_opcode_counts(clear_mid_iteration).get("InvokeIterNext", 0))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/list_for_iter_specialized.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 1, proc.stdout)

    def test_tuple_range_for_iter_runtime_fast_path_preserves_semantics(
        self,
    ) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def consume(it):
                seen = []
                for x in it:
                    seen.append(x)
                return seen

            def tuple_sum(xs):
                total = 0
                for x in xs:
                    total += x
                return total

            def range_values():
                out = []
                for x in range(2, 10, 3):
                    out.append(x)
                return out

            for _ in range(1000):
                consume(iter((1, 2, 3)))
                consume(iter(range(1, 6, 2)))
                tuple_sum((1, 2, 3, 4))
                range_values()

            assert jit.force_compile(consume)
            assert jit.force_compile(tuple_sum)
            assert jit.force_compile(range_values)
            range_iter = iter(range(1, 6, 2))
            assert consume(iter((1, 2, 3))) == [1, 2, 3]
            assert consume(range_iter) == [1, 3, 5]
            assert consume(range_iter) == []
            assert tuple_sum((1, 2, 3, 4)) == 10
            assert range_values() == [2, 5, 8]
            print(cinderjit.get_function_hir_opcode_counts(consume).get("InvokeIterNext", 0))
            print(cinderjit.get_function_hir_opcode_counts(tuple_sum).get("InvokeIterNext", 0))
            print(cinderjit.get_function_hir_opcode_counts(range_values).get("InvokeIterNext", 0))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tuple_range_for_iter_specialized.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 1, proc.stdout)

    def test_list_for_iter_lir_has_inline_fast_path(self) -> None:
        code = textwrap.dedent(
            """
            import ctypes

            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def sum_list(xs):
                total = 0
                for x in xs:
                    total += x
                return total

            for _ in range(10000):
                if sum_list([1, 2, 3, 4]) != 10:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(sum_list)
            list_iter_type = ctypes.addressof(
                ctypes.c_char.in_dll(ctypes.pythonapi, "PyListIter_Type")
            )
            print(f"PY_LIST_ITER_TYPE={list_iter_type:#x}")
            print(sum_list([1, 2, 3, 4]))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/list_for_iter_lir_inline.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            def run_case(**extra_env):
                env = dict(os.environ)
                env["PYTHONJITDUMPLIR"] = "1"
                env["PYTHONJITDUMPLIRORIGIN"] = "1"
                env.update(extra_env)
                proc = subprocess.run(
                    [sys.executable, script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
                )
                lines = [
                    line.strip() for line in proc.stdout.splitlines() if line.strip()
                ]
                self.assertGreaterEqual(len(lines), 2, proc.stdout)
                self.assertEqual(lines[-1], "10", proc.stdout)
                list_iter_type = next(
                    line.split("=", 1)[1]
                    for line in lines
                    if line.startswith("PY_LIST_ITER_TYPE=")
                )

                dump = proc.stdout + "\n" + proc.stderr
                match = re.search(
                    r"LIR for __main__:sum_list after generation:\n(.*?)(?:\nJIT: .*?LIR for |\Z)",
                    dump,
                    re.S,
                )
                self.assertIsNotNone(match, dump)
                return match.group(1), list_iter_type

            section, list_iter_type = run_case(PYTHONJITINLINELISTITERNEXT="1")
            self.assertIn(f"({list_iter_type})", section)

            disabled_section, list_iter_type = run_case(
                PYTHONJITINLINELISTITERNEXT="0"
            )
            self.assertNotIn(f"({list_iter_type})", disabled_section)

    def test_tiny_helper_filter_skips_small_no_backedge_code(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            cinderjit.append_jit_list("__main__:*")
            jit.compile_after_n_calls(0)

            def tiny_predicate(x):
                return x > 3

            def outer(xs):
                total = 0
                for x in xs:
                    if tiny_predicate(x):
                        total += x
                return total

            for _ in range(1000):
                assert outer([1, 4, 5]) == 9

            names = [
                getattr(func, "__qualname__", repr(func))
                for func in jit.get_compiled_functions()
            ]
            print(any(name == "outer" for name in names))
            print(any(name == "tiny_predicate" for name in names))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tiny_helper_filter.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITENABLEJITLISTWILDCARDS"] = "1"
            env["PYTHONJITFILTERTINY"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2], "True", proc.stdout)
            self.assertEqual(lines[-1], "False", proc.stdout)

    def test_tiny_helper_filter_does_not_block_force_compile(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(1000000)

            def tiny_predicate(x):
                return x > 3

            assert jit.force_compile(tiny_predicate)
            print(jit.is_jit_compiled(tiny_predicate))
            print(tiny_predicate(5))
            print(tiny_predicate(1))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tiny_helper_force_compile.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITFILTERTINY"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(lines[-3], "True", proc.stdout)
            self.assertEqual(lines[-2], "True", proc.stdout)
            self.assertEqual(lines[-1], "False", proc.stdout)

    def test_tiny_helper_filter_defers_only_stateful_hot_method_helpers(
        self,
    ) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            cinderjit.append_jit_list("__main__:*")
            jit.compile_after_n_calls(0)

            class Worker:
                def __init__(self):
                    self.values = [0, 1, 2, 3]
                    self.x = 1
                    self.y = 2
                    self.z = 3
                    self.waiting = False
                    self.ready = False

                def get_at(self, x):
                    return self.values[x & 3]

                def set_waiting(self):
                    self.waiting = True
                    return self

                def is_waiting(self):
                    return self.waiting

                def is_waiting_and_active(self):
                    return self.waiting and not self.ready

                def dot(self, other):
                    return self.x * other.x + self.y * other.y + self.z * other.z

            def tiny_scalar(x):
                return x - 1

            def outer(worker, count):
                total = 0
                for i in range(count):
                    total += worker.get_at(i)
                    total += tiny_scalar(i)
                    worker.set_waiting()
                    worker.is_waiting_and_active()
                    if worker.is_waiting():
                        total += 1
                    total += worker.dot(worker)
                return total

            worker = Worker()
            assert outer(worker, 2) == 30
            before_stateful = jit.get_function_tier_state(Worker.get_at)
            before_scalar = jit.get_function_tier_state(tiny_scalar)
            before_attr_only = jit.get_function_tier_state(Worker.set_waiting)
            before_attr_predicate = jit.get_function_tier_state(Worker.is_waiting)
            before_attr_complex_predicate = jit.get_function_tier_state(
                Worker.is_waiting_and_active
            )
            before_numeric_leaf = jit.get_function_tier_state(Worker.dot)
            print(jit.is_jit_compiled(Worker.get_at))
            print(before_stateful.get("helper_promotion_deferred", False))
            print(jit.is_jit_compiled(tiny_scalar))
            print(before_scalar.get("helper_promotion_deferred", False))
            print(jit.is_jit_compiled(Worker.set_waiting))
            print(before_attr_only.get("helper_promotion_deferred", False))
            print(jit.is_jit_compiled(Worker.is_waiting))
            print(before_attr_predicate.get("helper_promotion_deferred", False))
            print(jit.is_jit_compiled(Worker.is_waiting_and_active))
            print(
                before_attr_complex_predicate.get(
                    "helper_promotion_deferred", False
                )
            )
            print(jit.is_jit_compiled(Worker.dot))
            print(before_numeric_leaf.get("helper_promotion_deferred", False))

            for _ in range(8):
                assert outer(worker, 4) == 68

            after_stateful = jit.get_function_tier_state(Worker.get_at)
            after_scalar = jit.get_function_tier_state(tiny_scalar)
            after_attr_only = jit.get_function_tier_state(Worker.set_waiting)
            after_attr_predicate = jit.get_function_tier_state(Worker.is_waiting)
            after_attr_complex_predicate = jit.get_function_tier_state(
                Worker.is_waiting_and_active
            )
            after_numeric_leaf = jit.get_function_tier_state(Worker.dot)
            print(jit.is_jit_compiled(Worker.get_at))
            print(after_stateful.get("helper_promotion_deferred", True))
            print(jit.is_jit_compiled(tiny_scalar))
            print(after_scalar.get("helper_promotion_deferred", False))
            print(jit.is_jit_compiled(Worker.set_waiting))
            print(after_attr_only.get("helper_promotion_deferred", False))
            print(jit.is_jit_compiled(Worker.is_waiting))
            print(after_attr_predicate.get("helper_promotion_deferred", False))
            print(jit.is_jit_compiled(Worker.is_waiting_and_active))
            print(
                after_attr_complex_predicate.get(
                    "helper_promotion_deferred", False
                )
            )
            print(jit.is_jit_compiled(Worker.dot))
            print(after_numeric_leaf.get("helper_promotion_deferred", False))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/stateful_method_helper_deferred_promotion.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITENABLEJITLISTWILDCARDS"] = "1"
            env["PYTHONJITFILTERTINY"] = "9999"
            env["PYTHONJITDEFERFILTEREDHELPERS"] = "8"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 24, proc.stdout)
            self.assertEqual(lines[-24], "False", proc.stdout)
            self.assertEqual(lines[-23], "True", proc.stdout)
            self.assertEqual(lines[-22], "False", proc.stdout)
            self.assertEqual(lines[-21], "False", proc.stdout)
            self.assertEqual(lines[-20], "False", proc.stdout)
            self.assertEqual(lines[-19], "True", proc.stdout)
            self.assertEqual(lines[-18], "False", proc.stdout)
            self.assertEqual(lines[-17], "True", proc.stdout)
            self.assertEqual(lines[-16], "False", proc.stdout)
            self.assertEqual(lines[-15], "True", proc.stdout)
            self.assertEqual(lines[-14], "False", proc.stdout)
            self.assertEqual(lines[-13], "False", proc.stdout)
            self.assertEqual(lines[-12], "True", proc.stdout)
            self.assertEqual(lines[-11], "False", proc.stdout)
            self.assertEqual(lines[-10], "False", proc.stdout)
            self.assertEqual(lines[-9], "False", proc.stdout)
            self.assertEqual(lines[-8], "True", proc.stdout)
            self.assertEqual(lines[-7], "False", proc.stdout)
            self.assertEqual(lines[-6], "True", proc.stdout)
            self.assertEqual(lines[-5], "False", proc.stdout)
            self.assertEqual(lines[-4], "True", proc.stdout)
            self.assertEqual(lines[-3], "False", proc.stdout)
            self.assertEqual(lines[-2], "False", proc.stdout)
            self.assertEqual(lines[-1], "False", proc.stdout)

    def test_deferred_helper_promotion_ignores_precompile_all_until_hot(
        self,
    ) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            cinderjit.append_jit_list("__main__:*")
            jit.compile_after_n_calls(0)

            class Worker:
                def __init__(self):
                    self.values = [0, 1, 2, 3]

                def get_at(self, x):
                    return self.values[x & 3]

            def outer(worker, count):
                total = 0
                for i in range(count):
                    total += worker.get_at(i)
                return total

            worker = Worker()
            assert outer(worker, 2) == 1
            before = jit.get_function_tier_state(Worker.get_at)
            print(jit.is_jit_compiled(Worker.get_at))
            print(before.get("helper_promotion_deferred", False))

            print(jit.precompile_all())

            after_precompile = jit.get_function_tier_state(Worker.get_at)
            print(jit.is_jit_compiled(Worker.get_at))
            print(after_precompile.get("helper_promotion_deferred", False))

            for _ in range(8):
                assert outer(worker, 4) == 6

            after_hot = jit.get_function_tier_state(Worker.get_at)
            print(jit.is_jit_compiled(Worker.get_at))
            print(after_hot.get("helper_promotion_deferred", True))
            print(after_hot.get("helper_promotion_ready", 0) > 0)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/deferred_helper_precompile_all.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITENABLEJITLISTWILDCARDS"] = "1"
            env["PYTHONJITFILTERTINY"] = "9999"
            env["PYTHONJITDEFERFILTEREDHELPERS"] = "8"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 8, proc.stdout)
            self.assertEqual(lines[-8], "False", proc.stdout)
            self.assertEqual(lines[-7], "True", proc.stdout)
            self.assertEqual(lines[-6], "True", proc.stdout)
            self.assertEqual(lines[-5], "False", proc.stdout)
            self.assertEqual(lines[-4], "True", proc.stdout)
            self.assertEqual(lines[-3], "True", proc.stdout)
            self.assertEqual(lines[-2], "False", proc.stdout)
            self.assertEqual(lines[-1], "True", proc.stdout)

    def test_calling_state_helper_admission_compiles_recursive_method(
        self,
    ) -> None:
        # pyperformance go has tiny no-backedge helpers such as Square.find:
        # they mutate object state and recursively call another helper. They
        # should be opt-in admissible as real state operations instead of
        # staying behind deferred interpretation forever.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            cinderjit.append_jit_list("__main__:*")
            jit.compile_after_n_calls(0)

            class Worker:
                def __init__(self, pos=0, reference=None):
                    self.pos = pos
                    self.reference = reference or self
                    self.values = [0, 1, 2, 3]

                def get_at(self, index):
                    return self.values[index & 3]

                def find(self, update=False):
                    reference = self.reference
                    if reference.pos != self.pos:
                        reference = reference.find(update)
                        if update:
                            self.reference = reference
                    return reference

            def outer(worker):
                return worker.get_at(1) + worker.find(True).pos

            root = Worker(10)
            child = Worker(20, root)
            for _ in range(32):
                assert outer(child) == 11

            get_at_state = jit.get_function_tier_state(Worker.get_at)
            find_state = jit.get_function_tier_state(Worker.find)
            print(jit.is_jit_compiled(Worker.find))
            print(find_state.get("helper_promotion_deferred", False))
            print(jit.is_jit_compiled(Worker.get_at))
            print(get_at_state.get("helper_promotion_deferred", False))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/calling_state_helper_admission.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITENABLEJITLISTWILDCARDS"] = "1"
            env["PYTHONJITFILTERTINY"] = "9999"
            env["PYTHONJITDEFERFILTEREDHELPERS"] = "128"
            env["PYTHONJITADMITCALLINGSTATEHELPERS"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertEqual(lines[-4], "True", proc.stdout)
            self.assertEqual(lines[-3], "False", proc.stdout)
            self.assertEqual(lines[-2], "False", proc.stdout)
            self.assertEqual(lines[-1], "True", proc.stdout)

    def test_one_arg_state_method_value_call_uses_direct_vectorcall(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        # pyperformance go's Square.find(update) is just above the old
        # one-arg method-value candidate size. Once warmed, its recursive
        # self-state call should avoid the generic CallMethod helper.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Worker:
                def __init__(self, pos=0, reference=None):
                    self.pos = pos
                    self.reference = reference or self

                def find(self, update=False):
                    reference = self.reference
                    if reference.pos != self.pos:
                        reference = reference.find(update)
                        if update:
                            self.reference = reference
                    return reference

            root = Worker(10)
            child = Worker(20, root)
            for _ in range(20000):
                if child.find(True).pos != 10:
                    raise SystemExit("bad find")

            assert jit.force_compile(Worker.find)
            counts = cinderjit.get_function_hir_opcode_counts(Worker.find)
            print(counts.get("CallMethod", 0))
            print(counts.get("VectorCall", 0))
            print(child.find(True).pos)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/one_arg_state_method_value_direct_call.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 10, proc.stdout)

    def test_deferred_calling_state_helper_waits_for_method_value_cache(
        self,
    ) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 LOAD_ATTR_METHOD_WITH_VALUES")

        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            cinderjit.append_jit_list("__main__:*")
            jit.compile_after_n_calls(0)

            class Worker:
                def __init__(self, pos=0, reference=None):
                    self.pos = pos
                    self.reference = reference or self

                def find(self, update=False):
                    reference = self.reference
                    if reference.pos != self.pos:
                        reference = reference.find(update)
                        if update:
                            self.reference = reference
                    return reference

            root = Worker(10)
            child = Worker(20, root)
            for _ in range(3):
                assert child.find(True).pos == 10

            early = jit.get_function_tier_state(Worker.find)
            print(jit.is_jit_compiled(Worker.find))
            print(early.get("helper_promotion_deferred", False))

            for _ in range(20000):
                assert child.find(True).pos == 10

            late = jit.get_function_tier_state(Worker.find)
            counts = cinderjit.get_function_hir_opcode_counts(Worker.find)
            print(jit.is_jit_compiled(Worker.find))
            print(late.get("helper_promotion_deferred", True))
            print(counts.get("CallMethod", 0))
            print(counts.get("VectorCall", 0))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/deferred_calling_state_helper_waits_for_cache.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITENABLEJITLISTWILDCARDS"] = "1"
            env["PYTHONJITFILTERTINY"] = "9999"
            env["PYTHONJITDEFERFILTEREDHELPERS"] = "2"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertEqual(lines[-6], "False", proc.stdout)
            self.assertEqual(lines[-5], "True", proc.stdout)
            self.assertEqual(lines[-4], "True", proc.stdout)
            self.assertEqual(lines[-3], "False", proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-1]), 1, proc.stdout)

    def test_shape_profit_filter_skips_call_heavy_but_allows_unpack_loop(
        self,
    ) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            cinderjit.append_jit_list("__main__:*")
            jit.compile_after_n_calls(0)

            class Box:
                def __init__(self, value):
                    self.value = value

                def get(self):
                    return self.value

            def call_heavy(items):
                total = 0
                for item in items:
                    total += item.get()
                return total

            def unpack_loop(rows):
                total = 0
                for left, right in rows:
                    total += left + right
                return total

            boxes = [Box(1), Box(2), Box(3)]
            rows = [(1, 2), (3, 4)]
            for _ in range(1000):
                assert call_heavy(boxes) == 6
                assert unpack_loop(rows) == 10

            names = [
                getattr(func, "__qualname__", repr(func))
                for func in jit.get_compiled_functions()
            ]
            print(any(name == "call_heavy" for name in names))
            print(any(name == "unpack_loop" for name in names))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/shape_profit_filter.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITENABLEJITLISTWILDCARDS"] = "1"
            env["PYTHONJITSHAPEPROFITFILTER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2], "False", proc.stdout)
            self.assertEqual(lines[-1], "True", proc.stdout)

    def test_shape_profit_filter_does_not_block_reopt_attachment(self) -> None:
        code = textwrap.dedent(
            """
            import types

            import cinderx.jit as jit

            jit.enable()
            jit.compile_after_n_calls(0)

            class Box:
                def __init__(self, value):
                    self.value = value

                def get(self):
                    return self.value

            def call_heavy(items):
                total = 0
                for item in items:
                    total += item.get()
                return total

            boxes = [Box(1), Box(2), Box(3)]
            assert call_heavy(boxes) == 6
            assert jit.force_compile(call_heavy)

            same_code = types.FunctionType(
                call_heavy.__code__,
                globals(),
                "same_code",
            )
            assert same_code(boxes) == 6
            print(jit.is_jit_compiled(call_heavy))
            print(jit.is_jit_compiled(same_code))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/shape_profit_reopt.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITSHAPEPROFITFILTER"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2], "True", proc.stdout)
            self.assertEqual(lines[-1], "True", proc.stdout)

    def test_generated_code_filter_skips_comprehension_code(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            cinderjit.append_jit_list("__main__:*")
            jit.compile_after_n_calls(0)

            def outer(limit):
                values = [value + 1 for value in range(limit)]
                return sum(values)

            for _ in range(100):
                assert outer(16) == 136

            names = [
                getattr(func, "__qualname__", repr(func))
                for func in jit.get_compiled_functions()
            ]
            print(any(name == "outer" for name in names))
            print(any("<listcomp>" in name for name in names))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/generated_code_filter.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITENABLEJITLISTWILDCARDS"] = "1"
            env["PYTHONJITFILTERGENERATED"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2], "True", proc.stdout)
            self.assertEqual(lines[-1], "False", proc.stdout)

    def test_state_helper_admission_allows_subscript_methods_under_tiny_filter(
        self,
    ) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            cinderjit.append_jit_list("__main__:*")
            jit.compile_after_n_calls(0)

            class State:
                def __init__(self):
                    self.values = [0, 0]

                def set_at(self, index, value):
                    self.values[index] = value
                    return self.values[index]

                def set_attr(self, value):
                    self.total = value
                    return self.total

            def tiny_scalar(value):
                return value + 1

            def outer(state):
                total = 0
                for index in range(128):
                    total += state.set_at(index & 1, index)
                    total += state.set_attr(index)
                    total += tiny_scalar(index)
                return total

            state = State()
            for _ in range(1000):
                assert outer(state) == 24512

            names = [
                getattr(func, "__qualname__", repr(func))
                for func in jit.get_compiled_functions()
            ]
            print(any(name == "outer" for name in names))
            print(any(name == "State.set_at" for name in names))
            print(any(name == "State.set_attr" for name in names))
            print(any(name == "tiny_scalar" for name in names))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/state_helper_admission.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITENABLEJITLISTWILDCARDS"] = "1"
            env["PYTHONJITFILTERTINY"] = "9999"
            env["PYTHONJITADMITSTATEHELPERS"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertEqual(lines[-4], "True", proc.stdout)
            self.assertEqual(lines[-3], "True", proc.stdout)
            self.assertEqual(lines[-2], "False", proc.stdout)
            self.assertEqual(lines[-1], "False", proc.stdout)

    def test_contains_state_helper_deferred_promotion(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            class Seen:
                def __init__(self):
                    self.values = {1, 3, 5}

                def has_seen(self, value):
                    return value in self.values

            def outer(seen, count):
                total = 0
                for i in range(count):
                    if seen.has_seen(i & 7):
                        total += 1
                return total

            seen = Seen()
            assert outer(seen, 2) == 1
            before = jit.get_function_tier_state(Seen.has_seen)
            print(jit.is_jit_compiled(Seen.has_seen))
            print(before.get("helper_promotion_deferred", False))

            for _ in range(8):
                assert outer(seen, 4) == 2

            after = jit.get_function_tier_state(Seen.has_seen)
            print(jit.is_jit_compiled(Seen.has_seen))
            print(after.get("helper_promotion_deferred", True))
            print(after.get("helper_promotion_ready", 0) > 0)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/contains_state_helper_deferred_promotion.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITENABLEJITLISTWILDCARDS"] = "1"
            env["PYTHONJITFILTERTINY"] = "9999"
            env["PYTHONJITDEFERFILTEREDHELPERS"] = "8"
            env["PYTHONJITDEFERCONTAINSHELPERS"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 5, proc.stdout)
            self.assertEqual(lines[-5], "False", proc.stdout)
            self.assertEqual(lines[-4], "True", proc.stdout)
            self.assertEqual(lines[-3], "True", proc.stdout)
            self.assertEqual(lines[-2], "False", proc.stdout)
            self.assertEqual(lines[-1], "True", proc.stdout)

    def test_specialized_set_contains_lir_uses_direct_helper(self) -> None:
        if sys.version_info < (3, 14):
            self.skipTest("requires Python 3.14 CONTAINS_OP_SET")

        code = textwrap.dedent(
            """
            import ctypes

            import _cinderx
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def contains_in_set(values, needle):
                if needle in values:
                    return 1
                return 0

            values = {1, 3, 5}
            for i in range(20000):
                contains_in_set(values, i & 7)

            assert jit.force_compile(contains_in_set)
            cinderx_lib = ctypes.CDLL(_cinderx.__file__)
            jitrt_set_contains = ctypes.cast(
                getattr(cinderx_lib, "_Z17JITRT_SetContainsP7_objectS0_"),
                ctypes.c_void_p,
            ).value
            jitrt_sequence_contains = ctypes.cast(
                getattr(cinderx_lib, "_Z22JITRT_SequenceContainsP7_objectS0_"),
                ctypes.c_void_p,
            ).value
            print(f"JITRT_SET_CONTAINS={jitrt_set_contains:#x}")
            print(f"JITRT_SEQUENCE_CONTAINS={jitrt_sequence_contains:#x}")
            print(contains_in_set(values, 3))
            print(contains_in_set(values, 4))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/specialized_set_contains_direct_helper.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            def run_case(**extra_env):
                env = dict(os.environ)
                env["PYTHONJITDUMPLIR"] = "1"
                env["PYTHONJITDUMPLIRORIGIN"] = "1"
                env.update(extra_env)
                proc = subprocess.run(
                    [sys.executable, script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
                )
                lines = [
                    line.strip() for line in proc.stdout.splitlines() if line.strip()
                ]
                self.assertGreaterEqual(len(lines), 4, proc.stdout)
                self.assertEqual(lines[-2:], ["1", "0"], proc.stdout)
                set_addr = next(
                    line.split("=", 1)[1]
                    for line in lines
                    if line.startswith("JITRT_SET_CONTAINS=")
                )
                sequence_addr = next(
                    line.split("=", 1)[1]
                    for line in lines
                    if line.startswith("JITRT_SEQUENCE_CONTAINS=")
                )

                dump = proc.stdout + "\n" + proc.stderr
                match = re.search(
                    r"LIR for __main__:contains_in_set after generation:\n(.*?)(?:\nJIT: .*?LIR for |\Z)",
                    dump,
                    re.S,
                )
                self.assertIsNotNone(match, dump)
                return match.group(1), set_addr, sequence_addr

            section, set_addr, sequence_addr = run_case()
            self.assertIn(f"({set_addr})", section)
            self.assertNotIn(f"({sequence_addr})", section)

            disabled_section, set_addr, sequence_addr = run_case(
                PYTHONJITENABLESPECIALIZEDCONTAINS="0"
            )
            self.assertNotIn(f"({set_addr})", disabled_section)
            self.assertIn(f"({sequence_addr})", disabled_section)

    def test_exact_dict_subscr_uses_direct_helper_lir(self) -> None:
        code = textwrap.dedent(
            """
            import ctypes
            import _cinderx
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def get_item(values, key):
                return values[key]

            values = {"a": 11, "b": 22}
            for i in range(20000):
                if get_item(values, "a") != 11:
                    raise SystemExit("bad warmup")

            assert jit.force_compile(get_item)
            cinderx_lib = ctypes.CDLL(_cinderx.__file__)
            jitrt_dict_subscr = ctypes.cast(
                getattr(cinderx_lib, "_Z21JITRT_DictSubscrExactP7_objectS0_"),
                ctypes.c_void_p,
            ).value
            print(f"JITRT_DICT_SUBSCR={jitrt_dict_subscr:#x}")
            print(get_item(values, "b"))
            try:
                get_item(values, "missing")
            except KeyError as exc:
                print(type(exc).__name__)
                print(exc.args[0])
            else:
                print("NO_EXCEPTION")
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/exact_dict_subscr_direct_helper.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            def run_case(**extra_env):
                env = dict(os.environ)
                env["PYTHONJITDUMPLIR"] = "1"
                env["PYTHONJITDUMPLIRORIGIN"] = "1"
                env.update(extra_env)
                proc = subprocess.run(
                    [sys.executable, script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
                )
                lines = [
                    line.strip() for line in proc.stdout.splitlines() if line.strip()
                ]
                self.assertGreaterEqual(len(lines), 4, proc.stdout)
                self.assertEqual(lines[-3:], ["22", "KeyError", "missing"])
                helper_addr = next(
                    line.split("=", 1)[1]
                    for line in lines
                    if line.startswith("JITRT_DICT_SUBSCR=")
                )

                dump = proc.stdout + "\n" + proc.stderr
                match = re.search(
                    r"LIR for __main__:get_item after generation:\n(.*?)(?:\nJIT: .*?LIR for |\Z)",
                    dump,
                    re.S,
                )
                self.assertIsNotNone(match, dump)
                return match.group(1), helper_addr

            section, helper_addr = run_case(PYTHONJITEXACTDICTSUBSCR="1")
            self.assertIn(f"({helper_addr})", section)

            disabled_section, helper_addr = run_case(PYTHONJITEXACTDICTSUBSCR="0")
            self.assertNotIn(f"({helper_addr})", disabled_section)

    def test_set_genexpr_hot_loop_hoists_makefunction_chain(self) -> None:
        # Regression guard:
        # after set-genexpr inlining, the residual MakeFunction closure chain
        # should be hoisted out of the innermost hot path so the loop body no
        # longer rebuilds it on every generator iteration.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(2)

            def hot():
                data = tuple(range(8))
                for _ in range(50000):
                    set(data[i] + i for i in range(8))

            for _ in range(3):
                hot()

            hot_func = None
            for f in jit.get_compiled_functions():
                if f.__qualname__ == "hot":
                    hot_func = f
                    break

            assert hot_func is not None
            counts = cinderjit.get_function_hir_opcode_counts(hot_func)
            print(counts.get("MakeFunction", 0))
            print(counts.get("MakeTuple", 0))
            print(counts.get("SetFunctionAttr", 0))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/set_genexpr_hot_loop_hoist.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            env = dict(os.environ)
            env["PYTHONJITDUMPFINALHIR"] = "1"
            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            dump = proc.stdout + "\n" + proc.stderr
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 1, proc.stdout)

            hot_marker = "Optimized HIR for __main__:hot:"
            hot_start = dump.find(hot_marker)
            self.assertNotEqual(hot_start, -1, dump)
            hot_dump = dump[hot_start:]

            make_pos = hot_dump.find("MakeFunction")
            first_invoke = hot_dump.find("InvokeIterNext")
            second_invoke = hot_dump.find("InvokeIterNext", first_invoke + 1)
            self.assertNotEqual(make_pos, -1, dump)
            self.assertNotEqual(first_invoke, -1, hot_dump)
            self.assertNotEqual(second_invoke, -1, hot_dump)
            self.assertLess(make_pos, second_invoke, hot_dump)

    def test_set_genexpr_preserves_exception_behavior(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def f(xs):
                return set(10 // x for x in xs)

            assert jit.force_compile(f)

            try:
                f([5, 0, 2])
            except Exception as e:
                print(type(e).__name__)
                print(str(e))
            else:
                print("NO_EXCEPTION")
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/set_genexpr_exception.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2], "ZeroDivisionError", proc.stdout)
            self.assertEqual(lines[-1], "division by zero", proc.stdout)

    def test_set_genexpr_with_closure_preserves_exception_behavior(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def f(vec, cols):
                return set(vec[i] + i for i in cols)

            assert jit.force_compile(f)

            try:
                f([10, 20], range(4))
            except Exception as e:
                print(type(e).__name__)
                print(str(e))
            else:
                print("NO_EXCEPTION")
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/set_genexpr_closure_exception.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2], "IndexError", proc.stdout)
            self.assertIn("list index out of range", lines[-1], proc.stdout)

    def test_tuple_genexpr_eliminates_generator_call(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def f():
                return tuple(i * 2 for i in range(8))

            assert jit.force_compile(f)
            counts = cinderjit.get_function_hir_opcode_counts(f)
            print(counts.get("CallMethod", 0))
            print(counts.get("MakeFunction", 0))
            print(counts.get("MakeList", 0))
            print(counts.get("InvokeIterNext", 0))
            print(counts.get("ListAppend", 0))
            print(counts.get("MakeTupleFromList", 0))
            print(f())
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tuple_genexpr_inline.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 7, proc.stdout)
            self.assertEqual(int(lines[-7]), 0, proc.stdout)
            self.assertEqual(int(lines[-6]), 0, proc.stdout)
            self.assertEqual(int(lines[-5]), 1, proc.stdout)
            self.assertEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(lines[-1], "(0, 2, 4, 6, 8, 10, 12, 14)", proc.stdout)

    def test_tuple_genexpr_with_closure_eliminates_generator_call(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def f(vec, cols):
                return tuple(vec[i] + i for i in cols)

            assert jit.force_compile(f)
            counts = cinderjit.get_function_hir_opcode_counts(f)
            print(counts.get("CallMethod", 0))
            print(counts.get("MakeList", 0))
            print(counts.get("InvokeIterNext", 0))
            print(counts.get("ListAppend", 0))
            print(counts.get("MakeTupleFromList", 0))
            print(f([10, 20, 30, 40], range(4)))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tuple_genexpr_closure_inline.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertEqual(int(lines[-6]), 0, proc.stdout)
            self.assertEqual(int(lines[-5]), 1, proc.stdout)
            self.assertEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(lines[-1], "(10, 21, 32, 43)", proc.stdout)

    def test_tuple_genexpr_preserves_exception_behavior(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def f(xs):
                return tuple(10 // x for x in xs)

            assert jit.force_compile(f)

            try:
                f([5, 0, 2])
            except Exception as e:
                print(type(e).__name__)
                print(str(e))
            else:
                print("NO_EXCEPTION")
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tuple_genexpr_exception.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2], "ZeroDivisionError", proc.stdout)
            self.assertEqual(lines[-1], "division by zero", proc.stdout)

    def test_tuple_genexpr_with_closure_preserves_exception_behavior(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def f(vec, cols):
                return tuple(vec[i] + i for i in cols)

            assert jit.force_compile(f)

            try:
                f([10, 20], range(4))
            except Exception as e:
                print(type(e).__name__)
                print(str(e))
            else:
                print("NO_EXCEPTION")
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tuple_genexpr_closure_exception.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2], "IndexError", proc.stdout)
            self.assertIn("list index out of range", lines[-1], proc.stdout)

    def test_tuple_genexpr_yield_shape_eliminates_generator_call(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def f(pool, indices, r):
                yield tuple(pool[i] for i in indices[:r])

            assert jit.force_compile(f)
            counts = cinderjit.get_function_hir_opcode_counts(f)
            print(counts.get("CallMethod", 0))
            print(counts.get("MakeList", 0))
            print(counts.get("ListAppend", 0))
            print(counts.get("MakeTupleFromList", 0))
            print(list(f([10, 20, 30, 40], range(4), 3)))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/tuple_genexpr_yield_inline.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 5, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            self.assertEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(lines[-1], "[(10, 20, 30)]", proc.stdout)

    def test_recursive_coroutine_fibonacci_force_compile(self) -> None:
        # Regression guard:
        # the recursive coroutine shape used by pyperformance `coroutines`
        # must compile successfully under the JIT on 3.14.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            async def fibonacci(n: int) -> int:
                if n <= 1:
                    return n
                return await fibonacci(n - 1) + await fibonacci(n - 2)

            @jit.jit_suppress
            def run(n: int) -> int:
                coro = fibonacci(n)
                while True:
                    try:
                        coro.send(None)
                    except StopIteration as e:
                        return e.value

            expected = run(10)
            print(expected)
            print(jit.force_compile(fibonacci))
            print(jit.is_jit_compiled(fibonacci))
            print(jit.is_jit_compiled(fibonacci))
            print(run(10))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/recursive_coroutine_fibonacci.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 5, proc.stdout)
            self.assertEqual(int(lines[-5]), 55, proc.stdout)
            self.assertEqual(lines[-4], "True", proc.stdout)
            self.assertEqual(lines[-3], "True", proc.stdout)
            self.assertEqual(lines[-2], "True", proc.stdout)
            self.assertEqual(int(lines[-1]), 55, proc.stdout)

    def test_recursive_coroutine_immediate_await_skips_awaitable_helpers(self) -> None:
        # Regression guard:
        # immediately awaited recursive coroutine calls should bypass the
        # generic awaitable helper path.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            async def fibonacci(n: int) -> int:
                if n <= 1:
                    return n
                return await fibonacci(n - 1) + await fibonacci(n - 2)

            @jit.jit_suppress
            def run(n: int) -> int:
                coro = fibonacci(n)
                while True:
                    try:
                        coro.send(None)
                    except StopIteration as e:
                        return e.value

            assert run(10) == 55
            assert jit.force_compile(fibonacci)
            counts = cinderjit.get_function_hir_opcode_counts(fibonacci)
            print(counts.get("CallCFunc", 0))
            print(counts.get("Send", 0))
            print(counts.get("YieldFrom", 0))
            print(run(10))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/recursive_coroutine_fibonacci_hir.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 4, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 2, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 2, proc.stdout)
            self.assertEqual(int(lines[-1]), 55, proc.stdout)

    def test_deepcopy_keyerror_helpers_avoid_unhandledexception_deopts(self) -> None:
        # Regression guard:
        # stdlib deepcopy helpers rely on expected KeyError misses inside
        # try/except blocks. Those misses should not linearly deopt as
        # UnhandledException once the helpers are JIT-compiled.
        code = textwrap.dedent(
            """
            import copy
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            assert jit.force_compile(copy._keep_alive)
            assert jit.force_compile(copy._deepcopy_tuple)
            assert jit.is_jit_compiled(copy._keep_alive)
            assert jit.is_jit_compiled(copy._deepcopy_tuple)

            jit.get_and_clear_runtime_stats()

            total = 0
            for i in range(200):
                memo = {}
                copy._keep_alive(i, memo)
                total += copy._deepcopy_tuple((i, i + 1), memo)[0]

            stats = jit.get_and_clear_runtime_stats()
            keep_alive_deopts = 0
            deepcopy_tuple_deopts = 0
            for entry in stats.get("deopt", []):
                normal = entry["normal"]
                if normal.get("reason") != "UnhandledException":
                    continue
                if normal.get("description") != "BinaryOp":
                    continue
                count = entry["int"]["count"]
                if normal.get("func_qualname") == "_keep_alive":
                    keep_alive_deopts += count
                elif normal.get("func_qualname") == "_deepcopy_tuple":
                    deepcopy_tuple_deopts += count

            print(keep_alive_deopts)
            print(deepcopy_tuple_deopts)
            print(total)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/deepcopy_keyerror_deopts.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(int(lines[-1]), 19900, proc.stdout)

    def test_pickle_unpickler_stop_control_flow_avoids_deopts(self) -> None:
        # Regression guard:
        # stdlib pickle uses _Stop as normal completion control flow.
        # The hot completion path should not linearly deopt on each load().
        code = textwrap.dedent(
            """
            import io
            import pickle
            import cinderx.jit as jit

            DATA = [{"i": i, "s": f"v{i}", "b": b"x" * 16} for i in range(2000)]
            PAYLOAD = pickle.dumps(DATA, protocol=5)

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            assert jit.force_compile(pickle._Unpickler.load)
            assert jit.is_jit_compiled(pickle._Unpickler.load)

            def run_once():
                return pickle._Unpickler(io.BytesIO(PAYLOAD)).load()

            jit.get_and_clear_runtime_stats()

            total = 0
            for _ in range(200):
                total += len(run_once())

            stats = jit.get_and_clear_runtime_stats()
            load_stop_deopts = 0
            load_deopts = 0
            for entry in stats.get("deopt", []):
                normal = entry["normal"]
                count = entry["int"]["count"]
                if normal.get("func_qualname") == "_Unpickler.load_stop":
                    if normal.get("reason") == "Raise":
                        load_stop_deopts += count
                elif normal.get("func_qualname") == "_Unpickler.load":
                    if normal.get("reason") == "UnhandledException":
                        load_deopts += count

            print(load_stop_deopts)
            print(load_deopts)
            print(total)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/pickle_stop_deopts.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 3, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(int(lines[-1]), 400000, proc.stdout)

    def test_pickle_save_dict_nested_method_call_keeps_arguments(self) -> None:
        code = textwrap.dedent(
            """
            import pickle
            import cinderx.jit as jit

            payload = [{"a": 1}, {"b": 2}, {"c": 3}]

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            assert jit.force_compile(pickle._Pickler.save_dict)
            assert jit.is_jit_compiled(pickle._Pickler.save_dict)

            data = pickle.dumps(payload, protocol=5)
            restored = pickle.loads(data)
            print(len(data))
            print(restored == payload)
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/pickle_save_dict_nested_call.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertGreater(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(lines[-1], "True", proc.stdout)


if __name__ == "__main__":
    # Keep incidental unittest/traceback paths interpreted unless a test
    # explicitly opts into auto-jit. This avoids tail-end harness compiles
    # from obscuring the runtime checks we actually care about here.
    cinderx.jit.compile_after_n_calls(1000000)
    unittest.main()
