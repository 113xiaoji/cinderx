import types
import unittest
from unittest.mock import patch

import cinderx


class RuntimeSupportPolicyTests(unittest.TestCase):
    def test_supports_linux_314_when_gil_is_enabled(self) -> None:
        version_info = types.SimpleNamespace(major=3, minor=14)
        with (
            patch.object(cinderx.sys, "platform", "linux"),
            patch.object(cinderx.sys, "version_info", version_info),
            patch.dict(cinderx.environ, {"PYTHON_GIL": "1"}, clear=False),
        ):
            self.assertTrue(cinderx.is_supported_runtime())

    def test_supports_linux_315_when_gil_is_enabled(self) -> None:
        version_info = types.SimpleNamespace(major=3, minor=15)
        with (
            patch.object(cinderx.sys, "platform", "linux"),
            patch.object(cinderx.sys, "version_info", version_info),
            patch.dict(cinderx.environ, {"PYTHON_GIL": "1"}, clear=False),
        ):
            self.assertTrue(cinderx.is_supported_runtime())

    def test_rejects_linux_316_until_registered(self) -> None:
        version_info = types.SimpleNamespace(major=3, minor=16)
        with (
            patch.object(cinderx.sys, "platform", "linux"),
            patch.object(cinderx.sys, "version_info", version_info),
            patch.dict(cinderx.environ, {"PYTHON_GIL": "1"}, clear=False),
        ):
            self.assertFalse(cinderx.is_supported_runtime())


if __name__ == "__main__":
    unittest.main()
