# AArch64 LoadAttr Agent 复现发现

## 当前整体进展

- case 文件和 Agent 角色已经实现在：
  `plans/cases/aarch64-loadattr-agent-repro/`。
- 本轮运行时的本地分支：
  `codex/aarch64-new-optimizations-20260512`。
- 本轮运行时的本地 HEAD：
  `6a330ecc perf(jit): fold aarch64 fp compare branches`。
- 用户要求的 `35` 远端 SSH 超时。本轮复现在 `root@113.44.53.223` 运行，该机器是
  AArch64，并且有 GCC 14.3.0：`/opt/gcc-14.3.0/bin/gcc`。
- 223 机器上的已有 source/workdir 状态：
  - no-fastpath broad baseline 目录：
    `/root/work/cinderx-jit28-base-6b47-gcc143`
  - LoadAttr fastpath candidate 目录：
    `/root/work/cinderx-jit28-base-gcc14`
- 第一轮 broad `6b47` vs `95f8ac63` S3 显示过很大收益，但不计为干净的
  LoadAttr 结果，因为这两个目录差异不只包含 LoadAttr 优化，而且 harness 也有差异。

## 候选表

| 候选 | 命中 pattern | 文件 | 核心思路 | ARM 依据 | x86 影响 | 证据 | 状态 |
|---|---|---|---|---|---|---|---|
| AArch64 LoadAttrCachedFastPath | Pattern 2：helper call 距离和调用形态差异 | `cinderx/Jit/lir/generator.cpp`, `cinderx/Jit/lir/instruction.h`, `cinderx/Jit/lir/postalloc.cpp`, `cinderx/Jit/codegen/autogen.cpp`, `cinderx/Jit/codegen/gen_asm.cpp`, `cinderx/Jit/codegen/gen_asm_utils.cpp` | 把 cached loadattr helper call 表达成 LIR pseudo instruction，并让 AArch64 热调用进入优化后的 helper/stub 路径 | AArch64 `bl` 直达范围约 `±128MB`，远距离 helper call 更容易需要 literal-load/materialize target 加 `blr`；热 cache-hit 路径受益于减少 helper-call 开销和 call-target materialization | x86-64 `call rel32` 通常覆盖约 `±2GB`，更容易保持 direct call；除非单独证明 x86 也存在 indirect call 或 stub 收益，否则默认不归因到 x86 | `113.44.53.223` 上的 microbench + focused S12 + partial JIT28 S3 | partially reproduced；机制成立，pyperformance 不成立 |

## 代码因果链

- HIR builder 在非 method 路径从 bytecode 发出普通 `LoadAttr`。
- HIR simplify 在 attr cache 开启且满足条件时，把 `LoadAttr` 变成
  `LoadAttrCached`。
- LIR generator 只在下面条件下把 `LoadAttrCached` lowering 成
  `LoadAttrCachedFastPath`：
  `CINDER_AARCH64 && PY_VERSION_HEX >= 0x030E0000 && !Py_GIL_DISABLED`。
- 非 AArch64、旧 Python 或 free-threading build 回退成普通
  `jit::LoadAttrCache::invoke` helper call。
- `LoadAttrCachedFastPath` 在 LIR 中是 call-like：
  invalidated flags、64-bit output、essential。
- postalloc 在 `rewriteCallInstrs()` 中处理 `LoadAttrCachedFastPath`：
  按 ABI 移动参数，随后只保留 call target input。不同于普通 call，这里保留 opcode
  交给 codegen。
- autogen 要求 postalloc 后形态必须刚好有一个 immediate input。
- AArch64 codegen 扫描热 call target，记录 `LoadAttrCache::invoke`，并使用
  `PYTHONJITAARCH64LOADATTRSTUBMINCALLS` 决定是否发出和使用 shared LoadAttr
  invoke stub。
- shared stub 开启时，call site branch 到 stub；stub 处理
  `kSplitInlineKnownOffset` cache hit，miss 时 tail 到真实 helper。
- x86 安全性：
  这个分支里 x86 不生成 `LoadAttrCachedFastPath`，所以默认 x86 行为仍是普通
  helper call。

