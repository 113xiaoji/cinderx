# Loop 74：CompareBool op-specific helper

## 当前结论

Loop 74 是 Loop 69 之后的一个 **AArch64-only 增量收益** 候选。它把
`CompareBool` compact long fast path 从“运行时 helper 内部按 `op` 分发”进一步收窄为
“LIR 已知 compare op 时直接调用固定 op 的两参数 helper”。

当前状态：`ready-for-human-review`

标签：

- `arm-only-benefit`
- `x86-not-applicable`
- `do-not-merge-x86`
- `ready-for-human-review`

合入建议：可以合入 AArch64-only 代码和本 `case.md`。`candidate.patch` 继续作为本地候选归档，不随本次代码提交合入。

此前没有合入的原因：223 上已经有正向 full JIT28 S12 结果，但还缺第二台 ARM 同口径补充验证。现在 123.60.27.61 已完成同口径 full JIT28 S12，趋势同向、无 `>=5%` 回退，因此合入前准备已经补齐，只差人工检视确认。

## 方案简介

Loop 69 已经把 AArch64 上部分 `CompareBool` 的 exact compact `int` 比较从
`PyObject_RichCompareBool(left, right, op)` 收窄到
`JITRT_FastPyObjectRichCompareBool(left, right, op)`，并在 helper 内部先尝试 compact-long fast path。

Loop 74 继续优化同一条热路径。LIR lowering 生成 call 时已经静态知道 `CompareOp`，所以没有必要每次都把 `op` 当作第三个参数传给 helper，再让 helper 里做 `switch(op)`。本方案新增 6 个固定 op helper：

- `JITRT_FastPyObjectRichCompareBoolLessThan(v, w)`
- `JITRT_FastPyObjectRichCompareBoolLessThanEqual(v, w)`
- `JITRT_FastPyObjectRichCompareBoolEqual(v, w)`
- `JITRT_FastPyObjectRichCompareBoolNotEqual(v, w)`
- `JITRT_FastPyObjectRichCompareBoolGreaterThan(v, w)`
- `JITRT_FastPyObjectRichCompareBoolGreaterThanEqual(v, w)`

合入后的 AArch64 路径如下：

| 场景 | Loop 69 路径 | Loop 74 路径 |
|---|---|---|
| `TLongExact` + `TLongExact` 的 `<` | 三参数 fast helper，helper 内 `switch(op)` | 两参数 `LessThan` helper |
| `TLongExact` + `TLongExact` 的 `<=` | 同上 | 两参数 `LessThanEqual` helper |
| `TLongExact` + `TLongExact` 的 `==` | 同上 | 两参数 `Equal` helper |
| `TLongExact` + `TLongExact` 的 `!=` | 同上 | 两参数 `NotEqual` helper |
| `TLongExact` + `TLongExact` 的 `>` | 同上 | 两参数 `GreaterThan` helper |
| `TLongExact` + `TLongExact` 的 `>=` | 同上 | 两参数 `GreaterThanEqual` helper |
| pointer-eq 语义可用的 `==` / `!=` fallback | 三参数 fast helper | 两参数 `Equal` / `NotEqual` helper |
| 其他 compare op 或 generic rich compare fallback | 保持旧路径 | 保持旧路径 |

每个两参数 helper 的逻辑仍然很窄：

1. 先检查左右对象都是 exact `PyLong`。
2. 再检查左右对象都是 compact long。
3. 命中后直接读取 compact value，并执行该 helper 对应的固定整数比较。
4. 任一条件不满足时，完整 fallback 到 `PyObject_RichCompareBool(v, w, PYOP)`。

## 方案泛化性和边界

这个方案优化的是一类明确语义：JIT 已经静态知道 compare op，并且运行时左右对象可能是 exact compact `int` 的 bool 比较。它不是为某一个 benchmark、某一个常量或某个偶然 LIR 形态写的特例。

