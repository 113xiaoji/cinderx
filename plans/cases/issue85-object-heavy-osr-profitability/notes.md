# Notes

## 2026-04-07 kickoff

- 当前已知 object-heavy / search-heavy 代表 case：
  - `bm_go`
  - `bm_chaos`
- 当前已知非主问题但容易混淆的 case：
  - `barnes_hut`
  - `scimark_lu`
- 当前已知已被证明不是 blocker 的 case：
  - `comprehensions`

## Immediate next checks

- 重新确认 `#85` 对应 GitHub issue 是否已经存在
- 补一版 `#85` 的 shape taxonomy
- 明确下一轮最小实现应该落在：
  - `pyjit.cpp`
  - 还是 `builder.cpp`

## 2026-04-07 selected direction

- 当前选定先走：
  - `pyjit.cpp` same-activation hot-loop OSR 入口 profitability gate
- 暂不优先：
  - `builder.cpp` 的大范围 specialization / shape score 改写
- 进入实现前还需要：
  - 找到一个比 `bm_go` 更小、更适合落在 `test_arm_runtime.py` 的 object-heavy / search-heavy 红灯测试形状

## 2026-04-07 new finding

- 三个比 `bm_go` 更小的 object-heavy / search-like 探针形状，在 ARM 当前分支下都直接 `SIGSEGV`：
  - `attr_stateful`
  - `search_like`
  - `method_heavy_search`
- 这说明 `#85` 的第一阶段不能只盯性能回退，还需要先区分：
  - 是 profitability 问题
  - 还是同类 shape 还存在 correctness bug

## 2026-04-07 reproducer status after latest branch refresh

- `attr_stateful`
  - 当前最新安装态下：
    - `osr_count = 0`
    - `jit.is_jit_compiled(hot) = False`
    - `jit.is_jit_compiled(Cell.step) = False`
  - 结论：
    - 已不再是 `#85` 的当前红灯
    - 更适合作为回归守卫

- `search_like`
  - 当前最新安装态下：
    - `osr_count = 0`
    - `jit.is_jit_compiled(hot) = False`
  - 结论：
    - 也已不再是 `#85` 的当前红灯
    - 更适合作为回归守卫

- 当前判断：
  - `#85` 原始“same-activation OSR 误入 object-heavy/search-heavy shape”这层，在最新分支上暂时没有 clean 的当前 reproducer
  - 后续如果继续推进，更像是在做一般性的 profitability / shape policy，而不是修一个当前稳定可复现的 blocker

## Immediate next checks

- 对最小 probe 做 JIT on/off 对照
- 确认崩溃是否只在 same-activation OSR 命中后出现
- 再决定第一条正式红灯测试应该写“skip OSR”还是“no-crash”
