from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parent
VERIFY = ROOT / "verify_pyperf_venv.py"


def load_module():
    spec = importlib.util.spec_from_file_location("_issue63_verify_pyperf_venv", VERIFY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {VERIFY}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifyPyperfVenvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def setUp(self) -> None:
        self.saved_disable = os.environ.get("PYTHONJITDISABLE")

    def tearDown(self) -> None:
        if self.saved_disable is None:
            os.unsetenv("PYTHONJITDISABLE")
            os.environ.pop("PYTHONJITDISABLE", None)
        else:
            os.putenv("PYTHONJITDISABLE", self.saved_disable)
            os.environ["PYTHONJITDISABLE"] = self.saved_disable

    def test_worker_probe_strips_pythonjitdisable_for_marked_worker(self) -> None:
        os.environ["PYTHONJITDISABLE"] = "1"
        result = self.module.worker_probe(
            Path(sys.executable),
            [],
            env_overrides={
                "CINDERX_PYPERF_WORKER": "1",
                "CINDERX_WORKER_PYTHONJITAUTO": "10",
            },
        )
        self.assertEqual(result["returncode"], 0)
        summary = result["summary"]
        self.assertIsNone(summary["PYTHONJITDISABLE"])

    def test_worker_probe_preserves_pythonjitdisable_without_worker_marker(self) -> None:
        os.environ["PYTHONJITDISABLE"] = "1"
        result = self.module.worker_probe(Path(sys.executable), [])
        self.assertEqual(result["returncode"], 0)
        summary = result["summary"]
        self.assertEqual(summary["PYTHONJITDISABLE"], "1")


if __name__ == "__main__":
    unittest.main()
