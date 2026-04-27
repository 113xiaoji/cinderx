import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SUMMARIZER = ROOT / "scripts" / "arm" / "summarize_pyperf_subset.py"


def load_summarizer():
    spec = importlib.util.spec_from_file_location("summarize_pyperf_subset", SUMMARIZER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SummarizePyperfSubsetTests(unittest.TestCase):
    def _write_run(self, directory: Path, index: int, value: float) -> None:
        payload = {
            "benchmarks": [
                {
                    "runs": [
                        {
                            "values": [value],
                        },
                    ],
                },
            ],
            "metadata": {
                "name": "richards",
                "unit": "second",
            },
            "version": "1.0",
        }
        (directory / f"run_{index}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def test_uses_top_level_metadata_name_from_pyperformance_114(self) -> None:
        summarizer = load_summarizer()

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            self._write_run(tmpdir, 1, 0.120)
            self._write_run(tmpdir, 2, 0.124)
            output = tmpdir / "summary.json"

            summarizer.summarize(
                tmpdir,
                output,
                ["richards"],
                samples=2,
                autojit=50,
            )

            summary = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(summary["benchmark_filter"], ["richards"])
        self.assertEqual(summary["samples"], 2)
        self.assertEqual(summary["autojit"], 50)
        self.assertEqual(
            summary["benchmarks"],
            [
                {
                    "name": "richards",
                    "samples": [0.120, 0.124],
                    "median": 0.122,
                    "min": 0.120,
                    "max": 0.124,
                },
            ],
        )

    def test_skips_malformed_runs_without_dropping_valid_samples(self) -> None:
        summarizer = load_summarizer()

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            self._write_run(tmpdir, 1, 0.271)
            (tmpdir / "run_2.json").write_text(
                json.dumps({"benchmarks": [{"runs": [{"values": []}]}]}),
                encoding="utf-8",
            )
            output = tmpdir / "summary.json"

            summarizer.summarize(
                tmpdir,
                output,
                ["go"],
                samples=2,
                autojit=20,
            )

            summary = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(len(summary["benchmarks"]), 1)
        self.assertEqual(summary["benchmarks"][0]["samples"], [0.271])


if __name__ == "__main__":
    unittest.main()
