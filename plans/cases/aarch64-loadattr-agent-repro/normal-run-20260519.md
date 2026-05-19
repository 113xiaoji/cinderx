# AArch64 LoadAttr 正常验证轮 2026-05-19

## 运行范围

本轮按 `docs/agents/aarch64-jit-perf/README.md` 的 AGENTS 规则执行一次正常验证轮。
目标是验证 `AArch64 LoadAttrCachedFastPath` / `LoadAttrCache::invoke` shared stub
候选，而不是继续做新代码实现。

## Agent 分工

- Progress Audit Agent：只读复核本地分支、dirty 范围、候选状态和缺失证据。
- Analysis Agent：读取 `patterns.md`，确认该候选主命中
  `Pattern 2：helper call 距离和调用形态差异`。
- Perf Evidence Agent：给出本轮最小 benchmark matrix 和噪声判定规则。
- Orchestrator：在 223 远端执行真实验证命令，并统一记录 artifact。

## 远端环境

- 用户原先指定的 `root@124.70.162.35`：SSH 仍超时，未能运行。
- 实际运行远端：`root@113.44.53.223`
- 架构：`aarch64`
- 主机：`ecs-ed5f-bffc-437c-7edf`
- 时间：`2026-05-19T18:24:40+08:00`
- Python：`Python 3.14.3`
- GCC：`gcc (GCC) 14.3.0`
- source/wheel 目录：`/root/work/cinderx-jit28-base-gcc14`
- artifact 根目录：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440`

## Pattern 映射

主命中：
`Pattern 2：helper call 距离和调用形态差异`

原因：
`LoadAttrCachedFastPath` 把热的 `LoadAttrCache::invoke` helper call 提升为
AArch64 可识别的 LIR pseudo instruction。AArch64 codegen 可把远距离 helper 调用
转换为本地 `bl` 到 shared stub，并在 stub 内处理 split-inline cache hit；miss 再回
真实 helper。x86 默认仍是普通 helper call，不用 ARM 结论外推。

次要命中：
`Pattern 1：分支/guard 性能优势` 的 guard 子形态，因为 shared stub 内部包含 cache、
type、kind、inline values 等短 guard。

## Source Shape 证据

路径：
`/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/source_shape_grep.txt`

确认到：

- `cinderx/Jit/lir/generator.cpp` 生成 `Instruction::kLoadAttrCachedFastPath`
- `cinderx/Jit/codegen/gen_asm.cpp` 识别 `instr.isLoadAttrCachedFastPath()`
- `cinderx/Jit/codegen/gen_asm_utils.cpp` 有 `loadAttrStubMinCalls()`
- `emitLoadAttrCachedFastPathCall()` 处理 shared stub / fallback helper call
- `cinderx/Jit/codegen/autogen.cpp` 有 `translateLoadAttrCachedFastPath`
- autogen rule 为 `BEGIN_RULES(Instruction::kLoadAttrCachedFastPath)` / `GEN("i", ...)`

## LIR / ASM 证据

LIR-only probe 成功：

- 脚本：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/loadattr_probe.py`
- LIR log：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/loadattr_probe_lir_only.log`
- log 大小：`6403` bytes

关键形态：

- generation 阶段出现：
  `LoadAttrCachedFastPath ... cache, obj, name`
- register allocation 后出现：
  `X0:Object = LoadAttrCachedFastPath ... X20:Object, X19:Object`
- postalloc rewrites 后出现：
  `LoadAttrCachedFastPath 281473370770752(0xffffa0474d40):Object`
- postalloc 后只剩 immediate call target，符合 autogen `GEN("i", ...)` 形态。

ASM dump 仍不可用：

- `PYTHONJITDUMPASM=1` probe 90 秒后只生成 80 bytes：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/loadattr_probe_lir_asm.log`
- 内容只有 `JIT: ... gen_asm.cpp:923 --`
- 因此本轮 ASM 仍是缺口，不能声称已经拿到 before/after 机器码文本。

## Microbench

路径：

- baseline/disabled：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/loadattr_micro_disabled9999_s9.json`
- candidate/default：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/loadattr_micro_default_s9.json`
- compare：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/loadattr_micro_compare.json`

结果：

| Variant | Median |
|---|---:|
| disabled `PYTHONJITAARCH64LOADATTRSTUBMINCALLS=9999` | `0.062131447994033806s` |
| default shared stub | `0.048846403005882166s` |

delta：
`-21.382158982400245%`

结论：
机制层收益再次复现；只能作为 `mechanism-only`，不能当作 pyperformance workload
收益。

## Focused pyperformance S3

对比方法：

- 同一个 source/wheel：`/root/work/cinderx-jit28-base-gcc14`
- baseline/disabled：
  `PYTHONJITAARCH64LOADATTRSTUBMINCALLS=9999`
- candidate/default：
  不设置 `PYTHONJITAARCH64LOADATTRSTUBMINCALLS`
- benchmarks：
  `chaos,deltablue,go,nqueens,raytrace,richards`
- samples：`3`

artifact：

- baseline：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/disabled_stub9999_obj_s3.json`
- candidate：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/default_stub_obj_s3.json`
- compare：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/compare_default_vs_disabled_obj_s3.json`

结果：

| Benchmark | Delta | Baseline median | Candidate median |
|---|---:|---:|---:|
| chaos | `-1.029%` | `0.080942816` | `0.080109990` |
| deltablue | `+2.137%` | `0.004416237` | `0.004510622` |
| go | `-0.555%` | `0.136458452` | `0.135701591` |
| nqueens | `-4.646%` | `0.164746974` | `0.157092519` |
| raytrace | `+0.698%` | `0.389699831` | `0.392420518` |
| richards | `-1.616%` | `0.059034825` | `0.058081066` |

geomean：
`-0.8573638444860032%`

判定：

- geomean < 1%，默认噪声。
- 单项最大收益 `nqueens -4.646%`，没有达到单项 >= 5% 的 S12 升级阈值。
- 因此本轮按 Perf Evidence Agent 的规则不升级 focused S12。

## 停止条件

未满足：

- 没有可信重复 JIT28 单项 >= 30%。
- 没有 full JIT28 geomean >= 10%。
- 本轮只完成 focused S3；由于信号不足，没有升级 S12/full JIT28。

## 最终分类

`mechanism-only`

机制层结论：
`LoadAttrCachedFastPath` / shared stub 对 synthetic split-inline 属性读取路径有稳定
机器级收益。

workload 结论：
focused pyperformance S3 未给出足够信号；本轮不接受 workload benefit。

## 继续合入或汇报前的最小缺口

- 可用的 ASM/disassembly artifact，证明 default stub 和 disabled stub 的真实机器码
  调用形态差异。
- 如果要 claim workload 收益，需要同 host、同 wheel 的 focused S12 或 full JIT28
  S12 保持稳定同向信号。
- 如果要 claim patch commit 收益，而不是 stub toggle 机制收益，需要干净
  `pre-95f8ac63` vs `95f8ac63` same-host rebuild pair。
