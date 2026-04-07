# ERRORS

## 2026-04-07

- 错把 `HEAD^` 整包当成可直接在当前远端工作树增量构建的对照，导致和远端 stale headers / build cache 混出无意义的编译错误。
  - 修正：
    - 先整包同步 `HEAD`
    - 再做单文件或 clean rebuild A/B
- 仅根据一次 direct A/B 就判断 `comprehensions` 回退，后来被更厚样本推翻。
  - 修正：
    - 对非显著信号做更多 sample
    - 同时看 `osr_count` / `compiled_functions`
