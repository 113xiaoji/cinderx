# AArch64 JIT Agent 端到端找点轮 2026-05-19

## 最新整体进展

- 本轮目标不是跑一组 pyperformance 数字，而是先通过 Agent 协同找 LIR/CODEGEN/postalloc/regalloc 附近的 ARM 亲和优化点，再按仓库脚本验证。
- 分支：`codex/aarch64-new-optimizations-20260512`
- HEAD：`6a330ecc perf(jit): fold aarch64 fp compare branches`
- 本轮没有改 C++，没有跑长 benchmark。
- 当前 dirty 的 JIT C++ 文件经 Code Causal Chain Agent 复查，基本是 CRLF/LF 行尾噪音；真正语义 dirty 主要是文档、记录和 agent workflow 文件。
- 停止条件没有触发：
  - 没有可信重复 JIT28 单项提升 `>= 30%`。
  - 没有 full JIT28 geomean 提升 `>= 10%`。

## Agent 分工和结果

| Agent | 本轮职责 | 结果 |
|---|---|---|
| Orchestrator Agent | 控制范围、同步分支状态、合并结论 | 确认本轮先找点，不用 benchmark 当盲搜器 |
| Analysis Agent | 主动寻找 ARM/x86 差异和新 pattern | 产出 10 个候选，前 3 个优先做证据采集 |
| Code Causal Chain Agent | 追 HIR/LIR/postalloc/codegen 因果链 | 确认已有优化路径、x86 边界、dirty diff 噪音 |
| Perf Evidence Agent | 审测试方法和证据等级 | 确认正式验证必须用 `scripts/arm/run_pyperf_subset.sh`，但当前脚本不透传任意 env toggle |

## 当前最强候选排序

### 1. `GuardNotNegative` 热路径分支方向

- 状态：`needs-evidence`，不是 accepted。
- 落点：`cinderx/Jit/codegen/autogen.cpp` 的 AArch64 guard codegen；可能涉及 `gen_asm.cpp` 的 near-deopt island。
- 当前形态：
  - AArch64 `kNotNegative` 近似为 `tbz sign_bit, skip; b deopt; skip:`。
  - 热路径是 taken branch 到 `skip`，冷路径再跳 deopt。
- 目标形态：
  - 尝试 `tbnz sign_bit, near_deopt`，让非负热路径 fallthrough。
- ARM 依据：
  - AArch64 有 `tbz/tbnz`，适合 sign bit guard。
  - x86 通常是 flags branch，且短/长距离覆盖问题不同。
- 风险/去重：
  - 历史已有多个 `GuardNotNegative tbnz` 变体，结果 mixed 或 below-gate。
  - 不能直接重做；下一步先统计 still-hot shape 和 `b continuation` 开销是否解释了旧实验不稳。
- 预期 workload：
  - `nbody`, `float`, `scimark_*`, `spectral_norm`, `raytrace`。

### 2. 整数 `Compare + CondBranch` 融合

- 状态：`needs-evidence`，不是 accepted。
- 落点：`cinderx/Jit/lir/postalloc.cpp::doRewriteCondBranch()`。
- 当前形态：
  - FP compare 已可从 `fcmp; cset; cbz/cbnz` 变成 `fcmp; b.<cc>`。
  - 整数 compare 仍可能是 `cmp; cset tmp; cbnz tmp`。
- 目标形态：
  - 对 last-use 的整数 compare 也改成 `cmp; b.<cc>`。
- ARM 依据：
  - 去掉 bool materialization、减少临时 GP 寄存器依赖和一条条件选择。
  - x86 也可能受益，但 x86 macro-fusion 和 direct jcc 已更成熟，因此不是纯 ARM-only。
- 风险/去重：
  - 历史记录里有 direct compare-branch 相关候选，收益较小。
  - 下一步必须先做 LIR census，确认是否还有未覆盖的整数 compare branch 形态。
- 预期 workload：
  - `go`, `richards`, `deltablue`, `raytrace`, `nbody`, `scimark_*`。

### 3. `LoadModuleMethodCache` AArch64 快路径 stub

- 状态：`needs-evidence`。
- 落点：CODEGEN / helper-call stub。
- 当前已知相邻优化：
  - `LoadModuleAttrCache::lookupHelper` 已有 AArch64 专用 stub。
  - `LoadModuleMethodCached` 仍可能走 helper call。
- 目标形态：
  - 为 module-method cache hit 做 AArch64 fast path：module/cache pointer/value check + incref + 双寄存器返回。
  - miss 回原 helper。
