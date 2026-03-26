# Generators JIT 优化文档索引

**目标**: 消除 CinderX JIT 编译递归生成器（Tree.__iter__ 模式）中的性能回退

**当前状态**: Phase 3.2 T1-T4 完成，T5 待实现 🚧

**最新进展**:
- ✅ Phase 3.1: 逃逸分析完成 (2026-03-25)
- 🚧 Phase 3.2: 状态机内联 T1-T4 完成 (2026-03-26) ⭐
  - StateStackPush/Pop 全链路（HIR → LIR → x86_64/ARM64 codegen）
  - GenDataFooter 栈数组扩展（16 条目 x 16 字节 = 256 字节）
  - 待完成：T5 状态机逻辑（11 个占位符）

- **最新提交**: `d4d38af1` (Phase 3.2 T4: StateStackPush/Pop 全链路实现)

---

## 优化阶段概览

| 阶段 | 优化 | 状态 | 性能改进 | 关键技术 |
|------|------|------|----------|----------|
| Phase 0 | 基线分析 | ✅ 完成 | - | 性能剖析 |
| Phase 1 | OptimizedYieldFrom | ✅ 完成 | ~1% | Entry point 缓存 |
| Phase 2 | InlineIter | ✅ 完成 | 3-32% | 逃逸分析 + HIR 内联 |
| **Phase 3.2** | **状态机内联** | **🚧 进行中** | **4-6x (目标)** | **GenDataFooter 栈 + codegen** |
| Phase 3.3 | 去虚拟化 | 📋 计划中 | 额外 2-3x | 类型推断 + 直接访问 |

---

## 文档结构

```
generators/
├── plans/                          # 实施计划
├── specs/                          # 设计文档
├── research/                       # 研究报告
├── diagnostics/                    # 诊断和结果报告
├── decisions/                      # 决策记录
├── 2026-03-25-phase3-status-update.md  # Phase 3 状态更新 ⭐
└── README.md                       # 本文件
```

---

## 快速导航

### ⭐ Phase 3.2（状态机内联 - 进行中）
- **[实施计划](./plans/2026-03-26-phase3.2-state-machine-inlining-implementation-plan.md)** ⭐ 最新
  - T1-T7 任务分解、11 个占位符清单、实施顺序
- **[设计文档](./specs/2026-03-25-phase3.2-state-machine-inlining-design.md)**
  - 状态机 HIR 结构、数据结构、测试策略、成功标准
- **[Task 4 栈操作决策](./decisions/2026-03-26-phase3.2-task4-stack-implementation-decision.md)**
  - 方案 A（GenDataFooter 栈数组）选择理由和实施细节

### Phase 3.1（逃逸分析 - 已完成）
- [完成报告](./diagnostics/2026-03-25-generators-phase3.1-escape-analysis-completion.md)
- [性能基准](./diagnostics/2026-03-25-generators-phase3-benchmark-results.md)

### Phase 2（InlineIter - 已完成）
- [完整总结](./diagnostics/2026-03-23-generators-inline-iter-phase1-summary.md)
- [状态机研究报告](./research/2026-03-23-generators-phase2-state-machine-research.md)

---

## 已实施的优化

| 优化 | 状态 | 效果 | 日期 |
|------|------|------|------|
| 帧池化 (32768条目) | ✅ 有效 | ~1.5% 改进 | 2026-03-18 |
| OptimizedYieldFrom | ✅ 完成 | ~1% 改进 | 2026-03-21 |
| InlineIter (Phase 1) | ✅ 完成 | 3-32% 改进 | 2026-03-23 |
| 逃逸分析 (Phase 3.1) | ✅ 完成 | 0.6% 改进 | 2026-03-25 |
| **状态机内联 (Phase 3.2)** | **🚧 40%** | **4-6x (目标)** | **2026-03-26** |

---

## 关键代码文件

### Phase 3.2（最新）
- `cinderx/Jit/hir/tree_iter_state_machine_pass.h` - 状态机 Pass 和生成器声明
- `cinderx/Jit/hir/tree_iter_state_machine_pass.cpp` - 状态机实现（716 行）
- `cinderx/Jit/gen_data_footer.h` - GenDataFooter 扩展（StackEntry, state_stack）
- `cinderx/Jit/hir/hir_ops.h` - StateStackPush/Pop opcode
- `cinderx/Jit/hir/hir.h` - StateStackPush/Pop 指令类
- `cinderx/Jit/lir/instruction.h` - LIR 指令定义
- `cinderx/Jit/lir/generator.cpp` - HIR→LIR 降级
- `cinderx/Jit/codegen/autogen.cpp` - x86_64/ARM64 codegen

### Phase 3.1 / InlineIter
- `cinderx/Jit/hir/escape_analysis.cpp` - 逃逸分析实现
- `cinderx/Jit/hir/simplify.cpp` - InlineIter HIR 发射
- `cinderx/Jit/codegen/autogen.cpp` - InlineIter 代码生成

---

## 环境配置

```bash
# macOS 必须
export PYTHONJITHUGEPAGES=0

# 启用 JIT
export PYTHONJIT=1

# 生产环境禁用调试
export PYTHONJITDEBUG=0
```

## 运行测试

```bash
# Phase 3.2 状态机测试
PYTHONJITHUGEPAGES=0 PYTHONJIT=1 PYTHONJITDEBUG=0 .venv/bin/python test_phase3_state_machine.py -v

# Phase 2 InlineIter 基准测试
PYTHONJITHUGEPAGES=0 PYTHONJIT=1 PYTHONJIT_ARM_INLINE_YIELD_FROM=1 .venv/bin/python test_inline_iter.py
```

---

**维护者**: Claude Code Agent
**最后更新**: 2026-03-26
