# 3.14.x Compatibility Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `3.14.x` the explicit, well-verified OSS support family for CinderX while removing misleading `3.14.3`-only operational assumptions and leaving clean extension points for future `3.15` / `3.16` onboarding.

**Architecture:** Introduce one compatibility policy source that currently publishes only the `3.14` family, then make runtime gating, setup defaults, tests, docs, and release metadata consume that policy. Keep shipping only `cp314` artifacts in this phase, but refactor hardcoded minor checks into table-driven helpers so future minors can be added without another repo-wide sweep.

**Tech Stack:** Python packaging (`setuptools`, `cibuildwheel`), CMake build selection, GitHub Actions, PowerShell + bash remote ARM entry scripts, pytest/unittest.

---

### Task 1: Introduce a single 3.14 compatibility policy module

**Files:**
- Create: `C:\work\code\cinderx4\cinderx\PythonLib\cinderx\_compat.py`
- Create: `C:\work\code\cinderx4\tests\test_compat_policy.py`

- [ ] **Step 1: Write the failing policy tests**

```python
from cinderx import _compat


def test_oss_support_family_is_only_314() -> None:
    assert _compat.OSS_SUPPORTED_MINOR_FAMILIES == ("3.14",)


def test_314_validated_patches_are_explicit() -> None:
    family = _compat.get_family_policy("3.14")
    assert family.validated_patches == ("3.14.0", "3.14.1", "3.14.2", "3.14.3")
    assert family.default_build_patch == "3.14.3"
    assert family.publish_wheels is True


def test_unknown_minor_family_is_not_supported() -> None:
    assert _compat.get_family_policy("3.15") is None
    assert _compat.get_family_policy("3.16") is None
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_compat_policy.py -q
```

Expected: FAIL because `cinderx._compat` does not exist yet.

- [ ] **Step 3: Add the compatibility policy module**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FamilyPolicy:
    minor: str
    validated_patches: tuple[str, ...]
    default_build_patch: str
    publish_wheels: bool


OSS_SUPPORTED_MINOR_FAMILIES = ("3.14",)

_FAMILY_POLICIES: dict[str, FamilyPolicy] = {
    "3.14": FamilyPolicy(
        minor="3.14",
        validated_patches=("3.14.0", "3.14.1", "3.14.2", "3.14.3"),
        default_build_patch="3.14.3",
        publish_wheels=True,
    ),
}


def get_family_policy(minor: str) -> FamilyPolicy | None:
    return _FAMILY_POLICIES.get(minor)
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_compat_policy.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cinderx/PythonLib/cinderx/_compat.py tests/test_compat_policy.py
git commit -m "feat: add 3.14 compatibility policy"
```

### Task 2: Move setup defaults and runtime support gating onto the policy

**Files:**
- Modify: `C:\work\code\cinderx4\setup.py`
- Modify: `C:\work\code\cinderx4\cinderx\PythonLib\cinderx\__init__.py`
- Modify: `C:\work\code\cinderx4\tests\test_setup_adaptive_static_python.py`
- Modify: `C:\work\code\cinderx4\tests\test_setup_lightweight_frames.py`

- [ ] **Step 1: Write the failing policy-driven setup/runtime tests**

```python
import setup
from cinderx import _compat


def test_runtime_support_is_driven_by_policy() -> None:
    assert _compat.get_family_policy("3.14") is not None
    assert _compat.get_family_policy("3.15") is None


def test_adaptive_static_default_is_enabled_for_314_arm_only() -> None:
    assert setup.should_enable_adaptive_static_python("3.14", False, "aarch64") is True
    assert setup.should_enable_adaptive_static_python("3.14", False, "x86_64") is False
    assert setup.should_enable_adaptive_static_python("3.15", False, "aarch64") is False


def test_lightweight_frames_default_is_enabled_for_314_arm_only() -> None:
    assert setup.should_enable_lightweight_frames("3.14", False, "arm64") is True
    assert setup.should_enable_lightweight_frames("3.14", False, "x86_64") is False
    assert setup.should_enable_lightweight_frames("3.15", False, "arm64") is False
