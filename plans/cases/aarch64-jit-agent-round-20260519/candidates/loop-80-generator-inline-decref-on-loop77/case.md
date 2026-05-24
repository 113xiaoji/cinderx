# Loop 80 - generator inline decref 通用化

## 候选简介

本候选把历史 Loop 80 的 AArch64 定制写法改成通用写法：删除
`MakeDecref()` 中对 generator/coroutine/async generator 的 helper 早退分支，让所有架构在
generator 上都复用已有的 inline decref lowering。

原始定制写法是：

```cpp
#if !defined(CINDER_AARCH64)
  if (func_->code->co_flags & kCoFlagsAnyGenerator) {
    auto helper = xdecref ? JITRT_XDecref : JITRT_Decref;
    bbb.appendInvokeInstruction(helper, instr);
    return;
  }
#endif
```

通用化后不再按架构特判，也不再对 generator 单独强制 helper call。`Decref` 和
`XDecref` 都继续走后面的统一 inline refcount 更新逻辑。

## 代码方案

修改文件：

- `cinderx/Jit/lir/generator.cpp`

修改点：

- 删除 `func_->code->co_flags & kCoFlagsAnyGenerator` 的 early return。
- 不新增 helper，不改变 `JITRT_Decref` / `JITRT_XDecref` 实现。
- 不引入 AArch64/x86 条件宏。

通用化后的路径：

1. `XDecref` 先保留 null check。
2. 读取对象 refcount。
3. 如果可能是 immortal object，保留现有 immortal 分支。
4. 执行 `Dec` 并写回 refcount。
5. refcount 非 0 时 `BranchNZ` 到结束块。
6. refcount 为 0 时进入 cold dealloc block，调用已知 destructor 或 `_Py_Dealloc`。

## 为什么更通用

这个修改不再把收益限定在 AArch64，也不再把 generator/coroutine/async generator
当作一个特殊 refcount 语义域。它的核心判断是：`func_->code->co_flags &
kCoFlagsAnyGenerator` 只能说明当前 code object 会以 generator/coroutine 形态执行，
不能说明某一个 `Decref` 站点必须走 runtime helper。

原始 generator 分支来自 `0f7bd9a1 Compact generator decref lowering`。从该提交的
测试和记录看，它的动机是控制 LIR/basic block/compiled size 膨胀，而不是修复 generator
专有语义问题。因此它本质上是一个代码体积 heuristic：

- generator workload 里 `Decref` 站点多；
- 每个 inline decref 都会展开成 load/refcount decrement/store/branch/dealloc block；
- 为了压低 block count 和 compiled size，当时把整个 generator 函数内的 decref 都降成 helper。

这个 heuristic 的问题是粒度太粗：

- 普通函数也可能有很多 decref 站点，同样存在代码体积压力。
- generator 函数中也可能只有少量 decref，或者某些 decref 是热点快路径，适合 inline。
- 该判断按“函数种类”切换，而不是按“当前 decref 站点的成本、频率和类型信息”切换。
- 它还把 x86/AArch64、普通对象/精确类型对象、`Decref`/`XDecref` 都混在同一个判断里。

`JITRT_Decref(obj)` 本质是 `Py_DECREF(obj)`，`JITRT_XDecref(obj)` 本质是
`Py_XDECREF(obj)`；已有 inline decref 路径已经负责处理 refcount 非 0 快路径和
refcount 为 0 的 dealloc 慢路径。因此从语义上看，generator 不是必须 helper 的边界。

因此通用化后的规则更简单：

| 场景 | 旧行为 | 新行为 |
|---|---|---|
| 普通函数 | inline decref | inline decref |
| generator/coroutine/async generator | helper call | inline decref |
| AArch64 | 定制启用 inline decref | 通用 inline decref |
| x86_64 | 保持 helper call | 通用 inline decref |

如果后续仍需要保留“代码体积不要过大”的保护，应单独做一个与 generator 无关的通用策略，
例如：

```cpp
bool LIRGenerator::shouldUseDecrefHelper(
    std::optional<destructor> destructor,
    bool xdecref,
    bool possible_immortal) const;
```

