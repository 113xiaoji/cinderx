# Loop 69：CompareBool compact-long fast path

## 当前结论

这是一个 **AArch64 独有收益** 候选。223 上已经完成 correctness、工作负载命中证据、focused/full JIT28 S12 和
x86 后置对照；x86 对照实验显示没有稳定收益，因此最终合入形态必须保持 AArch64-only。

当前合入状态：`ready-for-human-review`

原因：223 上已有完整 ARM 收益和因果证据；123 上已补同口径 full JIT28 S12，确认趋势同向且无
`>=5%` 回退；x86 后置对照已实测无稳定收益。因此该候选已完成合入前准备，只剩人工检视确认。

标签：

- `arm-only-benefit`
- `x86-no-benefit`
- `do-not-merge-x86`
- `ready-for-human-review`

## 方案简介

原始路径里，`CompareBool` 在部分 lowering 场景会直接生成 `PyObject_RichCompareBool(left, right, op)`
runtime call：

| 场景 | 原始 helper |
|---|---|
| 左右都是 `TLongExact` | `PyObject_RichCompareBool(left, right, op)` |
| `Equal` / `NotEqual` 且左右类型适合 pointer-eq 语义 | `PyObject_RichCompareBool(left, right, op)` |
| 通用 rich compare bool fallback | `JITRT_RichCompareBool(left, right, op)` |

Loop 69 增加一个很窄的 exact compact `int` pair fast path：

1. 先检查左右对象都是 `PyLong_CheckExact`。
2. 再检查左右 `PyLongObject` 都是 compact long。
3. 命中后通过 `PyUnstable_Long_CompactValue` 取出 `Py_ssize_t` 值。
4. 对 `Py_LT`、`Py_LE`、`Py_EQ`、`Py_NE`、`Py_GT`、`Py_GE` 直接做 C++ 整数比较。
5. 返回 `0/1`，避开通用 rich-compare 对象路径。
6. 任一条件不满足时，完全回退到原有 helper。

合入形态应使用 `CINDERX_JIT_COMPACT_LONG_COMPARE_BOOL_FASTPATH` 平台宏控制，且只在 AArch64 打开：

```cpp
#if defined(__aarch64__)
#define CINDERX_JIT_COMPACT_LONG_COMPARE_BOOL_FASTPATH 1
#else
#define CINDERX_JIT_COMPACT_LONG_COMPARE_BOOL_FASTPATH 0
#endif
```

在 AArch64 上：

- `TLongExact` 的 `CompareBool` lowering 从直接调用 `PyObject_RichCompareBool` 改为调用
  `JITRT_FastPyObjectRichCompareBool`。
- pointer-eq 语义可用的 `Equal` / `NotEqual` fallback 也走同一个 wrapper。
- `JITRT_RichCompareBool` 自身在进入 `PyObject_RichCompare` 前先尝试 compact-long fast path。

在非 AArch64 上：

- `kFastLongRichCompareBool` 保持为 `PyObject_RichCompareBool`。
- `JITRT_FastPyObjectRichCompareBool` 不编译、不暴露。
- x86 默认路径不改变。

## 方案泛化性和边界

这个方案不是为单个 benchmark 写特例，而是覆盖一类明确语义：exact compact `int` 两两比较并返回 bool。

| 输入类型 | 处理方式 | 原因 |
|---|---|---|
| exact compact `int` + exact compact `int` | fast path | 可以安全取 compact value 直接比较 |
| 大整数 / non-compact long | fallback | 避免多 limb 比较和溢出语义变化 |
| `bool` | fallback | `bool` 不是 exact `int`，保持原语义 |
| `int` subclass | fallback | subclass 可能有自定义行为或副作用 |
| 非 `int` 对象 | fallback | 保持原 rich compare 行为 |
| 未知 compare op | fallback | 保持原 helper 行为和错误路径 |

泛化边界清楚：只优化 exact compact `PyLong` pair，不碰 Python 层可观察的 subclass、bool、大整数和非 int
行为。因此它足够通用，但不是跨架构默认通用；是否打开由平台收益证据决定。

## 为什么 AArch64 更亲和

