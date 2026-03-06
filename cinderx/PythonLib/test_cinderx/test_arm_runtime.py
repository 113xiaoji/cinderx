# Copyright (c) Meta Platforms, Inc. and affiliates.

import platform
import os
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

    def test_aarch64_load_module_attr_stub_tracks_invalidation(self) -> None:
        # Regression guard for the AArch64 LoadModuleAttrCached shared fast path:
        # enabling the stub should shrink code for repeated module loads without
        # breaking cache hits or invalidation after the module changes.
        cinderx.jit.enable()
        cinderx.jit.compile_after_n_calls(1000000)

        n_loads = 48

        def build_pi_accumulator():
            lines = ["def f():", "    s = 0.0"]
            lines.extend(["    s += math.pi"] * n_loads)
            lines.append("    return s")
            ns = {"math": math}
            exec("\n".join(lines), ns, ns)
            return ns["f"]

        old_min_calls = os.environ.get("PYTHONJITAARCH64SHAREDSTUBMINCALLS")
        old_pi = math.pi
        try:
            os.environ["PYTHONJITAARCH64SHAREDSTUBMINCALLS"] = "24"
            f = build_pi_accumulator()
            self.assertTrue(cinderx.jit.force_compile(f))
            size_with_stub = cinderx.jit.get_compiled_size(f)

            self.assertAlmostEqual(f(), float(n_loads) * old_pi)
            math.pi = 2.0
            self.assertEqual(f(), float(n_loads) * 2.0)
            math.pi = old_pi
            self.assertAlmostEqual(f(), float(n_loads) * old_pi)

            os.environ["PYTHONJITAARCH64SHAREDSTUBMINCALLS"] = "1000000"
            g = build_pi_accumulator()
            self.assertTrue(cinderx.jit.force_compile(g))
            size_without_stub = cinderx.jit.get_compiled_size(g)
        finally:
            math.pi = old_pi
            if old_min_calls is None:
                os.environ.pop("PYTHONJITAARCH64SHAREDSTUBMINCALLS", None)
            else:
                os.environ["PYTHONJITAARCH64SHAREDSTUBMINCALLS"] = old_min_calls

        self.assertLess(size_with_stub, size_without_stub, (size_with_stub, size_without_stub))

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


if __name__ == "__main__":
    unittest.main()
