# 递归生成器 JIT 优化实施计划

> **对于智能代理工作者：** 必需：使用 superpowers:subagent-driven-development（如果有子代理）或 superpowers:executing-plans 来执行此计划。步骤使用复选框（`- [ ]`）语法进行跟踪。

**目标：** 消除 JIT 编译递归生成器（Tree.__iter__ 模式）中的 1.8-1.9x 性能回退

**架构：** 数据驱动优化 - 先诊断瓶颈，再应用针对性修复（帧池化 / yield-from 内联 / 寄存器分配），如不足则回退到 HIR 转换

**技术栈：** Python 3.14, CinderX JIT, C++ (HIR/LIR), Docker ARM64 QEMU

---

## 块 1：诊断阶段（Phase 0）

**工作目录：** `/Users/luchen/Agents-Repo/Claude-Code/cinderx`

### 任务 1：创建诊断基础设施

**文件：**
- 创建：`scripts/diagnostics/benchmark_recursive_generator.py`
- 创建：`scripts/diagnostics/` 目录（如需要）

- [ ] **步骤 1：创建诊断目录**

运行：
```bash
cd /Users/luchen/Agents-Repo/Claude-Code/cinderx
mkdir -p scripts/diagnostics
mkdir -p docs/superpowers/diagnostics
```

预期：两个目录创建成功

- [ ] **步骤 2：编写基准测试工具脚本**

创建 `scripts/diagnostics/benchmark_recursive_generator.py`：

```python
#!/usr/bin/env python3
"""
递归生成器性能分析基准测试工具。
比较 CPython 解释器与 CinderX JIT 在 Tree.__iter__ 模式下的性能。
"""

import sys
import time
import statistics
from pathlib import Path

# 添加 PythonLib 到路径以便导入 cinderx
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cinderx" / "PythonLib"))

class Node:
    """使用递归生成器迭代器的树节点。"""

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


class StackNode:
    """使用栈式（非递归）迭代器的树节点。"""

    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        stack = [(self, False, False)]
        while stack:
            node, left_done, right_done = stack.pop()
            if not left_done and node.left:
                stack.append((node, True, False))
                stack.append((node.left, False, False))
            elif not right_done:
                yield node.value
                if node.right:
                    stack.append((node, True, True))
                    stack.append((node.right, False, False))


def build_tree(node_cls, depth):
    """构建平衡二叉树。"""
    if depth == 0:
        return None
    mid = 2 ** (depth - 1)
    return node_cls(
        mid,
        build_tree(node_cls, depth - 1),
        build_tree(node_cls, depth - 1)
    )


def traverse(tree):
    """遍历树并返回总和。"""
    s = 0
    for v in tree:
        s += v
    return s


def bench(tree, iterations=10):
    """基准测试树遍历。"""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        traverse(tree)
        times.append(time.perf_counter() - start)
    return statistics.mean(times), statistics.stdev(times)


def main():
    print("=" * 60)
    print("递归生成器性能诊断")
    print("=" * 60)

    depth = 15
    iterations = 15

    # 测试 1：递归生成器（基线）
    print("\n[1] 递归生成器 (Tree.__iter__)")
    tree1 = build_tree(Node, depth)
    mean, std = bench(tree1, iterations)
    print(f"    时间: {mean*1000:.3f}ms ± {std*1000:.3f}ms")

    # 测试 2：栈式迭代器
    print("\n[2] 栈式迭代器 (StackNode.__iter__)")
    tree2 = build_tree(StackNode, depth)
    mean2, std2 = bench(tree2, iterations)
    print(f"    时间: {mean2*1000:.3f}ms ± {std2*1000:.3f}ms")
    print(f"    加速比: {mean/mean2:.2f}x")

    # 测试 3：使用 CinderX JIT（如果可用）
    try:
        import cinderjit
        cinderjit.enable()

        print("\n[3] CinderX JIT（递归生成器）")
        tree3 = build_tree(Node, depth)
        cinderjit.force_compile(Node.__iter__)

        # 预热
        for _ in range(5):
            traverse(tree3)

        mean3, std3 = bench(tree3, iterations)
        print(f"    时间: {mean3*1000:.3f}ms ± {std3*1000:.3f}ms")
        print(f"    vs 基线: {mean/mean3:.2f}x")
        print(f"    vs 栈式: {mean2/mean3:.2f}x")

        # 编译信息
        print(f"\n    已编译: {cinderjit.is_jit_compiled(Node.__iter__)}")
        print(f"    代码大小: {cinderjit.get_compiled_size(Node.__iter__)} bytes")

    except ImportError:
        print("\n[3] CinderX 不可用，跳过 JIT 测试")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
```

