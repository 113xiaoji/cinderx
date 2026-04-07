## 摘要

- 完成 CinderX 3.14 上 issue #76 的 Phase 1 热循环 OSR MVP
- 修复 same-activation OSR 的对象所有权和循环入口 local mapping，使 loop-header secondary entry 使用编译后 block 真正期望的 live-in 位置
- 补充最终状态、当前范围边界以及 benchmark harness 后续工作的文档说明

## 本次改动

### 核心 OSR / 运行时修复

- [generated_cases.c.h](C:/work/code/cinderx1/cinderx/cinderx/Interpreter/3.14/Includes/generated_cases.c.h)
  - 在 same-activation OSR 通过 interpreter 返回后，正确关闭 interpreter frame 中 `localsplus` 的引用
- [pyjit.cpp](C:/work/code/cinderx1/cinderx/cinderx/Jit/pyjit.cpp)
  - 让 synthetic OSR entry 和 same-activation OSR 都以一致方式把对象所有权移交给编译后代码
- [gen_asm.cpp](C:/work/code/cinderx1/cinderx/cinderx/Jit/codegen/gen_asm.cpp)
  - Phase 0/1 的 OSR local mapping 改为从真实 entry LIR 的 live-in 直接提取，而不是根据附近的 deopt point 做猜测
- [test_arm_runtime.py](C:/work/code/cinderx1/cinderx/cinderx/PythonLib/test_cinderx/test_arm_runtime.py)
  - 新增并调整 ARM runtime 回归测试，覆盖：
    - Phase 0 synthetic OSR 的 refcount 保持
    - Phase 1 same-activation hot-loop OSR entry
    - 当前分支保留的 runtime heuristic 预期

### Helper / 工具链

- [remote_update_build_test.sh](C:/work/code/cinderx1/cinderx/scripts/arm/remote_update_build_test.sh)
  - 让过滤后的 ARM unittest 父进程保持解释执行，避免不相关的父进程 auto-JIT 在退出时引发崩溃
- [sitecustomize.py](C:/work/code/cinderx1/cinderx/scripts/arm/pyperf_env_hook/sitecustomize.py)
  - 收窄 ARM pyperformance worker 的 JIT 启用范围
  - 在 worker 中优先使用原始 `cinderjit`
  - 支持 jitlist-only worker 模式
- [run_pyperf_subset.sh](C:/work/code/cinderx1/cinderx/scripts/arm/run_pyperf_subset.sh)
  - 让 subset runner 与 worker-only JIT 环境约定保持一致

### 设计 / 状态文档

- [final_status.md](C:/work/code/cinderx1/cinderx/plans/2026-03-31-issue76-hot-loop-osr/final_status.md)
  - 记录 issue #76 的原始诉求、当前已完成内容、仍然超出范围的部分，以及为什么最终修复是结构性的，而不是针对单个 benchmark 的特化

## 与原始设计的对应关系

issue #76 的原始设计建议是：

- 不引入 tracing JIT
- 继续以 whole-function compilation 作为编译单位
- 增加 loop-header secondary entry 支持
- 支持“函数只调用一次，但循环在同一次 activation 内变热”的场景
- 让 MVP 保持窄范围、以 object-only 为主

这次改动实现的正是这套设计。

最终落地的行为仍然是推荐的 Scheme B：

- whole-function compile
- loop-header secondary entry
- same-activation interpreter-to-JIT transfer
- 继续复用现有 downward deopt 路径

本次改动**没有**引入 tracing、side trace，也没有加入任何 benchmark-specific 特判。

## 为什么这是通用修复

这次修复的核心 bug 是结构性的：

- 旧的 fallback local mapping 路径可能描述的是错误的 predecessor state
- OSR entry 因而把 locals 恢复到了与真实 compiled entry block live-ins 不匹配的物理位置

修复本身也是结构性的：

- local mapping 直接从实际 entry LIR 的 live-reg 输入中提取
- OSR entry value 的所有权转移在 runtime contract 层面被统一修正

因此，这不是仅针对 `fannkuch` 或 `v5` 的优化。这些 case 只是最容易复现问题的形状。

## 验证情况

本分支上的 ARM 新鲜验证包括：

- 过滤后的 ARM runtime runner：
  - `Ran 86 tests in 60.736s`
  - `OK`
- 标准 ARM helper：
  - 在 `SKIP_PYPERF=1` 下可以端到端通过
- 定向探针：
  - synthetic OSR probe `10/10` 成功退出
  - same-activation `v5` probe `10/10` 成功退出

## 仍未覆盖的部分

这个 PR **不**声称已经完成 Phase 2 及之后的工作。当前仍然超出范围的包括：

- generators / coroutines / async generators
- active exception-region OSR
- 更一般化的 primitive live-in 支持
- inlined-frame OSR
- 对所有 benchmark 配置都稳定可复现的 pyperformance before/after harness

## Benchmark 说明

当前分支上的 truthful JIT worker 已经可以跑通这次要求的 benchmark 集合，但旧 baseline 分支在同样的 truthful worker 配置下仍然会崩溃。因此，这个分支中的 benchmark harness 改动更适合作为后续测量工具，而不应作为 issue #76 “已经完成”的定义本身。

Refs #76
