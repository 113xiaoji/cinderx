# Generators 初始分析

## 目标

从计划中的 `Arm generator resume / attr / decref fast path` 方案开始，先确认 `pyperformance` 的 `generators` benchmark 当前到底卡在什么地方：

1. 是 generator method 根本没有进入 compiled set；
2. 还是已经编译了，但 resume / attr / decref 路径太重；
3. 或者两者同时存在。

## benchmark 形状

源码来自：

- `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_generators/run_benchmark.py`

关键形状很简单：

- `Tree.__iter__()` 是递归 generator
- 内部主要是：
  - `if self.left: yield from self.left`
  - `yield self.value`
  - `if self.right: yield from self.right`
- `bench_generators()` 先构建树，再遍历整棵树

这意味着 benchmark 的真正热点理论上应该非常靠近：

- `Tree.__iter__`
- generator resume / yield-from
- `self.left/self.value/self.right` 属性访问

## 当前本地基线

命令：

```bash
PYTHONPATH=/Users/luchen/Repo/cinderx/cinderx/PythonLib \
  /tmp/cinderx314-local/bin/python \
  scripts/arm/bench_pyperf_direct.py \
  --module-path /Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_generators/run_benchmark.py \
  --bench-func bench_generators \
  --bench-args-json "[1]" \
  --samples 5 \
  --prewarm-runs 1 \
  --compile-strategy all \
  --specialized-opcodes
```

结果摘要：

- `median_wall_sec = 0.10902658`
- `compiled_count = 3`
- `total_deopt_count = 0`

compiled qualnames 只有：

- `Tree.__init__`
- `tree`
- `bench_generators`

没有：

- `Tree.__iter__`

## 当前最重要的发现

最开始看到的现象是：

- benchmark 名字叫 `generators`
- 真正的 generator method 是 `Tree.__iter__`
- 但当前 `bench_pyperf_direct.py` 输出的 `compiled_qualnames` 里没有 `Tree.__iter__`

进一步 probe 后，结论已经更新：

### 1. `Tree.__iter__` 实际上是能编译的

本地 probe 结果：

- `jit.is_jit_compiled(Tree.__iter__) == false`（编译前）
- `jit.force_compile(Tree.__iter__) == true`
- `jit.is_jit_compiled(Tree.__iter__) == true`（编译后）
- `jit.get_compiled_size(Tree.__iter__) == 2736`

这说明 `Tree.__iter__` 本身并不存在“根本不能编”的问题。

### 2. benchmark 驱动对 compiled set 的统计口径低估了 generator

在 `bench_pyperf_direct.py` 的实际顺序里，候选函数顺序是：

- `Tree.__init__`
- `Tree.__iter__`
- `tree`
- `bench_generators`

实测发现：

- `Tree.__init__`: `force_compile == true`
- `Tree.__iter__`: `force_compile == false`，但 `is_jit_compiled == true`

也就是说，`Tree.__iter__` 会在前一个候选函数的依赖编译过程中被带上；等轮到它自己 `force_compile()` 时，因为已经 compiled，所以返回 `False`。  
而当前 `bench_pyperf_direct.py` 只把 `force_compile()` 返回 `True` 的函数记进 `compiled_qualnames`，于是把这类 generator 漏记了。

因此：

- `compiled_count = 3` 并不等于“只有 3 个函数真的被编译”
- 对 `generators` 来说，当前首先暴露的是 **driver 统计口径问题**

### 3. 真正的下一层问题已经不是 compile coverage，而是 generator runtime 成本

既然 `Tree.__iter__` 实际上已经编成，那后续真正该看的就变成：

- generator resume
- `yield from`
- refcount / decref

而不是继续停留在“为什么没进 compiled set”这个表层现象。

## 当前 HIR 证据

对真实 benchmark 模块里的 `Tree.__iter__` 抽样后，当前可见：

- `compiled_size = 2736`
- `YieldValue = 1`
- `YieldFrom = 2`
- `LoadField = 20`
- `CheckField = 5`
- `LoadAttrCached = 0`
- `GuardType = 0`
- `GuardIs = 0`
- `Decref = 10`
- `BatchDecref = 0`

这组数字说明两件事：

1. `Tree.__iter__` 已经吃到了 low-local generator attr lowering
   因为 `LoadAttrCached = 0`，而 `LoadField/CheckField` 明显存在。
2. 现在更值得怀疑的是 generator runtime / decref 仍然偏重
   特别是：
   - `YieldFrom = 2`
   - `Decref = 10`
   - `compiled_size = 2736`

仓库里已有的 ARM runtime 回归测试曾希望类似形状保持在：

- `compiled_size <= 2600`

而当前真实 benchmark 模块里的 `Tree.__iter__` 已经高于这个数量级。

进一步把真实 benchmark 的 LIR / Optimized HIR 量化后，当前得到：

- `bb_count = 43`
- `YieldFrom = 2`
- `YieldValue = 1`
- `GetIter = 2`
- `Send = 2`
- `Decref = 10`
- `BatchDecref = 0`
- `RaiseStatic = 2`

这说明：

1. **basic block 数本身没有爆炸**
   现有 toy 测试给的阈值是 `bb_count <= 45`，而真实 benchmark 目前是 `43`。
2. **真正偏大的不是 block 数，而是代码体积**
   当前是 `compiled_size = 2736`。
3. **`BatchDecref` 这条线当前不会自动触发**
   `optimizeLongDecrefRuns()` 只会合并长度 `>= 4` 的连续 `Decref`，而真实 `Tree.__iter__` 当前的连续 run 只有：
   - `[1, 1, 2, 1, 1, 3, 1]`
   所以 `BatchDecref = 0` 不是漏优化，而是现有阈值压根没命中。

