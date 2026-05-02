# Python 3.14 功能保障矩阵

## 目标

为 CinderX on CPython 3.14 提供一套可执行、可复用、可追溯的功能保障矩阵。

这套矩阵解决三个问题：

1. PR 前必须通过哪些功能检查
2. nightly 需要扩展到哪些更高风险的功能验证
3. release 前如何用统一远端入口做最终签收

## 正式远端入口

所有正式测试与验证统一通过以下入口执行：

- `scripts/push_to_arm.ps1`
- `scripts/arm/remote_update_build_test.sh`

## Profiles

- `py314-pr-core`
- `py314-nightly-extended`
- `py314-release-full`

## Lanes

### baseline lane

- 目标：证明在尽量关闭高风险优化时，CinderX 仍保持 Python 3.14 语义基线
- 典型策略：
  - 跳过默认 ARM runtime 集合
  - 跳过 JIT effectiveness smoke
  - 跳过 pyperformance/setup 路径
  - 通过 `EXTRA_TEST_CMD` 跑受控的语义测试集合

### optimized lane

- 目标：证明在开启 CinderX 关键优化后，功能语义仍然正确
- 典型策略：
  - 保留优化相关验证
  - 保留更广的 JIT/runtime 测试集合
  - 继续通过统一远端入口调用，不走临时命令

## v1 覆盖范围

### `py314-pr-core`

- baseline:
  - profile 契约测试
  - 快速语义 smoke
- optimized:
  - `test_frame_evaluator.py`
  - `test_jit_specialization.py`
  - `test_jit_generators.py`
  - `test_jit_coroutines.py`
  - `test_type_cache.py`

### `py314-nightly-extended`

- baseline:
  - `test_cpython_overrides` 的核心语义集
- optimized:
  - `py314-pr-core` optimized 全集
  - 更广的 runtime/JIT 相关集合
  - full `test_arm_runtime.py`

### `py314-release-full`

- baseline:
  - clean workdir + clean rebuild
  - 重跑 nightly baseline
- optimized:
  - clean workdir + clean rebuild
  - 重跑 nightly optimized
  - 禁止临时 skip

## Expected-Failure 策略

- expected failures 只能通过受版本控制的文件管理
- 正式验证禁止使用终端里一次性的临时 skip
- 如果 expected failure 转绿，应当清理对应记录

## Findings 记录模板

每次正式验证至少记录：

- 日期
- Profile
- Lane
- 远端 workdir
- 入口命令
- 结果
- 关键测试/关键说明

## v1 明确不包含

- benchmark gate
- 3.15 扩展
- 3.14t 扩展
- 全量 CI 平台重构
