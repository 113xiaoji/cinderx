# ERRORS

## 2026-04-11 Day 1 sprint

- Initially assumed `run_pyperf_subset.sh` was failing to execute, but the real
  bug was subtler: pyperformance raw JSON was present, and the summary code was
  silently dropping rows because it expected `metadata.name` that was not there.
- Initially assumed remote summary code could read `git_commit` from
  `/root/work/cinderx-main`, but that workdir is rsynced from a tarball and has
  no `.git` directory.

## 2026-04-11 Day 2 sprint

- The first `SKIP_PYPERF=1` fast-path patch incorrectly called `deactivate`
  after the helper had already left the driver venv, causing
  `deactivate: command not found`.
- The first attr-heavy gate threshold was set too high (`attr_ops >= 5`) and
  missed the object-stateful synthetic shape, which only had `attr_count = 4`.
- One attempted baseline direct comparison was invalidated because the remote
  worktree still contained current attr-gate code after a supposed baseline
  deploy. Remote source state must be verified before trusting a baseline run.
- One helper-side test attempt used `unittest discover` with a non-importable
  start directory, which obscured that the runtime itself was already fine.
- A compile probe helper initially forgot to substitute the benchmark name
  placeholder, which produced a fake file-not-found debugging branch.
- The first 5-repeat direct compare was over-interpreted before a thicker
  sample was run on the residual regressions.
- The initial broad-pass assumption that all remaining negatives might just be
  warmup noise was too optimistic; a 15-repeat pass showed several real median
  regressions remain.
- A failed remote helper retry can look like a broken test even when the first
  helper invocation already completed the deploy; always inspect the marker/log
  before assuming the latest deploy did not land.
- I initially treated the old `/root/work/incoming/remote_update_build_test.sh`
  as interchangeable with the updated workdir helper. That reused an outdated
  script and sent the run into a pyperformance setup crash that was unrelated to
  the candidate runtime change.
- I also tried to interpret `bm_go` benchmark behavior before separating
  \"fresh driver venv\" issues from \"real runtime path\" issues. The right
  order is: fresh venv first, then semantic A/B, then benchmark claims.

## 2026-04-07

- 错把 `HEAD^` 整包当成可直接在当前远端工作树增量构建的对照，导致和远端 stale headers / build cache 混出无意义的编译错误。
  - 修正：
    - 先整包同步 `HEAD`
    - 再做单文件或 clean rebuild A/B
- 仅根据一次 direct A/B 就判断 `comprehensions` 回退，后来被更厚样本推翻。
  - 修正：
    - 对非显著信号做更多 sample
    - 同时看 `osr_count` / `compiled_functions`
