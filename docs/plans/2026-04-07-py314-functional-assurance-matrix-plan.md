# Python 3.14 功能保障矩阵 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 CinderX on CPython 3.14 建立 v1 功能保障矩阵、命名远端 profile、统一远端测试入口调用方式，并把关键验证结果标准化写入 `findings.md`。

**Architecture:** 以现有 `scripts/push_to_arm.ps1 -> scripts/arm/remote_update_build_test.sh` 为唯一正式远端测试入口，在其上增加“profile 映射 + lane 展开”能力。测试矩阵成员放在受版本控制的数据文件中，入口脚本只负责读取 profile、展开环境变量、执行既有远端流程；文档和 `findings.md` 负责承载人类可读的策略与证据。

**Tech Stack:** PowerShell、Bash、Python `unittest`、JSON 配置、ARM 远端构建/测试入口、Markdown 文档。

---

### Task 1: 先把 profile 契约写成失败测试

**Files:**
- Create: `C:\work\code\cinderx2\tests\test_py314_functional_assurance_profiles.py`
- Test: `C:\work\code\cinderx2\tests\test_py314_functional_assurance_profiles.py`

- [ ] **Step 1: 写出失败测试**

```python
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "scripts" / "arm" / "py314_functional_assurance_profiles.json"


class FunctionalAssuranceProfilesTests(unittest.TestCase):
    def load_profiles(self) -> dict:
        return json.loads(PROFILES.read_text(encoding="utf-8"))

    def test_required_profiles_exist(self) -> None:
        data = self.load_profiles()
        self.assertEqual(
            sorted(data["profiles"]),
            [
                "py314-nightly-extended",
                "py314-pr-core",
                "py314-release-full",
            ],
        )

    def test_pr_core_baseline_lane_disables_jit_smoke_and_pyperf(self) -> None:
        lane = self.load_profiles()["profiles"]["py314-pr-core"]["baseline"]
        env = lane["remote_env"]
        self.assertEqual(env["SKIP_ARM_RUNTIME"], "1")
        self.assertEqual(env["SKIP_JIT_EFFECTIVENESS_SMOKE"], "1")
        self.assertEqual(env["SKIP_PYPERF_SETUP"], "1")
        self.assertIn(
            "python -m unittest tests/test_py314_functional_assurance_profiles.py -v",
            env["EXTRA_TEST_CMD"],
        )

    def test_pr_core_optimized_lane_keeps_runtime_validation_enabled(self) -> None:
        lane = self.load_profiles()["profiles"]["py314-pr-core"]["optimized"]
        env = lane["remote_env"]
        self.assertEqual(env["SKIP_PYPERF_SETUP"], "1")
        self.assertEqual(env["CINDERX_ENABLE_SPECIALIZED_OPCODES"], "1")
        self.assertIn(
            "python -m unittest cinderx/PythonLib/test_cinderx/test_frame_evaluator.py -v",
            env["EXTRA_TEST_CMD"],
        )

    def test_nightly_extended_optimized_lane_runs_full_arm_runtime(self) -> None:
        lane = self.load_profiles()["profiles"]["py314-nightly-extended"]["optimized"]
        env = lane["remote_env"]
        self.assertNotIn("SKIP_ARM_RUNTIME", env)
        self.assertEqual(env["SKIP_PYPERF_SETUP"], "1")
        self.assertIn(
            "python -m unittest cinderx/PythonLib/test_cinderx/test_jit_specialization.py -v",
            env["EXTRA_TEST_CMD"],
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 通过远端入口运行，确认它先失败**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx2 `
  -WorkBranch codex/py314-functional-assurance-matrix `
  -ArmHost 124.70.162.35 `
  -Profile py314-pr-core `
  -Lane baseline
```

Expected:

- `push_to_arm.ps1` 还不支持 `-Profile` / `-Lane`，命令失败
- `scripts/arm/py314_functional_assurance_profiles.json` 尚不存在
- 这证明“命名 profile 远端调用契约”确实还没实现

- [ ] **Step 3: 写出最小实现**