| 输入或路径 | 处理方式 | 原因 |
|---|---|---|
| exact compact `int` + exact compact `int` | 两参数 helper 直接整数比较 | 语义等价，且不需要动态 `op` 参数和 `switch` |
| non-compact long / 大整数 | fallback | 避免改变大整数比较语义 |
| `bool` | fallback | `bool` 不是 exact `int`，保持原行为 |
| `int` subclass | fallback | subclass 可能有自定义行为 |
| 非 `int` 对象 | fallback | 保持 Python rich compare 行为 |
| generic `JITRT_RichCompareBool(v, w, op)` fallback | 不拆成两参数 helper | 该路径仍然需要动态 `op`，过宽拆分有回退风险 |

因此它足够通用，但边界清晰：只优化 AArch64 上已经由 Loop 69 证明有收益的 `CompareBool` fast helper 调用形态，不扩大到 generic rich compare fallback。

## 为什么 AArch64 更亲和

AArch64 上 runtime helper call 的成本更容易被放大：`bl` 直接调用范围约为 `±128MB`，当 JIT code buffer 与 C++ runtime helper 距离较远时，更容易退化为加载目标地址后 `blr` 的间接调用形态。Loop 69 已经减少了进入通用 rich compare 对象路径的成本，Loop 74 继续剥掉 fast helper 热路径里的剩余开销：

- 不再为已知 compare op materialize 第三个参数。
- helper 内不再执行 `switch(op)`。
- 每个 helper 的成功路径只有固定比较表达式，更利于分支预测和指令布局。
- pointer-eq 可用的 `==` / `!=` fallback 也能走固定 op helper。

这类收益在 AArch64 上更容易体现为低个位数增量。最终代码也通过平台宏把新路径限定在 AArch64，避免给 x86 带来无证据的路径变化。

## x86 gate 判断

最终合入形态使用已有平台宏：

```cpp
#if defined(__aarch64__)
#define CINDERX_JIT_COMPACT_LONG_COMPARE_BOOL_FASTPATH 1
#else
#define CINDERX_JIT_COMPACT_LONG_COMPARE_BOOL_FASTPATH 0
#endif
```

Loop 74 新增的 helper 声明、helper 定义，以及 generator 中调用两参数 helper 的分支，全部放在 `CINDERX_JIT_COMPACT_LONG_COMPARE_BOOL_FASTPATH` 下。非 AArch64 上宏为 `0`：

- 新 helper 不声明、不定义。
- generator 不编译两参数 helper 调用分支。
- `kFastLongRichCompareBool` 仍然是 `PyObject_RichCompareBool`。
- x86 默认 `CompareBool` lowering 行为不变。

因此本候选的 x86 gate 结论是：`x86-not-applicable`。如果未来要让 x86 也尝试类似方案，必须另外打开平台宏或新增 x86 enable patch，并独立跑 correctness 和标准 pyperformance A/B；这不属于本次 AArch64-only 合入范围。

## 223 AArch64 正确性和性能证据

测试环境：223 AArch64 远端环境，使用标准 `scripts/arm/run_pyperf_subset.sh` 和 `scripts/arm/compare_pyperf_subset.py`。

| 测试 | 结果 | 判断 |
|---|---:|---|
| semantic smoke | 通过 | 覆盖 6 类 compare op、exact compact int、大整数、`bool`、`int` subclass 和自定义 fallback |
| focused S3 | 6 valid，geomean speedup `+0.462%` | 无 `>=5%` 回退 |
| focused S12 | 6 valid，geomean speedup `+0.609%` | 无 `>=5%` 回退 |
| counter focused S1 | `entries_all=603537`，`compact_all=597214`，`fallback_all=6323` | workload 命中明确 |
| full JIT28 S3 | 20 valid，geomean speedup `+0.351%` | 无 `>=5%` 回退 |
| full JIT28 S12 | 20 valid，geomean speedup `+0.626%` | 无 `>=5%` 回退 |