## 对照实验：哪些方向还有价值

为了避免继续在“看起来合理但其实没收益”的方向上绕圈，我做了 3 组上界对照实验。

### 1. truthiness 专项：`if self.left` -> `if self.left is not None`

这是当前最有希望的一条线。

| 形状 | compiled_size | `IsTruthy` | `Decref` | median wall time (s) | 相对原始 truthy speedup |
|---|---:|---:|---:|---:|---:|
| 原始 `if self.left` | 2736 | 2 | 10 | 0.06177658 | 1.0000x |
| `if self.left is not None` | 2616 | 0 | 8 | 0.06129371 | 1.0079x |

结论：

- 去掉两处 `IsTruthy` 后，代码体积下降了 `120` 字节
- `Decref` 也从 `10` 降到 `8`
- 本地 macOS Arm 上有小幅正向信号，约 `+0.79%`

这说明：

**当前 `generators` 剩余最像真优化方向的，是把 `Tree | None` 这类 truthiness 收窄成 `is not None` 检查。**

进一步对 `if self.left is not None` 的 Optimized HIR 做对照后，目标形状已经很具体了：

- 当前 `if self.left` 会生成：
  - `CheckField<"left">`
  - `IsTruthy`
  - `Decref`
  - `CondBranch`
- 而 `if self.left is not None` 会直接生成：
  - `CheckField<"left">`
  - `LoadConst<ImmortalNoneType>`
  - `PrimitiveCompare<Equal>`
  - `CondBranch`

也就是说，这条优化如果真的要做，实现目标并不是“泛泛优化 generator”，而是：

**让当前 `POP_JUMP_IF_FALSE` / `IsTruthy` 路径，在特定 object-or-`None` 形状上直接逼近 `is not None` 的 HIR。**

### 2. `yield from` 上界：改写成显式 `for x in child: yield x`

这个方向从“代码更小”角度看很诱人，但实际速度并不好。

| 形状 | compiled_size | `YieldFrom` | `YieldValue` | `Decref` | median wall time (s) | 相对 `is not None + yield from` speedup |
|---|---:|---:|---:|---:|---:|---:|
| `is not None + yield from` | 2616 | 2 | 1 | 8 | 0.06121142 | 1.0000x |
| `is not None + for/yield` | 2424 | 0 | 3 | 6 | 0.06458283 | 0.9478x |

结论：

- 显式 `for/yield` 确实让代码更小
- 但 wall time 明显更差，约 `-5.2%`

这说明：

**不能简单地把问题归因成“`yield from` lowering 太重”。至少在这个 benchmark 形状上，`yield from` 仍然是更好的执行路径。**

### 3. 字段复用上界：先存局部变量再 `yield from`

这个方向也很像“应该更快”，但实验结果同样是否定的。

| 形状 | compiled_size | `LoadField` | `CheckField` | `Decref` | median wall time (s) | 相对 `is not None` speedup |
|---|---:|---:|---:|---:|---:|---:|
| `if self.left is not None` | 2616 | 20 | 5 | 8 | 0.06074904 | 1.0000x |
| `left = self.left; if left is not None` | 2560 | 12 | 3 | 4 | 0.06330246 | 0.9597x |

结论：

- 把 `left/right` 落到局部变量后，HIR 指标确实更漂亮
- `LoadField`/`CheckField`/`Decref` 都降了
- 但 wall time 反而更差，约 `-4.0%`

这说明：

**“减少字段读取和 decref 次数”本身并不足以让 `generators` 更快。**

## 当前可以排除的方向

基于上面的真实 benchmark 和上界实验，当前可以先排除：

1. **`Tree.__iter__` 没被编译**
   这是 driver 统计口径问题，不是 coverage 问题。
2. **`BatchDecref` 没命中是主因**
   当前最长 run 只有 3，不会触发现有阈值。
3. **只要把 `yield from` 改成更简单的 lowering 就会更快**
   对照实验表明代码变小不等于更快。
4. **只要减少字段读取和 decref 就会更快**
   `local reuse` 对照实验已经把这条直觉证伪了。

## 下一步建议

优先按下面顺序查：

1. 记住 `bench_pyperf_direct.py` 对 generator 的 compiled 统计口径偏差
2. 把 generator 方向收敛到 **truthiness specialization**
3. 如果要做代码实验，优先考虑：
   - 在 [builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp) 的 `emitPopJumpIf()` / `emitJumpIf()` 周边，识别 `CheckField` 后立即进入 truthiness 分支的形状
   - 或者在 [simplify.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/simplify.cpp) 的 `simplifyIsTruthy()` 上，增加 object-or-`None` 的窄化规则
   - 目标是把它降成 `is not None` 风格的 `PrimitiveCompare<Equal/NotEqual> + CondBranch`
4. 不要优先继续做：
   - `yield from` 改写
   - `local reuse` 风格的字段缓存
   - 泛化的 `BatchDecref` 阈值修改

## 当前结论

`generators` 这项现在已经有了更准确的结论：

- `Tree.__iter__` 其实已经被编译
- 当前 `compiled_count=3` 主要是 driver 统计口径问题
- `bb_count` 没有爆炸，当前 `compiled_size=2736` 更像代码体积问题
- `yield from` 和字段复用这两条直觉方向，都没有在上界实验里带来正收益
- benchmark 下一阶段唯一还明显值得继续深挖的是：

**`Tree.__iter__` 里的 truthiness (`if self.left` / `if self.right`) 是否可以在 JIT 里专门收窄成 `is not None` 风格分支。**
