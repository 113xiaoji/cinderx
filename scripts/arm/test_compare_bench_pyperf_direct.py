import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).with_name("compare_bench_pyperf_direct.py")
SPEC = importlib.util.spec_from_file_location("compare_bench_pyperf_direct", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CompareBenchPyperfDirectTests(unittest.TestCase):
    def test_build_plain_args_uses_recipe_identity_fields(self):
        recipe = {
            "benchmark_name": "bm_go",
            "module_name": "bm_go_recipe",
            "bench_func": "versus_cpu",
            "bench_args": [],
            "stub_pyperf": True,
            "specialized_opcodes": True,
            "prewarm_runs": 2,
        }
        args = MODULE.build_plain_args(recipe, 3, Path("plain.json"))
        self.assertIn("--benchmark-name", args)
        self.assertIn("bm_go", args)
        self.assertIn("--module-name", args)
        self.assertIn("bm_go_recipe", args)
        self.assertIn("--bench-func", args)
        self.assertIn("versus_cpu", args)
        self.assertIn("--stub-pyperf", args)
        self.assertIn("--specialized-opcodes", args)
        self.assertIn("--prewarm-runs", args)

    def test_build_compare_payload_computes_delta(self):
        payload = MODULE.build_compare_payload(
            Path("recipe.json"),
            {
                "benchmark_name": "bm_go",
                "bench_func": "versus_cpu",
                "median_wall_sec": 2.0,
                "samples": [{"wall_sec": 2.0}],
            },
            {
                "recipe_name": "bm_go_board_useful",
                "benchmark_name": "bm_go",
                "bench_func": "versus_cpu",
                "median_wall_sec": 1.5,
                "samples": [{"wall_sec": 1.5}],
            },
        )
        self.assertEqual(payload["recipe_name"], "bm_go_board_useful")
        self.assertEqual(payload["benchmark_name"], "bm_go")
        self.assertEqual(payload["bench_func"], "versus_cpu")
        self.assertAlmostEqual(payload["delta_pct"], -25.0)

    def test_main_runs_plain_and_recipe_and_writes_output(self):
        recipe = {
            "name": "bm_go_board_useful",
            "benchmark_name": "bm_go",
            "module_name": "bm_go_recipe",
            "bench_func": "versus_cpu",
            "bench_args": [],
            "stub_pyperf": True,
        }

        def fake_run_command(args):
            output_idx = args.index("--output") + 1
            output_path = Path(args[output_idx])
            if "--recipe-json" in args:
                payload = {
                    "recipe_name": "bm_go_board_useful",
                    "benchmark_name": "bm_go",
                    "bench_func": "versus_cpu",
                    "median_wall_sec": 1.5,
                    "samples": [{"wall_sec": 1.5}],
                }
            else:
                payload = {
                    "benchmark_name": "bm_go",
                    "bench_func": "versus_cpu",
                    "median_wall_sec": 2.0,
                    "samples": [{"wall_sec": 2.0}],
                }
            output_path.write_text(json.dumps(payload), encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            recipe_path = Path(tmp) / "recipe.json"
            recipe_path.write_text(json.dumps(recipe), encoding="utf-8")
            output_path = Path(tmp) / "compare.json"

            with patch.object(MODULE, "run_command", side_effect=fake_run_command):
                with patch("sys.argv", [
                    "compare_bench_pyperf_direct.py",
                    "--recipe-json",
                    str(recipe_path),
                    "--samples",
                    "3",
                    "--output",
                    str(output_path),
                ]):
                    rc = MODULE.main()

            self.assertEqual(rc, 0)
            compare = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(compare["recipe_name"], "bm_go_board_useful")
            self.assertEqual(compare["benchmark_name"], "bm_go")
            self.assertAlmostEqual(compare["delta_pct"], -25.0)


if __name__ == "__main__":
    unittest.main()