- [ ] **步骤 3：使脚本可执行**

运行：
```bash
chmod +x scripts/diagnostics/benchmark_recursive_generator.py
```

预期：无输出，权限已更新

- [ ] **步骤 4：测试基线基准（不使用 JIT）**

运行：
```bash
python3 scripts/diagnostics/benchmark_recursive_generator.py 2>&1 | tee docs/superpowers/diagnostics/macos-baseline.txt
```

预期输出（近似值 - 实际值取决于硬件）：
```
============================================================
递归生成器性能诊断
============================================================

[1] 递归生成器 (Tree.__iter__)
    时间: 12.000-15.000ms ± 0.100-0.300ms

[2] 栈式迭代器 (StackNode.__iter__)
    时间: 3.000-5.000ms ± 0.050-0.150ms
    加速比: 2.8-4.0x

[3] CinderX 不可用，跳过 JIT 测试
============================================================
```

**成功标准：**
- 基线（递归）：10-16ms 范围
- 栈式：2-6ms 范围
- 栈式比递归快 2.5-4.5 倍

注意：超出这些范围的值可能表示平台差异或性能变化。这对诊断目的来说是 OK 的 - 我们要找的是相对性能模式，而不是绝对数值。

- [ ] **步骤 5：提交诊断工具**

运行：
```bash
git add scripts/diagnostics/benchmark_recursive_generator.py docs/superpowers/diagnostics/
git commit -m "diag: 添加递归生成器基准测试工具

基线对比：递归 vs 栈式迭代器。
测量性能以识别 JIT 优化机会。"
```

预期：Git 提交创建成功

---

### 任务 2：添加分段计时分析

**文件：**
- 创建：`scripts/diagnostics/profile_generator_phases.py`

- [ ] **步骤 1：编写阶段分析器脚本**

创建 `scripts/diagnostics/profile_generator_phases.py`：

```python
#!/usr/bin/env python3
"""
对生成器执行的各个阶段进行性能分析，以识别瓶颈。
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cinderx" / "PythonLib"))


class ProfiledNode:
    """带有阶段计时插桩的节点。"""

    # 类级别计时计数器
    frame_create_time = 0.0
    yield_from_delegate_time = 0.0
    yield_value_time = 0.0
    frame_cleanup_time = 0.0
    call_count = 0

    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        # 测量帧创建（每次调用仅第一次）
        start_frame = time.perf_counter()
        ProfiledNode.call_count += 1
        ProfiledNode.frame_create_time += time.perf_counter() - start_frame

        try:
            # 测量 yield-from 委托
            if self.left:
                start_delegate = time.perf_counter()
                for v in self.left:
                    ProfiledNode.yield_from_delegate_time += time.perf_counter() - start_delegate

                    # 测量值 yield
                    start_yield = time.perf_counter()
                    yield v
                    ProfiledNode.yield_value_time += time.perf_counter() - start_yield

                    start_delegate = time.perf_counter()

            # 测量自身值的 yield
            start_yield = time.perf_counter()
            yield self.value
            ProfiledNode.yield_value_time += time.perf_counter() - start_yield

            # 测量 yield-from 委托（右子树）
            if self.right:
                start_delegate = time.perf_counter()
                for v in self.right:
                    ProfiledNode.yield_from_delegate_time += time.perf_counter() - start_delegate

                    start_yield = time.perf_counter()
                    yield v
                    ProfiledNode.yield_value_time += time.perf_counter() - start_yield

                    start_delegate = time.perf_counter()

        finally:
            # 测量清理
            start_cleanup = time.perf_counter()
            pass
            ProfiledNode.frame_cleanup_time += time.perf_counter() - start_cleanup

    @classmethod
    def reset_stats(cls):
        cls.frame_create_time = 0.0
        cls.yield_from_delegate_time = 0.0
        cls.yield_value_time = 0.0
        cls.frame_cleanup_time = 0.0
        cls.call_count = 0

    @classmethod
    def print_stats(cls):
        total = (cls.frame_create_time + cls.yield_from_delegate_time +
                 cls.yield_value_time + cls.frame_cleanup_time)

        print(f"\n阶段计时分析：")
        print(f"  总测量时间: {total*1000:.3f}ms")
        print(f"  帧创建:      {cls.frame_create_time*1000:.3f}ms ({cls.frame_create_time/total*100:.1f}%)")
        print(f"  Yield-from 委托: {cls.yield_from_delegate_time*1000:.3f}ms ({cls.yield_from_delegate_time/total*100:.1f}%)")
        print(f"  值 yield:         {cls.yield_value_time*1000:.3f}ms ({cls.yield_value_time/total*100:.1f}%)")
        print(f"  帧清理:       {cls.frame_cleanup_time*1000:.3f}ms ({cls.frame_cleanup_time/total*100:.1f}%)")
        print(f"  调用次数:          {cls.call_count}")


def build_profiled_tree(depth):
    """构建分析树。"""
    if depth == 0:
        return None
    mid = 2 ** (depth - 1)
    return ProfiledNode(
        mid,
        build_profiled_tree(depth - 1),
        build_profiled_tree(depth - 1)
    )


def main():
    print("=" * 60)
    print("生成器阶段性能分析")
    print("=" * 60)

    depth = 15

    # 构建并遍历分析树
    print(f"\n构建树（深度={depth}）...")
    tree = build_profiled_tree(depth)

    print("遍历树...")
    ProfiledNode.reset_stats()

    s = 0
    for v in tree:
        s += v

    print(f"总和: {s}")
    ProfiledNode.print_stats()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
```

