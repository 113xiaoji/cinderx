# ARM/x86 差异 Pattern 库

Analysis Agent 做 AArch64 JIT 后端优化分析时，必须先读取本文件，但本文件只是第一轮
checklist 和已有经验库，不是搜索边界。Agent 必须先检查候选是否命中已有 pattern，
同时也要主动寻找新的 ARM/x86 差异、微架构机会和 LIR/CODEGEN 形态。

如果候选无法映射到已有 pattern，不代表它不成立；需要说明为什么这是新的 pattern，
列出机器级假设、代码因果链和需要补的证据。只有经过 LIR/ASM 和 benchmark 验证后，
才把新 pattern 沉淀回本文件。

这些 pattern 只能作为“优先检查项、找优化点和解释假设”的依据，不能单独作为性能
结论。任何 claim 仍然必须同时具备代码因果链、LIR/ASM 证据和 benchmark 证据。

## 使用原则

- 先查已有 pattern：确认是否命中已知 ARM/x86 差异。
- 再主动搜索新 pattern：不能因为已有 pattern 不匹配就停止分析。
- 新 pattern 必须写清：
  - 机器级差异是什么
  - 可能落在哪个 JIT 层级：LIR、CODEGEN、postalloc、regalloc、runtime helper
  - ARM 为什么更可能收益
  - x86 是不能做、成本高，还是可能也有收益
  - 需要哪些 LIR/ASM、microbench、focused/S12/JIT28 证据
- 未验证的新 pattern 状态只能是 `hypothesis` 或 `needs-evidence`，不能写成
  `accepted`。

## Pattern 1：分支/guard 性能优势

### 核心判断

AArch64 有一组更贴合 JIT guard 和短控制流的指令模式。对于 Python JIT 常见的
tag 检查、null guard、类型 guard、cache state guard、小分支和 index/offset 计算，
AArch64 往往可以用更短、更直接的机器码表达；x86 虽然也有成熟的 branch/cmov/lea
能力，但很多场景更容易落成 `cmp/test + jcc`、多条 uop，或需要额外 flag/临时寄存器
协调。

### 指令 pattern

| 场景 | AArch64 亲和指令 | 性能意义 |
|---|---|---|
| 零值判断 | `cbz` / `cbnz` | 比 `cmp/tst + branch` 更短，适合 null guard、cache miss guard、快速失败分支。 |
| bit 判断 | `tbz` / `tbnz` | tag bit、状态位判断更直接，适合对象 tag、flag、inline cache 状态位。 |
| 条件选择 | `csel` / `csinc` / `csinv` / `csneg` | 小分支可 branchless，减少预测失败风险。 |
| 短路比较 | `ccmp` / `ccmn` | 合并多个比较条件，减少多个分支块和中间跳转。 |
| 成对访存 | `ldp` / `stp` | 保存/恢复寄存器更紧凑，适合 prologue/epilogue、stub、slow path 边界。 |
| 乘加/地址计算 | `madd`、`add extended` | index、offset、hash、array/dict 探测地址计算更紧凑。 |

### 适合优先搜索的 JIT 形态

- LIR 中出现 `Test + BranchZ/BranchNZ`，且输入是寄存器零值判断。
- LIR 或 codegen 中有 tag bit、状态位、kind bit 的 mask/test/branch。
- 多个 guard 连续出现，失败边都跳向 deopt、helper 或 slow path。
- 小分支只是在两个值之间选择，或只是做 `0/1`、`-1/0`、取反等简单结果。
- stub/prologue/epilogue 中连续保存或恢复寄存器。
- index/offset/hash 计算里出现 multiply + add、sign/zero extend + add。

### x86 对照判断

- x86 不是“不能做”，而是很多场景已有 `test/cmp + jcc`、`cmov`、`lea`、
  macro-fusion 等成熟路径，继续优化的边际收益可能较小。
- 如果 x86 已经是 direct call、macro-fused compare-branch 或单条 `lea`，AArch64
  侧更可能是高收益对象。
- 如果 x86 也存在额外 load、indirect branch、flag 破坏或寄存器压力问题，可以单独
  评估 x86 版本，但不能默认和 AArch64 同收益。

### Analysis Agent 使用规则

- 发现候选时，先标注它命中的具体子 pattern，例如 `cbz/cbnz`、`tbz/tbnz`、
  `csel`、`ccmp`、`ldp/stp` 或 `madd/add extended`。
