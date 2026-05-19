# AArch64 JIT Agent 发现轮 2026-05-19

## 最新整体进展

- 分支：`codex/aarch64-new-optimizations-20260512`
- 本轮方式：4 个只读 subagent 并行复查，没有改 C++ 源码，没有跑新的远端 benchmark。
- 已确认 `docs/agents/aarch64-jit-perf/patterns.md` 只是第一轮 checklist，不是搜索边界。
- 本轮停止条件未触发：
  - 没有可信重复测试中的单个 JIT28 benchmark 提升 `>= 30%`。
  - 没有 full JIT28 geomean 提升 `>= 10%`。
- 当前唯一有 full JIT28 S12 级硬证据的候选仍是 `AArch64 FP compare branch folding`。
- `AArch64 LoadAttrCachedFastPath` 仍归类为 `mechanism-only`：microbench 证明 helper-call/stub 机制成立，但 pyperformance workload 收益未接受。

## Agent 分工

| Agent | 本轮职责 | 产出 |
|---|---|---|
| Progress Audit Agent | 扫 `progress.md`、`findings.md`、case 记录，区分 accepted、below-gate、rejected、needs-repeat | 全量候选状态表和证据索引 |
| Analysis Agent | 读取 pattern，但主动寻找不在 pattern 里的 ARM/x86 差异 | 新候选排序：indexed addressing、整数 compare+branch、near-deopt 布局、immediate encoding、absolute data address |
| Code Causal Chain Agent | 复查 LIR/CODEGEN/postalloc/regalloc 代码链路 | 给出候选的 HIR/LIR、postalloc、codegen 因果路径 |
| Perf Evidence Agent | 审计已有 JSON/compare/日志，判断可信度 | 明确 FP compare 是硬证据，LoadAttr 是机制证据，其余多数 below-gate 或 rejected |

## 当前最强候选

### 1. AArch64 FP compare branch folding

- 状态：`accepted / stable signal`，但未达到本轮 stop condition。
- 层级：postalloc + codegen。
- 代码因果：
  - before：`fcmp; cset; cbnz/cbz`
  - after：`fcmp; b.<cc>`
  - 少掉 bool materialization 和 GP register dependency。
- 证据：
  - focused S12 geomean：`-2.803%`
  - `scimark_sor` focused S12：`-12.246%`
  - full JIT28 S12 geomean：`-3.912%`
  - full JIT28 无 `>5%` 回归项。
- 记录：
  - `/root/work/arm-sync/candidate_g_fixedjit_focused_s12_compare_20260512_174941.json`
  - `/root/work/arm-sync/candidate_g_fixedjit_jit28_s12_compare_20260512_175606.json`
  - `plans/2026-05-12-aarch64-fp-compare-branch/issue_body.md`

### 2. AArch64 LoadAttrCachedFastPath

- 状态：`mechanism-only`，不作为 workload 收益。
- 层级：LIR pseudo instruction + codegen shared stub。
- 代码因果：
  - `LoadAttrCache::invoke` 从普通 helper call 变成 AArch64 可识别的 `LoadAttrCachedFastPath`。
  - AArch64 可走 shared stub/fast path，miss 回原 helper。
  - x86 默认 fallback 到普通 helper call。
- 证据：
  - microbench：default stub 相对禁用 stub `-21.38%` 左右。
  - focused pyperformance S3 geomean：`-0.857%`。
  - 没有单项 `>=5%` 的可信信号，因此未升级 S12。
  - 历史 S12 geomean约 `-0.087%`，不能证明 workload 收益。
- 记录：
  - `plans/cases/aarch64-loadattr-agent-repro/normal-run-20260519.md`
  - `plans/cases/aarch64-loadattr-agent-repro/findings.md`

### 3. Frame/tstate unlink 家族

- 状态：`below-gate / needs-repeat`。
- 层级：codegen + runtime helper。
- 代表候选：
  - `JITRT_UnlinkFrameFromTstate`
  - tstate-aware frame unlink + clear refinement
  - fast non-generator `FrameHeader` lookup
- 已有证据：
  - `JITRT_UnlinkFrameFromTstate` current4 S3/W3 object geomean：约 `-1.89%`
  - tstate-aware frame unlink + clear refinement S3/W3 object geomean：约 `-2.15%`
  - fast non-generator `FrameHeader` lookup S3/W3 object geomean：约 `-1.73%`
- 判断：
  - 这些是目前 below-gate 里最干净的一组，优先升级到同 host interleaved S12。
  - 不属于用户原始 `patterns.md` 的直接条目，应沉淀为新 hypothesis：frame/tstate runtime path。

### 4. GuardNotNegative near-aware `tbnz`

- 状态：`below-gate / needs-repeat`。
- 层级：codegen/postalloc。
- 命中 pattern：`tbz/tbnz` 分支/guard。
- 已有证据：
  - 223 ARM object S3：约 `-1.20%`
  - 28-row S1/S3 有小 geomean，但 mixed。
  - `pickle_list -22.62%` 是 tiny 行，不作为主证据。
- 技术风险：
  - `near_deopt_label()` 会引入 `b continuation`，在 fallthrough block 多时可能抵消 `tbz; b` -> `tbnz` 的收益。
- 判断：
  - 有形态价值，但不是 merge candidate。
  - 需要先做 fallthrough/near-deopt branch census，再做 S12。

## 新发现候选排序

