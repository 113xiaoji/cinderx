import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SUMMARIZE_SCRIPT = SCRIPT_DIR / "summarize_pyperf_subset.py"
COMPARE_SCRIPT = SCRIPT_DIR / "compare_pyperf_subset.py"


class PyperfSubsetToolsTests(unittest.TestCase):
    def test_summarize_infers_benchmark_name_and_preserves_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            raw = {
                "benchmarks": [
                    {
                        "runs": [
                            {
                                "values": [0.5313446190002651],
                            }
                        ]
                    }
                ],
                "metadata": {},
                "version": "1.0",
            }
            (tmpdir / "run_1.json").write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            output = tmpdir / "summary.json"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(SUMMARIZE_SCRIPT),
                    "--tmpdir",
                    str(tmpdir),
                    "--output",
                    str(output),
                    "--benchmarks",
                    "fannkuch",
                    "--samples",
                    "1",
                    "--autojit",
                    "50",
                    "--run-label",
                    "day1-current",
                    "--baseline-ref",
                    "fb105b6b",
                    "--workdir",
                    str(tmpdir),
                    "--specialized-opcodes",
                    "1",
                    "--jitlist-entries",
                    "",
                    "--git-commit",
                    "734ca08a",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["run_label"], "day1-current")
            self.assertEqual(data["baseline_ref"], "fb105b6b")
            self.assertEqual(data["git_commit"], "734ca08a")
            self.assertEqual(len(data["benchmarks"]), 1)
            self.assertEqual(data["benchmarks"][0]["name"], "fannkuch")
            self.assertAlmostEqual(
                data["benchmarks"][0]["median"],
                0.5313446190002651,
            )

    def test_compare_keeps_run_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            base = {
                "benchmarks": [{"name": "fannkuch", "median": 0.50}],
                "benchmark_filter": ["fannkuch"],
                "samples": 1,
                "autojit": 50,
                "run_label": "baseline",
                "baseline_ref": "fb105b6b",
                "git_commit": "fb105b6b",
            }
            current = {
                "benchmarks": [{"name": "fannkuch", "median": 0.55}],
                "benchmark_filter": ["fannkuch"],
                "samples": 1,
                "autojit": 50,
                "run_label": "current",
                "baseline_ref": "fb105b6b",
                "git_commit": "734ca08a",
            }
            base_path = tmpdir / "base.json"
            current_path = tmpdir / "current.json"
            output = tmpdir / "compare.json"
            base_path.write_text(
                json.dumps(base, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            current_path.write_text(
                json.dumps(current, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    str(COMPARE_SCRIPT),
                    "--base",
                    str(base_path),
                    "--current",
                    str(current_path),
                    "--output",
                    str(output),
                    "--warn-threshold-pct",
                    "5",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )

            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["base_metadata"]["run_label"], "baseline")
            self.assertEqual(data["current_metadata"]["run_label"], "current")
            self.assertEqual(data["base_metadata"]["git_commit"], "fb105b6b")
            self.assertEqual(data["current_metadata"]["git_commit"], "734ca08a")
            self.assertEqual(len(data["rows"]), 1)
            self.assertGreater(data["rows"][0]["delta_pct"], 5.0)

    def test_compare_rejects_mismatched_run_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            base = {
                "benchmarks": [{"name": "fannkuch", "median": 0.50}],
                "benchmark_filter": ["fannkuch"],
                "samples": 1,
                "autojit": 50,
                "run_label": "baseline",
                "baseline_ref": "fb105b6b",
                "git_commit": "fb105b6b",
            }
            current = {
                "benchmarks": [{"name": "fannkuch", "median": 0.55}],
                "benchmark_filter": ["go"],
                "samples": 3,
                "autojit": 100,
                "run_label": "current",
                "baseline_ref": "fb105b6b",
                "git_commit": "734ca08a",
            }
            base_path = tmpdir / "base.json"
            current_path = tmpdir / "current.json"
            output = tmpdir / "compare.json"
            base_path.write_text(
                json.dumps(base, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            current_path.write_text(
                json.dumps(current, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    str(COMPARE_SCRIPT),
                    "--base",
                    str(base_path),
                    "--current",
                    str(current_path),
                    "--output",
                    str(output),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("benchmark_filter", proc.stderr)


if __name__ == "__main__":
    unittest.main()