223 full JIT28 S12 的逐项额外收益如下。baseline 是 Loop 69，candidate 是 Loop 69 + Loop 74。该环境下有效 row 为 20 个，缺失的 8 行是 `logging_format`、`logging_silent`、`logging_simple` 和 5 个 `scimark_*`。

| benchmark | Loop74 额外收益 |
|---|---:|
| `pickle_list` | `+3.035%` |
| `unpack_sequence` | `+2.442%` |
| `coroutines` | `+1.959%` |
| `richards` | `+1.158%` |
| `spectral_norm` | `+1.106%` |
| `pickle_dict` | `+0.777%` |
| `go` | `+0.711%` |
| `generators` | `+0.653%` |
| `pickle` | `+0.465%` |
| `json_loads` | `+0.393%` |
| `chaos` | `+0.344%` |
| `deltablue` | `+0.340%` |
| `float` | `+0.203%` |
| `nqueens` | `+0.135%` |
| `json_dumps` | `+0.034%` |
| `nbody` | `+0.033%` |
| `raytrace` | `-0.016%` |
| `fannkuch` | `-0.103%` |
| `coverage` | `-0.405%` |
| `comprehensions` | `-0.901%` |

223 artifact：

| 内容 | 路径 |
|---|---|
| build log | `/root/work/arm-sync/build_comparebool_op_helper_loop74_20260521.log` |
| semantic smoke | `/root/work/arm-sync/comparebool_op_helper_loop74_semantic_smoke_20260521.log` |
| counter summary | `/root/work/arm-sync/comparebool_op_helper_loop74_counter_focus_s1_20260521/summary.json` |
| focused S3 compare | `/root/work/arm-sync/comparebool_op_helper_loop74_focus_s3_20260521_compare.json` |
| focused S12 compare | `/root/work/arm-sync/comparebool_op_helper_loop74_focus_s12_20260521_compare.json` |
| full JIT28 S3 compare | `/root/work/arm-sync/comparebool_op_helper_loop74_jit28_s3_20260521_compare.json` |
| full JIT28 S12 compare | `/root/work/arm-sync/comparebool_op_helper_loop74_jit28_s12_20260521_compare.json` |

## 123 第二台 ARM 补充验证

测试环境：`123.60.27.61` AArch64，使用同口径 full JIT28 S12。

测试方法说明：第一次最终复测在 patch apply 阶段遇到 CRLF/LF 上下文不一致，失败点是源码文本换行，不是代码冲突。最终有效复测使用同一份 Loop 69 baseline 源码，在 base 和 candidate 共同前置阶段只对 3 个相关源码文件做 LF 归一化，然后仍使用标准 `run_jit28_retest_fixed_20260521.sh`、标准 `scripts/arm/run_pyperf_subset.sh` 和标准 compare 逻辑跑 full JIT28 S12。因此 A/B 的源码语义和测试口径保持等价。

| 项目 | 内容 |
|---|---|
| 机器 | `123.60.27.61` |
| run dir | `/root/work/arm-sync/retest_positive_123_loop74_final_s12_norm_20260522_090900` |
| runner | `/root/work/arm-sync/run_jit28_retest_fixed_20260521.sh` |
| baseline | Loop 69 final source |
| candidate | Loop 69 final source + Loop 74 AArch64-only patch |
| samples | `SAMPLES=12` |
| AUTOJIT | `50` |
| specialized opcodes | `CINDERX_ENABLE_SPECIALIZED_OPCODES=1` |
| semantic smoke | 通过，`semantic_smoke_ok 6 14` |
| valid rows | `20` |
| geomean speedup | `+1.774%` |
| `>=5%` regression | 无 |
| `>=5%` speedup | `comprehensions`、`spectral_norm` |

123 full JIT28 S12 逐项结果如下：