```json
{
  "profiles": {
    "py314-pr-core": {
      "baseline": {
        "remote_env": {
          "SKIP_ARM_RUNTIME": "1",
          "SKIP_JIT_EFFECTIVENESS_SMOKE": "1",
          "SKIP_PYPERF_SETUP": "1",
          "EXTRA_TEST_CMD": "python -m unittest tests/test_py314_functional_assurance_profiles.py -v"
        }
      },
      "optimized": {
        "remote_env": {
          "SKIP_PYPERF_SETUP": "1",
          "CINDERX_ENABLE_SPECIALIZED_OPCODES": "1",
          "EXTRA_TEST_CMD": "python -m unittest cinderx/PythonLib/test_cinderx/test_frame_evaluator.py cinderx/PythonLib/test_cinderx/test_jit_specialization.py cinderx/PythonLib/test_cinderx/test_jit_generators.py cinderx/PythonLib/test_cinderx/test_jit_coroutines.py cinderx/PythonLib/test_cinderx/test_type_cache.py -v"
        }
      }
    },
    "py314-nightly-extended": {
      "baseline": {
        "remote_env": {
          "SKIP_ARM_RUNTIME": "1",
          "SKIP_JIT_EFFECTIVENESS_SMOKE": "1",
          "SKIP_PYPERF_SETUP": "1",
          "EXTRA_TEST_CMD": "python -m unittest cinderx/PythonLib/test_cinderx/test_cpython_overrides/test_asyncgen.py cinderx/PythonLib/test_cinderx/test_cpython_overrides/test_coroutines.py cinderx/PythonLib/test_cinderx/test_cpython_overrides/test_dis.py cinderx/PythonLib/test_cinderx/test_cpython_overrides/test_generators.py cinderx/PythonLib/test_cinderx/test_cpython_overrides/test_inspect.py cinderx/PythonLib/test_cinderx/test_cpython_overrides/test_trace.py cinderx/PythonLib/test_cinderx/test_cpython_overrides/test_tracemalloc.py cinderx/PythonLib/test_cinderx/test_cpython_overrides/test_types.py cinderx/PythonLib/test_cinderx/test_cpython_overrides/test__opcode.py -v"
        }
      },
      "optimized": {
        "remote_env": {
          "SKIP_PYPERF_SETUP": "1",
          "CINDERX_ENABLE_SPECIALIZED_OPCODES": "1",
          "EXTRA_TEST_CMD": "python -m unittest cinderx/PythonLib/test_cinderx/test_frame_evaluator.py cinderx/PythonLib/test_cinderx/test_jit_specialization.py cinderx/PythonLib/test_cinderx/test_jit_generators.py cinderx/PythonLib/test_cinderx/test_jit_coroutines.py cinderx/PythonLib/test_cinderx/test_type_cache.py cinderx/PythonLib/test_cinderx/test_shadowcode.py cinderx/PythonLib/test_cinderx/test_perfmaps.py -v"
        }
      }
    },
    "py314-release-full": {
      "baseline": {
        "remote_env": {
          "SKIP_ARM_RUNTIME": "1",
          "SKIP_JIT_EFFECTIVENESS_SMOKE": "1",
          "SKIP_PYPERF_SETUP": "1",
          "EXTRA_TEST_CMD": "python -m unittest tests/test_py314_functional_assurance_profiles.py -v"
        }
      },
      "optimized": {
        "remote_env": {
          "SKIP_PYPERF_SETUP": "1",
          "CINDERX_ENABLE_SPECIALIZED_OPCODES": "1",
          "EXTRA_TEST_CMD": "python -m unittest cinderx/PythonLib/test_cinderx/test_frame_evaluator.py cinderx/PythonLib/test_cinderx/test_jit_specialization.py cinderx/PythonLib/test_cinderx/test_jit_generators.py cinderx/PythonLib/test_cinderx/test_jit_coroutines.py cinderx/PythonLib/test_cinderx/test_type_cache.py -v"
        }
      }
    }
  }
}
```

- [ ] **Step 4: 再次通过远端入口运行，确认转绿**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx2 `
  -WorkBranch codex/py314-functional-assurance-matrix `
  -ArmHost 124.70.162.35 `
  -Profile py314-pr-core `
  -Lane baseline
```

Expected:

- `tests/test_py314_functional_assurance_profiles.py` PASS
- 远端流程不进入 pyperformance 路径
- 远端流程不执行 JIT effectiveness smoke

- [ ] **Step 5: Commit**

```bash
git add tests/test_py314_functional_assurance_profiles.py scripts/arm/py314_functional_assurance_profiles.json
git commit -m "test: define py314 functional assurance profile contract"
```

### Task 2: 给远端入口补上 profile 与 lane 支持

**Files:**
- Modify: `C:\work\code\cinderx2\scripts\push_to_arm.ps1`
- Modify: `C:\work\code\cinderx2\scripts\arm\remote_update_build_test.sh`
- Test: `C:\work\code\cinderx2\tests\test_py314_functional_assurance_profiles.py`

- [ ] **Step 1: 写出失败测试**

在 `tests/test_py314_functional_assurance_profiles.py` 里再补一组断言，要求 profile 数据中用到的新远端开关都被显式声明：

```python
    def test_all_remote_skip_flags_are_string_bools(self) -> None:
        data = self.load_profiles()["profiles"]
        for profile in data.values():
            for lane in profile.values():
                env = lane["remote_env"]
                for name in (
                    "SKIP_ARM_RUNTIME",
                    "SKIP_JIT_EFFECTIVENESS_SMOKE",
                    "SKIP_PYPERF_SETUP",
                ):
                    if name in env:
                        self.assertIn(env[name], {"0", "1"})
