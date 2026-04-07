# Plan

## Goal

在不破坏 `#76` Phase 1 正向收益 case 的前提下，收敛 object-heavy / search-heavy workload 的 same-activation OSR 回退。

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

### Stage 3: Candidate policy

- 提出 2-3 个 profitability policy 方向
- 比较 tradeoff
- 选一个最窄的先试

### Stage 4: TDD + implementation

- 先写失败测试
- 再做最小实现
- 统一走远端验证入口

### Stage 5: Closeout

- 更新 findings / learnings / mistake ledger
- 更新 issue / PR 文档