- 必须说明当前 LIR/ASM before 形态，以及期望 after 形态。
- 如果 focused benchmark 有收益，必须用 S12 验证；如果只在 microbench 中收益，
  分类为 `mechanism-only`。
- 如果 x86 路径也实现，必须单独报告 x86 的 before/after ASM 和 benchmark，不能用
  ARM 结论推断 x86。

## Pattern 2：helper call 距离和调用形态差异

### 核心判断

x86-64 的普通近调用通常使用 `call rel32`，目标地址是相对下一条指令的 32-bit
有符号偏移，按字节计，覆盖范围约为 `±2GB`。AArch64 的 `bl` 使用 26-bit 有符号
立即数并按 4 字节指令宽度缩放，覆盖范围约为 `±128MB`。

因此，在 JIT code buffer 和 C++ runtime helper 分布在虚拟地址空间中较远的位置时，
AArch64 更容易超出 direct branch/call 的可编码范围，需要退化成：

```asm
ldr/mov target_reg, helper_address
blr target_reg
```

或通过 veneer/shared stub 间接到达 helper。这个过程会增加指令数、占用临时寄存器，
并可能引入额外 load 或 indirect branch 成本。x86 在 helper 位于 `call rel32`
范围内时通常可以保持一条 direct call，所以同类 helper-call 优化在 AArch64 上更容易
成为高收益点。

这里讨论的是虚拟地址空间中的代码地址距离，不是物理内存距离；距离单位是字节。

### 适合优先搜索的 JIT 形态

- LIR 中有高频 runtime helper call，尤其是 cache-hit 很热、slow path 很冷的 helper。
- AArch64 ASM 中能看到 helper call 前需要 materialize target address，例如
  literal load、`movz/movk` 序列、`adrp/add`，随后 `blr`。
- x86 ASM 中同一 helper 是 `call rel32` 或等价 direct call。
- helper call 位于 JIT 热路径内，但大多数情况下只是执行快速 cache-hit 检查。
- 多个 call site 调用同一个 helper，适合用 shared stub 或 codegen stub 聚合热路径。

### 典型优化方向

- 将高频 helper call 抽象成 LIR pseudo instruction，让 AArch64 codegen 可以识别并
  生成专用 fast path 或 shared stub。
- 对 ARM-only 热路径使用 shared stub，把远距离 helper 调用变成本地短跳转加 stub 内
  fast path。
- 保留 helper fallback，miss、异常、deopt/debug-info 行为仍回到原 helper 语义。
- x86 默认 fallback，不因为 ARM 的距离问题强行改成 stub；除非 x86 A/B 证明 direct
  call 也存在显著开销。

### x86 对照判断

- x86 不是永远更优；如果目标超过 `±2GB`，x86 的 `call rel32` 也无法直接到达，需要
  `movabs + call *reg` 或其他 indirect call 形态。
- 但在常见 JIT/runtime 布局里，x86 direct call 的覆盖范围比 AArch64 `bl` 大得多，
  因此更常维持一条 direct call。
- 如果 x86 已经是 direct call，而 AArch64 是 load-address + `blr`，优先把该候选归为
  ARM-affine。
- 如果 x86 也被迫使用 indirect call，需要单独跑 x86 before/after ASM 和 benchmark，
  不能直接沿用 ARM 结论。

### 已知映射

- `AArch64 LoadAttrCachedFastPath` / `LoadAttrCache::invoke` shared stub：
  命中本 pattern。AArch64 通过 LIR pseudo instruction 识别热 helper call，并在 codegen
  中使用 shared stub/fast path 降低 helper-call materialization 和间接调用成本；x86
  默认仍保持普通 helper call，除非单独证明 x86 stub 有真实收益。

### Analysis Agent 使用规则

- 必须记录 x86 call 形态和 AArch64 call 形态：direct call、literal load + `blr`、
  `adrp/add + blr`、veneer，或 shared stub。
- 必须记录目标地址距离相关结论是否来自 ASM 证据、代码生成规则，还是推断。
- 如果用 shared stub 优化，必须解释 stub 是否改变语义；正常要求是 fast path hit
  优化，miss/fallback 仍保持原 helper 语义。
- microbench 只能证明调用形态机制，pyperformance/JIT28 才能证明 workload 收益。
