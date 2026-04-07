# Issue 76 当前完成度 Checklist

## 结论

`#76` 的 **Phase 1 MVP 主线已经完成**，当前已经具备评审/合入条件。  
还没有做完的部分，主要集中在：

- Phase 1 profitability 的后续收敛
- 已拆分出去的 object-heavy / search-heavy follow-up
- Phase 2 及之后的能力范围
- benchmark / harness 的长期稳定化

## 已完成

- [x] Phase 0 synthetic OSR entry 原型
- [x] Phase 1 same-activation hot-loop OSR 主 happy path
- [x] `JUMP_BACKWARD_JIT` 驱动同 activation 内的 loop-hot OSR
- [x] OSR runtime stats 采集与远端 probe 验证
- [x] Phase 0 / Phase 1 local mapping 的结构性修复
- [x] OSR ownership / refcount contract 修复
- [x] unsupported shape 的第一层保守 guard
- [x] ad-hoc ARM unittest runner exit crash 的父进程侧保护
- [x] `cinderx.jit` wrapper 对 partial `cinderjit` API 的兼容
- [x] 高调用密度 wrapper 误进 same-activation OSR 的第一轮止血

## 已完成但仍有后续优化空间

- [x] wrapper-shape profitability gate 已经落地
  - 当前相关提交：
    - `ccfe9126` `jit: skip same-activation osr for high-call wrappers`
    - `d3b45b32` `jit: localize wrapper osr gate to loop bodies`
    - `fb105b6b` `jit: lower wrapper osr call threshold`
- [x] 当前 gate 已经验证能拦住 `go` 一类误进 OSR 的 wrapper
- [x] 当前 gate 没有再明显伤到 `fannkuch`
- [ ] profitability 规则仍然是启发式，不是最终形态
- [ ] 还没有演化成更完整的 shape score / policy

## 已拆分到 Follow-up 的

- [ ] `#85` object-heavy / search-heavy workloads
  - 这类问题已经分析清楚，但还没有真正修复
  - 典型特征：
    - 大量对象状态更新
    - 大量属性访问和方法调用
    - 状态图遍历 / 搜索 / Monte Carlo tree search
    - 几何对象运算
    - 不是“单个稳定热循环主导”的函数
  - 这部分不再建议继续作为 `#76` 主线 blocker

## 仍未完成的 Phase 2+ 范围

- [ ] generators / coroutines / async generators
- [ ] active exception-region OSR
- [ ] inlined-frame OSR
- [ ] generalized primitive live-ins
- [ ] richer operand-stack reconstruction

## 验证层面仍不完美的地方

- [ ] pyperformance 端到端 harness 还不够稳定
- [ ] truthful baseline 对照还没有完全统一成一套长期稳定报告
- [ ] ARM 远端环境偶尔会有 SSH / build / worker 波动

## 当前最合理的判断

- 如果问题是“`#76` 的 Phase 1 MVP 是否成立”：**成立**
- 如果问题是“hot-loop OSR 是否已经彻底做完”：**没有**
- 当前最大未完成块：**`#85`**
- 第二大未完成块：**benchmark / harness 稳定化**
- 再往后才是 **Phase 2 能力扩展**

## 建议的合入边界

- `#76`：
  - 作为 Phase 1 MVP 合入
- `#85`：
  - 作为 object-heavy / search-heavy profitability follow-up 单独跟进
- benchmark/tooling：
  - 继续作为独立后续，不建议再阻塞 `#76`
