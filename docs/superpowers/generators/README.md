# Generators JIT 优化文档索引

**目标**: 消除 CinderX JIT 编译递归生成器（Tree.__iter__ 模式）中的性能回退

**当前状态**: Phase 3.2 ✅ 完成，pyperformance bm_generators 验证通过 🚀

**最新成果**:
- ✅ Phase 3.1: 逃逸分析完成 (2026-03-25)
- ✅ Phase 3.2: 状态机内联完成 (2026-04-02) ⭐
  - 16 基本块 GenDataFooter 驱动状态机
  - 8/8 操作原生 LIR codegen（含 Push/Pop）
  - **pyperformance bm_generators (`--worker -l5 -w11 -n2`)**:
    - macOS ARM64: **11.9x** 加速（324.7ms → 27.3ms）
    - kunpeng AArch64: **14.1x** 加速（83.7ms → 5.95ms）
  - postalloc fold 安全性修复（SaveCurrentNode 屏障 + MemoryIndirect 扫描）

- **最新提交**: `2af06899` (chore: 清理遗留调试文件)

---

## 优化阶段概览

| 阶段 | 优化 | 状态 | 性能改进 | 关键技术 |
|------|------|------|----------|----------|
| Phase 0 | 基线分析 | ✅ 完成 | - | 性能剖析 |
| Phase 1 | OptimizedYieldFrom | ✅ 完成 | ~1% | Entry point 缓存 |
| Phase 2 | InlineIter | ✅ 完成 | 3-32% | 逃逸分析 + HIR 内联 |
| **Phase 3.2** | **状态机内联** | **✅ 完成** | **11.9-14.1x** | **GenDataFooter 状态机 + 内联 codegen** |
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

### ⭐ Phase 3.2（状态机内联 - 已完成）
- **[状态更新](./2026-03-25-phase3-status-update.md)** ⭐ 最新（含 Plan B 内联 codegen）
- **[经验教训](./2026-03-30-tree-iter-state-machine-lessons-learned.md)** — 引用计数、SSA、clobber 等关键教训
- **[设计文档](./specs/2026-03-25-phase3.2-state-machine-inlining-design.md)**
- **[实施计划](./plans/2026-03-26-phase3.2-state-machine-inlining-implementation-plan.md)**
- **[Task 4 栈操作决策](./decisions/2026-03-26-phase3.2-task4-stack-implementation-decision.md)**

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
| **状态机内联 (Phase 3.2)** | **✅ 完成** | **11.9-14.1x 加速** | **2026-04-02** |

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
PYTHONJITHUGEPAGES=0 PYTHONJIT=1 PYTHONJITTREEITERSTATEMACHINE=1 PYTHONJITDEBUG=0 \
  .venv/bin/python test_phase3_state_machine.py -v

# pyperformance bm_generators 基准测试（kunpeng 示例）
PYTHONJIT=1 PYTHONJITAUTO=2 \
  PYTHONJITLISTFILE=/tmp/jitlist.txt PYTHONJITENABLEJITLISTWILDCARDS=1 \
  PYTHONJITDEBUG=0 \
  python3.14 /tmp/bench_generators_auto2.py --worker -l5 -w11 -n2

# JITLIST 文件格式（每行 module:qualname）
echo "__main__:Tree.__iter__" > /tmp/jitlist.txt
echo "__main__:tree" >> /tmp/jitlist.txt
echo "__main__:bench_generators" >> /tmp/jitlist.txt
```

> **重要**: `PYTHONJITAUTO=N` 仅设置阈值，**不激活自动编译**。必须在脚本中调用
> `cinderx.jit.compile_after_n_calls(N)` 或 `cinderx.jit.auto()` 才能激活。
> 低 AUTO 阈值（如 2）会编译标准库函数导致 segfault，需配合 `PYTHONJITLISTFILE` 限制编译范围。

---

**维护者**: Claude Code Agent
**最后更新**: 2026-04-02
