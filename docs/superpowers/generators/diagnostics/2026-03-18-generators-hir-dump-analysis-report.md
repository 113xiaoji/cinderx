# HIR Dump 分析报告 - YieldFrom 优化关键发现

**日期**: 2026-03-17 23:00
**分析对象**: `Node.__iter__` (递归生成器)
**目的**: 理解 yield-from 的 HIR 结构，为优化实施提供依据

---

## 关键发现 🔍

### 1. YieldFrom 指令的操作数结构

**HIR Dump**:
```hir
bb 2 (preds 3, 18) {
  v139:Object = Phi<3, 18> v144 v135
  v141:Object = Send v133 v139 {
    ...
  }
  v142:CInt64 = GetSecondOutput<CInt64> v141
  CondBranch<32, 3> v142
}

bb 3 (preds 2) {
  v144:Object = YieldFrom v141 v133 {
    ...
  }
}
```

**指令签名**:
```cpp
YieldFrom(send_value, iter)
```

- **v141** (`send_value`): 来自 `Send` 指令
- **v133** (`iter`): 来自 **Phi 节点**（不是 LoadAttr！）

---

### 2. iter 操作数的来源（Phi 节点）

**关键代码路径**:

```hir
# bb 16: 加载 self.left
v129:Object = CheckField<"left"> v128

# bb 19: 类型检查（是否是 Gen）
CondBranchCheckType<20, 23, Gen> v129

# bb 20: 如果是 Gen，直接使用
Incref v129
Branch<18>

# bb 23: 如果不是 Gen，调用 GetIter
v132:Object = GetIter v129
Branch<18>

# bb 18: Phi 节点合并两个路径
v133:Object = Phi<20, 23> v129 v132
```

**数据流**:
```
self.left (LoadField)
    ↓
类型检查 (Gen vs 其他)
    ↓
├─ Gen 路径: v129 (直接)
└─ 其他路径: GetIter(v129) → v132
    ↓
Phi 节点: v133 = Phi(v129, v132)
    ↓
YieldFrom(v141, v133)
```

---

### 3. 模式检测失败的原因

**原始检测逻辑**:
```cpp
if (!iter->instr()->IsLoadAttr()) {
    JIT_LOG("iter is not LoadAttr");
    return nullptr;
}
```

**实际 HIR**:
- `iter` 是 **Phi 节点**，不是 LoadAttr
- Phi 的输入之一 (v129) 来自 `LoadField<left@24>`
- Phi 的另一个输入 (v132) 来自 `GetIter(v129)`

**结果**: 直接的 `IsLoadAttr()` 检查失败 ❌

---

### 4. 正确的检测策略

**需要追溯 Phi 节点的输入**:

```cpp
// 伪代码
if (iter->instr()->IsPhi()) {
    Phi* phi = iter->instr()->as<Phi>();
    for (each input in phi) {
        if (input->instr()->IsGetIter()) {
            GetIter* get_iter = input->instr()->as<GetIter>();
            Register* source = get_iter->GetOperand(0);
            if (source->instr()->IsLoadField()) {
                LoadField* load_field = source->instr()->as<LoadField>();
                if (load_field->GetOperand(0)->id() == 0) {
                    // ✅ 找到 self.<attr> 模式！
                }
            }
        }
    }
}
```

---

## 优化实施路线图

### Phase 2-A: 模式检测增强（2-3 小时）

**目标**: 完善 Phi 节点追溯逻辑

**步骤**:
1. ✅ 识别 Phi 节点（已实现）
2. ✅ 遍历 Phi 输入（已实现）
3. ✅ 检测 GetIter 指令（已实现）
4. ✅ 追溯 GetIter 源到 LoadField（已实现）
5. ✅ 验证 LoadField 接收器是 self（已实现）
6. 📋 **待修复**: 编译错误（HIR API 使用不当）

**预期结果**:
- Profiling 数据显示优化机会检测成功
- 日志显示 "✅ Phi->GetIter->LoadField(self) detected!"

---

### Phase 2-B: 性能数据收集（1-2 小时）

**目标**: 完整的 profiling 数据

**步骤**:
1. 修复编译错误
2. 运行完整 benchmark
3. 收集检测频率数据
4. 评估 ROI

**成功标准**:
- 检测率 > 50% (优化机会频繁出现)
- ROI 验证（值得实施完整优化）

---

### Phase 2-C: 完整优化实施（3-5 天）

**前提条件**: Phase 2-B 数据证明 ROI

**技术挑战**:
1. **创建循环**: 需要在 HIR builder 中生成循环结构
2. **状态机**: 内联 generator 的 send/throw/close 协议
3. **异常处理**: StopIteration 的处理
4. **Deopt 安全性**: 保留足够的状态信息

**参考实现**:
- `simplifyIsTruthy`: 简单的 peephole 优化示例
- `simplifyYieldFrom`: 需要更复杂的控制流处理