```

- [ ] **Step 2: 通过远端入口运行，确认它仍然失败**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx2 `
  -WorkBranch codex/py314-functional-assurance-matrix `
  -ArmHost 124.70.162.35 `
  -Profile py314-pr-core `
  -Lane baseline
```

Expected:

- `push_to_arm.ps1` 还不会读取 profile 文件
- `remote_update_build_test.sh` 还不会识别 `SKIP_ARM_RUNTIME` / `SKIP_JIT_EFFECTIVENESS_SMOKE` / `SKIP_PYPERF_SETUP`

- [ ] **Step 3: 写出最小实现**

在 `scripts/push_to_arm.ps1` 中增加参数并读取 profile：

```powershell
[string]$Profile = "",
[ValidateSet("baseline", "optimized")]
[string]$Lane = "baseline",

$profileFile = Join-Path $PSScriptRoot "arm\\py314_functional_assurance_profiles.json"
if ($Profile) {
  $profileData = Get-Content $profileFile -Raw | ConvertFrom-Json
  $laneConfig = $profileData.profiles.$Profile.$Lane
  foreach ($prop in $laneConfig.remote_env.PSObject.Properties) {
    $envPrefix += " $($prop.Name)=$($prop.Value)"
  }
}
```

在 `scripts/arm/remote_update_build_test.sh` 中增加新开关：

```bash
SKIP_ARM_RUNTIME="${SKIP_ARM_RUNTIME:-0}"
SKIP_JIT_EFFECTIVENESS_SMOKE="${SKIP_JIT_EFFECTIVENESS_SMOKE:-0}"
SKIP_PYPERF_SETUP="${SKIP_PYPERF_SETUP:-0}"
```

并把默认 ARM runtime / JIT smoke / pyperf setup 包起来：

```bash
if [[ "$SKIP_ARM_RUNTIME" != "1" ]]; then
  # existing ARM runtime block
fi

if [[ "$SKIP_JIT_EFFECTIVENESS_SMOKE" != "1" ]]; then
  # existing JIT effectiveness smoke block
fi

if [[ "$SKIP_PYPERF_SETUP" == "1" ]]; then
  echo "SKIP_PYPERF_SETUP=1 set; done after extra verification."
  exit 0
fi
```

- [ ] **Step 4: 再次通过远端入口运行，确认转绿**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx2 `
  -WorkBranch codex/py314-functional-assurance-matrix `
  -ArmHost 124.70.162.35 `
  -Profile py314-pr-core `
  -Lane baseline
```

Expected:

- 远端命名 profile 被正确展开
- 新 skip 开关生效
- `tests/test_py314_functional_assurance_profiles.py` PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/push_to_arm.ps1 scripts/arm/remote_update_build_test.sh tests/test_py314_functional_assurance_profiles.py
git commit -m "test: add py314 functional assurance profile plumbing"
```

### Task 3: 落地正式矩阵文档与 findings 模板

**Files:**
- Create: `C:\work\code\cinderx2\docs\py314-functional-assurance-matrix.md`
- Modify: `C:\work\code\cinderx2\findings.md`

- [ ] **Step 1: 先写一条失败约束**

在 `tests/test_py314_functional_assurance_profiles.py` 中补一个文档存在性断言：

```python
    def test_matrix_doc_exists(self) -> None:
        path = ROOT / "docs" / "py314-functional-assurance-matrix.md"
        self.assertTrue(path.exists(), path)
```

- [ ] **Step 2: 通过远端入口运行，确认它先失败**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx2 `
  -WorkBranch codex/py314-functional-assurance-matrix `
  -ArmHost 124.70.162.35 `
  -Profile py314-pr-core `
  -Lane baseline
```

Expected:

- `test_matrix_doc_exists` FAIL

- [ ] **Step 3: 写出最小实现**

文档文件 `docs/py314-functional-assurance-matrix.md` 至少包含以下结构：

```markdown
# Python 3.14 功能保障矩阵

## Profiles
- py314-pr-core
- py314-nightly-extended
- py314-release-full

## Lanes
- baseline lane
- optimized lane

## 正式远端入口
- scripts/push_to_arm.ps1
- scripts/arm/remote_update_build_test.sh

## Expected-Failure 策略
- 只能通过受版本控制的文件管理

