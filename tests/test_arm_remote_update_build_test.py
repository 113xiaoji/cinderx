from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REMOTE_HELPER = ROOT / "scripts" / "arm" / "remote_update_build_test.sh"


class RemoteUpdateBuildTestScriptTests(unittest.TestCase):
    def test_build_uses_no_isolation(self) -> None:
        text = REMOTE_HELPER.read_text(encoding="utf-8")
        self.assertIn('"$PY" -m build --wheel -n', text)

    def test_driver_venv_pip_commands_disable_cinderx_autoload(self) -> None:
        text = REMOTE_HELPER.read_text(encoding="utf-8")
        self.assertIn(
            "CINDERX_DISABLE=1 PYTHONJIT=0 python -m pip install -q -U pip",
            text,
        )
        self.assertIn(
            'CINDERX_DISABLE=1 PYTHONJIT=0 python -m pip install -q --force-reinstall "$WHEEL"',
            text,
        )
        self.assertIn(
            "CINDERX_DISABLE=1 PYTHONJIT=0 python -m pip install -q -U pyperformance",
            text,
        )

    def test_driver_venv_pyperformance_management_disables_cinderx_autoload(
        self,
    ) -> None:
        text = REMOTE_HELPER.read_text(encoding="utf-8")
        self.assertIn(
            'CINDERX_DISABLE=1 PYTHONJIT=0 "${cmd[@]}"',
            text,
        )
        self.assertIn(
            'CINDERX_DISABLE=1 PYTHONJIT=0 python -m pyperformance venv show',
            text,
        )


if __name__ == "__main__":
    unittest.main()