这些不是已有 pattern 的机械展开，全部是 `hypothesis / needs-evidence`。

| 排名 | 候选 | 代码位置 | ARM 依据 | x86 影响判断 | 下一步证据 |
|---:|---|---|---|---|---|
| 1 | AArch64 indexed load/store 直接寻址 | `autogen.cpp` 的 `ptrIndirect()`；`generator.cpp` 的 array/tuple indexing | AArch64 支持 register-offset / shifted-register addressing，可省 `add scratch` | x86 已有 SIB，一般收益小 | 采集 ASM：`add tmp, base, idx, lsl; ldr` -> `ldr [base, idx, lsl]` |
| 2 | 整数 compare + `CondBranch` 融合 | `postalloc.cpp` FP-only fusion；`autogen.cpp` compare/cset | 去掉 `cset + cbz/cbnz`，直接 `cmp + b.<cc>` | x86 也可能受益，不是 ARM-only | 统计 last-use integer compare branch；做 LIR/ASM probe |
| 3 | `BitTest/Test32/sign-bit` -> `tbz/tbnz` | `generator.cpp` frame cleanup/refcount；`autogen.cpp` `BitTest` | bit branch 直接表达，不污染 flags | x86 `bt + jc/jnc` 已自然匹配 | 先语义验证，再 shape/benchmark |
| 4 | cache helper fast stub 扩展到 LoadMethod/TypeMethod/TypeAttr | `generator.cpp` cache helper call；`gen_asm_utils.cpp` target special cases | AArch64 helper call 常为 literal load + `blr`，cache hit 热 | x86 direct call 成本低，但 inline fast path 仍可能有效 | hot call target count + AArch64/x86 ASM |
| 5 | near-deopt stub 布局优化 | `flushAarch64NearDeoptBranches()` | AArch64 短条件分支需要 near island，但 island 可能污染 hot path | x86 `jcc rel32` 通常无此问题 | 统计 hot `b continuation` 数量和距离 |
| 6 | 负立即数/常量乘法 ARM 化 | `postgen.cpp` large const；`arch.cpp` `cmp_immediate()`；`autogen.cpp` `Mul imm` | `cmn`、shifted add/sub、lsl 可省 scratch/mul | x86 有 imm32 `imul` 和 `lea` | micro ASM + focused primitive/int rows |
| 7 | absolute data address 加载池化/基址复用 | `postalloc.cpp` MemImm rewrite；cache entry load sites | AArch64 absolute data load 需 address materialization | x86 可直接 memory operand | cache entry load ASM/code size census |

## 代码因果链摘录

- `postalloc.cpp` 目前只对 FP compare + branch 做 fusion，整数 compare 仍会走 `cmp/fcmp + cset`，然后 `BranchZ/NZ` 才发 `cbz/cbnz`。
- `autogen.cpp` 的 AArch64 `BranchZ/BranchNZ` 已经能发 `cbz/cbnz`，问题在 compare 结果已经被物化成 bool。
- `autogen.cpp` 的 AArch64 `BitTest` 当前发 `tst reg, mask`，后续 `BranchC/BranchNC` 仍是 flag branch；可探索直接 `tbz/tbnz`。
- `gen_asm_utils.cpp` 中 AArch64 普通 helper call 在 hot section 倾向 literal load + `blr` 或 shared stub；x86 仍是 direct call。
- `gen_asm.cpp` 的 near-deopt flush 会在 fallthrough 场景插入 `b continuation`，这是 `GuardNotNegative tbnz` 小收益变 mixed 的主要怀疑点。

## 测试证据分类

### full JIT28 真实收益

- 只有 FP compare branch folding 有 full JIT28 S12：geomean `-3.912%`。

### focused S12 / S3 below-gate

- frame/tstate unlink：约 `-1.89%` 到 `-2.15%` object S3/W3。
- fast non-generator `FrameHeader`：约 `-1.73%` object S3/W3。
- `GuardNotNegative tbnz`：约 `-1%` 附近，但 mixed。
- direct primitive `StoreArrayItem`：scimark S3/W3 geomean 约 `-1.59%`。

### micro / mechanism-only

- LoadAttr shared stub microbench 约 `-21%`，但 workload 不成立。
- LoadMethod shared stub perf 可以让 helper sample 降到 0，但 `go/richards` 回归，属于机制成立、真实 workload 不采用。

### tiny / 噪声警告

- `logging_silent`
- `logging_format`
- `logging_simple`
- `comprehensions`
- `pickle_list`
- `unpack_sequence`

这些绝对耗时太小或历史上 S3/S12 不稳定，不能当 stop condition 或合入主证据。

## 下一步建议

1. 先做最小 LIR/ASM census，不直接写优化：
   - integer compare + branch last-use 形态数量；
   - indexed load/store 当前 `add scratch + ldr/str` 数量；
   - `BitTest/Test32/sign-bit` 后接 branch 数量；
   - near-deopt `b continuation` 数量。
2. 如果要继续跑性能，优先把 frame/tstate 和 near-aware `GuardNotNegative tbnz` 升级到同 host focused S12。
3. 如果要开发新代码，第一优先级是整数 compare + branch 或 indexed addressing，但必须先确认已有历史 prototype 没有覆盖同形态，避免重复实验。
4. 对 LoadAttr 不建议继续用 pyperformance 追 full JIT28，除非先补齐可用 ASM/disassembly 证据；它当前只支持机制汇报。
