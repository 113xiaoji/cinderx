# Generators JIT 优化文档索引

**目标**: 消除 CinderX JIT 编译递归生成器（Tree.__iter__ 模式）中的性能回退

**当前状态**: InlineIter Phase 1 完成（3-32% 性能提升） ✅

**最新进展**: InlineIter HIR 指令 + 逃逸分析已实施，远超 OptimizedYieldFrom 的 ~1% 改进

---

## 🎯 优化阶段概览

| 阶段 | 优化 | 状态 | 性能改进 | 关键技术 |
|------|------|------|----------|----------|
| Phase 0 | 基线分析 | ✅ 完成 | - | 性能剖析 |
| Phase 1 | OptimizedYieldFrom | ✅ 完成 | ~1% | Entry point 缓存 |
| Phase 2 | **InlineIter** | ✅ **完成** | **3-32%** ⭐ | **逃逸分析 + HIR 内联** |
| Phase 3 | **状态机生成** | 📋 **计划中** | **4-6x** ⭐ | **编译时状态机扁平化** |
| Phase 4 | 帧消除 | 📋 计划中 | 10-12x (预期) | 直接代码生成 |

---

## 文档结构

```
generators/
├── plans/                          # 实施计划
├── specs/                          # 设计文档
├── research/                       # 研究报告
├── diagnostics/                    # 诊断和结果报告
├── decisions/                      # 决策记录
├── inline-iter-phase1-summary.md  # Phase 1 (InlineIter) 完整总结 ⭐ 新增
└── README.md                       # 本文件
```

---

## 快速导航

### ⭐ Phase 2（InlineIter - 最新完成）
- **[Phase 2 完整总结](./diagnostics/2026-03-23-generators-inline-iter-phase1-summary.md)** - InlineIter 优化完整报告 ⭐ 最新
  - 性能：3-32% 提升（depth 10-12 达到 32%）
  - 技术：逃逸分析 + InlineIter HIR 指令
  - 包含：架构设计、性能数据、实现细节、已知陷阱

### 📋 Phase 3（状态机生成 - 计划中）
- **[Phase 3 实施计划](./plans/2026-03-24-generators-phase2-state-machine-plan.md)** - 状态机生成完整计划 📋 新增
  - 目标：4-6x 性能提升（深度 ≤ 5）
  - 技术：HIR 级别状态机生成 + 扁平化嵌套
  - 包含：技术设计、任务分解、风险评估、测试计划
- **[状态机研究报告](./research/2026-03-23-generators-phase2-state-machine-research.md)** - 理论基础

### 🔍 快速开始
- [生成器初始分析](./plans/2026-03-16-generators-initial-analysis.md) - 了解问题背景
- [性能剖析报告](./diagnostics/2026-03-18-generators-phase2c-implementation-report.md) - 瓶颈分析

### 📋 实施计划
- [递归生成器 JIT 优化计划](./plans/2026-03-17-recursive-generator-jit-optimization.md) - 完整路线图
- [Yield-From 内联优化计划](./plans/2026-03-18-generators-yield-from-inline-optimization-plan.md) - Phase 2-C 详细计划
- **[Phase 3 状态机生成计划](./plans/2026-03-24-generators-phase2-state-machine-plan.md)** ⭐ **最新**

### 📐 设计文档
- [递归生成器 JIT 优化设计](./specs/2026-03-17-generators-recursive-jit-optimization-design.md) - 技术设计

### 🔬 研究报告
- [Yield-From 实现机制](./research/2026-03-18-generators-yield-from-implementation-mechanism.md) - 深入理解
- [Yield-From 内联分析](./research/2026-03-17-generators-yield-from-inlining-analysis.md) - 内联可行性研究
- [帧池化发现](./research/2026-03-18-generators-frame-pooling-discovery.md) - 发现现有实现
- [帧池化分析](./research/2026-03-18-generators-frame-pooling-analysis.md) - 优化配置分析
- **[状态机生成研究报告](./research/2026-03-23-generators-phase2-state-machine-research.md)** ⭐ **最新**

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
- [Phase 2-C 最终结果](./diagnostics/2026-03-19-generators-phase2c-final-results.md)
- [InlineIter Phase 1 总结](./diagnostics/2026-03-23-generators-inline-iter-phase1-summary.md) ⭐ **最新**
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

### 性能瓶颈分布（基线）
```
Yield-from委托:  53.9%  ← 主要瓶颈
值yield:          45.8%  ← 次要
其他:              0.3%
```