```

- [ ] **Step 2: Run the setup/runtime tests to verify they fail for the right reason**

Run:

```powershell
python -m pytest tests/test_setup_adaptive_static_python.py tests/test_setup_lightweight_frames.py tests/test_compat_policy.py -q
```

Expected: FAIL because setup/runtime code still hardcodes `3.14` / `3.15` behavior instead of consuming the policy.

- [ ] **Step 3: Refactor setup/runtime code to use the policy**

```python
# setup.py
def is_supported_oss_minor(py_version: str) -> bool:
    return get_family_policy(py_version) is not None


def should_enable_adaptive_static_python(py_version: str, meta_python: bool, machine: str | None = None) -> bool:
    if meta_python and py_version == "3.12":
        return True
    if get_family_policy(py_version) is None:
        return False
    machine = (machine or platform.machine()).lower()
    return py_version == "3.14" and machine in {"aarch64", "arm64"}
```

```python
# cinderx/__init__.py
version = f"{sys.version_info.major}.{sys.version_info.minor}"
if get_family_policy(version) is not None:
    return environ.get("PYTHON_GIL") != "0"
```

- [ ] **Step 4: Run the setup/runtime tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_setup_adaptive_static_python.py tests/test_setup_lightweight_frames.py tests/test_compat_policy.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add setup.py cinderx/PythonLib/cinderx/__init__.py tests/test_setup_adaptive_static_python.py tests/test_setup_lightweight_frames.py tests/test_compat_policy.py
git commit -m "refactor: drive 3.14 support gates from compatibility policy"
```

### Task 3: Align OSS smoke tests with the 3.14 compatibility policy

**Files:**
- Modify: `C:\work\code\cinderx4\cinderx\PythonLib\test_cinderx\test_oss_quick.py`

- [ ] **Step 1: Write the failing OSS smoke expectation change**

```python
def expected_oss_runtime_features() -> tuple[bool, bool]:
    machine = platform.machine().lower()
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    family = _compat.get_family_policy(version)
    if family is None:
        return (False, False)
    is_314_arm = version == "3.14" and machine in {"aarch64", "arm64"}
    return (is_314_arm, is_314_arm)
```

- [ ] **Step 2: Run the OSS smoke test to verify the current code does not yet use the policy**

Run:

```powershell
python -m pytest cinderx/PythonLib/test_cinderx/test_oss_quick.py -q
```

Expected: FAIL after the test is updated because the test still uses its own hardcoded runtime expectations.

- [ ] **Step 3: Update the OSS smoke test to use the policy-derived expectation**

```python
adaptive_expected, lightweight_expected = expected_oss_runtime_features()
self.assertEqual(enabled, adaptive_expected)
```

- [ ] **Step 4: Run the OSS smoke test to verify it passes**

Run:

```powershell
python -m pytest cinderx/PythonLib/test_cinderx/test_oss_quick.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cinderx/PythonLib/test_cinderx/test_oss_quick.py
git commit -m "test: align OSS smoke expectations with 3.14 policy"
```

### Task 4: Align docs and packaging metadata with 3.14.x-only OSS support

**Files:**
- Modify: `C:\work\code\cinderx4\README.md`
- Modify: `C:\work\code\cinderx4\pyproject.toml`
- Modify: `C:\work\code\cinderx4\build\fbcode_builder\manifests\python-3_14`
- Modify: `C:\work\code\cinderx4\.github\workflows\publish.yml`

- [ ] **Step 1: Write the failing metadata/documentation checks**

```python
from pathlib import Path


def test_readme_mentions_314x_support() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert "Python 3.14.x" in text
    assert "3.14.3 or later" not in text


def test_pyproject_limits_oss_release_to_314_family() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">= 3.14.0, < 3.15"' in text
    assert 'cp314-manylinux_x86_64' in text
```

- [ ] **Step 2: Run the metadata/documentation checks to verify they fail**

Run:

```powershell
python -m pytest tests/test_compat_policy.py -q
```

Expected: FAIL after adding the assertions because current docs/metadata still mention `3.14.3` and `< 3.16`.

- [ ] **Step 3: Apply the metadata/doc changes**

```toml
requires-python = ">= 3.14.0, < 3.15"
classifiers = [
    "Programming Language :: Python :: 3.14",
]
```

```markdown
## Requirements

- CPython 3.14.x
- Linux (x86_64)
- GCC 13+ or Clang 18+
```

