# 递归生成器 JIT 优化设计文档

**日期**: 2026-03-17
**状态**: 草稿
**作者**: Claude Code（基于头脑风暴会话）

## 1. 问题陈述

### 当前情况

使用 `yield from` 的 JIT 编译递归生成器相比 CPython 解释器有 1.8-1.9x 的性能回退：

- **CPython 基线（ARM 硬件）**: ~29.8ms
- **CinderX JIT（ARM 硬件）**: ~57.2ms（慢 1.92x）
- **Docker ARM64 QEMU**: ~35.7ms（CPython）vs ~67.5ms（CinderX JIT，慢 1.89x）

这个回退是递归生成器特有的。非递归生成器和栈式迭代器表现良好：
- 简单生成器：JIT 与 CPython ~相同
- 栈式迭代器（非递归）：JIT 比 CPython 快 3.1x

### 根本原因假设

回退似乎是由递归生成器模式的低效代码生成引起的，具体包括：
- 生成器帧创建/销毁开销
- Yield-from 状态机实现
- 次优的内存访问模式或寄存器分配

## 2. 优化目标

### 主要目标

消除 1.8-1.9x 性能回退，将 JIT 编译的递归生成器恢复到至少 CPython 解释器基线性能。

### 量化目标

| 指标 | 当前 | 目标 |
|------|------|------|
| CPython 基线（Docker ARM64） | ~35.7ms | N/A |
| CinderX JIT（Docker ARM64） | ~67.5ms | **≤35.7ms** |
| 慢化因子 | 1.89x | **≤1.0x** |

### 约束条件

1. **不影响其他代码性能**：非递归生成器、普通函数和其他 JIT 编译的代码不能变慢
2. **通过现有测试**：必须通过所有 CinderX 测试套件（test_jit*.py, test_cinderx.py 等）
3. **ARM Docker 验证**：必须在 ARM Docker 容器中用 pyperformance generators benchmark 验证

### 优化范围

- **阶段 1**：专门优化 `Tree.__iter__` 模式（递归 + 在 self 属性上的 yield from）
- **未来**：根据经验考虑泛化到类似模式

## 3. 诊断阶段（Phase 0）

### 3.1 macOS 本地验证（快速迭代）

**目标**：通过简单迭代快速定位性能瓶颈

**检查点 1：JIT 执行路径验证**
```python
import cinderjit
cinderjit.enable()
cinderjit.force_compile(Node.__iter__)

# 验证编译成功
assert cinderjit.is_jit_compiled(Node.__iter__)
print(f"编译大小: {cinderjit.get_compiled_size(Node.__iter__)}")

# 运行并检查反优化
tree = build_tree(15)
for _ in tree:
    pass

# 检查反优化计数（应为 0 或很小）
```

**检查点 2：分段计时**
在 `Node.__iter__` 中插入计时点以测量：
- 帧创建时间
- Yield-from 委托时间
- 值 yield 时间
- 帧清理时间

**检查点 3：基线对比**
对比三种实现：
- 简单生成器（已知 JIT 性能正常）
- 递归生成器（当前慢）
- 栈式迭代器（已知快 3.1x）

### 3.2 Docker ARM64 验证

在 Docker ARM64 QEMU 环境中复现 macOS 发现，确认瓶颈一致性。

**输出**：性能瓶颈识别报告，指出哪个阶段消耗最多时间。

## 4. 优化阶段（基于诊断结果）

### 4.1 如果瓶颈是生成器帧创建/销毁

**优化策略 A：帧池化**

**机制**：
- 为递归生成器复用帧对象
- 在 HIR 中标记递归生成器并生成快速路径
- 只创建帧一次，在后续 yield/resume 时复用

**实现位置**：
- `cinderx/Jit/hir/builder.cpp` - 在 HIR 构建期间标记递归模式
- `cinderx/Jit/generators_*.cpp` - 添加帧池化逻辑
- `cinderx/Jit/lir/generator.cpp` - 生成快速路径代码

**预期改进**：30-50%

### 4.2 如果瓶颈是 Yield-From 状态机

**优化策略 B：内联 Yield-From**

**机制**：
- 检测 `yield from self.left` 模式
- 生成内联状态转换代码以避免函数调用开销
- 类似 CPython 的 `SEND` + `YIELD_FROM` 快速路径

**实现位置**：
- `cinderx/Jit/hir/builder.cpp` - 特化 `emitYieldFrom()`
- `cinderx/Jit/hir/hir.h` - 添加 `InlineYieldFrom` 指令

**预期改进**：20-40%

### 4.3 如果瓶颈是内存访问/寄存器分配

**优化策略 C：改进寄存器分配**

**机制**：
- 为递归生成器保留专用寄存器（self, left, right）
- 减少 stack spill/load 操作
- 优化 `CheckField` / `LoadAttr` 的寄存器使用

**实现位置**：
- `cinderx/Jit/lir/generator.cpp` - 改进寄存器分配策略
- `cinderx/Jit/hir/simplify.cpp` - 应用类似方法到现有的 `simplifyIsTruthy()`

**预期改进**：10-30%

### 4.4 如果以上策略不足

**优化策略 D：HIR 转换为栈式迭代器**

**机制**：
- 在 HIR 构建期间检测 `Tree.__iter__` 模式
- 自动转换为等价的栈式 HIR
- 生成非递归机器码

**实现位置**：
- `cinderx/Jit/hir/builder.cpp` - 添加模式检测
- 新文件：`cinderx/Jit/hir/generator_transforms.cpp`

