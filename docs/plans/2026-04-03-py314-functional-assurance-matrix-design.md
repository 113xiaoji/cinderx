# Python 3.14 功能保障矩阵设计

## Issue

为 CinderX on CPython 3.14 建立一个 v1 版本的功能保障矩阵，要求所有正式验证统一通过 ARM 远端测试入口执行，并规范关键验证结论写入 `findings.md` 的方式。

## 目标

为 Python 3.14 建立一份小而清晰、可复用的测试契约，回答三个问题：

1. 代码改动在合入前必须通过哪些检查？
2. 哪些更广的验证需要在 nightly 或 release 前执行？
3. 这些检查应当如何以统一方式运行和记录？

这个设计的目标是提升功能正确性的把握，而不是扩展成一次完整的 CI 平台改造或性能基准体系建设。

## 非目标

- 增加 benchmark gate 或性能回归策略
- 将矩阵扩展到 Python 3.15
- 将矩阵扩展到 Python 3.14 free-threaded（`3.14t`）
- 用第二套 runner 替换现有 ARM 远端流程
- 全面重构 GitHub Actions 或内部 Buck 流水线

## 约束

- 统一远端入口保持不变：
  - `scripts/push_to_arm.ps1`
  - `scripts/arm/remote_update_build_test.sh`
- 正式验证必须通过这个入口执行，而不是通过临时 SSH 命令手工拼接。
- 所有影响 issue 关闭、合并决策或功能签收的关键结果，都必须写入 `findings.md`。
- v1 必须足够精简，确保它可以真实作为 PR gate 使用。

## 问题描述

当前仓库里已经存在若干有价值但彼此割裂的验证层：

- `.github/workflows/ci.yml` 里的 OSS CI smoke tests
- `cinderx/PythonLib/test_cinderx` 下的 CinderX Python 回归测试
- `cinderx/RuntimeTests` 下的 C++ runtime tests
- 通过 ARM 远端脚本驱动的 targeted ARM runtime regressions
- 按 issue 记录在 `findings.md` 中的历史验证证据

当前缺少的是一份正式的 Python 3.14 功能保障契约，用来明确：

- 哪些测试属于快速 PR 路径
- 哪些测试属于 nightly 或 release 的更广泛验证
- 哪些检查应该在兼容性导向的 baseline 模式下执行，哪些应在开启优化的模式下执行
- 这些检查应如何统一触发与记录

## 方案概述

引入一个以矩阵为中心的设计，并通过命名 profile 组织验证流程。每个 profile 都包含两条 lane：

- `baseline lane`
  - 用于证明 CinderX 存在时仍不破坏预期的 CPython 语义基线
  - 在可能的情况下显式关闭高风险优化
- `optimized lane`
  - 用于证明支持的 CinderX 优化路径在开启后仍保持语义正确
  - 显式启用该 profile 需要验证的运行时特性

矩阵定义保存在仓库文档中，并通过一个轻量的 profile 映射层，将 profile 名称转换成现有远端入口所需的环境变量和附加命令。

这个方案保持“一个正式远端执行路径”的原则，同时消除每次手工拼接验证命令的成本。

## Profiles

### 1. `py314-pr-core`

用途：

- 作为 PR 阻塞门，要求足够快且稳定

Baseline lane 内容：

- wheel/build/install smoke
- 顶层 `tests/` 下的 setup 和 API smoke 覆盖
- `test_cpython_overrides` 中的核心语义集：
  - `test_asyncgen.py`
  - `test_coroutines.py`
  - `test_dis.py`
  - `test_generators.py`
  - `test_inspect.py`
  - `test_trace.py`
  - `test_tracemalloc.py`
  - `test_types.py`
  - `test__opcode.py`

Optimized lane 内容：

- `test_frame_evaluator.py`
- `test_jit_specialization.py`
- `test_jit_generators.py`
- `test_jit_coroutines.py`
- `test_type_cache.py`
- 当活跃 issue 需要时，再补一小组 targeted ARM runtime subset

### 2. `py314-nightly-extended`

用途：

- 作为 Python 3.14 的 nightly 功能保障主入口

Baseline lane 内容：

- 继承 `py314-pr-core` 的全部 baseline 检查
- 扩展到更广的 `test_cinderx`
- 补充更高风险的 CPython-facing 区域：
  - `test_gc`
  - `test_import`
  - `test_subprocess`
  - `test_threading`
  - `test_capi`
  - `test_embed`