```toml
# This manifest intentionally pins the default build baseline to 3.14.3.
# It does not define the full OSS support range, which is tracked separately as 3.14.x.
url = https://github.com/python/cpython/archive/refs/tags/v3.14.3.tar.gz
```

- [ ] **Step 4: Run the metadata/documentation checks to verify they pass**

Run:

```powershell
python -m pytest tests/test_compat_policy.py -q
```

Expected: PASS after the assertions are added to the test file.

- [ ] **Step 5: Commit**

```bash
git add README.md pyproject.toml build/fbcode_builder/manifests/python-3_14 .github/workflows/publish.yml tests/test_compat_policy.py
git commit -m "docs: align OSS support statement to 3.14.x"
```

### Task 5: Make the remote ARM entrypoint usable for targeted 3.14.x verification

**Files:**
- Modify: `C:\work\code\cinderx4\scripts\push_to_arm.ps1`
- Modify: `C:\work\code\cinderx4\scripts\arm\remote_update_build_test.sh`

- [ ] **Step 1: Add a failing verification scenario to justify the interface**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx4 `
  -SkipPyperformance
```

Expected: the current wrapper can only trigger the default ARM smoke path; it cannot inject targeted `pytest` commands or switch between validated `3.14.x` runtimes in a structured way.

- [ ] **Step 2: Add passthrough parameters for targeted verification**

```powershell
[string]$ExtraTestCmd = "",
[string]$ExtraVerifyCmd = ""
```

```powershell
"EXTRA_TEST_CMD=$ExtraTestCmd",
"EXTRA_VERIFY_CMD=$ExtraVerifyCmd"
```

- [ ] **Step 3: Verify the updated entrypoint can run targeted checks through the unified remote path**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx4 `
  -SkipPyperformance `
  -RemotePython /opt/python-3.14/bin/python3.14 `
  -RemoteDriverVenv /root/venv-cinderx314 `
  -ExtraTestCmd "python -m pytest tests/test_compat_policy.py tests/test_setup_adaptive_static_python.py tests/test_setup_lightweight_frames.py cinderx/PythonLib/test_cinderx/test_oss_quick.py -q"
```

Expected: remote build succeeds and the targeted tests run through `remote_update_build_test.sh`.

- [ ] **Step 4: Commit**

```bash
git add scripts/push_to_arm.ps1 scripts/arm/remote_update_build_test.sh
git commit -m "chore: expose targeted 3.14 verification through remote entrypoint"
```

### Task 6: Run the 3.14.x verification matrix and record the results

**Files:**
- Modify: `C:\work\code\cinderx4\findings.md`

- [ ] **Step 1: Run the default 3.14 baseline through the unified remote path**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx4 `
  -SkipPyperformance `
  -RemotePython /opt/python-3.14/bin/python3.14 `
  -RemoteDriverVenv /root/venv-cinderx314 `
  -ExtraTestCmd "python -m pytest tests/test_compat_policy.py tests/test_setup_adaptive_static_python.py tests/test_setup_lightweight_frames.py cinderx/PythonLib/test_cinderx/test_oss_quick.py -q"
```

Expected: PASS on the current default `3.14` baseline.

- [ ] **Step 2: Run one additional validated 3.14 patch baseline through the same entrypoint**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx4 `
  -SkipPyperformance `
  -RemotePython /opt/python-3.14.0/bin/python3.14 `
  -RemoteDriverVenv /root/venv-cinderx3140 `
  -ExtraTestCmd "python -m pytest tests/test_compat_policy.py tests/test_setup_adaptive_static_python.py tests/test_setup_lightweight_frames.py cinderx/PythonLib/test_cinderx/test_oss_quick.py -q"
```

Expected: PASS if that interpreter/venv pair is provisioned on the ARM host; if not provisioned yet, provision it first and record the actual path in `findings.md`.

- [ ] **Step 3: Write the verification evidence to `findings.md`**

```markdown
- 2026-04-03 verification: 3.14.x compatibility stabilization
  - baseline runtime:
    - `/opt/python-3.14/bin/python3.14`
  - additional validated runtime:
    - `/opt/python-3.14.0/bin/python3.14`
  - unified entrypoint:
    - `scripts/push_to_arm.ps1`
    - `scripts/arm/remote_update_build_test.sh`
  - targeted test command:
    - `python -m pytest tests/test_compat_policy.py ...`
  - result:
    - PASS / FAIL with artifact references