- [ ] **步骤 2：使脚本可执行**

运行：
```bash
chmod +x scripts/diagnostics/profile_generator_phases.py
```

预期：无输出

- [ ] **步骤 3：测试阶段分析器**

运行：
```bash
python3 scripts/diagnostics/profile_generator_phases.py
```

预期输出：
```
============================================================
生成器阶段性能分析
============================================================

构建树（深度=15）...
遍历树...
总和: <大数字>

阶段计时分析：
  总测量时间: ~12-14ms
  帧创建:      ~Xms (X%)
  Yield-from 委托: ~Yms (Y%)
  值 yield:         ~Zms (Z%)
  帧清理:       ~Wms (W%)
  调用次数:          2^15 - 1 = 32767

============================================================
```

注意：百分比将识别瓶颈阶段

**关键输出：** 最高百分比的阶段是我们的优化目标！

- [ ] **步骤 4：提交阶段分析器**

运行：
```bash
git add scripts/diagnostics/profile_generator_phases.py
git commit -m "diag: 添加生成器阶段分析器

对生成器执行进行插桩以测量时间消耗：
- 帧创建
- Yield-from 委托
- 值 yield
- 帧清理

帮助识别瓶颈以进行针对性优化。"
```

预期：提交创建成功

---

### 任务 3：验证 JIT 执行路径

**文件：**
- 创建：`scripts/diagnostics/verify_jit_path.py`

- [ ] **步骤 1：编写 JIT 验证脚本**

创建 `scripts/diagnostics/verify_jit_path.py`：

