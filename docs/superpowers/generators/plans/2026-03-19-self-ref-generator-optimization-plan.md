# 自引用委托生成器优化 - 实施计划

> **对于智能代理工作者：** 必需：使用 superpowers:subagent-driven-development（如果有子代理）或 superpowers:executing-plans 来执行此计划。步骤使用复选框（`- [ ]`）语法进行跟踪。

**目标：** 通过4种优化策略消除递归生成器中 `yield from self.attr` 委托的性能开销，目标恢复至 CPython 基线性能。

**架构：** 利用已存在于 simplify.cpp 中的 `simplifyYieldFrom` 模式检测，在 HIR 层面为自引用委托生成优化代码路径，绕过通用的 `JITRT_GenSend` → `PyIter_Send` 调用链。

**技术栈：** CinderX JIT (HIR → LIR → codegen), ARM64/x86_64 assembly

---

## Chunk 1: 优化A - 内联调用链（跳过 PyIter_Send）

### 概述
检测 `yield from self.left/right` 模式，直接调用子生成器的 JIT 编译入口点而非通过迭代器协议。

### 核心思路
```
原始路径:
  SEND self.left
    → JITRT_GenSend(gen, None, 0)
      → PyIter_Send(gen, None, &retval)
        → tp_iternext(gen)
          → 再次调用 JIT 编译代码...

优化后路径:
  SEND self.left
    → 直接调用 self.left 的 JIT 入口点
      → 无需 PyIter_Send 开销
```

### Task 1.1: 添加 HIR 特化指令 OptimizedYieldFrom

**Files:**
- Modify: `cinderx/Jit/hir/hir.h:3648-3653` - 添加 `OptimizedYieldFrom` 指令定义
- Modify: `cinderx/Jit/hir/opcode.h` - 添加 opcode
- Modify: `cinderx/Jit/hir/builder.cpp:5348-5365` - emitYieldFrom 中检测模式并生成 OptimizedYieldFrom

- [ ] **Step 1: 在 hir.h 中添加 OptimizedYieldFrom 指令**

```cpp
// OptimizedYieldFrom 用于自引用委托场景
// 绕过 JITRT_GenSend，直接调用子生成器
DEFINE_SIMPLE_INSTR(
    OptimizedYieldFrom,
    (TObject, TOptObject),
    HasOutput,
    Operands<3>,  // send_value, iter, target_entry
    DeoptBase);
```

- [ ] **Step 2: 添加 opcode 到 opcode.h**

```cpp
// 在 FOREACH_OPCODE 宏中添加
F(OptimizedYieldFrom)
```

- [ ] **Step 3: 在 builder.cpp 中实现模式检测**

```cpp
void HIRBuilder::emitYieldFrom(TranslationContext& tc, Register* out) {
  auto& stack = tc.frame.stack;
  auto send_value = stack.pop();
  auto iter = stack.top();

  // 检测自引用模式
  if (isSelfReferencePattern(iter)) {
    // 生成 OptimizedYieldFrom 指令
    Register* entry = temps_.AllocateNonStack();
    tc.emit<LoadFuncPtr>(entry, getSubGeneratorEntry(iter));
    tc.emit<OptimizedYieldFrom>(out, send_value, iter, entry, tc.frame);
  } else {
    tc.emit<YieldFrom>(out, send_value, iter, tc.frame);
  }
  stack.pop();
  stack.push(out);
}
```

- [ ] **Step 4: 添加 instr_effects.cpp 支持**

- [ ] **Step 5: 添加 hir.cpp 支持**

- [ ] **Step 6: Commit**

```bash
git add cinderx/Jit/hir/hir.h cinderx/Jit/hir/opcode.h cinderx/Jit/hir/builder.cpp
git commit -m "feat: 添加 OptimizedYieldFrom HIR 指令用于自引用委托"
```

### Task 1.2: 添加 LIR 层面的 OptimizedYieldFrom 处理