```

- [ ] **Step 4: Commit**

```bash
git add findings.md
git commit -m "docs: record 3.14.x compatibility verification"
```

## Execution Checklist

### Sprint 1: Internal Source Of Truth

- [ ] Create `cinderx/PythonLib/cinderx/_compat.py`.
- [ ] Define a `FamilyPolicy` type with explicit `3.14` fields only.
- [ ] Register `3.14` as the only OSS-supported family in this phase.
- [ ] Add `tests/test_compat_policy.py`.
- [ ] Verify `3.14` returns a policy.
- [ ] Verify `3.15` returns `None`.
- [ ] Verify `3.16` returns `None`.
- [ ] Refactor `setup.py` to read the policy.
- [ ] Remove handwritten minor-family support decisions from `setup.py`.
- [ ] Keep current `3.14` ARM feature defaults unchanged.
- [ ] Refactor `cinderx/PythonLib/cinderx/__init__.py` runtime gating to read the policy.
- [ ] Keep OSS runtime support narrowed to `3.14` in this phase.
- [ ] Refactor `cinderx/PythonLib/test_cinderx/test_oss_quick.py` to derive expectations from the policy.
- [ ] Run local tests:

```powershell
python -m pytest tests/test_compat_policy.py tests/test_setup_adaptive_static_python.py tests/test_setup_lightweight_frames.py cinderx/PythonLib/test_cinderx/test_oss_quick.py -q
```

- [ ] Confirm all local policy/setup/smoke tests pass.

### Sprint 2: Public Support Statement

- [ ] Update `README.md` to say `CPython 3.14.x`.
- [ ] Remove `3.14.3 or later` wording from `README.md`.
- [ ] State clearly that `3.14.3` is the default build/publish baseline.
- [ ] Update `pyproject.toml` to keep OSS release scope at `cp314`.
- [ ] Set `requires-python` to the intended `3.14.x` public support range.
- [ ] Keep classifiers aligned to current OSS support only.
- [ ] Keep `cibuildwheel` producing only `cp314` wheels.
- [ ] Add or update comments in `build/fbcode_builder/manifests/python-3_14` to clarify baseline vs support range.
- [ ] Update any release workflow wording in `.github/workflows/publish.yml` that implies `3.14.3` is the only supported patch.
- [ ] Re-read docs and metadata for consistency.

### Sprint 3: Unified Remote Verification

- [ ] Add `ExtraTestCmd` passthrough to `scripts/push_to_arm.ps1`.
- [ ] Add `ExtraVerifyCmd` passthrough to `scripts/push_to_arm.ps1`.
- [ ] Wire those parameters to `EXTRA_TEST_CMD` and `EXTRA_VERIFY_CMD`.
- [ ] Keep default remote behavior unchanged when these parameters are omitted.
- [ ] Verify the remote entrypoint still works on the baseline environment.
- [ ] Run the baseline `3.14` environment through the unified remote path.
- [ ] Run one additional validated `3.14.x` patch environment through the same path.
- [ ] Use the same targeted test command in both environments.
- [ ] Capture interpreter path, driver venv, command, and outcome for each run.
- [ ] Write the verification evidence to `findings.md`.
- [ ] Confirm `findings.md` distinguishes:
  - baseline patch
  - additional validated patch
  - actual command used
  - actual outcome

### Final Exit Criteria

- [ ] There is one internal source of truth for OSS-supported runtime families.
- [ ] Current OSS support is explicitly and consistently `3.14.x`.
- [ ] `3.14.3` is documented as a baseline, not as the only supported patch.
- [ ] `setup.py`, runtime gating, and OSS smoke tests all consume the same support policy.
- [ ] OSS packaging still publishes only `cp314` in this phase.
- [ ] Unified remote verification covers at least two `3.14.x` patch points.
- [ ] Verification evidence is written to `findings.md`.
- [ ] The resulting structure is ready for future `3.15` / `3.16` onboarding without another repo-wide hardcoded-version sweep.
