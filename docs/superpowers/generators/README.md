# Generators JIT 优化文档索引

**目标**: 消除 CinderX JIT 编译递归生成器（Tree.__iter__ 模式）中的性能回退

**当前状态**: Chunk 1 完成，OptimizedYieldFrom HIR 指令已实施，entry point 解析已实现

---

## 文档结构

```
generators/
├── plans/           # 实施计划
├── specs/           # 设计文档
├── research/        # 研究报告
├── diagnostics/     # 诊断和结果报告
└── decisions/       # 决策记录
```

---

## 快速导航

### 🔍 快速开始
- [生成器初始分析](./plans/2026-03-16-generators-initial-analysis.md) - 了解问题背景
- [性能剖析报告](./diagnostics/2026-03-18-generators-phase2c-implementation-report.md) - 瓶颈分析

### 📋 实施计划
- [递归生成器 JIT 优化计划](./plans/2026-03-17-recursive-generator-jit-optimization.md) - 完整路线图
- [Yield-From 内联优化计划](./plans/2026-03-18-generators-yield-from-inline-optimization-plan.md) - Phase 2-C 详细计划

### 📐 设计文档
- [递归生成器 JIT 优化设计](./specs/2026-03-17-generators-recursive-jit-optimization-design.md) - 技术设计

### 🔬 研究报告
- [Yield-From 实现机制](./research/2026-03-18-generators-yield-from-implementation-mechanism.md) - 深入理解
- [Yield-From 内联分析](./research/2026-03-17-generators-yield-from-inlining-analysis.md) - 内联可行性研究
- [帧池化发现](./research/2026-03-18-generators-frame-pooling-discovery.md) - 发现现有实现
- [帧池化分析](./research/2026-03-18-generators-frame-pooling-analysis.md) - 优化配置分析

### 📊 诊断报告
- [Phase 0 诊断报告](./diagnostics/2026-03-17-generators-phase0-report.md) - 初始瓶颈分析
- [HIR 架构分析](./diagnostics/2026-03-18-generators-hir-architecture-analysis.md) - yield-from 实现深度解析
- [HIR Dump 分析报告](./diagnostics/2026-03-18-generators-hir-dump-analysis-report.md) - 关键发现
- [性能剖析报告](./diagnostics/2026-03-18-generators-performance-profiling-report.md) - 瓶颈定位
- [最终总结报告](./diagnostics/2026-03-18-generators-final-summary-report.md) - 阶段性总结
- [Phase 2-A 完成报告](./diagnostics/2026-03-17-generators-phase2a-completion-report.md)
- [Phase 2-B Phi 验证报告](./diagnostics/2026-03-17-generators-phi-detection-verification-report.md)
- [Phase 2 技术总结](./diagnostics/2026-03-18-generators-phase2-technical-summary-report.md)
- [Phase 2-C 实施报告](./diagnostics/2026-03-18-generators-phase2c-implementation-report.md)
- [Phase 2-C 最终结果](./diagnostics/2026-03-19-generators-phase2c-final-results.md) ⭐ 最新
- [Task 2 完成报告](./diagnostics/2026-03-18-generators-task2-completion-report.md)

### 📈 基线和日志数据
- [递归生成器 HIR 基线](./diagnostics/2026-03-17-generators-hir-baseline-recursive.txt) - Node.__iter__ HIR dump
- [栈式迭代器 HIR 基线](./diagnostics/2026-03-17-generators-hir-baseline-stack.txt) - StackNode.__iter__ HIR dump
- [HIR 基线日志](./diagnostics/2026-03-17-generators-hir-baseline.txt) - 完整 JIT 编译日志
- [HIR Dump 日志](./diagnostics/2026-03-17-generators-hir-dump-full.txt) - 详细 HIR dump
- [macOS 基线数据](./diagnostics/2026-03-17-generators-macos-baseline.txt) - 性能对比数据
- [macOS JIT 基线](./diagnostics/2026-03-17-generators-macos-jit-baseline.txt) - JIT 编译状态
- [macOS JIT 阶段分析](./diagnostics/2026-03-17-generators-macos-jit-phases.txt) - 性能阶段分解

### ⚖️ 决策记录
- [Phase 2-C 优化方向决策](./decisions/2026-03-18-generators-phase2c-optimization-direction.md)

---

## 关键发现总结

### 性能瓶颈分布
```
Yield-from委托:  53.9%  ← 主要瓶颈
值yield:          45.8%  ← 次要
其他:              0.3%
```

### 已实施的优化
| 优化 | 状态 | 效果 |
|------|------|------|
| 帧池化 (32768条目) | ✅ 有效 | ~1.5% 改进 |
| 寄存器分配 (CALLER_SAVE_REGS) | ❌ 回滚 | 导致断言失败 |

### 结论
真正的性能提升需要优化 **yield-from 委托机制**，而不是帧池化或寄存器分配。

---

## 相关代码
- `cinderx/Jit/generators_mm.h` - 帧池化配置
- `cinderx/Jit/lir/regalloc.cpp` - 寄存器分配
- `cinderx/Jit/hir/builder.cpp` - HIR 构建
- `cinderx/Jit/jit_rt.cpp` - JIT 运行时函数

## 相关脚本
- `scripts/diagnostics/benchmark_recursive_generator.py` - 性能基准测试
- `scripts/diagnostics/profile_recursive_generator.py` - 性能剖析工具
- `scripts/diagnostics/simple_perf_test.py` - 简化性能测试