## Findings 记录模板
- 日期
- Profile
- Lane
- 远端 workdir
- 入口命令
- 结果
- 关键说明
```

并在 `findings.md` 中预留一个新 section 标题：

```markdown
## 2026-04-07 Issue: Python 3.14 功能保障矩阵
```

- [ ] **Step 4: 再次通过远端入口运行，确认转绿**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx2 `
  -WorkBranch codex/py314-functional-assurance-matrix `
  -ArmHost 124.70.162.35 `
  -Profile py314-pr-core `
  -Lane baseline
```

Expected:

- `tests/test_py314_functional_assurance_profiles.py` 全绿
- baseline 文档约束已满足

- [ ] **Step 5: Commit**

```bash
git add docs/py314-functional-assurance-matrix.md findings.md tests/test_py314_functional_assurance_profiles.py
git commit -m "docs: add py314 functional assurance matrix"
```

### Task 4: 用真实远端运行签收 `py314-pr-core` 与 `py314-nightly-extended`

**Files:**
- Modify: `C:\work\code\cinderx2\findings.md`
- Test: `C:\work\code\cinderx2\tests\test_py314_functional_assurance_profiles.py`

- [ ] **Step 1: 跑 `py314-pr-core` baseline**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx2 `
  -WorkBranch codex/py314-functional-assurance-matrix `
  -ArmHost 124.70.162.35 `
  -Profile py314-pr-core `
  -Lane baseline
```

Expected:

- profile contract test PASS
- 远端流程按 baseline lane 早停

- [ ] **Step 2: 跑 `py314-pr-core` optimized**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx2 `
  -WorkBranch codex/py314-functional-assurance-matrix `
  -ArmHost 124.70.162.35 `
  -Profile py314-pr-core `
  -Lane optimized
```

Expected:

- `test_frame_evaluator.py`、`test_jit_specialization.py` 等 PASS
- optimized lane 保留 JIT 相关验证

- [ ] **Step 3: 跑 `py314-nightly-extended` baseline 与 optimized**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx2 `
  -WorkBranch codex/py314-functional-assurance-matrix `
  -ArmHost 124.70.162.35 `
  -Profile py314-nightly-extended `
  -Lane baseline

powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx2 `
  -WorkBranch codex/py314-functional-assurance-matrix `
  -ArmHost 124.70.162.35 `
  -Profile py314-nightly-extended `
  -Lane optimized
```

Expected:

- baseline lane 跑更广的 CPython-facing 语义集
- optimized lane 跑 full `test_arm_runtime.py` 和更广的 JIT/runtime 集合

- [ ] **Step 4: 把关键结果写入 `findings.md`**

记录格式：

```markdown
## 2026-04-07 Issue: Python 3.14 功能保障矩阵

### py314-pr-core / baseline
- 入口：
  - `scripts/push_to_arm.ps1`
  - `scripts/arm/remote_update_build_test.sh`
- 远端 workdir：
  - `/root/work/cinderx-main`
- 结果：
  - PASS / FAIL
- 关键测试：
  - `tests/test_py314_functional_assurance_profiles.py`

### py314-pr-core / optimized
- 结果：
  - PASS / FAIL
- 关键测试：
  - `test_frame_evaluator.py`
  - `test_jit_specialization.py`

### py314-nightly-extended / baseline
- 结果：
  - PASS / FAIL

### py314-nightly-extended / optimized
- 结果：
  - PASS / FAIL
```

- [ ] **Step 5: Commit**

```bash
git add findings.md
git commit -m "docs: record py314 functional assurance matrix verification"
```

## Testing and Validation

- 所有测试与验证统一通过远端入口执行：
  - `scripts/push_to_arm.ps1`
  - `scripts/arm/remote_update_build_test.sh`
- PR 级验证至少要覆盖：
  - `py314-pr-core / baseline`
  - `py314-pr-core / optimized`
- 夜间级验证至少要覆盖：
  - `py314-nightly-extended / baseline`
  - `py314-nightly-extended / optimized`

## Risks and Edge Cases

- `remote_update_build_test.sh` 当前默认流程偏向 benchmark/JIT smoke，若新 skip 开关位置放错，会导致 baseline lane 仍然做多余工作。
- `push_to_arm.ps1` 新增 `-Profile` / `-Lane` 后，必须保证旧调用方式保持兼容。
- `EXTRA_TEST_CMD` 使用长命令字符串时，需要注意 PowerShell 与 Bash 的引号转义。
- `py314-nightly-extended` 如果一开始塞入过多测试，可能会让 nightly 变得不稳定；v1 必须优先保证收敛和可复用。

## Open Questions

- 无。
