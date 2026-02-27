# CinderX JIT 与 CPython 原生 JIT（AArch64）汇编差异

日期：2026-02-27  
主机：`root@124.70.162.35`（aarch64 Linux）  
Python：3.14.3

## 范围与方法
- 两侧使用相同 Python 代码形态：
  - `def f(n): s=0; for i in range(n): s += i; return s`
- CinderX 侧：
  - 强制编译 `f`
  - 用 `cinderjit.dump_elf()` 导出 JIT 代码
  - 抽取 `.text` 为原始二进制并按 AArch64 反汇编
- CPython 原生 JIT 侧：
  - `PYTHON_JIT=1`
  - 在 `JUMP_BACKWARD` 上定位 executor（`_opcode.get_executor`）
  - 为了等长对比，取返回 `jit_code` 前 `952` 字节进行反汇编

## 原始工件
- CinderX 反汇编：`artifacts/asm/cinderx_f_disasm_aarch64.txt`
- CPython 反汇编（前 952）：`artifacts/asm/cpython_executor_disasm_head952_aarch64.txt`
- CPython 反汇编（前 2880）：`artifacts/asm/cpython_executor_disasm_head2880_aarch64.txt`
- CinderX text 二进制：`artifacts/asm/cinderx_f_text.bin`
- CPython executor 二进制（前 952）：`artifacts/asm/cpython_executor_head952.bin`
- CPython executor 完整 blob：`artifacts/asm/cpython_executor_full4096.bin`
- 字节对比摘要：`artifacts/asm/byte_compare_cinderx_vs_cpython_head952.txt`
- 指令分布摘要：`artifacts/asm/inst_mix_cinderx_vs_cpython_head952.txt`

## 高层结论
- 代码生成模型不同：
  - CinderX：函数级原生代码，明显使用字面量池间接调用（`ldr x16, literal` + `blr x16`）。
  - CPython 原生 JIT：executor/superblock 风格（copy-and-patch stencil），更多内部直接 `bl`，辅以少量间接回调。
- 等长二进制对比（`952 vs 952`）字节相同率很低：
  - `same_bytes=62`，`same_ratio=6.5126%`，`lcp=0`。
- 等长窗口指令分布（两侧均 `238` 条）：
  - CinderX：`blr=14`、`ldr-literal=14`、`b.cond=16`、`tbz/tbnz=2`、`ret=3`。
  - CPython：`blr=2`、`ldr-literal=4`、`b.cond=8`、`tbz/tbnz=6`、`ret=0`。

## 分块对齐观察

### 1）入口/包装层
- CinderX 入口可见字面量池 helper 调用：
  - `ldr x16, 0x370; blr x16`、`ldr x16, 0x388; blr x16`
  - 参考：`cinderx_f_disasm_aarch64.txt` 的 `0x14..0x40`。
- CPython 入口先做 refcount/state 初始化与原子环：
  - `ldaxr/stlxr` 后接字面量加载与存储
  - 参考：`cpython_executor_disasm_head952_aarch64.txt` 的 `0x00..0x44`。

### 2）序言与守护形态
- 两者均有常见序言（`stp x29, x30` + callee-saved 保存），但守护链路不同：
  - CinderX 较快进入 helper 驱动的 frame/runtime 路径（`0x4c..0x138`）。
  - CPython 在核心块前保留更长的类型守护通道（`0xc8..0x104`）。

### 3）调用降级模式
- CinderX 热路径多次通过字面量池间接调用：
  - 示例位点：`0x1c8`、`0x1dc`、`0x238`、`0x264`、`0x294`、`0x2a4`。
- CPython 的等长窗口中，间接回调更少（`blr x8`），更多是对 blob 内部偏移的直接 `bl 0x...`。

### 4）deopt/退出组织
- CinderX 存在紧凑 deopt 分发梯：
  - `0x2cc..0x338` 推入 reason + resume target 后 `bl 0x33c`。
- CPython 的等价退出路径更分散在 executor 块中；回调路径可见于 `0x2c8..0x328`。

## 对性能解释的意义
- CinderX 更重的字面量池间接调用占比，与该分支 AArch64 调用目标去重策略和 runtime-helper 分层一致。
- CPython 原生 JIT 在该窗口中有更多 executor 内部直接分支，间接层次较少；但其对象是 executor 块而非完整函数体，不能与函数级 JIT 代码体积/时延直接 1:1 比较。

## 注意事项
- 本分析是“对齐采样”，不是逐指令语义等价证明。
- CPython `jit_code` blob 为 `4096` 字节页对齐；`952` 窗口仅用于与 CinderX 函数 text（`952` 字节）做等长比较。