```python
#!/usr/bin/env python3
"""
验证 JIT 编译对递归生成器是否正常工作。
检查反优化和编译状态。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cinderx" / "PythonLib"))

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


def build_tree(depth):
    if depth == 0:
        return None
    mid = 2 ** (depth - 1)
    return Node(mid, build_tree(depth - 1), build_tree(depth - 1))


def main():
    print("=" * 60)
    print("JIT 执行路径验证")
    print("=" * 60)

    try:
        import cinderjit
    except ImportError:
        print("\n错误：CinderX 不可用")
        print("请先构建并安装 CinderX：")
        print("  pip install -e . --no-build-isolation")
        return 1

    print("\n[1] 启用 JIT...")
    cinderjit.enable()
    print("    ✓ JIT 已启用")

    print("\n[2] 强制编译 Node.__iter__...")
    cinderjit.force_compile(Node.__iter__)
    print("    ✓ 编译已请求")

    print("\n[3] 检查编译状态...")
    is_compiled = cinderjit.is_jit_compiled(Node.__iter__)
    print(f"    已编译: {is_compiled}")

    if is_compiled:
        size = cinderjit.get_compiled_size(Node.__iter__)
        print(f"    代码大小: {size} bytes")
    else:
        print("    错误：函数未编译！")
        return 1

    print("\n[4] 构建测试树...")
    tree = build_tree(10)
    print("    ✓ 树已构建（深度=10）")

    print("\n[5] 运行遍历（应使用 JIT 代码）...")
    result = list(tree)
    expected = list(range(1, 2**10))

    if result == expected:
        print("    ✓ 正确性已验证")
    else:
        print("    错误：结果不匹配！")
        print(f"    期望 {len(expected)} 项，得到 {len(result)} 项")
        return 1

    print("\n[6] 检查反优化...")
    # 注意：CinderX 可能不直接暴露反优化计数，但我们检查能检查的
    print("    （反优化检查尚未实现 - 使用 JIT_LOG 手动验证）")

    print("\n" + "=" * 60)
    print("✓ 所有检查通过")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **步骤 2：使脚本可执行**

运行：
```bash
chmod +x scripts/diagnostics/verify_jit_path.py
```

预期：无输出

- [ ] **步骤 3：测试验证脚本（在 CinderX 构建前会失败）**

运行：
```bash
python3 scripts/diagnostics/verify_jit_path.py
```

预期输出（CinderX 构建前）：
```
============================================================
JIT 执行路径验证
============================================================

错误：CinderX 不可用
请先构建并安装 CinderX：
  pip install -e . --no-build-isolation
```

注意：这是预期的 - 将在任务 4 后通过

- [ ] **步骤 4：提交验证脚本**

运行：
```bash
git add scripts/diagnostics/verify_jit_path.py
git commit -m "diag: 添加 JIT 执行路径验证器

检查：
- JIT 是否启用并正常运行
- Node.__iter__ 是否已编译
- 编译后的代码是否产生正确结果
- 没有明显的执行路径问题"
```

预期：提交创建成功

---

### 任务 4：在 macOS 上运行诊断套件

**工作目录：** `/Users/luchen/Agents-Repo/Claude-Code/cinderx`

- [ ] **步骤 0：检查构建前提条件**

运行：
```bash
gcc-15 --version | head -1
g++-15 --version | head -1
python3 --version
```

预期：
```
gcc-15 (GCC) 15.x.x
g++-15 (GCC) 15.x.x
Python 3.14.x
```

如果命令失败，先安装 GCC 15 或修改构建命令使用 `clang` 代替。

- [ ] **步骤 1：本地构建 CinderX**

运行：
```bash
cd /Users/luchen/Agents-Repo/Claude-Code/cinderx

ENABLE_STATIC_PYTHON=0 \
ENABLE_ADAPTIVE_STATIC_PYTHON=0 \
ENABLE_LIGHTWEIGHT_FRAMES=0 \
CC=gcc-15 \
CXX=g++-15 \
python3 -m pip install -e . --no-build-isolation
```

预期：
- 构建在 2-5 分钟内完成
- 最终输出：`Successfully installed cinderx-VERSION`
- 无构建错误

如果构建超过 5 分钟，检查：
- 缺少依赖项（应自动安装）
- 编译器警告（可接受，但错误不可接受）
- 磁盘空间问题

- [ ] **步骤 2：验证 JIT 正常工作**

运行：
```bash
python3 scripts/diagnostics/verify_jit_path.py
```

预期输出：
```
============================================================
JIT 执行路径验证
============================================================

[1] 启用 JIT...
    ✓ JIT 已启用

[2] 强制编译 Node.__iter__...
    ✓ 编译已请求

[3] 检查编译状态...
    已编译: True
    代码大小: <2000-3000> bytes

[4] 构建测试树...
    ✓ 树已构建（深度=10）

[5] 运行遍历（应使用 JIT 代码）...
    ✓ 正确性已验证

[6] 检查反优化...
    （反优化检查尚未实现 - 使用 JIT_LOG 手动验证）