Optimized lane 内容：

- 继承 `py314-pr-core` 的全部 optimized 检查
- 跑完整 `test_arm_runtime.py`
- 跑更广的 JIT、frame、shadowcode 与 runtime 相关 `test_cinderx`
- 所有 expected failure 必须通过受版本控制的文件显式管理，不能通过一次性的命令行 skip 处理

### 3. `py314-release-full`

用途：

- 作为 release 或等价合并里程碑前的最终 Python 3.14 功能签收入口

Baseline lane 内容：

- clean remote workdir
- clean rebuild
- 重跑全部 nightly baseline 覆盖

Optimized lane 内容：

- clean remote workdir
- clean rebuild
- 重跑全部 nightly optimized 覆盖
- 禁止临时未跟踪 skip
- 所有 expected failure 都必须在 issue 上下文和 `findings.md` 中同时说明

## 接口设计

正式接口是“命名远端 profile”。这个 profile 不是第二套 runner，而是现有 ARM 远端入口上的一层薄映射。

考虑过两种实现方式：

1. 直接给 `scripts/push_to_arm.ps1` 增加 `-Profile` 参数
2. 新增一个 profile 映射文件或辅助脚本，把 profile 名称翻译成当前环境变量接口

推荐第二种实现方式。

原因：

- 可以把矩阵策略与 runner 实现解耦
- 能保持当前远端 helper 稳定
- 后续新增 `3.14t` 或 `3.15` 时侵入性更小
- 调整测试成员时，只需要评审矩阵和映射定义，而不必每次都改 PowerShell 传输层

## 产物

本 issue 应产出以下仓库内产物：

- 一份 Python 3.14 功能保障矩阵文档
- 一份机器可读或脚本可读的 profile 映射定义
- 面向统一远端入口的轻量调用说明
- 一份标准化的 `findings.md` 正式验证记录模板

## 验收标准

当且仅当以下条件全部满足时，本 issue 才算完成：

1. 仓库中存在一份正式的 Python 3.14 功能保障矩阵文档，且包含三个命名 profile。
2. 仓库中存在一套可复用方式，能够通过统一 ARM 远端入口调用这些 profile。
3. 至少完成一次真实远端验证：
   - `py314-pr-core`
   - `py314-nightly-extended`
4. 这两次验证的关键结果已经按统一模板记录到 `findings.md`。
5. 文档中已明确写出：
   - baseline lane 与 optimized lane 的职责
   - profile 级测试清单
   - expected-failure 与 skip 策略
   - v1 明确不纳入的范围

## 数据流

预期流程如下：

1. 选择一个命名 profile
2. 将 profile 展开为远端入口输入
3. 通过以下统一路径执行正式验证：
   - `scripts/push_to_arm.ps1`
   - `scripts/arm/remote_update_build_test.sh`
4. 抽取关键结果字段
5. 将结果追加到 `findings.md`

这样可以确保人类可读的策略、实际执行路径以及证据记录三者保持一致。

## Expected-Failure 策略

Expected failure 可以存在，但只能以“受版本控制、可评审”的形式存在。

规则如下：

- 正式验证禁止使用仅存在于终端里的临时 skip
- issue 关闭不能建立在未文档化的一次性命令变体上
- 如果某个测试预计失败，它必须通过受跟踪的文件或受跟踪的矩阵策略体现出来
- 如果某个 expected failure 开始转绿，应当作为正常维护的一部分清理掉

这与仓库当前 `cinder_test_runner312.py` 的行为是一致的，也能让测试债务始终可见。

## 风险

### 范围漂移

这个 issue 很容易膨胀成 CI 改造、平台扩展或性能策略工程。本设计通过把范围限制在“矩阵定义、远端 profile 调用和证据归档”上，避免问题失控。

### PR Gate 不稳定

如果 `py314-pr-core` 过大，开发者就不会信任它。本设计通过有意缩小 PR profile，把更重的覆盖放到 nightly 和 release profile 中来缓解这个问题。

### Skip 与 Expected-Failure 失控

如果例外项没有统一追踪，矩阵就会沦为形式化流程而非可信保障。本设计通过把“受跟踪的例外项”纳入契约本身来解决这一点。

## 开放问题

- v1 无开放问题。未来是否扩展到 `3.14t`、`3.15` 或 benchmark 策略，明确作为后续工作处理，而不是在当前 issue 中保留模糊空间。