| benchmark | Loop74 额外收益 | base median | candidate median |
|---|---:|---:|---:|
| `spectral_norm` | `+6.480%` | `0.147637259506` | `0.138069852022` |
| `comprehensions` | `+5.944%` | `0.000065777975` | `0.000061867991` |
| `pickle` | `+3.258%` | `0.000019677877` | `0.000019036824` |
| `raytrace` | `+2.907%` | `0.554837968026` | `0.538707235537` |
| `coroutines` | `+2.667%` | `0.052118661522` | `0.050728586502` |
| `go` | `+2.547%` | `0.175971367455` | `0.171489605505` |
| `pickle_list` | `+2.538%` | `0.000007170305` | `0.000006988301` |
| `fannkuch` | `+1.788%` | `0.610965139524` | `0.600039399986` |
| `deltablue` | `+1.689%` | `0.063358406012` | `0.062288089481` |
| `json_dumps` | `+1.610%` | `0.029628838005` | `0.029151825002` |
| `richards` | `+1.525%` | `0.086761085026` | `0.085437856906` |
| `json_loads` | `+1.431%` | `0.000499933251` | `0.000492777725` |
| `nqueens` | `+1.360%` | `0.214064765023` | `0.211152734468` |
| `generators` | `+1.357%` | `0.072371148039` | `0.071389191959` |
| `nbody` | `+0.920%` | `0.136626799998` | `0.135370113479` |
| `chaos` | `-0.117%` | `0.123090469511` | `0.123234714032` |
| `coverage` | `-0.300%` | `0.010972297518` | `0.011005185021` |
| `unpack_sequence` | `-0.554%` | `0.000000106055` | `0.000000106643` |
| `pickle_dict` | `-0.723%` | `0.000034718600` | `0.000034969603` |
| `float` | `-1.236%` | `0.082201395009` | `0.083217804029` |

123 artifact：

| 内容 | 路径 |
|---|---|
| status | `/root/work/arm-sync/retest_positive_123_loop74_final_s12_norm_20260522_090900/status.tsv` |
| base JIT28 S12 | `/root/work/arm-sync/retest_positive_123_loop74_final_s12_norm_20260522_090900/base_jit28_s12.json` |
| candidate JIT28 S12 | `/root/work/arm-sync/retest_positive_123_loop74_final_s12_norm_20260522_090900/loop74_jit28_s12.json` |
| compare | `/root/work/arm-sync/retest_positive_123_loop74_final_s12_norm_20260522_090900/loop74_compare_s12.json` |
| summary | `/root/work/arm-sync/retest_positive_123_loop74_final_s12_norm_20260522_090900/loop74_summary_s12.json` |
| semantic smoke | `/root/work/arm-sync/retest_positive_123_loop74_final_s12_norm_20260522_090900/loop74_semantic_smoke.log` |

## 合入判断

| gate | 当前状态 | 说明 |
|---|---|---|
| 方案泛化性 | 通过 | 优化静态已知 compare op 的 exact compact `int` bool 比较，不是 benchmark 特例 |
| AArch64 平台边界 | 通过 | 新 helper 和 generator 两参数调用均在 AArch64 宏下 |
| x86 gate | 通过 | 最终代码非 AArch64 不编译新路径，判定为 `x86-not-applicable` |
| 223 correctness | 通过 | semantic smoke 覆盖关键 fallback 语义 |
| 223 full JIT28 S12 | 通过 | `+0.626%` geomean，无 `>=5%` 回退 |
| workload 命中证据 | 通过 | counter 显示 603537 次 op-helper 入口，597214 次 compact hit |
| 123 第二台 ARM | 通过 | full JIT28 S12 `+1.774%` geomean，无 `>=5%` 回退 |
| 中文 case | 通过 | 本文件用中文记录方案、边界、ARM/x86 判断、测试证据和合入结论 |

最终结论：Loop 74 是一个小而干净的 AArch64 增量收益候选。两台 ARM 上 full JIT28 S12 均为正向，且没有稳定 `>=5%` 回退；x86 默认路径不受影响。建议合入 AArch64-only 代码和本 case 记录。