============================================================
✓ 所有检查通过
============================================================
```

- [ ] **步骤 3：使用 JIT 运行基准测试**

运行：
```bash
python3 scripts/diagnostics/benchmark_recursive_generator.py 2>&1 | tee docs/superpowers/diagnostics/macos-jit-baseline.txt
```

预期输出：
```
============================================================
递归生成器性能诊断
============================================================

[1] 递归生成器 (Tree.__iter__)
    时间: ~12-14ms ± 0.2ms

[2] 栈式迭代器 (StackNode.__iter__)
    时间: ~3-4ms ± 0.1ms
    加速比: 3.1-3.5x

[3] CinderX JIT（递归生成器）
    时间: ~21-23ms ± 0.3ms
    vs 基线: 0.54-0.65x (更慢！)
    vs 栈式: 0.17-0.19x

    已编译: True
    代码大小: <2000-3000> bytes
============================================================
```

**关键：** 这确认了我们试图修复的 1.8-1.9x 回退！

- [ ] **步骤 4：使用 JIT 运行阶段分析器**

运行：
```bash
python3 scripts/diagnostics/profile_generator_phases.py 2>&1 | tee docs/superpowers/diagnostics/macos-jit-phases.txt
```

预期输出：
```
============================================================
生成器阶段性能分析
============================================================

构建树（深度=15）...
遍历树...
总和: <大数字>

阶段计时分析：
  总测量时间: ~21-23ms
  帧创建:      ~Xms (X%)
  Yield-from 委托: ~Yms (Y%)
  值 yield:         ~Zms (Z%)
  帧清理:       ~Wms (W%)

============================================================
```

**关键输出：** 最高百分比的阶段是我们的优化目标！

- [ ] **步骤 5：创建诊断报告**

创建 `docs/superpowers/diagnostics/phase0-report.md`：

```markdown
# Phase 0 诊断报告

**日期**: 2026-03-17
**平台**: macOS ARM64（本地）

## 摘要

[在此粘贴 macos-jit-baseline.txt 输出]

## 阶段计时分析

[在此粘贴 macos-jit-phases.txt 输出]

## 瓶颈识别

基于性能分析结果，主要瓶颈是：

**阶段**: [帧创建 | YIELD-FROM 委托 | 值 YIELD | 帧清理]

**百分比**: X%

**根本原因假设**:
[基于百分比和预期行为解释为什么这个阶段慢]

## 下一步

选择的优化策略：**[A | B | C | D]**

- [ ] 策略 A：帧池化（如果帧创建/清理是瓶颈）
- [ ] 策略 B：内联 Yield-From（如果 yield-from 委托是瓶颈）
- [ ] 策略 C：改进寄存器分配（如果值 yield 是瓶颈）
- [ ] 策略 D：HIR 转换（如果多个阶段或策略 A-C 不足）

**目标改进**：至少 50%（达到 ~10-12ms）

## Docker ARM64 验证

TODO：在 Docker ARM64 中复现这些测试以确认一致性。
```

- [ ] **步骤 6：提交诊断报告**

运行：
```bash
git add docs/superpowers/diagnostics/
git commit -m "diag: 添加 Phase 0 诊断结果（macOS JIT）

递归生成器优化的基线测量和瓶颈识别。

关键发现：
- JIT 回退：比 CPython 慢 1.8-1.9x
- 瓶颈阶段：[基于结果待定]
- 目标：≤12-14ms（匹配 CPython 基线）"
```

预期：提交创建成功

---

## 块 1 完成

**决策点：** 基于 Phase 0 结果，继续到块 2 并选择优化策略。

**本块创建的文件：**
- `scripts/diagnostics/benchmark_recursive_generator.py`
- `scripts/diagnostics/profile_generator_phases.py`
- `scripts/diagnostics/verify_jit_path.py`
- `docs/superpowers/diagnostics/macos-baseline.txt`
- `docs/superpowers/diagnostics/macos-jit-baseline.txt`
- `docs/superpowers/diagnostics/macos-jit-phases.txt`
- `docs/superpowers/diagnostics/phase0-report.md`

**下一块将：**
- 分析诊断结果
- 选择优化策略（A/B/C/D）
- 实现针对性修复
- 验证改进

---

## 块 2：优化实现（策略基于 Phase 0 结果待定）

[将在块 1 完成并识别瓶颈后填写]

---

## 块 3：集成和验证

[将在块 2 完成后填写]
