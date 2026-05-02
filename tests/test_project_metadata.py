from pathlib import Path


def test_readme_mentions_314x_support() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert "CPython 3.14.x and 3.15" in text
    assert "3.14.3 or later" not in text


def test_pyproject_limits_oss_release_to_314_family() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">= 3.14.0, < 3.16"' in text
    assert '"Programming Language :: Python :: 3.14"' in text
    assert '"Programming Language :: Python :: 3.15"' in text
    assert 'cp314-manylinux_x86_64' in text
    assert 'cp315-manylinux_x86_64' in text
