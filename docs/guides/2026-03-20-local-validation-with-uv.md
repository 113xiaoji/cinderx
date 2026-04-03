# CinderX 本地验证手册（uv 隔离环境）

## 1. 目的

这份文档用于帮助协作者在本地复现 CinderX 的源码验证流程，并避免不同项目之间的 Python / CinderX 安装互相污染。

本文档的目标是：

- 用项目自己的隔离环境进行本地验证
- 确保运行的是当前源码树编出来的 `cinderx`
- 稳定复现 benchmark、HIR opcode 统计和热点观察
- 提前规避本地最常见的环境问题

## 2. 结论先行

本仓库的本地验证，推荐统一使用以下口径：

- 使用 `uv` 管理项目虚拟环境
- 但虚拟环境底座使用本机可用的 `python3.14`
- 运行 benchmark 和测试时使用项目内 `.venv/bin/python`
- 给 `uv` 指定项目内 cache 目录
- 运行 JIT benchmark 时显式设置 `PYTHONJITHUGEPAGES=0`

不要直接使用系统全局 `python3` 或 Homebrew 全局 `python3` 运行本仓库测试。  
原因是这样很容易误用到别的项目安装过的 `cinderx`，从而拿到错误的 benchmark 和热点数据。

## 3. 适用范围

这套流程适用于：

- 本地 benchmark 回归
- HIR / opcode 统计抓取
- 调试当前源码版 JIT 是否真正生效
- 需要确认“跑到的是当前工作树，而不是系统已安装版本”

本文档使用 `pyperformance` 的 `mdp` 作为示例 benchmark，但环境搭建方式本身不依赖 `mdp`。

## 4. 前置条件

开始之前请确认：

- 当前位于仓库根目录
- 本机已安装 `uv`
- 本机有可用的 `python3.14`
- 如果要跑 `pyperformance` 类 benchmark，本机有对应 benchmark 源码树

建议提前准备三个环境变量：

```bash
export REPO_ROOT="$(pwd)"
export UV_CACHE_DIR="$REPO_ROOT/.uv-cache"
export PYPERFORMANCE_ROOT="<path-to-pyperformance-repo>"
```

其中：

- `REPO_ROOT` 指向当前仓库根目录
- `UV_CACHE_DIR` 指向项目内 `uv` cache
- `PYPERFORMANCE_ROOT` 指向本机的 `pyperformance` 源码树根目录

如果这次不跑 `pyperformance`，可以不设置 `PYPERFORMANCE_ROOT`。

## 5. 第一次建立本地环境

### 5.1 创建项目虚拟环境

先在仓库根目录执行：

```bash
uv venv --python python3.14 .venv
```

如果你希望强制使用某个具体的 `python3.14`，可以这样写：

```bash
uv venv --python "$(command -v python3.14)" .venv
```

说明：

- 这里仍然是 `uv` 管理的项目环境
- 但底座解释器来自本机可用的 `python3.14`
- 这样能保持项目间隔离，同时避免与某些 `uv` 自带解释器的 ABI 差异撞上

### 5.2 安装基础依赖

```bash
UV_CACHE_DIR="$UV_CACHE_DIR" \
uv pip install --python .venv/bin/python pyperf
```

如果当前任务不需要 `pyperf`，可以只安装你实际需要的依赖。

### 5.3 安装当前源码

首次安装当前源码：

```bash
UV_CACHE_DIR="$UV_CACHE_DIR" \
uv pip install --python .venv/bin/python -e .
```

如果你已经装过一轮，后续修改 C/C++ 源码后，仍然建议重新执行这一条，保证 `.venv` 里拿到的是当前源码版本。

## 6. 构建当前源码扩展

### 6.1 日常性能近似验证

性能近似验证推荐使用 `RelWithDebInfo`：

```bash
CMAKE_BUILD_TYPE=RelWithDebInfo \
.venv/bin/python setup.py build_ext --inplace --build-temp scratch/temp.macos-arm64-cpython-314-rel
```

### 6.2 HIR / 调试分析

需要做 HIR 文本抓取、debug 断言或额外诊断时，使用 `Debug`：

```bash
CMAKE_BUILD_TYPE=Debug \
.venv/bin/python setup.py build_ext --inplace --build-temp scratch/temp.macos-arm64-cpython-314
```

建议：

- 平时 benchmark 优先 `RelWithDebInfo`
- 需要 `print_hir()`、调试断言或精细分析时再切 `Debug`

## 7. 运行前自检

在开始 benchmark 前，先确认当前运行的是项目环境和源码版 `cinderx`：

```bash
.venv/bin/python - <<'PY'
import sys
import cinderx
import cinderx.jit as jit

print("python:", sys.executable)
print("cinderx:", cinderx.__file__)
print("jit:", jit.__file__)
PY
```

你应当看到：

- `sys.executable` 指向仓库内 `.venv/bin/python`
- `cinderx` 和 `cinderx.jit` 指向当前项目环境中的源码安装结果

如果这里指向了系统或别的项目的 site-packages，说明环境没切干净，不要继续跑 benchmark。

## 8. 最重要的运行时开关

当前本地环境下，运行 JIT benchmark 前请显式加：

```bash
export PYTHONJITHUGEPAGES=0
```

这是本地稳定运行源码版 JIT 的必要前提。  
如果不加，JIT 可能在 code allocator 阶段直接失败。

## 9. 运行 benchmark

### 9.1 `pyperformance/mdp` 示例：6 个关键热点函数

