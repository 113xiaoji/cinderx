# InlineIter 优化 - 生成器内联迭代

## 概述

InlineIter 是 CinderX JIT 中的一个优化，用于内联非逃逸生成器的迭代操作。该优化主要针对树遍历等常见模式，通过逃逸分析识别可以安全内联的生成器，从而减少帧切换开销。

## 实现状态

### Phase 1 (已完成 ✅)
- **InlineIter HIR 指令**: 新增指令用于非逃逸生成器
- **逃逸分析**: 检测树遍历模式 (self.left/right)
- **LIR Codegen**: 支持物理寄存器和栈槽操作数
- **性能**: 3-32% 改进 (相比 OptimizedYieldFrom 的 ~1%)

### Phase 2-3 (计划中)
- **状态机生成**: 在 HIR builder 中生成状态机
- **直接代码生成**: 消除帧切换，实现 10-12x 性能提升

## 架构设计

### HIR 指令
```cpp
// InlineIter 指令定义 (cinderx/Jit/hir/hir.h)
class InlineIter : public Instruction {
  // 输入: send_value, iter, state_size
  // 输出: 生成的值或停止标志
  // 用途: 内联非逃逸生成器的迭代操作
};
```

### 逃逸分析
逃逸分析检测生成器是否逃逸出当前作用域。对于树遍历模式：

```python
class Node:
    def __iter__(self):
        if self.left:
            yield from self.left  # 模式: self.left
        yield self.value
        if self.right:
            yield from self.right  # 模式: self.right
```

逃逸分析会：
1. 检测 Phi 节点（循环变量）
2. 递归检查所有 Phi 输入是否匹配 `self.left` 或 `self.right` 模式
3. 如果所有输入都匹配且字段一致，返回 `kNoEscape`

### 代码生成
LIR codegen 处理两种操作数类型：
- **物理寄存器**: 直接使用寄存器值
- **栈槽**: 从栈帧加载值

关键代码模式：
```cpp
const OperandBase* operand = instr->getInput(i);
if (operand->isReg()) {
  // 使用物理寄存器
  as->mov(reg, x86::gpb(operand->getPhyRegister()));
} else {
  // 从栈槽加载
  PhyLocation loc = operand->getStackSlot();
  as->mov(reg, x86::ptr(x86::rbp, loc.loc));
}
```

## 性能基准测试

### 测试方法
```bash
PYTHONJITHUGEPAGES=0 PYTHONJIT=1 \
  PYTHONJIT_ARM_INLINE_YIELD_FROM=1 \
  PYTHONJITDEBUG=0 \
  .venv/bin/python3 test_inline_iter.py
```

### 性能结果

| 树深度 | 节点数 | WITH InlineIter (ms) | WITHOUT (ms) | 改进 |
|--------|--------|---------------------|--------------|------|
| 5      | 63     | 0.0171              | 0.0183       | 6.6% |
| 8      | 511    | 0.1691              | 0.1800       | 6.1% |
| 10     | 2047   | 0.7713              | 1.1438       | **32.6%** |
| 12     | 8191   | 3.4025              | 5.0189       | **32.2%** |
| 14     | 32767  | 14.879              | 15.292       | 2.7% |
| 15     | 65535  | 30.013              | 31.759       | 5.5% |
| 16     | 131071 | 62.408              | 65.568       | 4.8% |

### 为什么不是 10-12x?

当前实现 (Phase 1) 仍然调用 `JITRT_GetGenResumeEntry` 运行时辅助函数，与 OptimizedYieldFrom 相同。这意味着：

- **帧切换开销仍存在**: 每次 yield/resume 都需要切换生成器帧
- **状态机未内联**: 生成器状态机仍在运行时管理

Phase 2-3 将实现：
- **状态机生成**: 在编译时生成状态机，消除运行时状态管理
- **直接代码生成**: 将生成器逻辑直接内联到调用方，消除帧切换

## 使用方法

### 环境变量
```bash
export PYTHONJITHUGEPAGES=0      # macOS 必需
export PYTHONJIT=1               # 启用 JIT
export PYTHONJIT_ARM_INLINE_YIELD_FROM=1  # 启用 InlineIter
export PYTHONJITDEBUG=0          # 生产环境设为 0
```

### 代码示例
```python
import cinderx.jit

# 启用 JIT
cinderx.jit.enable()

class TreeNode:
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

def traverse_and_collect(tree):
    result = []
    for x in tree:
        result.append(x)
    return result

# 强制编译调用方函数
cinderx.jit.force_compile(traverse_and_collect)

# 不要强制编译生成器本身！
# cinderx.jit.force_compile(TreeNode.__iter__)  # ❌ 会导致崩溃
```

