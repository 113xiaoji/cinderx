# AArch64 LIR/CODEGEN 优化合入记录

日期：2026-05-11

分支：`cinderx-6b47ba85b309507`

提交：

- `7614afd2 perf(jit): tighten aarch64 guard branches`

## 结论

本次合入只包含 LIR 和 CODEGEN 两个阶段的 AArch64 亲和优化，最终远端合入面为
6 个源码文件，未带入前序试验分支中的旧提交、回滚提交、临时脚本或过程文档。

全量 JIT28 复测没有达到原始停止门槛：

- 未出现单个用例 30% 以上提升。
- 全量 JIT28 stacked geomean 为 `+2.65%`，未达到整体 10%。

但两个优化已经在多个大颗粒 benchmark 上复现 5% 以上收益，且代码层证据显示收益
来自 LIR/CODEGEN 形态变化，而不是测试方法变化：

- guard-near 优化是主收益来源。
- cbz/cbnz register branch 优化是小收益补充。
- `unpack_sequence` 虽多次显示 5% 以上提升，但属于纳秒级 benchmark，且在
  guard-only 重点复跑中没有复现，记录为不稳定信号，不作为主收益结论。

## 合入范围

最终提交只修改以下 6 个文件：

- `cinderx/Jit/codegen/autogen.cpp`
- `cinderx/Jit/codegen/environ.h`
- `cinderx/Jit/codegen/gen_asm.cpp`
- `cinderx/Jit/codegen/gen_asm.h`
- `cinderx/Jit/lir/postalloc.cpp`
- `cinderx/Jit/lir/verify.cpp`

最终 diff 规模：

```text
6 files changed, 128 insertions(+), 52 deletions(-)
```

## 优化内容

### guard-near deopt branch

AArch64 条件分支、`cbz` 和 `cbnz` 的直接编码距离较短。原先 guard failure 路径
通过反向条件分支跳过一个远跳转 stub，热路径需要执行一个 taken branch。新实现把
guard failure 边落到当前 LIR basic block 后的 near-deopt stub，再由该 stub 跳到
冷 deopt exit。

收益机制：

- 热路径的 guard 条件分支通常为 not-taken，更贴近 AArch64 分支预测。
- guard failure 的短条件分支目标靠近当前 basic block，降低 code section 距离风险。
- fallthrough successor 在同 section 时，会先发一个 `b continuation` 跳过 block-local
  deopt stubs，保持原控制流。

### CondBranch to cbz/cbnz

postalloc 阶段对 AArch64 的 32-bit、64-bit、object register 条件分支保留寄存器
输入，让 CODEGEN 直接生成 `cbz`/`cbnz`。非 AArch64 或无法编码的类型仍保留
`Test + BranchCC` 形态。

验证器已收紧：

- 两输入 `BranchZ`/`BranchNZ` 仅允许 AArch64。
- 第一个输入必须是 register。
- 类型必须是 `k32bit`、`k64bit` 或 `kObject`。
- label 仍必须是最后一个输入。

## 环境

远端机器：

- host: `root@124.70.162.35`
- arch: AArch64
- Python: `3.14.3`
- pyperformance: `1.14.0`
- pyperf: `2.10.0`
- GCC: `gcc (GCC) 14.2.0`
- G++: `g++ (GCC) 14.2.0`

构建方式：

- GCC 14.2.0
- PGO off
- LTO on
- wheel 产物用于 pyperformance worker venv 安装

构建产物：

```text
cbzonly:
  /root/work/cinderx-cbzonly-nopgo-gcc14-20260510/dist/cinderx-2026.5.10.0-cp314-cp314-linux_aarch64.whl
  size=36632301
  sha256=01a90d4580b64e96873b9fb7ae4b56a208737ff82e3ed85c4ddb3fabae2cc523

guardonly:
  /root/work/cinderx-guardonly-nopgo-gcc14-20260510/dist/cinderx-2026.5.10.0-cp314-cp314-linux_aarch64.whl
  size=36664427
  sha256=17682fe3a22b840d6284635276f0aff32d788722de702733675a30f7508295e6

stacked:
  /root/work/cinderx-guardnear-nopgo-gcc14-20260510/dist/cinderx-2026.5.10.0-cp314-cp314-linux_aarch64.whl
  size=36667384
  sha256=5082403f6c61ded4cfb69c7468d796860595c89e4a5a172699fa2986937092ba
```

构建日志：