## 测试证据

### 远端 Artifact 根目录

`/root/work/arm-sync/aarch64_loadattr_agent_repro_20260519`

### 2026-05-19 正常验证轮 Artifact 根目录

`/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440`

本轮运行在 `root@113.44.53.223`，`root@124.70.162.35` SSH 超时。环境为 AArch64、
Python 3.14.3、GCC 14.3.0，source/wheel 为 `/root/work/cinderx-jit28-base-gcc14`。

### 功能 / LIR 形态

- 单测：
  - 输出：
    `/root/work/arm-sync/aarch64_loadattr_agent_repro_20260519/loadattr_lir_fastpath_unittest.out`
  - 结果：passed
- LIR probe：
  - 脚本：
    `/root/work/arm-sync/aarch64_loadattr_agent_repro_20260519/loadattr_probe.py`
  - LIR log：
    `/root/work/arm-sync/aarch64_loadattr_agent_repro_20260519/loadattr_probe_lir.log`
  - LIR log 中 `LoadAttrCachedFastPath` 文本出现 4 次。
  - postalloc final section 包含：
    `LoadAttrCachedFastPath ...`，随后 guard 使用 `X0`。
- ASM dump：
  - 尝试使用 `PYTHONJITDUMPASM=1`，但这个小 probe 没有产生有用的汇编输出。
    因此本轮 ASM 证据暂时是 source-level codegen + LIR dump。

### 2026-05-19 正常验证轮 LIR / ASM

- Source shape：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/source_shape_grep.txt`
  确认 `LoadAttrCachedFastPath`、`loadAttrStubMinCalls()`、
  `emitLoadAttrCachedFastPathCall()` 和 autogen `GEN("i", ...)` 存在。
- LIR-only probe：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/loadattr_probe_lir_only.log`
  生成 `6403` bytes。
- LIR 形态：
  - generation 阶段出现 `LoadAttrCachedFastPath ... cache, obj, name`
  - register allocation 后出现 `X0:Object = LoadAttrCachedFastPath ...`
  - postalloc rewrites 后只剩 `LoadAttrCachedFastPath <immediate call target>`
- ASM dump：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/loadattr_probe_lir_asm.log`
  仍只有 80 bytes，未能提供可用机器码文本；ASM/disassembly 仍是缺失证据。

### Focused pyperformance：默认 stub vs 禁用 shared stub

对比方法：
- 同一个 source/wheel：`/root/work/cinderx-jit28-base-gcc14`
- current/default：不设置 `PYTHONJITAARCH64LOADATTRSTUBMINCALLS`
- base/disabled：`PYTHONJITAARCH64LOADATTRSTUBMINCALLS=9999`
- 扩展 harness，让 LoadAttr env var 传给 worker：
  `/root/work/arm-sync/aarch64_loadattr_agent_repro_20260519/run_subset_with_loadattr_env.sh`

Focused S3 object subset：
- compare：
  `/root/work/arm-sync/aarch64_loadattr_agent_repro_20260519/compare_default_vs_disabled_obj_s3.json`
- geomean：-0.896%
- rows：
  - `chaos`：-1.449%
  - `deltablue`：-0.623%
  - `go`：-0.406%
  - `nqueens`：-5.307%
  - `raytrace`：+1.903%
  - `richards`：+0.660%

Focused S12 object subset：
- compare：
  `/root/work/arm-sync/aarch64_loadattr_agent_repro_20260519/compare_default_vs_disabled_obj_s12.json`
- geomean：-0.087%
- rows：
  - `chaos`：-0.455%
  - `deltablue`：+0.636%
  - `go`：-0.725%
  - `nqueens`：+0.298%
  - `raytrace`：+0.714%
  - `richards`：-0.974%
- 结论：
  S3 中 `nqueens` >5% 信号没有通过 S12；分类为噪声或顺序效应，不是 accepted
  benchmark win。

### Microbench

Microbench 脚本：
`/root/work/arm-sync/aarch64_loadattr_agent_repro_20260519/loadattr_micro.py`

形态：
- `Box.value` split-inline 风格实例属性
- 对读取 `obj.value` 的 tight loop 强制 JIT
- 每个 sample 2,000,000 次循环，每个 variant 9 个 samples

结果：
- 禁用 shared stub median：
  `0.06207386200549081s`
- 默认 shared stub median：
  `0.048468282999238s`
- delta：
  `-21.918%`

结论：
合成的 split-inline 属性读取路径上，机器级机制强烈复现。但这不等价于
pyperformance workload 加速。

### 2026-05-19 正常验证轮 Microbench

- baseline/disabled：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/loadattr_micro_disabled9999_s9.json`
- candidate/default：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/loadattr_micro_default_s9.json`
- compare：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/loadattr_micro_compare.json`
- disabled median：`0.062131447994033806s`
- default median：`0.048846403005882166s`
- delta：`-21.382158982400245%`
- 分类：`mechanism-only`

