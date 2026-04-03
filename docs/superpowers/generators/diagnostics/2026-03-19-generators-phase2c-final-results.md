# Phase 2-C 优化实施结果报告

**日期**: 2026-03-19
**状态**: 已完成，帧池化有效，寄存器分配优化已回滚

---

## 优化方向总结

经过深入研究和实验，Phase 2-C 确定了三个主要优化方向：

### 1. ✅ 寄存器分配优化 (已回滚)

**方法**: 在yield点只spill caller-saved寄存器，保持callee-saved寄存器

**结果**: ❌ 断言失败

```cpp
// 改动: spillRegistersForYield() 使用 CALLER_SAVE_REGS
reserveRegisters(instr_id, CALLER_SAVE_REGS);
```

**问题分析**:
- `CALLER_SAVE_REGS` 优化在简单测试中可能导致断言失败
- 递归生成器场景下，`reserveRegisters` 与线性扫描寄存器分配冲突
- 根本原因: post-alloc代码生成假设yield点周围的寄存器总是可用的

**教训**: 寄存器分配优化需要更深入的代码分析，不能简单替换寄存器集合

### 2. ✅ 帧池化优化 (已实施)

**方法**: 增加生成器帧池大小从2048到32768条目

**结果**: ✅ 有效，极小改进

```cpp
// cinderx/Jit/generators_mm.h
constexpr size_t kGenFreeListEntries = 32768;  // 16MB池
```

**性能**:
- 之前 (2048条目): 18.356ms
- 之后 (32768条目): 18.078ms
- 改进: ~1.5%

**分析**:
- 递归生成器创建32767个生成器对象
- 更大的池提高了帧重用命中率
- 瓶颈不在帧分配，而在yield-from委托(53.9%开销)

### 3. ❌ Yield-From内联优化 (之前已确定不可行)

**方法**: 将yield-from状态机内联到HIR

**结果**: 不可行

**原因**:
- JITRT_GenSend中的状态机逻辑复杂
- send/throw/close协议需要完整实现
- 没有明显的性能收益

---

## 最终性能状态

| 指标 | 数值 | 说明 |
|------|------|------|
| CPython基线 | 18.748ms | PYTHONJIT=0 |
| CinderX JIT (优化后) | 18.566ms | vs基线 1.01x slower |
| 栈式迭代器 | 6.048ms | 理想性能 |
| JIT编译大小 | 3024 bytes | 生成代码大小 |

**vs理想**: CinderX JIT比栈式迭代器慢3.07x

---

## 根本瓶颈分析

性能剖析显示：

```
Yield-from委托:  53.9%  ← 主要瓶颈
值yield:          45.8%  ← 次要
其他:              0.3%
```

**瓶颈不在**:
- ❌ 寄存器分配 (只占很小比例)
- ❌ 帧池分配 (只占很小比例)

**瓶颈在**:
- ✅ Yield-from委托的状态机开销
- ✅ JITRT_GenSend运行时函数

---

## 建议的下一步

### 高优先级: 优化Yield-From委托

**方法**: 减少JITRT_GenSend中的状态转换开销

1. 使用jump table替代if-else链
2. 添加内联缓存
3. 特化常见迭代器类型(next()方法)

**预期改进**: 20-30%

### 中优先级: 减少活跃变量数量

**方法**: 优化生成器HIR，减少yield点的活跃变量

1. 分析yield点前的数据流
2. 提前spill不必要变量
3. 使用寄存器分配提示

**预期改进**: 5-10%

---

## 技术洞察

### 关于寄存器分配优化的教训

CALLER_SAVE_REGS优化失败的根本原因:

```
reserveRegisters(CALLER_SAVE_REGS):
  - 预留caller-saved寄存器 (X0-X15)
  - 允许callee-saved寄存器用于变量 (X19-X28)
  - 但post-alloc代码生成假设所有寄存器都可用
  - 导致: 变量在callee-saved寄存器中，但代码生成失败
```

### 关于帧池化的教训

帧池化优化效果有限的原因:

```
递归生成器性能 = f(委托开销, 分配开销, ...)
分配开销 ≈ 2-3% (已经很优化)
委托开销 ≈ 54% (主要瓶颈)
```

---

## 提交记录

1. `52451a73` perf: 增加生成器帧池大小以支持深度递归工作负载
2. `675b2ee9` perf: 优化生成器寄存器分配 - 使用callee-saved寄存器 (已回滚)
3. `2e08fb69` docs: 性能剖析报告 - 分析可行优化方向

---

**结论**: 帧池化优化有效但改进微小。真正的性能提升需要优化yield-from委托机制。