这个策略应该看的是通用成本信号，而不是 `co_flags`：

- 当前函数中 `Decref`/`XDecref` 站点数量；
- inline decref 预计新增的 LIR block 和 native code 体积；
- 当前站点是否需要 `XDecref` null check；
- 当前类型是否可能 immortal；
- 是否有精确 destructor，可否在 zero-ref 慢路径直接调用；
- 目标架构的 helper call 成本和代码体积权衡。

也就是说，代码体积策略可以存在，但应该叫“decref inline budget”或
“decref helper lowering policy”，而不是“generator 就 helper”。

## 已有 ARM 证据

历史 Loop 80 在 Loop 69/74/77 stack 上验证过 AArch64 定制版本。该版本在 ARM 上的代码效果
与当前通用版本一致，因为两者都会让 AArch64 generator 走 inline decref。

测试结果：

| 测试 | 结果 |
|---|---|
| focused S3 | 7 valid，geomean speedup `+1.810%`，无 `>=5%` 回退 |
| focused S12 | 7 valid，geomean speedup `+1.666%`，无 `>=5%` 回退 |
| full JIT28 S3 | 20 valid，geomean speedup `+0.337%`，`json_dumps +6.934% time` warning |
| targeted S12 repeat | geomean speedup `+0.521%`，无 `>=5%` 回退，`json_dumps` 变为 `+0.454%` speedup |
| full JIT28 S12 | 20 valid，geomean speedup `+0.475%`，无 `>=5%` 回退 |

full JIT28 S12 主要收益行：

| benchmark | speedup |
|---|---:|
| `coroutines` | `+4.646%` |
| `nqueens` | `+4.132%` |
| `generators` | `+2.197%` |
| `unpack_sequence` | `+1.707%` |
| `pickle_dict` | `+1.199%` |

## 需要补的验证

通用化后会改变 x86_64 generator decref lowering，因此不能只沿用 AArch64-only 的合入结论。
本轮已经在 x86_64 环境补了 gate：

| 验证项 | 环境 | 命令/口径 | 结果 |
|---|---|---|---|
| baseline build + smoke | `106.14.164.133` x86_64 | `remote_update_build_test_x86.sh`，`SKIP_PYPERF=1` | 通过，JIT worker startup OK，`smoke-ok` |
| candidate build + smoke | `106.14.164.133` x86_64 | 同上，候选为删除 generator helper early return | 通过，JIT worker startup OK，`smoke-ok` |
| x86 LIR 命中证据 | `106.14.164.133` x86_64 | `Tree.__iter__` + `PYTHONJITDUMPLIR=1` | baseline 为 helper call，candidate 展开 inline decref |
| x86 focused S3 | `106.14.164.133` x86_64 | `coroutines,generators,nqueens,unpack_sequence,pickle_dict`，`SAMPLES=3` | 无 `>=5%` 回退，geomean speedup `+5.186%` |
| x86 focused S12 | `106.14.164.133` x86_64 | 同一组 benchmark，`SAMPLES=12` | 无 `>=5%` 回退，geomean speedup `+0.416%` |

x86 LIR 证据：

| 版本 | compiled size | BB 数 | `# Decref` 标记 | `Dec` 指令数 | 说明 |
|---|---:|---:|---:|---:|---|
| baseline | `1840` | `176` | `32` | `0` | generator decref 走 helper call |
| candidate | `2024` | `268` | `96` | `32` | generator decref 展开 inline 快路径 |

这说明通用化确实改变了 x86 lowering：它不是“空改”。不过 x86 S12 的整体收益只有
`+0.416%`，且 `generators`/`nqueens` 小幅变慢，不能把它当成 x86 明确收益方案。
它的价值仍主要来自 AArch64；x86 gate 的结论是“语义 smoke 通过、无明显性能回退”。

x86 focused S12 明细：

