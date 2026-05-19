# cinderx 目录 Agent 入口

## 先读

如果存在 `Internal/AGENTS.md`，先读取它。该文件可能包含内部环境和私有构建约束。

## 目录背景

- `cinderx` 是 CinderX 运行时和 JIT 的主要实现目录。
- JIT 的 HIR 在 `Jit/hir/`，LIR 生成和降低在 `Jit/lir/`，机器码生成在
  `Jit/codegen/`。
- 多 Python 版本差异通常通过 `PY_VERSION_HEX`、`Py_GIL_DISABLED` 和 `Common/`
  中的兼容封装处理。
- 需要使用 CPython 非公开 API 时，优先使用 `UpstreamBorrow/` 的自动借用
  机制，不要手工复制上游代码。

## 常用定位

- 新 HIR 指令通常涉及 `Jit/hir/opcode.h`、`Jit/hir/hir.h`、
  `Jit/lir/generator.cpp`、`Jit/hir/instr_effects.cpp`、`Jit/hir/hir.cpp`、
  `Jit/hir/printer.cpp`、`Jit/hir/pass.cpp` 和必要时的解析器/运行时 helper。
- 调查单个 JIT 函数问题时，可用 `cinderx.jit.force_compile` 缩小范围。
- 需要看 HIR/LIR/ASM 时，优先使用现有转储/日志机制，避免改基准测试口径。

## AArch64 JIT 性能任务

涉及 ARM/AArch64 JIT 后端性能，尤其是 LIR、CODEGEN、postalloc、regalloc、
verifier、autogen、helper 调用降低、共享桩或 ARM/x86 性能差异时，
不要在本文件里查完整流程，改读根目录下的 agent 文档：

- `../docs/agents/aarch64-jit-perf/README.md`
- `../docs/agents/aarch64-jit-perf/patterns.md`
- `../docs/agents/aarch64-jit-perf/orchestrator-agent.md`
- `../docs/agents/aarch64-jit-perf/perf-evidence-agent.md`
- `../docs/agents/aarch64-jit-perf/analysis-agent.md`
- `../docs/agents/aarch64-jit-perf/code-causal-chain-agent.md`
- `../docs/agents/aarch64-jit-perf/implementation-agent.md`
- `../docs/agents/aarch64-jit-perf/debug-agent.md`
- `../docs/agents/aarch64-jit-perf/review-agent.md`

入口只保留这条硬规则：一旦性能收益已经确定，下一步必须立即补因果证据
（工作负载命中证据、轻量计数器、LIR/ASM 统计或等价统计），不能先进入最终
复查/汇报。