- `/root/work/arm-sync/build_cbzonly_merge_nopgo_lto_gcc14_20260510.log`
- `/root/work/arm-sync/build_guardonly_merge_nopgo_lto_gcc14_20260510.log`
- `/root/work/arm-sync/build_stacked_merge_nopgo_lto_gcc14_20260510.log`

## 测试方法

正式性能测试使用仓库文档要求的 runner：

- `/root/work/arm-sync/run_pyperf_subset_mdjit.sh`

关键环境：

```text
PYTHONJITAUTO=2
PYTHONJITLISTFILE=<workdir>/.pyperformance-cinderx/jit_list.txt
PYTHONJITTYPEANNOTATIONGUARDS=1
PYTHONJITENABLEJITLISTWILDCARDS=1
PYTHONJITENABLEHIRINLINER=1
PYTHONJITSPECIALIZEDOPCODES=1
CINDERX_ENABLE_SPECIALIZED_OPCODES=1
```

JIT28 名称映射：

pyperformance 1.14.0 不接受旧拆分名 `logging_format`、`logging_silent`、
`logging_simple`、`scimark_fft`、`scimark_lu`、`scimark_monte_carlo`、
`scimark_sor`、`scimark_sparse_mat_mult` 作为 `-b` 过滤名。实际命令使用
`logging` 和 `scimark` 聚合名，由对应 benchmark 在 JSON 中展开为 3 个 logging
row 和 5 个 scimark row，最终脚本强制校验每个结果 JSON 正好包含 28 rows。

## 功能正确性

验证命令安装 stacked wheel 后运行 AArch64 runtime smoke：

```text
PYTHONPATH="$WORK/cinderx/PythonLib" "$PY" -m unittest -v \
  test_cinderx.test_arm_runtime.ArmRuntimeTests.test_jit_force_compile_smoke \
  test_cinderx.test_arm_runtime.ArmRuntimeTests.test_multiple_code_sections_force_compile_smoke \
  test_cinderx.test_arm_runtime.ArmRuntimeTests.test_multiple_code_sections_large_distance_force_compile_smoke \
  test_cinderx.test_arm_runtime.ArmRuntimeTests.test_autojit0_lightweight_frame_typing_import_smoke
```

结果：

```text
Ran 4 tests in 1.661s
OK
```

日志：

- `/root/work/arm-sync/merge_min_correctness_stacked_20260510.log`
- `/root/work/arm-sync/merge_min_correctness_install_20260510.log`

## 全量 JIT28 结果

全量复测配置：

- samples: `3`
- warmups: `3`
- rows: `28`
- base: `/root/work/cinderx-mdbase-nopgo-gcc14-20260510`
- cbzonly: `/root/work/cinderx-cbzonly-nopgo-gcc14-20260510`
- guardonly: `/root/work/cinderx-guardonly-nopgo-gcc14-20260510`
- stacked: `/root/work/cinderx-guardnear-nopgo-gcc14-20260510`

结果文件：

- `/root/work/arm-sync/merge_min_jit28true_base_s3_20260510.json`
- `/root/work/arm-sync/merge_min_jit28true_cbzonly_s3_20260510.json`
- `/root/work/arm-sync/merge_min_jit28true_guardonly_s3_20260510.json`
- `/root/work/arm-sync/merge_min_jit28true_stacked_s3_20260510.json`
- `/root/work/arm-sync/merge_min_jit28true_compare_s3_20260510.txt`

### cbzonly vs base

```text
benchmarks=28 geomean=0.90%
unpack_sequence          +23.78%
scimark_sor               +8.87%
go                        +3.48%
richards                  +2.51%
comprehensions            +2.40%
```

主要回退：

```text
logging_silent            -6.40%
logging_format            -3.16%
logging_simple            -2.79%
nqueens                   -2.68%
coroutines                -1.62%
```

### guardonly vs base

```text
benchmarks=28 geomean=2.74%
unpack_sequence          +13.25%
scimark_sor              +10.26%
chaos                     +9.95%
coverage                  +8.84%
go                        +7.54%
scimark_monte_carlo       +7.15%
richards                  +6.02%
comprehensions            +5.10%
```

主要回退：

```text
logging_silent            -7.18%
logging_format            -2.58%
logging_simple            -2.21%
json_dumps                -1.10%
json_loads                -0.85%
```

### stacked vs base

```text
benchmarks=28 geomean=2.65%
unpack_sequence          +20.79%
chaos                     +9.31%
go                        +8.61%
scimark_sor               +8.33%
coverage                  +8.27%
float                     +5.79%
richards                  +5.40%
comprehensions            +5.16%
generators                +5.10%
```

