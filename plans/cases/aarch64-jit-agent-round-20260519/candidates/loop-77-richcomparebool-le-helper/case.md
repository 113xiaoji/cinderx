# Loop 77 - RichCompareBool <= helper

## 候选简介

本候选把 Loop 76 的“按比较 op 拆分 RichCompareBool helper”收窄到
`<=` 一个比较操作：在 AArch64 上给残留的 generic `CompareBool <=` 调用增加
`JITRT_RichCompareBoolLessThanEqual(PyObject* v, PyObject* w)`，让 compact `int <= int`
直接在 helper 内完成，不再经过通用 `JITRT_RichCompareBool(v, w, op)` 的运行时 op
参数分发。

这不是替代 Loop 69/74，而是叠加在它们之后的补充路径：

- Loop 69/74 优先覆盖 JIT 能静态看到 `TLongExact + TLongExact` 或固定 op helper 的路径。
- Loop 77 覆盖剩余仍落到 generic `RichCompareBool` 的 `<=` 路径。
- 因此它的收益应理解为“在 69/74 之后还能拿到的额外收益”。

## 代码方案

- `jit_rt.cpp`
  - 抽出 `static int JITRT_RichCompareBoolGeneric(PyObject* v, PyObject* w, int op)`，保留原有
    `PyObject_RichCompare`、`PyBool_Check`、`PyObject_IsTrue` 语义。
  - 在 `CINDERX_JIT_COMPACT_LONG_COMPARE_BOOL_FASTPATH` 下新增
    `JITRT_RichCompareBoolLessThanEqual(v, w)`。
  - helper 内先检查 `PyLong_CheckExact(v/w)`，再检查
    `PyUnstable_Long_IsCompact(left/right)`；命中后直接取
    `PyUnstable_Long_CompactValue` 并返回 `left <= right`。
  - 未命中时回落到 `JITRT_RichCompareBoolGeneric(v, w, Py_LE)`。
- `jit_rt.h`
  - 只在 AArch64 compact-long fastpath 宏打开时声明 `JITRT_RichCompareBoolLessThanEqual`。
- `lir/generator.cpp`
  - 只在 `CINDERX_JIT_COMPACT_LONG_COMPARE_BOOL_FASTPATH` 下，把 residual generic
    `CompareBool` 且 op 为 `kLessThanEqual` 的调用改为两参 helper。
  - 其他比较 op 继续走原通用 `JITRT_RichCompareBool(v, w, op)`。

## ARM 亲和性

这个方案是 ARM 亲和、x86 不作为主要受益目标：

- 当前 final patch 用 `CINDERX_JIT_COMPACT_LONG_COMPARE_BOOL_FASTPATH` 包住 helper 声明、
  helper 实现和 LIR 选择逻辑；该宏只在 AArch64 compact-long compare fastpath 路径启用。
- AArch64 调用约定下，两参 fixed helper 比三参 generic helper 少传一个 `op` 参数，helper 内也少一层
  `switch/op` 分发；对热点小整数比较更友好。
- x86 原本调用/分支成本相对低，而且这个补丁的主要命中来自 ARM 上 `coverage` 的大量 compact
  `<=` 比较；为了保持“ARM 收益、x86 不受益/不扰动”的目标，本候选不在 x86 默认路径启用。

## 证据与环境

历史验证：

- 构建日志：`/root/work/arm-sync/build_richcomparebool_le_helper_loop77_20260521.log`
- 语义 smoke：`/root/work/arm-sync/richcomparebool_le_helper_loop77_semantic_smoke_20260521.log`
- Focused S3：`/root/work/arm-sync/richcomparebool_le_helper_loop77_focus_s3_20260521_compare.json`
- Focused S12：`/root/work/arm-sync/richcomparebool_le_helper_loop77_focus_s12_20260521_compare.json`
- Targeted S12 repeat：`/root/work/arm-sync/richcomparebool_le_helper_loop77_regression_s12_20260521_compare.json`
- Full JIT28 S3：`/root/work/arm-sync/richcomparebool_le_helper_loop77_jit28_s3_20260521_compare.json`
- Full JIT28 S12：`/root/work/arm-sync/richcomparebool_le_helper_loop77_jit28_s12_20260521_compare.json`