```bash
PYTHONJITHUGEPAGES=0 \
.venv/bin/python scripts/arm/bench_pyperf_direct.py \
  --module-path "$PYPERFORMANCE_ROOT/pyperformance/data-files/benchmarks/bm_mdp/run_benchmark.py" \
  --bench-func bench_mdp \
  --bench-args-json '[1]' \
  --compile-strategy names \
  --compile-names 'Battle.evaluate,Battle.getSuccessors,Battle._getSuccessorsB,getCritDist,topoSort,applyHPChange' \
  --samples 5 \
  --prewarm-runs 1 \
  --specialized-opcodes
```

这条命令适合做：

- 日常回归
- 局部优化前后对比
- 关键热点函数的快速近似验证

### 9.2 `pyperformance/mdp` 示例：全量强制编译

```bash
PYTHONJITHUGEPAGES=0 \
.venv/bin/python scripts/arm/bench_pyperf_direct.py \
  --module-path "$PYPERFORMANCE_ROOT/pyperformance/data-files/benchmarks/bm_mdp/run_benchmark.py" \
  --bench-func bench_mdp \
  --bench-args-json '[1]' \
  --compile-strategy all \
  --samples 5 \
  --prewarm-runs 1 \
  --specialized-opcodes
```

这条命令适合做：

- 查看当前源码在“尽量多编译”的情况下的上限
- 对照热点白名单版本，判断是否还有未覆盖的剩余热点

### 9.3 如何理解当前结果

以最近一次 `mdp` 本地验证为例：

- 6 个关键热点强编：约 `0.944s`
- 全量强编：约 `0.936s`

两者差距只有约 `0.84%`，而且 `deopt = 0`。  
这意味着当前主要大坑已经被填平，剩余空间更像 steady-state 的小幅优化，而不是明显的高收益缺口。

## 10. 抓取 HIR 和热点数据

### 10.1 直接看 HIR opcode 统计

当前仓库已有直接 runner，可配合 `get_function_hir_opcode_counts()` 使用。  
如需快速抓取某个函数的 opcode 统计，建议复用已有 `scripts/arm/bench_pyperf_direct.py` 或直接写一个最小 Python 驱动，在当前 `.venv` 下执行。

### 10.2 Debug 构建下抓文本 HIR

如果需要文本 HIR，请先确保使用 `Debug` 构建，然后再运行：

```bash
PYTHONJITHUGEPAGES=0 \
PYTHONJITDUMPFINALHIR=1 \
.venv/bin/python <your_script>.py
```

如果需要更细粒度控制，可以继续使用仓库里已有的诊断脚本和 `-X jit-list-file=...` 方式定点抓取。

### 10.3 当前还值得关注的 steady-state 函数

在最近一轮 `mdp` 基线下，剩余较值得观察的 steady-state 函数主要是：

- `Battle.evaluate`
- `getDamages`
- `Battle.getSuccessorsList`
- `_applyAction*`

其中：

- `Battle.evaluate` 仍然最重
- `getDamages` 可能解释“全量强编略优于热点白名单强编”的剩余差值

## 11. 常见问题

### 11.1 误用了全局 Python

症状：

- benchmark 能跑
- 但导入到的是别的项目安装过的 `cinderx`
- HIR、热点、性能数据与当前源码不一致

排查：

```bash
.venv/bin/python - <<'PY'
import sys
import cinderx
print(sys.executable)
print(cinderx.__file__)
PY
```

修复：

- 强制使用 `.venv/bin/python`
- 不要直接用全局 `python3`

### 11.2 `uv` 走了错误的解释器底座

症状：

- editable install 失败
- 或源码扩展构建/加载行为异常

修复：

- 删除当前 `.venv`
- 重新用本机可用的 `python3.14` 建环境：

```bash
rm -rf .venv
uv venv --python python3.14 .venv
```

### 11.3 缺少 `pyperf`

症状：

- 运行 benchmark 时出现 `ModuleNotFoundError: No module named 'pyperf'`

修复：

```bash
UV_CACHE_DIR="$UV_CACHE_DIR" \
uv pip install --python .venv/bin/python pyperf
```

### 11.4 JIT 初始化失败或可执行内存分配失败

症状：

- `jit.enable()` 失败
- 或 code allocator / huge pages 相关报错

修复：

```bash
export PYTHONJITHUGEPAGES=0
```

然后重新运行验证命令。

### 11.5 修改了 C/C++ 源码，但结果看起来没变化

症状：

- benchmark 能跑
- 但结果像仍在使用旧版本扩展

修复顺序：

1. 重新执行 `build_ext --inplace`
2. 重新执行 `uv pip install --python .venv/bin/python -e .`
3. 用“运行前自检”确认实际导入位置

## 12. 推荐的日常工作流

建议把日常工作流固定成下面这套：

1. 进入仓库根目录
2. 激活或直接使用 `.venv/bin/python`
3. 设置：

```bash
export UV_CACHE_DIR="$(pwd)/.uv-cache"
export PYTHONJITHUGEPAGES=0
export PYPERFORMANCE_ROOT="<path-to-pyperformance-repo>"
```

4. 代码改动后重新构建：

```bash
CMAKE_BUILD_TYPE=RelWithDebInfo \
.venv/bin/python setup.py build_ext --inplace --build-temp scratch/temp.macos-arm64-cpython-314-rel
```

5. 跑热点白名单近似验证
6. 必要时再跑全量强编
7. 需要 HIR 时切 `Debug`

## 13. 什么时候不必继续追优化

如果你看到以下信号同时出现：

- 热点白名单强编与全量强编差距已经很小
- `total_deopt_count = 0`
- 剩余热点主要是一类 steady-state 调用链
- 新方案开始变成高复杂度、低确定性的小修小补

那么更合理的选择通常是：

- 停止继续挖高风险优化
- 固化当前验证口径
- 把时间放到正式 ARM 验证或下一轮 benchmark 上
