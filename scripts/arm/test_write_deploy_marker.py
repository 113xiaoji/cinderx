import json
import subprocess
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
MARKER_SCRIPT = SCRIPT_DIR / "write_deploy_marker.py"


class WriteDeployMarkerTests(unittest.TestCase):
    def test_writes_source_commit_and_file_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            workdir = tmpdir / "work"
            workdir.mkdir()
            tracked = workdir / "cinderx" / "Jit" / "pyjit.cpp"
            tracked.parent.mkdir(parents=True)
            tracked.write_text("int main() { return 0; }\n", encoding="utf-8")

            output = tmpdir / "marker.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(MARKER_SCRIPT),
                    "--output",
                    str(output),
                    "--source-commit",
                    "abc123",
                    "--workdir",
                    str(workdir),
                    "--wheel",
                    "dist/example.whl",
                    "--build-no-isolation",
                    "1",
                    "--skip-pyperf",
                    "1",
                    "--path",
                    "cinderx/Jit/pyjit.cpp",
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
            self.assertEqual(data["source_commit"], "abc123")
            self.assertEqual(data["wheel"], "dist/example.whl")
            self.assertTrue(data["build_no_isolation"])
            self.assertTrue(data["skip_pyperf"])
            self.assertEqual(len(data["files"]), 1)
            file_info = data["files"][0]
            self.assertEqual(file_info["path"], "cinderx/Jit/pyjit.cpp")
            self.assertTrue(file_info["exists"])
            expected = sha256(tracked.read_bytes()).hexdigest()
            self.assertEqual(file_info["sha256"], expected)


if __name__ == "__main__":
    unittest.main()
