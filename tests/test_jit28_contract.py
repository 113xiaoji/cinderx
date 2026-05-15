import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def load_contract_module():
    module_path = Path("scripts/arm/jit28_contract.py")
    spec = importlib.util.spec_from_file_location("jit28_contract", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Jit28ContractTests(unittest.TestCase):
    def write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def test_suite_lock_must_match_manifest_hash_and_resolved_cases(self):
        mod = load_contract_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            suite_path = root / "benchmark-contract" / "suites" / "suite.json"
            lock_path = root / "benchmark-contract" / "suites" / "suite.lock.json"
            contract_path = root / "benchmark-contract" / "contract.json"

            suite = {
                "suite_id": "sample-suite-v1",
                "runner": "pyperformance",
                "selection": {
                    "mode": "pyperformance_filter",
                    "selectors": ["logging"],
                },
            }
            self.write_json(suite_path, suite)
            digest = mod.canonical_json_sha256(suite)
            self.write_json(
                lock_path,
                {
                    "suite_id": "sample-suite-v1",
                    "runner": "pyperformance",
                    "manifest_sha256": digest,
                    "case_count": 3,
                    "resolved_cases": [
                        "logging_format",
                        "logging_silent",
                        "logging_simple",
                    ],
                },
            )
            self.write_json(
                contract_path,
                {
                    "contract_id": "sample-contract-v1",
                    "schema_version": 1,
                    "suite_manifest": "benchmark-contract/suites/suite.json",
                    "suite_lock": "benchmark-contract/suites/suite.lock.json",
                    "runner": "pyperformance",
                    "samples": 12,
                    "autojit": 50,
                    "expected_case_count": 3,
                },
            )

            contract = mod.load_contract(contract_path)
            self.assertEqual(contract.selectors, ["logging"])
            self.assertEqual(
                contract.resolved_cases,
                ["logging_format", "logging_silent", "logging_simple"],
            )
            self.assertEqual(contract.suite_manifest_sha256, digest)

            bad_lock = json.loads(lock_path.read_text(encoding="utf-8"))
            bad_lock["resolved_cases"] = ["logging_format", "logging_simple"]
            self.write_json(lock_path, bad_lock)
            with self.assertRaisesRegex(mod.ContractError, "resolved case count"):
                mod.load_contract(contract_path)

    def test_summary_validation_requires_contract_cases_and_sample_count(self):
        mod = load_contract_module()
        contract = mod.Contract(
            root=Path("."),
            contract_path=Path("contract.json"),
            contract_id="sample-contract-v1",
            runner="pyperformance",
            samples=3,
            autojit=50,
            expected_case_count=2,
            selectors=["chaos", "go"],
            resolved_cases=["chaos", "go"],
            suite_id="sample-suite-v1",
            suite_manifest_sha256="abc",
        )
        valid_summary = {
            "contract_id": "sample-contract-v1",
            "suite_id": "sample-suite-v1",
            "suite_manifest_sha256": "abc",
            "benchmark_filter": ["chaos", "go"],
            "samples": 3,
            "autojit": 50,
            "benchmarks": [
                {"name": "chaos", "samples": [1.0, 1.1, 1.2], "median": 1.1},
                {"name": "go", "samples": [2.0, 2.1, 2.2], "median": 2.1},
            ],
        }
        mod.validate_summary(contract, valid_summary)

        unstamped_summary = json.loads(json.dumps(valid_summary))
        del unstamped_summary["contract_id"]
        with self.assertRaisesRegex(mod.ContractError, "missing required metadata"):
            mod.validate_summary(contract, unstamped_summary)

        invalid_summary = json.loads(json.dumps(valid_summary))
        invalid_summary["benchmarks"][1]["samples"] = [2.0, 2.1]
        with self.assertRaisesRegex(mod.ContractError, "sample count"):
            mod.validate_summary(contract, invalid_summary)

    def test_compare_summaries_marks_real_gain_only_when_ci_excludes_zero(self):
        mod = load_contract_module()
        contract = mod.Contract(
            root=Path("."),
            contract_path=Path("contract.json"),
            contract_id="sample-contract-v1",
            runner="pyperformance",
            samples=3,
            autojit=50,
            expected_case_count=2,
            selectors=["chaos", "go"],
            resolved_cases=["chaos", "go"],
            suite_id="sample-suite-v1",
            suite_manifest_sha256="abc",
        )
        base = {
            "contract_id": "sample-contract-v1",
            "suite_id": "sample-suite-v1",
            "suite_manifest_sha256": "abc",
            "benchmark_filter": ["chaos", "go"],
            "samples": 3,
            "autojit": 50,
            "benchmarks": [
                {"name": "chaos", "samples": [1.0, 1.0, 1.0], "median": 1.0},
                {"name": "go", "samples": [2.0, 2.0, 2.0], "median": 2.0},
            ],
        }
        candidate = {
            "contract_id": "sample-contract-v1",
            "suite_id": "sample-suite-v1",
            "suite_manifest_sha256": "abc",
            "benchmark_filter": ["chaos", "go"],
            "samples": 3,
            "autojit": 50,
            "benchmarks": [
                {"name": "chaos", "samples": [0.9, 0.9, 0.9], "median": 0.9},
                {"name": "go", "samples": [1.8, 1.8, 1.8], "median": 1.8},
            ],
        }

        report = mod.compare_summaries(
            contract,
            base,
            candidate,
            bootstrap_samples=200,
            seed=123,
        )

        self.assertLess(report["geomean_pct"], 0)
        self.assertLess(report["geomean_bootstrap_95ci_pct"][1], 0)
        self.assertEqual(report["conclusion"], "real_gain")

    def test_compare_reports_requires_same_contract_and_stable_conclusion(self):
        mod = load_contract_module()
        left = {
            "contract_id": "jit28-fixed-s12-v1",
            "suite_id": "jit28-candidates-v1",
            "suite_manifest_sha256": "abc",
            "case_count": 28,
            "samples": 12,
            "autojit": 50,
            "geomean_pct": 0.11,
            "geomean_bootstrap_95ci_pct": [-0.4, 0.7],
            "conclusion": "noise",
        }
        right = dict(left)
        right["geomean_pct"] = 0.22
        right["geomean_bootstrap_95ci_pct"] = [-0.3, 0.8]

        result = mod.compare_reports(left, right, max_geomean_diff_pct=0.5)
        self.assertTrue(result["consistent"])
        self.assertEqual(result["reason"], "same_contract_same_conclusion")

        changed = dict(right)
        changed["conclusion"] = "real_regression"
        changed_result = mod.compare_reports(left, changed, max_geomean_diff_pct=0.5)
        self.assertFalse(changed_result["consistent"])
        self.assertEqual(changed_result["reason"], "different_conclusion")

        wrong_suite = dict(right)
        wrong_suite["suite_manifest_sha256"] = "def"
        with self.assertRaisesRegex(mod.ContractError, "report metadata mismatch"):
            mod.compare_reports(left, wrong_suite, max_geomean_diff_pct=0.5)

    def test_subset_runner_is_workdir_pinned_and_hook_overridable(self):
        text = Path("scripts/arm/run_pyperf_subset.sh").read_text(encoding="utf-8")

        self.assertIn('cd "$WORKDIR"', text)
        self.assertIn('HOOK_DIR="${HOOK_DIR:-$WORKDIR/scripts/arm/pyperf_env_hook}"', text)
        self.assertIn("LD_LIBRARY_PATH", text)
        self.assertIn("pyperf_subset_inherit_environ", text)

    def test_contract_runner_uses_external_suite_not_hardcoded_benchmarks(self):
        text = Path("scripts/arm/run_jit28_contract_compare.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("CONTRACT_TOOL", text)
        self.assertIn("emit-benchmarks", text)
        self.assertIn("stamp-summary", text)
        self.assertIn(" compare \\", text)
        self.assertIn('bash "$SUBSET_RUNNER"', text)
        self.assertNotIn("chaos,comprehensions", text)

    def test_contract_runner_fails_closed_on_worker_jit_probe(self):
        text = Path("scripts/arm/run_jit28_contract_compare.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("VERIFY_TOOL", text)
        self.assertIn("verify_pyperf_venv.py", text)
        self.assertIn("--require-sitecustomize-prefix", text)
        self.assertIn("--require-cinderx-initialized", text)
        self.assertIn("--require-jit-enabled", text)
        self.assertIn("--require-compile-after", text)
        self.assertIn("LD_LIBRARY_PATH", text)

    def test_runner_hook_sets_worker_compile_after_threshold(self):
        text = Path("scripts/arm/pyperf_env_hook/sitecustomize.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("compile_after_n_calls", text)
        self.assertIn("CINDERX_WORKER_PYTHONJITAUTO", text)


if __name__ == "__main__":
    unittest.main()