**Files:**
- Modify: `cinderx/Jit/lir/generator.cpp:1264-1280` - 添加 case
- Create: `cinderx/Jit/codegen/autogen.cpp` - 添加 translateOptimizedYieldFrom

- [ ] **Step 1: 在 generator.cpp 中添加 LIR 翻译 case**

```cpp
case Opcode::kOptimizedYieldFrom: {
  Instruction* instr = bbb.appendInstr(
      i.output(),
      Instruction::kOptimizedYieldFrom,
      env_->asm_tstate,
      i.GetOperand(0),  // send_value
      i.GetOperand(1), // iter
      i.GetOperand(2)  // entry_point
  );
  finishYield(bbb, instr, static_cast<const DeoptBase*>(&i));
  break;
}
```

- [ ] **Step 2: 添加 autogen.cpp 中的 translateOptimizedYieldFrom**

- [ ] **Step 3: Commit**

```bash
git add cinderx/Jit/lir/generator.cpp cinderx/Jit/codegen/autogen.cpp
git commit -m "feat: 添加 OptimizedYieldFrom LIR 翻译"
```

### Task 1.3: 实现 ARM64 代码生成

**Files:**
- Modify: `cinderx/Jit/codegen/arch/aarch64.cpp` - 实现 translateOptimizedYieldFrom

- [ ] **Step 1: 实现 translateOptimizedYieldFrom for ARM64**

```cpp
void translateOptimizedYieldFrom(Environ* env, const Instruction* instr) {
  // 1. 设置 tstate 到 X0
  // 2. 设置 send_value 到 X1
  // 3. 加载子生成器到 X0
  // 4. 直接调用子生成器的 JIT 入口点（尾调用）
  // 5. 处理返回值
}
```

- [ ] **Step 2: 测试编译**

```bash
python3.14 -m build --wheel
# 预期: 编译成功，无错误
```

- [ ] **Step 3: Commit**

```bash
git add cinderx/Jit/codegen/arch/aarch64.cpp
git commit -m "feat: 实现 ARM64 OptimizedYieldFrom 代码生成"
```

### Task 1.4: 添加性能测试

**Files:**
- Create: `scripts/diagnostics/test_optimized_yield_from.py`

- [ ] **Step 1: 创建测试脚本**

```python
#!/usr/bin/env python3
"""测试 OptimizedYieldFrom 优化效果"""
import sys
import time
sys.path.insert(0, "cinderx/PythonLib")

def benchmark():
    from cinderx import jit as cinderjit
    cinderjit.auto()

    class Node:
        def __init__(self, value, left=None, right=None):
            self.value = value
            self.left = left
            self.right = right

        def __iter__(self):
            if self.left:
                yield from self.left
            yield self.value
            if self.right:
                yield from self.right

    # Build tree
    def build(depth):
        if depth == 0: return None
        return Node(2**(depth-1), build(depth-1), build(depth-1))

    tree = build(15)

    # Benchmark
    times = []
    for _ in range(10):
        start = time.perf_counter()
        sum(tree)
        times.append(time.perf_counter() - start)

    print(f"Optimized: {sum(times)/len(times)*1000:.2f}ms")
```

- [ ] **Step 2: 运行测试**

```bash
PYTHONJIT=1 python3.14 scripts/diagnostics/test_optimized_yield_from.py
# 预期: 比优化前快
```

- [ ] **Step 3: Commit**

```bash
git add scripts/diagnostics/test_optimized_yield_from.py
git commit -m "test: 添加 OptimizedYieldFrom 性能测试"
```

---

## Chunk 2: 优化B - 尾部调用优化

### 概述
当子生成器与父生成器共享相同的代码对象时，使用尾调用跳转而非函数调用。

### Task 2.1: 检测尾部调用条件

- [ ] **Step 1: 在 simplifyYieldFrom 中检测尾部调用条件**

```cpp
// 检查条件:
// 1. 子生成器类型与父生成器相同
// 2. 子生成器的 __iter__ 已 JIT 编译
// 3. 无需特殊的 send/throw/close 处理
```

- [ ] **Step 2: 生成尾部调用代码**