## 已知限制和陷阱

### 1. force_compile 冲突
**问题**: 同时 `force_compile` 生成器函数和使用 InlineIter 会导致崩溃。

**原因**: InlineIter 设计为从外部调用，同时强制编译生成器本身会创建冲突。

**解决**: 只 `force_compile` 调用方函数（如 `traverse_and_collect`），不要 `force_compile` 生成器本身。

### 2. macOS 特殊要求
- **PYTHONJITHUGEPAGES=0**: 必须设置，否则 mmap(PROT_EXEC) 失败
- **GCC 15 + libstdc++**: macOS 上需要显式链接 GCC 的 C++ 标准库
- **代码签名**: 构建后必须重新签名 `.so` 文件

### 3. 模式匹配限制
当前实现只检测以下模式：
- `self.left` / `self.right` 字段访问
- 通过 Phi 节点的循环变量
- `CheckField(LoadField)` 和 `GetIter(CheckField(LoadField))` 链

其他生成器模式（如 `self.children[i]`）不会被优化。

## 实现文件

### 新增文件
- `cinderx/Jit/hir/escape_analysis.cpp` - 逃逸分析实现
- `cinderx/Jit/hir/escape_analysis.h` - 逃逸分析接口
- `dump_hir.py` - Node 类测试脚本
- `test_inline_iter.py` - 性能基准测试脚本

### 修改文件
- `cinderx/Jit/hir/hir_ops.h` - 添加 `V(InlineIter)` opcode
- `cinderx/Jit/hir/hir.h` - 定义 `InlineIter` 指令类
- `cinderx/Jit/hir/hir.cpp` - 添加 `isReplayable()`, `isPassthrough()`
- `cinderx/Jit/hir/instr_effects.cpp` - 添加内存效果
- `cinderx/Jit/hir/printer.cpp` - 添加调试输出
- `cinderx/Jit/hir/parser.cpp` - 添加 HIR 解析支持
- `cinderx/Jit/hir/pass.cpp` - 添加输出类型
- `cinderx/Jit/hir/refcount_insertion.cpp` - 添加引用计数处理
- `cinderx/Jit/hir/simplify.cpp` - 集成逃逸分析和 InlineIter 发射
- `cinderx/Jit/lir/instruction.h` - 添加 LIR InlineIter 指令
- `cinderx/Jit/codegen/autogen.cpp` - 添加 ARM64/x86_64 代码生成

## 构建说明 (macOS ARM64)

```bash
# 使用 GCC 15 构建
CC=/opt/homebrew/bin/gcc-15 CXX=/opt/homebrew/bin/g++-15 \
  CMAKE=/usr/bin/cmake \
  LDFLAGS="-L/opt/homebrew/Cellar/gcc/15.2.0_1/lib/gcc/current -lstdc++" \
  python setup.py build

# 重新签名
codesign --force --deep --sign - scratch/lib.macosx-11.0-arm64-cpython-314/_cinderx.so
```

## 调试

### 启用调试日志
```bash
PYTHONJITDEBUG=1 .venv/bin/python3 test_inline_iter.py
```

### 查看 HIR
```python
import cinderx.jit
cinderx.jit.dump_hir(some_function)
```

### 常见问题

**Q: 为什么性能提升不是 10-12x?**
A: 当前实现是 Phase 1，仍调用运行时辅助函数。Phase 2-3 将实现状态机内联以消除帧切换。

**Q: 为什么 force_compile 生成器会崩溃?**
A: InlineIter 设计为从外部调用，强制编译生成器会创建循环依赖。只编译调用方即可。

**Q: 哪些生成器模式会被优化?**
A: 目前只支持 `self.left/right` 的树遍历模式。其他模式可以扩展 `matchesTreePattern()` 函数。

## 未来工作

### Phase 2: 状态机生成
- 在 HIR builder 中生成状态机
- 将生成器逻辑转换为显式状态转换
- 消除运行时状态管理

### Phase 3: 直接代码生成
- 将状态机直接内联到调用方代码
- 消除所有帧切换开销
- 预期性能: 10-12x 改进

### 扩展模式识别
- 支持更多字段访问模式
- 支持数组/列表元素迭代
- 支持嵌套生成器组合

## 参考

- [JIT Guide](guide.md) - JIT 整体架构
- [Deoptimization](deoptimization.md) - 退优化机制
- [Progress](../../progress.md) - 项目进度和会话记录