| benchmark | baseline median | candidate median | time delta | speedup |
|---|---:|---:|---:|---:|
| `coroutines` | `49.823 ms` | `49.026 ms` | `-1.598%` | `+1.624%` |
| `generators` | `109.292 ms` | `109.579 ms` | `+0.263%` | `-0.262%` |
| `nqueens` | `207.974 ms` | `211.560 ms` | `+1.724%` | `-1.695%` |
| `pickle_dict` | `40.684 us` | `41.555 us` | `+2.140%` | `-2.096%` |
| `unpack_sequence` | `142.830 ns` | `136.469 ns` | `-4.454%` | `+4.661%` |

x86 focused S3 明细：

| benchmark | baseline median | candidate median | time delta | speedup |
|---|---:|---:|---:|---:|
| `coroutines` | `49.874 ms` | `48.289 ms` | `-3.176%` | `+3.280%` |
| `generators` | `108.001 ms` | `108.491 ms` | `+0.454%` | `-0.452%` |
| `nqueens` | `207.907 ms` | `210.655 ms` | `+1.322%` | `-1.305%` |
| `pickle_dict` | `46.194 us` | `41.334 us` | `-10.521%` | `+11.758%` |
| `unpack_sequence` | `148.476 ns` | `130.762 ns` | `-11.930%` | `+13.547%` |

测试产物：

- x86 baseline build/smoke log：`/root/work/arm-sync/loop80-x86-generic-20260524/base_build_smoke.log`
- x86 candidate build/smoke log：`/root/work/arm-sync/loop80-x86-generic-20260524/cand_build_smoke.log`
- x86 LIR logs：`/root/work/arm-sync/loop80-x86-generic-20260524/base_tree_iter_lir.log`，`cand_tree_iter_lir.log`
- x86 S3 compare：`/root/work/arm-sync/loop80-x86-generic-20260524/compare_focus_s3.json`
- x86 S12 compare：`/root/work/arm-sync/loop80-x86-generic-20260524/compare_focus_s12.json`

## 当前决策

状态：`accepted`

代码已经改成本地通用候选，x86 gate 已补齐。合入判断：

- ARM/AArch64 是主收益来源：历史 Loop80 在 Loop69/74/77 stack 上 full JIT28 S12 geomean
  `+0.475%`，`coroutines`、`nqueens`、`generators` 等相关项有明确收益。
- x86 不是明确收益来源：focused S12 geomean 只有 `+0.416%`，部分相关项小幅变慢。
- x86 安全性可接受：build/smoke 通过，focused S12 无 `>=5%` 回退。
- 通用性比 AArch64 定制宏更好：不再用 `co_flags` 把 generator/coroutine/async generator
  当成 refcount 语义边界；如果后续要控制代码体积，应另做通用 decref inline budget。

因此建议进入人工检视和合入准备。合入理由应写成“去掉不合理的 generator 级别 helper
heuristic，让 decref lowering 使用统一 inline 路径；ARM 收益明确，x86 gate 无明显回退”，
而不是宣传 x86 性能收益。

## 合入前代码检视结论

本轮按 Review Agent gate 复核后，结论是可以合入：

- 代码改动最小：只删除 `MakeDecref()` 里按 `kCoFlagsAnyGenerator` 强制走
  `JITRT_Decref` / `JITRT_XDecref` helper 的 early return。
- 方案足够通用：`co_flags` 只描述当前 code object 的执行形态，不能作为某个
  `Decref` 站点必须走 runtime helper 的语义边界。
- ARM 收益证据充分：已有 focused S3/S12、full JIT28 S3/S12 和 targeted S12
  repeat；full JIT28 S12 无 `>=5%` 回退，相关 workload 有明确收益。
- x86 gate 已补齐：x86 build/smoke 通过，LIR 证明 candidate 确实改变 lowering；
  focused S12 无 `>=5%` 回退，但收益不稳定，因此只作为安全性证据。
- 剩余风险可接受：该方案会增加 generator 场景的 inline decref 体积；如果后续发现
  代码体积压力，应另做与 generator 无关的通用 decref inline budget。

合入标签：`arm-benefit`、`x86-no-clear-benefit`、`x86-safety-passed`。
