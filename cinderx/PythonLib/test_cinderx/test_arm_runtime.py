# Copyright (c) Meta Platforms, Inc. and affiliates.

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
        if self._compile_after_n_calls is None:
            cinderx.jit.compile_after_n_calls(0)
        else:
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
            self.assertGreaterEqual(int(lines[-4]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 6, proc.stdout)
            self.assertLessEqual(int(lines[-2]), 3, proc.stdout)
            self.assertEqual(float(lines[-1]), 32.0, proc.stdout)

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
            self.assertGreaterEqual(int(lines[-6]), 2, proc.stdout)
            self.assertGreaterEqual(int(lines[-5]), 18, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(float(lines[-2]), 54.0, proc.stdout)
            self.assertEqual(float(lines[-1]), 45.0, proc.stdout)

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
            self.assertGreaterEqual(int(lines[-5]), 12, proc.stdout)
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 6, proc.stdout)
            self.assertEqual(float(lines[-1]), 5.196152422706632, proc.stdout)

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

    def test_instance_value_specialized_opcodes_lower_to_field_ops(self) -> None:
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
            self.assertGreaterEqual(len(lines), 5, proc.stdout)
            self.assertEqual(int(lines[-1]), 200001, proc.stdout)

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

            self.assertLessEqual(bb_count, 52, dump)
            self.assertLessEqual(compiled_size, 2600, proc.stdout)

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
            self.assertIn("DoubleBinaryOp<Add>", dump)
            self.assertIn("DoubleBinaryOp<Subtract>", dump)
            self.assertIn("DoubleBinaryOp<Multiply>", dump)

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

            dump = proc.stdout + "\n" + proc.stderr
            self.assertIn("DoubleBinaryOp<Add>", dump)

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(float(lines[-1]), 1000.0, proc.stdout)

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
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(int(lines[-1]), 7, proc.stdout)

    def test_math_sqrt_cdouble_lowers_to_double_sqrt(self) -> None:
        # Regression guard:
        # builtin math.sqrt on a CDouble input should lower to DoubleSqrt and
        # eliminate the module attr load / VectorCall chain from final HIR.
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
            self.assertGreaterEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(float(lines[-1]), 5.0, proc.stdout)

    def test_from_import_math_sqrt_cdouble_lowers_to_double_sqrt(self) -> None:
        # Regression guard:
        # `from math import sqrt; sqrt(x)` should intrinsify the same way as
        # `import math; math.sqrt(x)` and avoid the VectorCall chain.
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
            self.assertGreaterEqual(int(lines[-6]), 1, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            self.assertEqual(float(lines[-4]), 3.0, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(float(lines[-1]), 4.0, proc.stdout)

    def test_int_float_builtin_lowers_to_double_to_int(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def int_builtin(x):
                return int(x)

            for _ in range(10000):
                int_builtin(3.7)

            assert jit.force_compile(int_builtin)
            counts = cinderjit.get_function_hir_opcode_counts(int_builtin)
            print(counts.get("DoubleToInt", 0))
            print(counts.get("VectorCall", 0))
            print(int_builtin(3.7))
            print(int_builtin(-3.7))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/int_float_builtin_lowering.py"
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
            self.assertEqual(int(lines[-2]), 3, proc.stdout)
            self.assertEqual(int(lines[-1]), -3, proc.stdout)

    def test_round_float_builtin_lowers_to_round_to_int(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def round_builtin(x):
                return round(x)

            for _ in range(10000):
                round_builtin(3.7)

            assert jit.force_compile(round_builtin)
            counts = cinderjit.get_function_hir_opcode_counts(round_builtin)
            print(counts.get("DoubleRoundToInt", 0))
            print(counts.get("VectorCall", 0))
            print(round_builtin(2.5))
            print(round_builtin(3.5))
            print(round_builtin(-0.5))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/round_float_builtin_lowering.py"
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
            self.assertEqual(int(lines[-4]), 0, proc.stdout)
            self.assertEqual(int(lines[-3]), 2, proc.stdout)
            self.assertEqual(int(lines[-2]), 4, proc.stdout)
            self.assertEqual(int(lines[-1]), 0, proc.stdout)

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
        # two-arg builtin min/max on exact floats should avoid the generic
        # VectorCall path while preserving Python result semantics.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit

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
            print(counts_min.get("VectorCall", 0))
            print(counts_max.get("VectorCall", 0))
            print(counts_min.get("PrimitiveCompare", 0))
            print(counts_max.get("PrimitiveCompare", 0))
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
            self.assertGreaterEqual(len(lines), 6, proc.stdout)
            self.assertEqual(int(lines[-6]), 0, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            self.assertGreaterEqual(int(lines[-4]), 1, proc.stdout)
            self.assertGreaterEqual(int(lines[-3]), 1, proc.stdout)
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

    def test_len_truthiness_avoids_boxed_int_compare(self) -> None:
        # Regression guard:
        # `while len(lst):` should not box the length result back to LongExact
        # just to compare it against zero for truthiness.
        code = textwrap.dedent(
            """
            import cinderx.jit as jit

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            def test_len_truthiness(lst):
                hits = 0
                while len(lst):
                    hits += 1
                    break
                return hits

            data = list(range(8))
            for _ in range(100000):
                test_len_truthiness(data)

            assert jit.force_compile(test_len_truthiness)
            print(test_len_truthiness([]))
            print(test_len_truthiness([1]))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/len_truthiness_primitive_bool.py"
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
            self.assertNotIn("PrimitiveBox<CInt64>", dump)
            self.assertIn("GetLengthInt64", dump)
            self.assertIn("PrimitiveCompare<NotEqual>", dump)

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2, proc.stdout)
            self.assertEqual(lines[-2:], ["0", "1"])

    def test_primitive_unbox_cse_for_float_add_self(self) -> None:
        # Regression guard:
        # for g(x) = x + x (float path), final HIR should keep a single
        # PrimitiveUnbox<CDouble> and reuse it for both operands.
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
            self.assertEqual(int(proc.stdout.strip().splitlines()[-1]), 1, proc.stdout)

    def test_primitive_box_remat_elides_frame_state_only_boxes(self) -> None:
        # Regression guard:
        # temporary float boxes that are only kept for FrameState deopt payloads
        # should be rematerialized at deopt time; only the return-value box
        # should remain in final HIR for this shape.
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
            self.assertEqual(int(lines[-2]), 1, proc.stdout)
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
            self.assertIn("PrimitiveBox<CDouble>", dump)
            self.assertLess(
                dump.index("StoreArrayItem"),
                dump.index("PrimitiveBox<CDouble>"),
                dump,
            )

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
            self.assertEqual(int(lines[-5]), 2, proc.stdout)
            self.assertEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
            self.assertEqual(lines[-1], "([10, 20], 30, [40, 50])", proc.stdout)

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

            self.assertGreaterEqual(equal_count, 2, section)
            self.assertEqual(int(proc.stdout.strip().splitlines()[-1]), 0, proc.stdout)

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
            self.assertEqual(int(lines[-7]), 2, proc.stdout)
            self.assertEqual(int(lines[-6]), 1, proc.stdout)
            self.assertEqual(int(lines[-5]), 1, proc.stdout)
            self.assertEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 0, proc.stdout)
            self.assertEqual(int(lines[-2]), 0, proc.stdout)
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
            self.assertGreaterEqual(len(lines), 5, proc.stdout)
            self.assertEqual(int(lines[-5]), 0, proc.stdout)
            self.assertEqual(int(lines[-4]), 1, proc.stdout)
            self.assertEqual(int(lines[-3]), 1, proc.stdout)
            self.assertEqual(int(lines[-2]), 1, proc.stdout)
            self.assertEqual(lines[-1], "{32, 10, 43, 21}", proc.stdout)

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


if __name__ == "__main__":
    unittest.main()