### JIT28 / 更宽 pyperformance

20-row JIT28-compatible S3 subset：
- compare：
  `/root/work/arm-sync/aarch64_loadattr_agent_repro_20260519/compare_default_vs_disabled_jit28_s3.json`
- geomean：
  `-0.231%`
- 最大变慢行：
  - `go`：+3.413%
  - `json_dumps`：+2.503%
  - `generators`：+1.899%
- 最大变快行：
  - `pickle`：-3.829%，tiny
  - `comprehensions`：-2.777%，tiny
  - `coverage`：-2.202%

补充 `logging,scimark` group S3：
- compare：
  `/root/work/arm-sync/aarch64_loadattr_agent_repro_20260519/compare_default_vs_disabled_groups_logging_scimark_s3.json`
- S3 中 `logging_format`、`logging_silent`、`scimark_sor` 出现过 >5% 表面回退。

补充 `logging,scimark` group S12：
- compare：
  `/root/work/arm-sync/aarch64_loadattr_agent_repro_20260519/compare_default_vs_disabled_groups_logging_scimark_s12.json`
- 所有行低于 5%：
  - `logging_format`：-2.307%，tiny
  - `logging_silent`：+2.287%，tiny
  - `logging_simple`：-2.314%，tiny
  - `scimark_fft`：+0.075%
  - `scimark_lu`：+0.809%
  - `scimark_monte_carlo`：-0.053%
  - `scimark_sor`：-0.208%
  - `scimark_sparse_mat_mult`：+1.366%
- 结论：
  S3 group 回退不稳定。

### 2026-05-19 正常验证轮 Focused S3

- baseline：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/disabled_stub9999_obj_s3.json`
- candidate：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/default_stub_obj_s3.json`
- compare：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/compare_default_vs_disabled_obj_s3.json`
- geomean：`-0.8573638444860032%`
- rows：
  - `chaos`: `-1.029%`
  - `deltablue`: `+2.137%`
  - `go`: `-0.555%`
  - `nqueens`: `-4.646%`
  - `raytrace`: `+0.698%`
  - `richards`: `-1.616%`
- 结论：
  geomean < 1%，单项最大收益 `nqueens -4.646%` 未达到 >= 5% 的升级阈值；
  不升级 S12，分类为 noise / below gate。

## 缺失证据

- 本轮没有运行干净的 `pre-95f8ac63` vs `95f8ac63` same-host rebuild。这里最干净
  的可复现变量是同一个 candidate wheel 内的默认 shared stub vs 禁用 shared stub。
- 小 probe 没有捕获到有用 JIT ASM dump。source-level codegen 和 LIR dump 能证明
  路径选择，但最终合入证据最好补一个 disassembly artifact。
- 没有运行 full 28-row S12，因为 focused S12 没有保留性能信号，补充 groups 也清除
  了 >5% S3 异常。

## 最终分类

`mechanism-only` / `partially reproduced`

这套 Agent 工作流成功复现了：
- 代码因果链
- AArch64-only LIR 形态
- 合成机器级收益

没有复现：
- 可信 focused pyperformance 收益
- 任何 JIT28 停止条件结果

当前正确状态是：
机制 accepted，pyperformance workload benefit 不 accepted。