---

## 编译错误分析

**当前错误**:
```
error: no member named 'opcode' in 'jit::hir::Instr'
error: no member named 'GetOperand' in 'jit::hir::Phi' (wrong method)
```

**根本原因**:
1. CinderX HIR API 与标准指令 API 不同
2. 需要查阅正确的 API 文档或现有代码示例

**解决方案**:
1. 查看 `cinderx/Jit/hir/hir.h` 中的类定义
2. 参考 `float_accumulator_promotion.cpp` 中的 Phi 使用示例
3. 使用正确的方法名称（如 `NumOperands()`, `GetOperand()`）

---

## 下次会话行动计划

### 立即行动（优先级 1）

1. **修复编译错误**
   ```bash
   # 查看正确的 API
   grep -A 20 "class Phi " cinderx/Jit/hir/hir.h
   grep "Phi->NumOperands\|Phi->GetOperand" cinderx/Jit/hir/*.cpp
   ```

2. **测试模式检测**
   ```bash
   PYTHONJIT_ARM_INLINE_YIELD_FROM=1 \
   PYTHONJITLOGFILE=/tmp/test.log \
   python3 scripts/diagnostics/benchmark_recursive_generator.py
   ```

3. **验证日志输出**
   ```bash
   grep "✅ Phi->GetIter->LoadField" /tmp/test.log
   ```

### 短期行动（优先级 2）

4. **完成 profiling 数据收集**
5. **评估 ROI**
6. **决策**: 继续 Phase 2-C 或采用选项 C

---

## HIR 指令参考

### 关键指令类型

| 指令 | 描述 | 示例 |
|------|------|------|
| `LoadField` | 加载字段 | `v129 = LoadField<left@24> v91` |
| `CheckField` | 字段类型检查 | `v129 = CheckField<"left"> v128` |
| `GetIter` | 获取迭代器 | `v132 = GetIter v129` |
| `Phi` | SSA Phi 节点 | `v133 = Phi<20, 23> v129 v132` |
| `Send` | Generator send | `v141 = Send v133 v139` |
| `YieldFrom` | Yield-from 指令 | `v144 = YieldFrom v141 v133` |

### 基本块控制流

```
bb 0 (entry)
  ↓
bb 16 (load self.left + 检查)
  ↓
bb 1 (类型检查)
  ↓
bb 19 (Gen? 分支)
  ├─→ bb 20 (Gen 路径)
  └─→ bb 23 (GetIter 路径)
      ↓
      bb 18 (Phi 合并)
        ↓
        bb 2 (Send loop)
          ↓
          bb 3 (YieldFrom)
```

---

## 性能预期

### 当前性能
- **CPython**: 8.919ms
- **CinderX JIT**: 18.792ms (2.1x 回退)

### 优化目标
- **保守目标**: ≤12ms (35% 改进)
- **理想目标**: ≤9.044ms (匹配 CPython)

### 瓶颈占比
- **Yield-from 委托**: 53.9% (1262ms)
- **值 yield**: 45.8% (1072ms)

### 预期改进
如果优化 yield-from 委托：
- **30-40% 改进**: 18.792ms → ~12ms
- **50% 改进**: 18.792ms → ~9ms

---

## 参考文件

### 已创建的文档
- `docs/superpowers/diagnostics/hir-dump-full.log` - 完整 HIR dump (800+ 行)
- `docs/superpowers/diagnostics/hir-baseline-recursive.txt` - 带注释的 HIR 分析
- `docs/superpowers/diagnostics/hir-architecture-analysis.md` - HIR 架构文档

### 代码位置
- `cinderx/Jit/hir/simplify.cpp:963-1088` - simplifyYieldFrom 实现
- `cinderx/Jit/hir/hir.h` - HIR 指令定义
- `cinderx/Jit/hir/builder.cpp:5320-5330` - emitYieldFrom

### 参考实现
- `cinderx/Jit/hir/float_accumulator_promotion.cpp:129` - Phi 节点遍历示例
- `cinderx/Jit/hir/simplify.cpp:837-883` - simplifyIsTruthy 示例

---

## 总结

**关键洞察**:
✅ HIR dump 分析成功揭示了 yield-from 的真实结构
✅ 识别了 Phi 节点作为 iter 操作数的来源
✅ 确认了优化机会存在（self.left -> GetIter -> Phi -> YieldFrom）

**技术挑战**:
⚠️ Phi 节点追溯需要额外的 HIR API 知识
⚠️ 完整优化需要创建循环和状态机（复杂度高）

**下一步**:
📋 修复编译错误 → 完成模式检测 → 收集 profiling 数据 → 实施 Phase 2

**预计完成时间**: 3-5 天（如果 ROI 验证通过）

---

**报告生成**: 2026-03-17 23:00
**分析者**: Claude Code
**会话**: 第2次会话