### 已实施的优化
| 优化 | 状态 | 效果 | 日期 |
|------|------|------|------|
| 帧池化 (32768条目) | ✅ 有效 | ~1.5% 改进 | 2026-03-18 |
| 寄存器分配 (CALLER_SAVE_REGS) | ❌ 回滚 | 导致断言失败 | 2026-03-18 |
| OptimizedYieldFrom | ✅ 完成 | ~1% 改进 | 2026-03-21 |
| **InlineIter (Phase 1)** | ✅ **完成** | **3-32% 改进** ⭐ | 2026-03-23 |

### InlineIter Phase 1 性能数据

| 树深度 | 节点数 | 改进幅度 |
|--------|--------|---------|
| 5-8 | 63-511 | 6-7% |
| 10-12 | 2047-8191 | **32%** ⭐ |
| 14-16 | 32767-131071 | 3-6% |

### 结论
1. **OptimizedYieldFrom**: ~1% 改进，受限于运行时帧切换
2. **InlineIter Phase 1**: 3-32% 改进，通过逃逸分析和 HIR 内联
3. **未来潜力**: Phase 2-3（状态机生成 + 帧消除）可实现 10-12x 改进

---

## 相关代码

### InlineIter Phase 1（最新）
- `cinderx/Jit/hir/escape_analysis.cpp/h` - 逃逸分析实现 ⭐ 新增
- `cinderx/Jit/hir/simplify.cpp` - InlineIter HIR 发射 ⭐ 修改
- `cinderx/Jit/codegen/autogen.cpp` - InlineIter 代码生成 ⭐ 修改
- `cinderx/Jit/inline_iter.md` - InlineIter 技术文档 ⭐ 新增

### OptimizedYieldFrom（历史）
- `cinderx/Jit/generators_mm.h` - 帧池化配置
- `cinderx/Jit/lir/regalloc.cpp` - 寄存器分配
- `cinderx/Jit/hir/builder.cpp` - HIR 构建
- `cinderx/Jit/jit_rt.cpp` - JIT 运行时函数

## 相关脚本

### InlineIter 测试（最新）
- `test_inline_iter.py` - 性能基准测试 ⭐ 新增
- `dump_hir.py` - HIR dump 和验证 ⭐ 新增

### OptimizedYieldFrom 测试（历史）
- `scripts/diagnostics/benchmark_recursive_generator.py` - 性能基准测试
- `scripts/diagnostics/profile_recursive_generator.py` - 性能剖析工具
- `scripts/diagnostics/simple_perf_test.py` - 简化性能测试

---

## 🚀 快速开始（InlineIter）

### 环境配置

```bash
# macOS 必须
export PYTHONJITHUGEPAGES=0

# 启用 JIT 和 InlineIter
export PYTHONJIT=1
export PYTHONJIT_ARM_INLINE_YIELD_FROM=1

# 生产环境禁用调试
export PYTHONJITDEBUG=0
```

### 运行测试

```bash
# 性能基准测试
.venv/bin/python3 test_inline_iter.py

# 调试模式
PYTHONJITDEBUG=1 .venv/bin/python3 test_inline_iter.py
```

### 预期结果

```
JIT enabled: True
Testing InlineIter optimization...
  depth=10: 2047 values (expected 2047), 100 iterations in 77.13ms (0.7713ms/iter)
  depth=12: 8191 values (expected 8191), 100 iterations in 340.25ms (3.4025ms/iter)
All tests passed!
```

---

## ⚠️ 已知陷阱（InlineIter）

### 1. force_compile 冲突

❌ **错误**:
```python
cinderx.jit.force_compile(Node.__iter__)  # 会导致崩溃
```

✅ **正确**:
```python
cinderx.jit.force_compile(traverse_and_collect)  # 只编译调用方
```

### 2. macOS 特殊要求

- 必须设置 `PYTHONJITHUGEPAGES=0`
- GCC 15 构建需要 `-lstdc++` 链接
- 构建后必须重新签名 `.so` 文件

详见：**[Phase 1 完整总结](./inline-iter-phase1-summary.md)**

---

## 📚 扩展阅读

- [JIT Guide](../../cinderx/Jit/guide.md) - JIT 整体架构
- [InlineIter 技术文档](../../cinderx/Jit/inline_iter.md) - InlineIter 详细实现
- [Progress Log](../../progress.md) - 项目进度记录

---

**维护者**: Claude Code Agent
**最后更新**: 2026-03-23
**项目状态**: InlineIter Phase 1 完成 ✅
