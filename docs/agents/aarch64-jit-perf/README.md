# AArch64 JIT 性能优化 Agent 工作流

## 当前覆盖规则

用户已要求：候选不需要“足够小”才执行，整个流程默认全自动推进。
Orchestrator 选择当前证据最强、可执行的候选后，Implementation Agent 直接实现实验 patch；
只有越出 LIR/CODEGEN/postalloc/regalloc 范围、改变 benchmark 脚本语义、破坏 x86 默认安全边界、
或远端环境不可用时才暂停并记录 blocker。未触发停止条件时必须继续下一轮。

这套工作流用于推进 CinderX ARM/AArch64 JIT 后端性能优化。范围刻意收紧在
LIR、CODEGEN、postalloc、regalloc、LIR/ASM 证据，以及后端附近的 runtime
helper 调用成本。除非 HIR 改动能明确服务于 ARM 后端性能证明或解锁，否则不要
把这套流程扩展成泛泛的 HIR 功能优化。

## 适用场景

任务提到下面任意内容时，使用这套流程：

- ARM、AArch64、鲲鹏，或 ARM/x86 性能差异
- CinderX JIT 后端性能
- LIR、CODEGEN、postalloc、regalloc、verifier、autogen
- helper-call 优化、shared stub、codegen stub、call lowering
- 后端改动带来的 pyperformance/JIT28 性能结论

## 停止条件

满足任一条件后，停止继续搜索，转入复查和汇报：

- 可信重复测试中，某个 JIT28 单项提升至少 30%
- full JIT28 geomean 提升至少 10%

小集合 focused 收益不满足停止条件。它必须继续升级到 S12/full JIT28 证据，或者
明确记录为什么暂时无法做更大范围验证。

## 必需证据门槛

任何性能结论都必须同时具备：

- 代码因果链
- LIR 证据，以及可行时的 ASM 证据
- benchmark 证据，并给出 baseline/candidate 路径
- 噪声或 tiny benchmark 分类
- ARM/x86 边界解释

单独 benchmark 数字不够。单独 LIR/ASM 形态也不够。

### 确定收益后的立即补证规则

一旦 focused S12、full JIT28 或可信重复 A/B 显示确定收益，Orchestrator 必须立即
进入 causality gate，补 workload 命中证据、轻量 counter、LIR/ASM census 或等价统计
数据，证明收益来自该代码改动。这一步发生在收益确认之后、Review Agent 和最终汇报之前；
不能把它当成最终 review/reporting 阶段才补的材料。

## 默认 Agent 集合

每个非平凡的 AArch64 JIT 性能任务默认使用这些 Agent：

| Agent | 职责 |
|---|---|
| Orchestrator Agent | 控范围、停止条件、分支纪律和最终 gate。 |
| Progress Audit Agent | 从 git、progress、findings、plans、artifacts 重建当前真实状态。 |
| Analysis Agent | 找 ARM/x86 差异 pattern，排序 ARM 亲和候选。 |
| Code Causal Chain Agent | 审计候选从 IR 生成、改写到机器码发射的完整因果链。 |
| Perf Evidence Agent | 定位或运行 focused/S12/JIT28 证据，并判断噪声。 |
| Implementation Agent | 在证据允许后做最小代码或 harness 改动。 |
| Debug Agent | 处理失败、崩溃、无效 benchmark 和可疑收益。 |
| Review Agent | 检查正确性、x86 安全、最小改动集和合入条件。 |

Analysis Agent 必须先读取 `patterns.md`，但已有 pattern 只是第一轮 checklist，
不是搜索边界。Analysis Agent 还必须主动寻找新的 ARM/x86 差异、微架构机会和
LIR/CODEGEN 形态。当前已记录的核心差异 pattern 包括：
分支/guard 性能优势，即 AArch64 的 `cbz/cbnz`、`tbz/tbnz`、`csel`、
`ccmp/ccmn`、`ldp/stp`、`madd/add extended` 等指令更贴合 JIT 常见控制流和
地址计算形态；以及 helper call 距离和调用形态差异，即 x86-64 `call rel32`
通常可覆盖约 `±2GB`，而 AArch64 `bl` 约 `±128MB`，远距离 runtime helper call
在 AArch64 上更容易变成加载目标地址后 `blr`。

做 PPT 或高层汇报时，外部表述可以压缩成五个角色：Orchestrator、Analysis、
Implementation、Perf、Review。工程执行时建议保留上面八个角色的分工。

## 标准流程

1. 从 `case-template.md` 创建一个 case 目录。
2. 先启动 Progress Audit 和 Code Causal Chain 这两个只读 Agent；Perf Evidence Agent
   不是只读角色，负责在需要时运行正式 benchmark snapshot 或 A/B。
3. Orchestrator 先汇总：
   - 最新整体进展
   - 当前最强候选
   - 代码因果链
   - 测试证据
   - 下一步最小验证
4. 然后才进入 Implementation 或 Debug。
5. 每个候选都记录到 case 的 `findings.md`。
6. 合入或汇报前，运行 Review Agent 并更新最终分类。

## 连续循环协议

这套 workflow 的默认形态不是一次性审计，而是一个持续优化循环。除非用户明确要求暂停，
或者已经触发停止条件，否则 Orchestrator Agent 必须继续进入下一轮，不能停在
“下一步建议”。