```cpp
// 直接跳转而非调用
// 需要保存当前帧状态并恢复子帧
```

- [ ] **Step 3: Commit**

---

## Chunk 3: 优化C - 特化 Send 指令

### 概述
为已知类型（Node）添加内联缓存的 Send 指令特化。

### Task 3.1: 添加 Send 特化

- [ ] **Step 1: 在 simplify.cpp 中实现 Send 特化**

```cpp
Register* simplifySend(Env& env, const Send* instr) {
  Register* iter = instr->GetOperand(0);
  Register* value = instr->GetOperand(1);

  // 检测 iter 是否为 Node 类型
  if (isNodeType(env, iter)) {
    // 生成特化代码
    return emitSpecializedSend(iter, value);
  }

  return nullptr;  // 使用默认实现
}
```

- [ ] **Step 2: 添加快速路径**

```cpp
// Node 特化快速路径
// 直接调用 node.left.__iter__() 并委托
```

- [ ] **Step 3: Commit**

---

## Chunk 4: 优化D - 尾部递归优化

### 概述
当子生成器与父生成器是同一实例时（即尾部递归），直接跳转到父生成器的开头。

### Task 4.1: 检测尾部递归模式

- [ ] **Step 1: 检测 self.yield_from_self 模式**

```python
def __iter__(self):
    yield from self  # 尾部递归！
```

- [ ] **Step 2: 实现直接跳转**

```cpp
// 保存当前状态，跳转到函数开头
// 无需创建新的生成器帧
```

- [ ] **Step 3: Commit**

---

## Chunk 5: 性能验证与回归测试

### Task 5.1: 综合性能测试

- [ ] **Step 1: 运行 benchmark_recursive_generator.py**

```bash
PYTHONJIT=1 PYTHONJITAUTO=1 python3.14 scripts/diagnostics/benchmark_recursive_generator.py
```

- [ ] **Step 2: 验证目标达成**

```
目标:
- CPython 基线: ~10ms
- 优化后 CinderX: ≤10ms
- 当前 CinderX: ~18ms
```

- [ ] **Step 3: 回归测试**

```bash
pytest cinderx/PythonLib/test_cinderx/test_cinderjit.py -v
# 确保无回归
```

### Task 5.2: 生成最终报告

**Files:**
- Create: `docs/superpowers/generators/diagnostics/YYYY-MM-DD-optimization-results.md`

---

## 文件修改清单

### HIR 层
- `cinderx/Jit/hir/hir.h` - 添加 OptimizedYieldFrom 指令
- `cinderx/Jit/hir/opcode.h` - 添加 opcode
- `cinderx/Jit/hir/builder.cpp` - emitYieldFrom 模式检测
- `cinderx/Jit/hir/instr_effects.cpp` - 指令效果
- `cinderx/Jit/hir/hir.cpp` - 指令支持
- `cinderx/Jit/hir/simplify.cpp` - Send/YieldFrom 特化

### LIR 层
- `cinderx/Jit/lir/generator.cpp` - LIR 翻译

### Codegen 层
- `cinderx/Jit/codegen/autogen.cpp` - 通用代码生成
- `cinderx/Jit/codegen/arch/aarch64.cpp` - ARM64 代码生成

### 测试
- `scripts/diagnostics/test_optimized_yield_from.py` - 优化测试
- `docs/superpowers/generators/diagnostics/YYYY-MM-DD-optimization-results.md` - 结果报告

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| deopt 处理复杂 | 高 | 使用环境变量控制，只在简单场景启用 |
| 寄存器分配冲突 | 中 | 参考已回滚的 CALLER_SAVE_REGS 教训 |
| 类型检测不准确 | 中 | 添加运行时检查和回退机制 |

---

## 预期改进

| 优化 | 预期改进 | 优先级 |
|------|----------|--------|
| A: 内联调用链 | 20-30% | P0 |
| B: 尾部调用 | 10-15% | P1 |
| C: Send 特化 | 15-20% | P1 |
| D: 尾部递归 | 5-10% | P2 |
