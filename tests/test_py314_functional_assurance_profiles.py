import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "scripts" / "arm" / "py314_functional_assurance_profiles.json"


class FunctionalAssuranceProfilesTests(unittest.TestCase):
    def load_profiles(self) -> dict:
        return json.loads(PROFILES.read_text(encoding="utf-8"))

    def test_required_profiles_exist(self) -> None:
        data = self.load_profiles()
        self.assertEqual(
            sorted(data["profiles"]),
            [
                "py314-nightly-extended",
                "py314-pr-core",
                "py314-release-full",
            ],
        )

    def test_matrix_doc_exists(self) -> None:
        path = ROOT / "docs" / "py314-functional-assurance-matrix.md"
        self.assertTrue(path.exists(), path)

    def test_pr_core_baseline_lane_disables_jit_smoke_and_pyperf(self) -> None:
        lane = self.load_profiles()["profiles"]["py314-pr-core"]["baseline"]
        env = lane["remote_env"]
        self.assertEqual(env["SKIP_ARM_RUNTIME"], "1")
        self.assertEqual(env["SKIP_JIT_EFFECTIVENESS_SMOKE"], "1")
        self.assertEqual(env["SKIP_PYPERF_SETUP"], "1")
        self.assertIn(
            "python -m unittest tests/test_py314_functional_assurance_profiles.py -v",
            env["EXTRA_TEST_CMD"],
        )

    def test_pr_core_optimized_lane_keeps_runtime_validation_enabled(self) -> None:
        lane = self.load_profiles()["profiles"]["py314-pr-core"]["optimized"]
        env = lane["remote_env"]
        self.assertEqual(env["SKIP_ARM_RUNTIME"], "1")
        self.assertEqual(env["SKIP_PYPERF_SETUP"], "1")
        self.assertEqual(env["CINDERX_ENABLE_SPECIALIZED_OPCODES"], "1")
        self.assertTrue(
            env["EXTRA_TEST_CMD"].startswith(
                "PYTHONPATH=cinderx/PythonLib python -m unittest "
            )
        )
        self.assertIn(
            "test_cinderx.test_frame_evaluator",
            env["EXTRA_TEST_CMD"],
        )
        self.assertIn("test_cinderx.test_jit_disable", env["EXTRA_TEST_CMD"])
        self.assertIn("test_cinderx.test_jit_exception", env["EXTRA_TEST_CMD"])
        self.assertNotIn("test_cinderx.test_jit_coroutines", env["EXTRA_TEST_CMD"])
        self.assertNotIn("test_cinderx.test_type_cache", env["EXTRA_TEST_CMD"])
        self.assertTrue(env["EXTRA_TEST_CMD"].endswith(" -v"))

    def test_nightly_extended_optimized_lane_runs_full_arm_runtime(self) -> None:
        lane = self.load_profiles()["profiles"]["py314-nightly-extended"]["optimized"]
        env = lane["remote_env"]
        self.assertNotIn("SKIP_ARM_RUNTIME", env)
        self.assertEqual(env["SKIP_PYPERF_SETUP"], "1")
        self.assertTrue(
            env["EXTRA_TEST_CMD"].startswith(
                "PYTHONPATH=cinderx/PythonLib python -m unittest "
            )
        )
        self.assertIn(
            "test_cinderx.test_jit_specialization",
            env["EXTRA_TEST_CMD"],
        )
        self.assertIn("test_cinderx.test_jit_disable", env["EXTRA_TEST_CMD"])
        self.assertNotIn("test_cinderx.test_jit_coroutines", env["EXTRA_TEST_CMD"])
        self.assertNotIn("test_cinderx.test_type_cache", env["EXTRA_TEST_CMD"])
        self.assertTrue(env["EXTRA_TEST_CMD"].endswith(" -v"))

    def test_nightly_extended_baseline_avoids_removed_opcode_expectations(self) -> None:
        lane = self.load_profiles()["profiles"]["py314-nightly-extended"]["baseline"]
        env = lane["remote_env"]
        self.assertTrue(
            env["EXTRA_TEST_CMD"].startswith(
                "PYTHONPATH=cinderx/PythonLib python -m unittest "
            )
        )
        self.assertIn(
            "test_cinderx.test_cpython_overrides.test_dis",
            env["EXTRA_TEST_CMD"],
        )
        self.assertNotIn(
            "test_cinderx.test_cpython_overrides.test__opcode",
            env["EXTRA_TEST_CMD"],
        )


if __name__ == "__main__":
    unittest.main()