每一轮必须按下面顺序推进：

1. **Benchmark snapshot**：Perf Evidence Agent 用
   `scripts/arm/run_pyperf_subset.sh` 跑当前基线或候选的 focused benchmark。
   这一步不是可选项。没有候选时也要跑当前基线、收集耗时分布，作为分析输入。
2. **Census / hotspot analysis**：Analysis Agent 和 Code Causal Chain Agent 基于
   benchmark 结果、LIR dump、ASM dump、已有 pattern 和新 pattern 搜索优化点。
3. **Candidate selection**：Orchestrator Agent 选择一个当前证据最强、可执行的候选进入实现；不以“足够小”作为阻塞条件。
   候选必须写清代码因果假设、预期命中 workload、需要的验证矩阵。
4. **Implementation**：Implementation Agent 在 Orchestrator 选定后自动实现实验 patch。
   不需要每轮等待用户再次批准；只有越出 LIR/CODEGEN/postalloc/regalloc 范围、
   需要破坏 x86 默认行为、或需要改测试 harness 语义时才停下来请示。
5. **Correctness gate**：跑最小正确性测试、构建检查、verifier/autogen 相关测试。
   失败则进入 Debug Agent；Debug 后要么修复继续测，要么记录 rejected。
6. **Perf gate**：Perf Evidence Agent 用固定脚本做 baseline/candidate A/B：
   focused S3 -> 有信号升 S12 -> 必要时 full JIT28。
7. **Causality gate**：一旦有确定收益，必须立即回到代码、workload 命中证据、
   轻量 counter、LIR/ASM census 或等价统计数据，解释为什么是代码改动造成的，
   而不是噪声、host drift、tiny benchmark 或叠加误归因；完成这个 gate 后才进入
   Review Agent 或最终汇报。
8. **Record and loop**：无论 accepted、needs-repeat、mechanism-only、rejected，
   都必须写入 case `findings.md` 和 `progress.md`，然后选择下一个候选继续。

### 循环停止规则

- 满足停止条件后，停止搜索，立即补 causality/workload 命中证据；该 gate 完成后
  才进入 Review Agent 和汇报。
- 用户明确说停止、暂停、只汇报时，停止搜索。
- 构建环境或远端机器不可用时，记录 blocker，并转为能在本地完成的代码/census 工作。
- 目标很高甚至可能永远达不到时，仍按循环继续；每轮只允许因为明确 blocker 或用户指令
  暂停，而不能因为“还没有大收益”就结束。

### 每轮必须产出的文件

每轮至少更新：

- `progress.md`：本轮做了什么、跑了哪些命令、artifact 路径、下一轮动作。
- `findings.md`：候选状态、代码因果、benchmark 分类。
- `benchmark-matrix.md`：baseline/candidate/compare JSON 路径。

每个候选至少记录：

- 候选名称和状态。
- 改动文件。
- 核心思路。
- ARM 理论依据。
- x86 影响判断。
- benchmark 文件路径。
- LIR/ASM 或 census 证据路径。
- focused 结果。
- S12/full JIT28 结果，如有。
- 接受、重复、否决或继续叠加的原因。

## 循环角色触发规则

- **Perf Evidence Agent 是 benchmark 执行者**，不是只读审计者。它负责实际运行
  `run_pyperf_subset.sh` 和 `compare_pyperf_subset.py`，除非当前轮明确处在代码实现前的
  只读 census 阶段。
- **Analysis Agent 必须消费 benchmark 数据**。pattern 只是 check 项，候选必须结合
  当前耗时、LIR/ASM 频率或历史 artifacts 排序。
- **Implementation Agent 由 Orchestrator 触发**。只要候选满足“范围内、可执行、
  有验证计划”，就进入实现，不把“等待批准”作为默认阻塞。
- **Debug Agent 只处理失败和异常**，不能让一次失败自动终止循环。
- **Review Agent 只在 accepted/汇报/合入前 gate**，不能阻止普通候选实验继续推进。

## 固定输出顺序

每一轮报告按这个顺序输出：

1. 最新整体进展
2. 当前最强候选
3. 代码因果链
4. 测试证据
5. 下一轮动作

## 候选状态

候选只能使用下面这些状态之一：

- `accepted`：代码因果链和重复 benchmark 证据都支持该结论
- `stacked`：只有和其他 accepted 候选叠加时才有价值
- `rejected`：证据为负、噪声、过小、不安全，或缺少因果链
- `needs-repeat`：有希望，但缺 S12/full JIT28 或 LIR/ASM 证明
- `mechanism-only`：microbench 或 LIR/ASM 机制成立，但真实 workload 不支持采用

## 重要边界

- ARM-only 优化如果改变行为或生成机器码，必须使用 `CINDER_AARCH64` 或等价平台
  边界隔离。
- 新 LIR opcode 必须对 verifier、regalloc/postalloc、autogen 和非 AArch64 fallback
  路径安全。
- 不要把全日志粗 grep 统计和过滤后的 postalloc 阶段统计混用。
- 不要把耗时极小的 logging/pickle/unpack 等 tiny 行作为主证据。
- 叠加 benchmark 的收益不能归因到单个 patch，除非 A/B 实验隔离了该 patch。