- ARM 依据：
  - 命中 `helper call 距离和调用形态差异` pattern。
  - AArch64 helper call 更容易退化为 literal load + `blr` 或 shared stub；x86 direct call 成本通常低。
- 风险：
  - 多返回寄存器、refcount、method/self 语义必须精确。
  - 需要先证明 JIT28 中 `LoadModuleMethodCached` 动态频率足够高。
- 预期 workload：
  - `go`, `richards`, `deltablue`, `chaos`, `nqueens`。

## 机制候选池

这些候选暂时只能算 `mechanism-only` 或 `needs-evidence`，不能作为性能结论：

| 候选 | 主要理由 | 下一步证据 |
|---|---|---|
| `LoadMethodCache` / `LoadTypeMethodCache` fast stub | 多寄存器返回 inline-cache helper 消除；历史上 helper sample 可降，但 workload mixed | cache hit 率、ABI ASM、focused method-call benchmark |
| `BitTest + Branch` -> `tbz/tbnz` | AArch64 bit branch 更直接；历史已有类似实验 | LIR 频率、目标距离、generator/coroutine subset |
| primitive modulo -> `sdiv/udiv + msub` | AArch64 有 `msub`，x86 路径不同 | 热点是否真有 `JITRT_Mod*`，语义边界 |
| constant multiply strength reduction | `*2^k` / `*(2^k±1)` 可用 shift/add/sub | `Mul imm` 常量分布和 numeric focused |
| `Select` immediate 特化 | `0/1` 可退化为 `cset`，false=0 可用 `wzr/xzr` | JIT28 `Select` 常量形态统计 |
| `MemImm` 绝对地址 load 池化 | AArch64 每次 materialize address，x86 可直接 memory operand | 重复地址和 hot block ASM 统计 |
| `optimizeMoveSequence` 更细保留 copy facts | ARM helper literal scratch 和 call-arg rewrite 放大 move/reload | move/spill/reload census |

## 已有强证据和否决边界

### 已有 full JIT28 硬证据

- `AArch64 FP compare branch folding`
- 证据：
  - focused S12 geomean：约 `-2.803%`
  - `scimark_sor` focused S12：约 `-12.246%`
  - full JIT28 S12 geomean：约 `-3.912%`
  - full JIT28 无 `>5%` 回归项
- 状态：
  - 有真实 workload 收益，但没有达到停止条件。

### mechanism-only

- `LoadAttrCachedFastPath`
- 机制：
  - 把 `LoadAttrCache::invoke` 从普通 helper call 变成 AArch64 可识别的 LIR pseudo instruction。
  - AArch64 可进入 shared stub；miss 回原 helper。
  - x86 默认普通 helper call。
- 证据：
  - microbench 可以看到约 `-21%` 机制收益。
  - focused S3 geomean约 `-0.857%`。
  - 历史 S12 geomean约 `-0.087%`。
- 状态：
  - 机制成立，pyperformance workload benefit 不 accepted。

## 测试方法结论

- 正式性能验证必须走：
  - `scripts/arm/run_pyperf_subset.sh`
  - `scripts/arm/compare_pyperf_subset.py`
  - `scripts/arm/pyperf_env_hook/sitecustomize.py`
- 固定口径：
  - driver：`PYTHONJITDISABLE=1`
  - worker：由 hook 读 `CINDERX_WORKER_PYTHONJITAUTO`
  - 默认 `AUTOJIT=50`
  - 默认 `CINDERX_ENABLE_SPECIALIZED_OPCODES=1`
  - GCC14
- 当前脚本不透传任意 env toggle，只继承有限变量。
- 因此正式 A/B 优先用两套干净 wheel / workdir，而不是临时 env toggle。

## 下一步建议

1. 先做 LIR/ASM census，不直接写优化：
   - `GuardNotNegative`：统计 sign-bit guard 数量、分支方向、near-deopt `b continuation` 数量。
   - 整数 compare branch：统计 `Compare -> CondBranch` last-use 数量和 `cset+cbz/cbnz` ASM。
   - `LoadModuleMethodCache`：统计 helper call target 数量、cache hit 相关 LIR、AArch64 call 形态。
2. 从 census 里选一个动态频率最高、证据最强、可执行的候选，自动写实验 patch。
3. 按脚本跑：
   - smoke：`nbody S1`
   - focused S3：候选相关 subset
   - 若单项 `>=5%` 或 geomean 有清晰信号，升级 S12
   - 合入/汇报前再跑 full JIT28
4. 对历史已经测过且 below-gate 的候选，不重复投入，除非 census 证明这次命中了新的未覆盖形态。
