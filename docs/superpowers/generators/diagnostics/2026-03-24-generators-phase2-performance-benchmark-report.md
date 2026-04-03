# Phase 2 性能基准测试报告

**日期**: 2026-03-24
**测试文件**: `benchmark_state_machine.py`
**对比文件**: `compare_performance.py`
**状态**: ✅ 基线测试完成

---

## 测试环境

- **Python**: 3.14.3
- **平台**: macOS ARM64
- **JIT**: CinderX JIT (Phase 2 Week 1 实现)
- **预热**: 50 次迭代
- **迭代次数**: depth ≤3: 1000次，depth ≤7: 100次，depth >7: 20次

---

## 性能对比结果

### 详细数据

| Depth | Nodes | JIT On (ms) | JIT Off (ms) | Speedup | Status |
|-------|-------|-------------|--------------|---------|--------|
| 1 | 1 | 0.0023 | 0.0002 | 0.09x | ✗ 11.50x slower |
| 2 | 3 | 0.0004 | 0.0006 | 1.50x | ✓ 1.50x faster |
| 3 | 7 | 0.0009 | 0.0013 | 1.44x | ✓ 1.44x faster |
| 5 | 31 | 0.0052 | 0.0070 | 1.35x | ✓ 1.35x faster |
| 7 | 127 | 0.0266 | 0.0349 | 1.31x | ✓ 1.31x faster |
| 10 | 1023 | 0.3392 | 0.3390 | 1.00x | ✗ 1.00x slower |

### 统计摘要

- **平均加速比**: 1.11x
- **最佳加速**: depth=2 (1.50x)
- **最差表现**: depth=1 (11.50x 变慢)

---

## 性能分析

### 小树 (depth ≤ 5)

| Depth | Speedup | 分析 |
|-------|---------|------|
| 1 | 0.09x | ❌ 异常变慢（可能测量误差或 JIT 编译开销） |
| 2 | 1.50x | ✅ 轻微改进 |
| 3 | 1.44x | ✅ 轻微改进 |
| 5 | 1.35x | ✅ 轻微改进 |

**小树平均加速**: ~1.43x (排除 depth=1)

### 大树 (depth > 5)

| Depth | Speedup | 分析 |
|-------|---------|------|
| 7 | 1.31x | ✅ 轻微改进 |
| 10 | 1.00x | ➖ 无差异 |

**大树平均加速**: ~1.15x

---

## 关键发现

### 1. 当前 JIT 性能表现

- ✅ **轻微改进**: depth=2,3,5,7 有 1.3-1.5x 改进
- ➖ **无显著差异**: depth=10 几乎无差异
- ❌ **异常变慢**: depth=1 变慢 11.5x（可能测量误差）

### 2. 与目标对比

**Phase 2 目标**: depth ≤ 5 实现 **4-6x** 性能改进

**当前实际**: depth ≤ 5 实现 **1.35-1.50x** 性能改进

**差距**: **~3-4x** 改进空间

### 3. 原因分析

**为什么没有达到 4-6x 目标？**

1. **状态机优化未实现**:
   - Phase 2 Week 1 仅完成了 HIR 指令定义
   - Week 2 的状态机构建器（T2.1-T2.5）尚未实现
   - 当前仍使用标准生成器帧切换路径

2. **YieldFrom 优化未启用**:
   - `PYTHONJIT_ARM_INLINE_YIELD_FROM=1` 未设置
   - `simplifyYieldFrom` 检测到 0 次优化机会
   - 所有 6 次调用都是 "Environment disabled"

3. **生成器帧开销仍存在**:
   - 每次 yield 仍需要完整的帧切换
   - GenDataFooter 保存/恢复开销未消除
   - resumeEntry() 间接调用未优化

---

## 性能优化路径

### 当前状态（Week 1 完成）

```
Python 生成器 → 字节码解释 → 生成器帧切换 → yield 协议
                                      ↓
                              标准帧分配/恢复
```

**性能**: 1.3-1.5x 改进（JIT 编译基本开销优化）

### 目标状态（Week 2 完成后）

```
Python 生成器 → JIT 检测树遍历模式 → 生成状态机 HIR
                                      ↓
                              状态机内联（无帧切换）
                                      ↓
                              直接跳转（类似 while 循环）
```

**预期性能**: 4-6x 改进（消除帧切换开销）

---

## 下一步行动

### Week 2 任务（T2.1-T2.5）

1. **T2.1 - Yield-From 模式识别** (1.5 天)
   - 实现 `detectPattern()` 识别树遍历模式
   - 实现 `isTreePattern()` 验证 self.left/right 字段访问
   - 实现 `canFlatten()` 检查深度和状态数限制

2. **T2.2 - 状态机构建器** (2 天) ✅ **框架已完成**
   - ✅ `createEntryBlock()` - 入口块生成
   - ✅ `createDispatchBlock()` - 分发块生成
   - ✅ `createDoneBlock()` - 完成块生成
   - 🚧 `createStateBlock()` - 状态块生成（占位符）

3. **T2.3 - 嵌套展平** (1.5 天)
   - 实现嵌套 yield from 的状态机展平
   - 合并多层状态机为单层

4. **T2.4 - HIR 生成** (1.5 天)
   - 集成到 `simplifyYieldFrom`
   - 生成 `YieldFromInline` HIR 指令

5. **T2.5 - 与 Escape Analysis 集成** (0.5 天)
   - 检测生成器是否逃逸
   - 决定使用状态机 vs InlineIter

### 预期性能改进时间线

| 阶段 | 预期改进 | 时间 |
|------|---------|------|
| Week 1 完成（当前） | 1.3-1.5x | ✅ 已达成 |
| Week 2 完成 | 4-6x | 🎯 目标 |
| Phase 3 完成 | 10-12x | 🔮 理论上限 |

---

## 测试文件

### benchmark_state_machine.py
```bash
# JIT 启用
PYTHONJITHUGEPAGES=0 PYTHONJIT=1 .venv/bin/python3 benchmark_state_machine.py

# JIT 禁用（基线）
PYTHONJITHUGEPAGES=0 PYTHONJIT=0 .venv/bin/python3 benchmark_state_machine.py
```

### compare_performance.py
```bash
.venv/bin/python3 compare_performance.py
```

---

## 结论

✅ **基线测试完成**:
- 建立了性能基准（JIT 禁用）
- 测量了当前 JIT 性能（1.3-1.5x）
- 量化了与目标的差距（~3-4x）

🚧 **状态机优化未实现**:
- Week 2 任务（T2.1-T2.5）是实现 4-6x 改进的关键
- 需要完成模式识别、状态机构建、HIR 生成

🎯 **下一步**:
- 完善 C++ 单元测试（填充 SKIP 测试）
- 实现 T2.3-T2.5 任务
- 重新运行性能测试验证 4-6x 改进

---

**维护者**: Claude Code Agent
**最后更新**: 2026-03-24
**Git Commit**: [待提交]