**预期改进**：200-300%（但实现复杂度高）

**决策点**：仅当策略 A/B/C 组合实现目标改进的 <50% 时才追求策略 D。

## 5. 验证和测试

### 5.1 单元测试

**新测试文件**：`test_recursive_generator_perf.py`

```python
class TestRecursiveGeneratorOptimization:
    def test_tree_iter_compiled(self):
        """验证 Tree.__iter__ 被 JIT 编译"""
        cinderjit.force_compile(Node.__iter__)
        assert cinderjit.is_jit_compiled(Node.__iter__)

    def test_tree_iter_no_deopt(self):
        """验证运行时没有频繁反优化"""
        tree = build_tree(10)
        for _ in tree:
            pass
        # 检查反优化计数应为 0 或很小

    def test_correctness(self):
        """验证优化后的结果正确"""
        tree = build_tree(15)
        result = list(tree)
        expected = list(range(1, 2**15))
        assert result == expected

    def test_performance_regression(self):
        """验证性能至少匹配 CPython"""
        # 运行 15 次，取中位数
        # assert median_time <= CPython_baseline * 1.05  # 允许 5% 容差
```

### 5.2 回归测试

**必须通过的现有测试**：
- `test_jit.py` - 所有 JIT 基础测试
- `test_jit_generators.py` - 生成器相关测试（如果存在）
- `test_cinderx.py` - CinderX 综合测试

**性能回归检查**：
- 在 Docker ARM64 中运行完整 pyperformance
- 对比优化前后的所有 benchmark
- 确认没有 benchmark 回退 >2%

### 5.3 ARM Docker 验证流程

```bash
# 在 cpython-baseline 容器中
cd /root/bm_generators

# 1. 安装新版本
pip install /dist/cinderx-*.whl --force-reinstall

# 2. 正确性验证
python3 -c "
import sys
sys.path.insert(0, '/root/bm_generators')
from run_benchmark import Tree, build_tree
import cinderjit
cinderjit.enable()
cinderjit.force_compile(Tree.__iter__)
tree = build_tree(15)
assert list(tree) == list(range(1, 2**15))
print('正确性 OK')
"

# 3. 性能验证
python3 << 'PY'
import sys, statistics
sys.path.insert(0, '/root/bm_generators')
from run_benchmark import bench_generators
import cinderjit
cinderjit.enable()

# 预热
for _ in range(5):
    bench_generators(1)

# 测量
times = []
for _ in range(15):
    times.append(bench_generators(1))

print(f'CinderX JIT: {statistics.mean(times)*1000:.3f}ms ± {statistics.stdev(times)*1000:.3f}ms')
print(f'目标: ≤35.7ms')
PY
```

## 6. 实施路线图

### Phase 0：诊断（1-2 天）
- [ ] macOS 本地：验证 JIT 执行路径，确认无频繁反优化
- [ ] macOS 本地：分段计时定位瓶颈（帧创建 vs yield-from vs 其他）
- [ ] Docker ARM64：复现瓶颈，确认一致性
- [ ] **交付物**：性能瓶颈识别报告

### Phase 1：快速优化（2-3 天）
- [ ] 根据诊断结果选择匹配的优化策略（A/B/C）
- [ ] 实现优化（预计修改 1-3 个文件）
- [ ] 单元测试验证
- [ ] Docker ARM64 性能验证
- [ ] **Go/No-Go 决策点**：如果改进 ≥50%，进入 Phase 3；否则进入 Phase 2

### Phase 2：深度优化（3-5 天，条件执行）
- [ ] 实现策略 D（HIR 转换为栈式迭代器）
- [ ] 完整正确性测试
- [ ] Docker ARM64 性能验证
- [ ] 回归测试

### Phase 3：集成和验证（1-2 天）
- [ ] 运行完整 CinderX 测试套件
- [ ] 在 Docker ARM64 中运行完整 pyperformance
- [ ] 确认其他 benchmark 无回退
- [ ] 代码审查
- [ ] 文档更新

**总预计时间**：4-10 天（取决于是否需要 Phase 2）

## 7. 风险和缓解措施

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 诊断发现不明确的瓶颈 | 中 | 延期 | 多角度分析（perf、手动插桩、HIR dump） |
| Phase 1 优化不足 | 中 | 需要更多时间 | Go/No-Go 机制，及时切换到 Phase 2 |
| Phase 2 实现复杂度高 | 高 | 延期 | 可降低目标（接受部分改进） |
| 优化导致其他 benchmark 回退 | 低 | 阻塞发布 | 回滚机制 + 完整回归测试 |
| ARM Docker 和真实硬件表现不同 | 低 | 误判 | 预留真实硬件验证时间 |

## 8. 成功标准

优化将被视为成功，如果：

1. **性能**：CinderX JIT 在递归生成器（Tree.__iter__）上在 ARM Docker 中 ≤ 35.7ms（至少匹配 CPython 基线）
2. **正确性**：所有现有 CinderX 测试通过
3. **无回退**：没有其他 pyperformance benchmark 回退 >2%
4. **可维护性**：代码变更经过良好文档化和审查

## 9. 未来工作

如果此优化成功，潜在的后续工作包括：

1. **泛化**：将优化扩展到 Tree.__iter__ 之外的类似递归生成器模式
2. **主动优化**：添加启发式方法自动检测和优化递归生成器
3. **文档**：记录编写 JIT 友好的递生成器的最佳实践
4. **监控**：向 CI/CD 管道添加性能回归测试