主要回退：

```text
logging_silent            -6.67%
logging_simple            -2.42%
logging_format            -2.14%
scimark_sparse_mat_mult   -1.54%
coroutines                -0.92%
```

## 重点项复跑

重点复跑覆盖全量 JIT28 中超过 5% 或接近 5% 的大颗粒项和疑似项：

```text
chaos, coverage, go, richards, scimark, comprehensions, float, generators,
unpack_sequence
```

配置：

- samples: `3`
- warmups: `5`
- rows: `13`

结果文件：

- `/root/work/arm-sync/merge_min_toprepeat_base_s3w5_20260511.json`
- `/root/work/arm-sync/merge_min_toprepeat_cbzonly_s3w5_20260511.json`
- `/root/work/arm-sync/merge_min_toprepeat_guardonly_s3w5_20260511.json`
- `/root/work/arm-sync/merge_min_toprepeat_stacked_s3w5_20260511.json`
- `/root/work/arm-sync/merge_min_toprepeat_compare_s3w5_20260511.txt`

### cbzonly vs base

```text
benchmarks=13 geomean=2.67%
unpack_sequence          +16.20%
scimark_sor               +9.00%
go                        +2.44%
comprehensions            +2.31%
generators                +1.90%
richards                  +1.89%
chaos                     +1.77%
```

结论：

- `scimark_sor` 复现了稳定正向收益。
- `unpack_sequence` 继续正向，但为纳秒级 benchmark，不作为主收益结论。

### guardonly vs base

```text
benchmarks=13 geomean=4.76%
chaos                    +10.45%
coverage                  +9.02%
scimark_sor               +8.89%
go                        +7.20%
richards                  +5.98%
generators                +4.67%
float                     +4.42%
comprehensions            +4.34%
scimark_monte_carlo       +4.10%
```

结论：

- guard-near 是主收益来源。
- 大颗粒 benchmark 中 `chaos`、`coverage`、`scimark_sor`、`go`、`richards`
  均复现 5% 以上收益。
- `unpack_sequence` 在 guardonly 中为 `-2.88%`，说明该项不适合作为主结论。

### stacked vs base

```text
benchmarks=13 geomean=5.93%
unpack_sequence          +16.49%
chaos                     +9.39%
scimark_sor               +8.60%
coverage                  +8.48%
go                        +8.43%
float                     +5.97%
richards                  +5.53%
generators                +4.97%
comprehensions            +4.64%
```

结论：

- 叠加后重点子集继续保持正向。
- 主要收益仍来自 guard-near。
- cbz/cbnz 对 `scimark_sor` 和少量 register-test 热路径有补充收益。

## 代码层证据

LIR census 对比 `chaos`：

```text
base files=23
  Test*=35332
  BranchZ/NZ register-form=0
  BranchZ label-form=3485
  BranchNZ label-form=32375

guardnear files=23
  Test*=31328
  BranchZ/NZ register-form=4004
  BranchZ label-form=1540
  BranchNZ label-form=30316
```

说明：

- AArch64 register-form `BranchZ/NZ` 从 0 增加到 4004。
- `Test*` 数量减少 4004。
- 这对应 postalloc 保留 CondBranch register input，并由 CODEGEN 生成 `cbz/cbnz`。
- guard-near 的收益来自 guard failure target 近端化和热路径分支形态变化。

相关旧日志：

- `/root/work/arm-sync/mdjit_lirchaos_base_*.log`
- `/root/work/arm-sync/mdjit_lirchaos_guardnear_*.log`

## Code review 结果

子代理复核结论：

- 无合并前必须修的问题。
- 最小集 OK：只包含 6 个源码文件。
- `git diff --check` 通过。
- 原先行尾和格式噪声已清理。

已知残余风险：

- near-deopt stub 当前在每个 LIR basic block 后 flush。它解决了 hot section end
  远距离目标的主要风险。
- 理论上，如果单个超大 straight-line basic block 内某个 guard 到 block-end stub
  距离超过 AArch64 条件分支约 1MiB 编码范围，仍可能触发 relocation overflow。
- 现有 large-distance MCS smoke 已通过；该风险记录为边界残留，不阻塞本次合入。

## 远端状态

远端分支 `cinderx-6b47ba85b309507` 已更新到：

```text
7614afd254cdbcef4feb13c3a012fafc799aad31
```

本次记录提交前，代码优化提交已经推送到：

```text
git@github.com:113xiaoji/cinderx.git
branch: cinderx-6b47ba85b309507
```
