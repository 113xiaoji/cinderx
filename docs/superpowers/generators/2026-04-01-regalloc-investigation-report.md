# 寄存器分配器调查报告：LoadPoppedPhase 原生 LIR 失败分析与修复

> 日期: 2026-04-01
> 状态: **已修复** — `cinderx/Jit/lir/postalloc.cpp` 中 optimizeMoveSequence fold 优化错误删除了 kCall 返回值 Move
>
> **注意**: 此报告记录了 postalloc fold 问题的调试过程和根因分析。修复包含三部分：
> 1. 中间寄存器使用检查（防止 fold 删除仍在使用的 Move）
> 2. MemoryIndirect 操作数中的 base/index 寄存器检查（防止遗漏间接内存操作数中的使用）
> 3. SaveCurrentNode 屏障（其 codegen 可能调用 `_Py_Dealloc`，clobber caller-save 寄存器）

## 1. 摘要

TreeIterStateMachinePass 的 8 个运行时操作中，6 个已成功转换为原生 LIR 指令（Plan B 内联 codegen），但 `LoadPoppedPhase` 和 `LoadStackTop` 原生 LIR 失败。

**根因**: `optimizeMoveSequence` 的 fold 优化将 `Move X19, X0`（kCall 返回值保存）和 `Move X0, X19`（Decref 参数设置）折叠，错误删除了 `Move X19, X0`。该优化向后扫描时遇到 Call 指令才停止，但原生 LIR 不是 Call，扫描穿过了 `LoadPoppedPhase` 和 `SaveCurrentNode`，导致 fold 范围错误跨越。

## 2. 调试过程

### 2.1 系统性排除

| 实验 | 结果 |
|------|------|
| LoadPoppedPhase 原生 LIR | **失败** |
| LoadStackTop 原生 LIR | 通过 |
| LoadPoppedPhase 用 kLoadPhase opcode | 失败 |
| LoadPoppedPhase 读取 current_phase 偏移 | 失败 |
| LoadPoppedPhase hasArbitraryExecution=true | 失败 |
| translateLoadPoppedPhase 内部用 `blr` 调 C 函数 | **通过** |

排除了: opcode、偏移量、hasArbitraryExecution、translate 函数逻辑、FP 完整性。

### 2.2 LIR Dump 对比（关键突破）

使用 `PYTHONJITDUMPLIR=1` 导出两个版本，对比 `after postalloc rewrites` 的 bb_pop：

**基线（kCall both）**:
```
Call (StateStackPop)            ← kCall, output removed
Move X19, X0                    ← 返回值保存
Call (LoadPoppedPhase)          ← kCall, output removed
Move W20, W0                    ← 返回值保存
SaveCurrentNode X19
Move X0, X19                    ← Decref 参数
Call (Decref)
```

**原生 LoadPoppedPhase**:
```
Call (StateStackPop)              ← kCall, output removed
                                   ← ❌ Move X19, X0 被删除！
LoadPoppedPhase W20               ← 原生 LIR
SaveCurrentNode X19               ← 读取 stale X19！
                                   ← ❌ Move X0, X19 也被删除
Call (Decref)                      ← 参数错误
```

### 2.3 fprintf 调试验证

在 `postalloc.cpp` 添加 fprintf 独立确认：
1. `rewriteCallInstrs` **正确插入** `Move X19, X0`
2. `optimizeMoveSequence` **错误删除** 该 Move（`isLastUse()` 为 true，但 X19 在中间被 SaveCurrentNode 使用）
3. `optimizeMoveInstrs` 删除产生的 `Move X0, X0`

## 3. 根因分析

**文件**: `cinderx/Jit/lir/postalloc.cpp:1050-1107`

`optimizeMoveSequence` 的 fold 优化逻辑：
- 向后扫描查找 `Move tmp, <retreg>` → `Move <argreg>, tmp` 模式
- 仅在遇到 `isCall()` 时停止扫描（line 1065）
- 不检查非 Call 指令是否读取了中间寄存器

当 `LoadPoppedPhase` 从 kCall 变为原生 LIR：
- 扫描从 Decref 的 `Move X0, X19` 向后
- 跳过 `SaveCurrentNode X19`（非 Call）→ 跳过 `LoadPoppedPhase W20`（非 Call）
- 找到 `Move X19, X0` → fold 并删除

**缺失的检查**: fold 范围内中间寄存器被其他指令读取时，不应删除定义该寄存器的 Move。

## 4. 修复

在 `optimizeMoveSequence` 的 `found_chain` 分支中，删除 chain_iter 前检查中间使用：

```cpp
if (found_chain) {
    PhyLocation intermediate_reg = in->getPhyRegister();
    // ... fold 改写 ...

    // 检查中间寄存器是否在 fold 范围内被其他指令读取
    bool intermediate_used = false;
    auto check_iter = chain_iter;
    ++check_iter;
    for (; check_iter != instr_iter; ++check_iter) {
        auto check_instr = check_iter->get();
        for (size_t ci = 0; ci < check_instr->getNumInputs(); ci++) {
            auto check_in = check_instr->getInput(ci);
            if (check_in->isReg() && check_in->getPhyRegister() == intermediate_reg) {
                intermediate_used = true;
                break;
            }
        }
        if (intermediate_used) break;
    }

    if (opnd->isLastUse() && !intermediate_used) {
        basicblock->instructions().erase(chain_iter);
    }
}
```

## 5. 修复后状态

所有 8 个操作均已转为原生 LIR（Plan B 内联 codegen），含 SaveCurrentNode/StateStackPush/Pop。

**正确性**: `test_phase3_state_machine.py` 9/9 通过（depth 1-12），但需注意：
- 测试通过 `jit.auto()` 触发（阈值 1000 次调用后才编译），需足够迭代次数
- `PYTHONJITALL=1` 模式在 cleanup 阶段有独立于原生 codegen 的 Segfault（kCall 基线也有此问题）
- 缺少显式启用 `PYTHONJITTREEITERSTATEMACHINE=1` 的 checked-in 回归测试覆盖原生路径

**性能** (native Push/Pop codegen vs 原始 yield-from):
| depth | nodes | OFF (µs) | ON (µs) | 加速比 |
|-------|-------|----------|---------|--------|
| 8     | 255   | 65.71    | 8.58    | 7.7x   |
| 10    | 1023  | 296.73   | 33.73   | 8.8x   |
| 12    | 4095  | 2023.12  | 135.25  | **15.0x** |

## 6. 教训

1. **JIT postalloc 优化对原生 LIR 指令不可见**: `optimizeMoveSequence` 的 fold 仅在 Call 边界停止。新增非 Call 原生指令时，fold 可能跨越不该跨越的指令。修复: 将 `SaveCurrentNode` 加入 fold 屏障（其 codegen 可调用 `_Py_Dealloc`）。
2. **LIR dump 是调试 postalloc 问题的利器**: 对比 `after register allocation` 和 `after postalloc rewrites` 版本，直接看出哪个 Move 被插入或删除。
3. **`isLastUse()` 不够**: 仅检查指令之后的引用，不检查 fold 范围内的引用。新增原生 LIR 时必须额外验证中间使用。
4. **MemoryIndirect 操作数中的寄存器需单独扫描**: `getNumInputs()` 只返回显式输入操作数，不包含 MemoryIndirect 的 base/index 寄存器。中间使用检查必须同时遍历这两种。
5. **测试脚本必须显式启用优化路径**: 调试用脚本仅调用 `jit.auto()` 而未设 `PYTHONJITTREEITERSTATEMACHINE=1`，实际未触发状态机 pass。"通过"不等于"覆盖了目标路径"。