2026-05-22 复测：

- 机器：`113.44.53.223`，`aarch64`
- run dir：`/root/work/arm-sync/retest_loop77_current_v5_20260522_114209`
- base：Loop 74 wheel，`/root/work/comparebool_op_helper_loop74_20260521_work`
- candidate：Loop 77 wheel，`/root/work/richcomparebool_le_helper_loop77_20260521_work`
- 方法：`scripts/arm/run_pyperf_subset.sh` 生成结果，
  `scripts/arm/compare_pyperf_subset.py` 生成对比；`AUTOJIT=50`，
  `CINDERX_ENABLE_SPECIALIZED_OPCODES=1`
- 说明：本轮 223 复测复用了 2026-05-21 的 Loop77 AArch64 wheel；本地
  `candidate.patch` 已更新为更严格的 `CINDERX_JIT_COMPACT_LONG_COMPARE_BOOL_FASTPATH`
  guarded 形态。2026-05-22 已基于 develop HEAD 重新构建 base/candidate wheel，并用
  guarded patch 完成 full JIT28 S12 最终确认。

2026-05-22 guarded final patch 复测：

- 机器：`113.44.53.223`，`aarch64`
- run dir：`/root/work/arm-sync/retest_loop77_guarded_develop_20260522_161300`
- base workdir：`/root/work/develop_head_base_20260522_work`
- candidate workdir：`/root/work/develop_head_loop77_guarded_20260522_work`
- base wheel：`/root/work/develop_head_base_20260522_work/dist/cinderx-2026.5.22.0-cp314-cp314-linux_aarch64.whl`
- candidate wheel：`/root/work/develop_head_loop77_guarded_20260522_work/dist/cinderx-2026.5.22.0-cp314-cp314-linux_aarch64.whl`
- build logs：
  - `/root/work/arm-sync/build_develop_head_base_20260522_v2.log`
  - `/root/work/arm-sync/build_loop77_guarded_on_develop_20260522.log`
- 方法：从本地 `develop` HEAD 导出同一份源码包，base 不改，candidate 只覆盖
  `jit_rt.cpp`、`jit_rt.h`、`lir/generator.cpp` 三个 guarded patch 文件；两边分别 rebuild
  wheel 后，用 `scripts/arm/run_pyperf_subset.sh` 跑 smoke + full JIT28 S12，
  用 `scripts/arm/compare_pyperf_subset.py` 对比。

## 测试结果

| 测试 | valid | time geomean | speedup geomean | >=5% 回归 | 最大收益项 | 结论 |
|---|---:|---:|---:|---|---|---|
| smoke `nbody` S1 | 1/1 | `-1.332%` | `+1.349%` | 无 | `nbody -1.332% time` | correctness/基本性能入口通过 |
| focused S3 | 7/7 | `-1.981%` | `+2.021%` | 无 | `coverage -10.037% time` | 短样本收益明显 |
| focused S12 | 7/7 | `-0.886%` | `+0.894%` | 无 | `coverage -9.359% time` | 收益方向稳定 |
| full JIT28 S3 | 20/20 | `-0.928%` | `+0.937%` | 无 | `coverage -10.057% time` | 全量短样本正向 |
| full JIT28 S12 | 20/20 | `-0.359%` | `+0.360%` | 无 | `coverage -9.666% time` | 全量稳定样本仍正向，收益小于历史值 |

Guarded final patch rebuild 后的最终确认：

| 测试 | valid | time geomean | speedup geomean | >=5% 回归 | 最大收益项 | 结论 |
|---|---:|---:|---:|---|---|---|
| full JIT28 S12 | 20/20 | `-0.100%` | `+0.100%` | 无 | `coverage -6.532% time` | 全量 geomean 极小正向，主要价值来自单项热点收益 |

Guarded final patch full JIT28 S12 主要行：