第一，AArch64 的 runtime helper call 成本更容易被放大。AArch64 普通 `bl` 的立即数范围约为 `±128MB`；
当 JIT code buffer 和 C++ runtime helper 地址距离较远时，call 形态更容易退化为加载目标地址后 `blr`
的间接调用。这个形态会增加指令数、占用临时寄存器，并引入间接分支成本。

第二，x86-64 常见 `call rel32` 覆盖约 `±2GB`，在通常布局下更容易保持一条直接 call。也就是说，同样减少
helper 热路径，ARM 上节省的调用和分支成本更大，x86 上新增检查更容易抵消收益。

第三，workload 命中结构和 ARM 收益行对得上。Loop 68 的 counter 显示 exact compact long pair 在
`CompareBool` helper 中大量出现，Loop 69 的 ARM S12 正向行集中在同一批高命中 workload。

## 代码因果链

Loop 68 的轻量 counter 记录了 JIT28 S1 中 `CompareBool` helper 的动态命中：

| 指标 | 计数 |
|---|---:|
| aggregate total | `1536004` |
| both exact long | `1218783` |
| both exact compact long | `1216653` |
| `go` compact-long | `537043` |
| `coverage` compact-long | `244443` |
| `coroutines` compact-long | `243737` |
| `richards` compact-long | `88932` |
| `chaos` compact-long | `43142` |

Loop 69 正好处理这类 operand：

- 入口条件对应 `both exact compact long`。
- fast path 直接返回整数比较结果，省掉通用 rich compare 对象路径。
- fallback 覆盖 bool、subclass、non-compact long、non-long 和未知 op。
- 223 上 S12 收益最明显的 `coverage`、`go`、`coroutines` 与 counter 高命中 workload 对齐。

## 223 AArch64 正确性和性能证据

测试环境：223 AArch64 远端环境，使用标准 `scripts/arm/run_pyperf_subset.sh` 和
`scripts/arm/compare_pyperf_subset.py`。

| 测试 | 结果 | 判断 |
|---|---:|---|
| semantic smoke | 通过 | compact int、大整数、`bool`、`int` subclass fallback 和六类比较操作语义保持 |
| `nbody` S1 | speedup `+6.068%` | smoke 正向，无 warning |
| full JIT28 S3 | 20 valid，geomean speedup `+0.065%` | `coverage +14.949%`，但 `pickle_list -5.268%` 需要复核 |
| focused S12：`coverage,pickle_list,go,coroutines,nbody` | geomean speedup `+4.207%` | `coverage +14.738%`，`pickle_list -0.299%`，S3 回退未复现 |
| full JIT28 S12 | 20 valid，geomean speedup `+1.253%` | 无 `>=5%` 回退，`coverage +15.640%`、`coroutines +2.632%`、`go +2.121%` |

223 artifact：

| 内容 | 路径 |
|---|---|
| build log | `/root/work/arm-sync/build_comparebool_compact_long_loop69_20260521.log` |
| install log | `/root/work/arm-sync/install_comparebool_compact_long_loop69_20260521.log` |
| semantic smoke | `/root/work/arm-sync/comparebool_compact_long_loop69_semantic_smoke_20260521` |
| `nbody` S1 compare | `/root/work/arm-sync/comparebool_compact_long_loop69_smoke_s1_20260521/compare.json` |
| full JIT28 S3 compare | `/root/work/arm-sync/comparebool_compact_long_loop69_jit28_s3_20260521/compare.json` |
| focused S12 compare | `/root/work/arm-sync/comparebool_compact_long_loop69_focus_s12_20260521/compare.json` |
| full JIT28 S12 compare | `/root/work/arm-sync/comparebool_compact_long_loop69_jit28_s12_20260521/compare.json` |

## 第二台 ARM 补充验证

123 上已经完成修正 runner 后的有效 full JIT28 S3：

| 项 | 结果 |
|---|---|
| 机器 | `123.60.27.61` |
| 架构 | `aarch64` |
| runner | `/root/work/arm-sync/run_jit28_retest_fixed_20260521.sh` |
| benchmark | full JIT28，当前环境有效展开为 20 rows |
| samples | `SAMPLES=3` |
| direct_url 检查 | baseline 和 candidate 均通过 driver/worker venv 来源检查 |
| candidate workdir | 使用 `rsync` 干净复制，排除 `scratch/`、`dist/`、`venv/` |

