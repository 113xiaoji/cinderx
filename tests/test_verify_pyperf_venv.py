from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFY_PYPERF_VENV = ROOT / "scripts" / "arm" / "verify_pyperf_venv.py"


class VerifyPyperfVenvScriptTests(unittest.TestCase):
    def test_worker_probe_prefers_cinderjit_before_cinderx_jit(self) -> None:
        text = VERIFY_PYPERF_VENV.read_text(encoding="utf-8")
        self.assertIn("import cinderjit as jit_ext", text)
        self.assertIn("import cinderx.jit as jit_ext", text)
        self.assertLess(
            text.index("import cinderjit as jit_ext"),
            text.index("import cinderx.jit as jit_ext"),
        )


if __name__ == "__main__":
    unittest.main()