| benchmark | time delta | 说明 |
|---|---:|---|
| `coverage` | `-6.532%` | 最大稳定收益，符合 `<=` compact-long 热点命中预期 |
| `pickle_list` | `-5.043%` | 本轮进入 >=5% 正向收益行 |
| `deltablue` | `-0.222%` | 小幅正向 |
| `float` | `-0.134%` | 小幅正向 |
| `coroutines` | `-0.102%` | 小幅正向 |
| `comprehensions` | `+2.644%` | 最大负向但低于 5% 门限 |
| `unpack_sequence` | `+1.661%` | 低于 5% 门限 |
| `nqueens` | `+1.083%` | 低于 5% 门限 |

Full JIT28 S12 主要行：

| benchmark | time delta | 说明 |
|---|---:|---|
| `coverage` | `-9.666%` | 最大稳定收益，符合 `<=` compact-long 热点命中预期 |
| `unpack_sequence` | `-3.866%` | 次级收益，需视为伴随噪声/间接受益 |
| `json_dumps` | `-1.309%` | 小幅正向 |
| `pickle_list` | `-1.219%` | 历史曾有波动，本轮 S12 为正向 |
| `pickle` | `+2.343%` | 最大负向但低于 5% 门限 |
| `raytrace` | `+2.026%` | 低于 5% 门限 |
| `coroutines` | `+1.537%` | 低于 5% 门限 |

历史结果对照：

| 测试 | 历史 speedup geomean | 2026-05-22 复测 | 变化 |
|---|---:|---:|---|
| focused S3 | `+1.221%` | `+2.021%` | 更好 |
| focused S12 | `+0.513%` | `+0.894%` | 更好 |
| full JIT28 S3 | `+0.404%` | `+0.937%` | 更好 |
| full JIT28 S12 | `+0.632%` | `+0.360%` | 仍正向，但收敛后更小 |

Guarded final patch rebuild 后，full JIT28 S12 进一步收敛到 `+0.100%` geomean。这个结果说明：

- 方案仍没有暴露 >=5% regression。
- `coverage` 与 `pickle_list` 单项收益明确。
- full JIT28 geomean 收益已经接近噪声带，不能再按历史 `+0.6%` 作为稳定收益口径。

## coverage 为什么提升

Loop 76 的计数证据显示 `coverage` 在 focused S1 中有约 `242735` 次 compact `<=` 命中。
`coverage` 的热点里有大量小整数行号、边界、计数类比较，且常见形式正好是 `int <= int`。
Loop 77 将这类残留 `<=` 比较从通用 rich compare helper 中拆出来：

- 命中 compact long 时少一次 `PyObject_RichCompare` 调用。
- 少一次按 `op` 参数选择比较语义的泛化分支。
- 直接返回 C++ `left <= right` 的 bool 结果。

因此 `coverage` 的收益大、且在 S3/S12/full JIT28 中都复现，是符合代码路径和 workload 命中证据的。

## 是否可叠加 69/74

可以叠加。2026-05-22 的 base 已经是 Loop 74 wheel，candidate 是 Loop 77 wheel，所以 full
JIT28 S12 的 `+0.360%` 就是相对 69/74 之后的额外收益。

由于本轮 guarded rebuild 复测低于历史 `+0.632%`，合入收益预期应按保守口径记录为：

- focused workload：旧 wheel 复测约 `+0.9%` 到 `+2.0%`
- full JIT28 S12：guarded final patch 约 `+0.1%`，旧 wheel 复测约 `+0.36%`
- 最大稳定单项：`coverage` 约 `+6%` 到 `+10%`

## 决策

状态：`accepted/perf-positive-tiny-geomean`

用户已确认准备合入。本候选按保守口径接受：full JIT28 geomean 只是极小正向，
但 guarded final patch 在 20/20 JIT28 S12 中没有 `>=5%` 回归，且 `coverage`
和 `pickle_list` 的单项收益明确。合入判断如下：

- 合入范围只包含 AArch64 宏保护下的代码和本中文 `case.md`。
- `candidate.patch` 继续只作为本地归档，不随代码合入。
- x86 不需要默认实现/实测作为合入前置，因为本方案已明确通过 AArch64 fastpath 宏隔离，
  目标就是 ARM 收益且 x86 不扰动。
- 后续如果继续优化，应以 develop 上的 Loop 69/74/77 作为新的 compare helper baseline。