123 full JIT28 S3 结果：

| 指标 | 结果 |
|---|---:|
| geomean speedup | `+1.918%` |
| `coverage` | `+23.505%` |
| `coroutines` | 正向，进入 `>=5%` 正向行集合 |
| `comprehensions` | 正向，进入 `>=5%` 正向行集合 |
| `unpack_sequence` | `-7.990%` |

123 full JIT28 S12 结果：

| 指标 | 结果 |
|---|---:|
| valid rows | `20` |
| geomean speedup | `+1.853%` |
| `>=5%` 回退 | 无 |
| `coverage` | `+22.579%` |
| `coroutines` | `+3.169%` |
| `go` | `+2.137%` |
| `pickle_list` | `+1.991%` |
| `unpack_sequence` | `+0.743%` |

123 S12 artifact：

| 内容 | 路径 |
|---|---|
| run dir | `/root/work/arm-sync/retest_positive_123_loop69_s12_20260521_230506_s12` |
| baseline JSON | `/root/work/arm-sync/retest_positive_123_loop69_s12_20260521_230506_s12/base_jit28_s12.json` |
| candidate JSON | `/root/work/arm-sync/retest_positive_123_loop69_s12_20260521_230506_s12/loop69_jit28_s12.json` |
| compare JSON | `/root/work/arm-sync/retest_positive_123_loop69_s12_20260521_230506_s12/loop69_compare_s12.json` |
| summary JSON | `/root/work/arm-sync/retest_positive_123_loop69_s12_20260521_230506_s12/loop69_summary_s12.json` |

当前判断：123 S3 复现了 ARM 侧强 row 信号；S12 进一步确认 geomean 正向，`coverage` 强收益重复，
且 S3 的 `unpack_sequence` 回退没有复现。第二台 ARM gate 通过。

## x86 收益判断

由于 AArch64 上已有明确收益，Loop 110 已进入后置 x86 gate，并实际做了 x86 enable/测试。

结论：x86 不建议合入，最终代码必须保持 AArch64-only。

| 测试 | valid | geomean | 重点结果 | 判断 |
|---|---:|---:|---|---|
| x86 semantic smoke | - | - | compact int、大整数、`bool`、`int` subclass fallback 通过 | 正确性通过 |
| x86 full JIT28 S3 | 20 | speedup `-0.312%` | `coverage +3.418%` time，`json_loads +11.221%` time，`go -3.809%` time，`pickle_list -12.652%` time | full 范围不受益 |
| x86 focused S12 | 6 | speedup `+0.880%` | 无 `>=5%` 单项收益/回退 | 弱信号，不够合入 |

x86 artifact 记录在 `../loop-110-x86-comparebool-compact-long-fastpath/case.md`。Loop 110 的最终标签是：

- `arm-only-benefit`
- `x86-no-benefit`
- `do-not-merge-x86`

## 合入判断

| gate | 状态 | 说明 |
|---|---|---|
| 方案泛化性 | 通过 | 覆盖 exact compact `int` pair 这一类语义，不是 benchmark 特例 |
| AArch64 正确性 | 通过 | semantic smoke 已覆盖关键 fallback 语义 |
| AArch64 223 S12 | 通过 | full JIT28 S12 `+1.253%`，无 `>=5%` 回退 |
| 工作负载命中证据 | 通过 | Loop 68 counter 与 Loop 69 收益行对齐 |
| 第二台 ARM | 通过 | 123 full JIT28 S12 `+1.853%`，无 `>=5%` 回退，`coverage +22.579%` |
| x86 gate | 通过 | x86 已实测无稳定收益，最终合入应保持 AArch64-only |
| 中文 case | 已补齐 | 本文件已用中文记录方案、收益、x86 边界和合入判断 |
| patch 归档 | 已有本地归档 | `candidate.patch` 保留在本目录；本次合入可以不包含 patch 文件 |

当前可以标记为 `ready-for-human-review`。建议合入 AArch64-only 代码和本 `case.md`；`candidate.patch`
只保留为本地归档，本次合入不包含 patch 文件。x86 实验 patch 不合入，x86 默认路径保持不变。
