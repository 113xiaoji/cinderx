# Plan

## Goal

在不破坏 `#76` Phase 1 正向收益 case 的前提下，把 object-heavy / search-heavy workload 的问题重新定义成稳定的 profitability / shape policy 任务，而不是没有当前红灯时继续盲改运行时代码。

## Stages

### Stage 1: Shape taxonomy

- 识别并分类：
  - wrapper pollution
  - object-heavy / search-heavy
  - helper-fragmented but non-OSR-related
- 输出：
  - 每类的代表 case
  - 每类的关键 shape 特征

### Stage 2: Runtime evidence

- 用统一远端入口验证：
  - `go`
  - `chaos`
  - 其他代表性 case
- 同时记录：
  - `osr_count`
  - `is_jit_compiled`
  - `get_compiled_functions`
  - timing
- 当前结论：
  - 最新分支上已经没有 clean 的 current same-activation reproducer
  - 这一阶段后续主要用于发现新的 shape，而不是继续复测已收住的旧 shape

### Stage 3: Candidate policy

- 提出 2-3 个 profitability policy 方向
- 比较 tradeoff
- 选一个最窄的先试

### Stage 4: TDD + implementation

- 只有在拿到新的 clean 红灯之后，才进入这一阶段
- 先写失败测试
- 再做最小实现
- 统一走远端验证入口

### Stage 5: Closeout

- 更新 findings / learnings / mistake ledger
- 更新 issue / PR 文档
