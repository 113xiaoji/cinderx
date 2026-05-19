# AArch64 LoadAttr Agent 复现进展

## 2026-05-19

- 创建 case 工作流，用显式 Agent 角色复现 AArch64 LoadAttr 优化。
- 开始只读审计当前分支、代码因果链和性能证据。
- Progress Audit Agent 发现当前 source diff 主要是换行噪声和记录文件改动；
  没有活跃的未提交 LoadAttr 源码候选。
- Code Causal Chain Agent 确认路径：
  HIR `LoadAttrCached` -> AArch64-only LIR `LoadAttrCachedFastPath` ->
  postalloc call rewrite -> AArch64 shared LoadAttr invoke stub。
- Perf Evidence Agent 发现历史记录缺少干净的
  `pre-95f8ac63` vs `95f8ac63` pyperformance pair。
- 远端 `root@124.70.162.35` SSH 超时。改用可访问的 AArch64 机器
  `root@113.44.53.223`。
- 创建远端 harness：
  `/root/work/arm-sync/aarch64_loadattr_agent_repro_20260519/run_subset_with_loadattr_env.sh`
  让 pyperformance worker 继承 `PYTHONJITAARCH64LOADATTRSTUBMINCALLS`。
- 在同一个 candidate wheel 内运行默认 LoadAttr shared stub 对比禁用 shared stub
  (`PYTHONJITAARCH64LOADATTRSTUBMINCALLS=9999`)。
- Focused S3 出现一个表面上的 `nqueens` -5.307% 收益，但 focused S12 中同一行
  变成 +0.298%；将 S3 信号分类为噪声。
- Microbench 复现机制：
  default stub `0.048468282999238s` vs disabled `0.06207386200549081s`，
  delta `-21.918%`。
- 更宽的 20-row S3 geomean 只有 `-0.231%`。
- 补充 `logging,scimark` S12 清除了 S3 中 >5% 的异常。
- 本轮最终状态：
  partially reproduced；机制成立，pyperformance workload 收益不成立。

## 2026-05-19 AGENTS 规则干运行

- 按 `docs/agents/aarch64-jit-perf/README.md` 的规则并行启动 4 个只读 Agent：
  Progress Audit、Analysis、Code Causal Chain、Perf Evidence。
- Orchestrator 本地检查通过：
  - 当前分支：`codex/aarch64-new-optimizations-20260512`
  - `docs/agents/aarch64-jit-perf/patterns.md` 存在
  - case `findings.md` 已有 `命中 pattern` 列
  - `AArch64 LoadAttrCachedFastPath` 已映射到
    `Pattern 2：helper call 距离和调用形态差异`
- Progress Audit Agent 输出有效：
  - 当前最强候选为 `AArch64 LoadAttrCachedFastPath`
  - 状态应归为 `mechanism-only`，case 内历史写作 `partially reproduced`
  - `PYTHONJITAARCH64LOADATTRSTUBMINCALLS=6` threshold tuning 为 rejected
  - broad `6b47` vs `95f8ac63` S3 为 invalid，不可归因到 LoadAttr
- Analysis Agent 输出有效：
  - 主命中 `Pattern 2`
  - 次要命中 `Pattern 1` 中的 guard 子形态
  - 判断该候选仍是 ARM-affine，但 workload 收益不能 accepted
- Code Causal Chain Agent 输出有效：
  - 确认 HIR `LoadAttr` -> `LoadAttrCached`
  - AArch64/Python 3.14+/非 no-GIL 下生成 `LoadAttrCachedFastPath`
  - postalloc 按 call-like ABI 改写并保留 opcode
  - AArch64 codegen 选择 direct helper call 或 shared stub
  - x86 继续普通 `kCall LoadAttrCache::invoke`
  - 主要风险为 verifier 契约、ABI 隐式约定、CPython 布局同步
- Perf Evidence Agent 输出有效：
  - microbench：default stub 比 disabled 快 `21.918%`
  - focused S12：geomean `-0.087%`，判定为 noise
  - 20-row JIT28-compatible S3：geomean `-0.231%`，远低于 stop gate
  - 最终分类：机制层 accepted，pyperformance workload benefit not accepted
- 干运行结论：
  AGENTS 规则可以跑起来，并且能把 pattern、代码因果链和性能证据连接起来。
  这套流程没有把 microbench 收益误判成 workload 收益，也能明确列出继续合入前
  缺少的干净 same-host rebuild、ASM/disassembly artifact 和 full JIT28 S12。

## 2026-05-19 AGENTS 正常验证轮

- 按 AGENTS 规则正常跑了一轮，不修改 JIT 源码。
- 并行启动 3 个只读 Agent：
  Progress Audit、Analysis、Perf Evidence。
- `root@124.70.162.35` SSH 仍超时；本轮实际运行在
  `root@113.44.53.223`。
- 远端环境：
  - arch：`aarch64`
  - Python：`Python 3.14.3`
  - GCC：`gcc (GCC) 14.3.0`
  - source/wheel：`/root/work/cinderx-jit28-base-gcc14`
  - artifact 根：
    `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440`
- Source shape grep 确认候选目录包含：
  `LoadAttrCachedFastPath` lowering、`loadAttrStubMinCalls()`、
  `emitLoadAttrCachedFastPathCall()`、autogen `GEN("i", ...)`。
- LIR-only probe 成功：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/loadattr_probe_lir_only.log`
  中 postalloc 后仍有 `LoadAttrCachedFastPath`，且形态变成单 immediate call target。
- ASM dump 仍不可用：
  `PYTHONJITDUMPASM=1` 90 秒只生成 80 bytes，本轮继续把 ASM/disassembly 标为缺口。
- Microbench S9：
  default shared stub median `0.048846403005882166s`，
  disabled stub median `0.062131447994033806s`，
  delta `-21.382158982400245%`。
- Focused object S3：
  compare 路径：
  `/root/work/arm-sync/aarch64_loadattr_agent_normal_20260519_182440/compare_default_vs_disabled_obj_s3.json`
  geomean `-0.8573638444860032%`。
- Focused S3 rows：
  - `chaos`: `-1.029%`
  - `deltablue`: `+2.137%`
  - `go`: `-0.555%`
  - `nqueens`: `-4.646%`
  - `raytrace`: `+0.698%`
  - `richards`: `-1.616%`
- 按 Perf Evidence Agent 噪声规则：
  geomean < 1%，且没有单项 >= 5%，所以不升级 S12。
- 本轮最终状态：
  `mechanism-only`。机制收益复现，pyperformance workload 收益未 accepted，未满足停止条件。
