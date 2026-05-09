# CinderX 集成 pyperformance 测试方法

本文档是 CinderX 做 pyperformance 性能测试的固定方法。所有 AI 或人工在做
pyperformance 性能对比时，都应优先按本文档执行；不要临时发明另一套 venv、
环境变量或 worker 启动方式。

核心原则：

```text
命令形态固定，具体目录按机器实际情况配置。
```

因此本文档不把某台机器上的 Python、venv、结果目录写死。执行前只需要把实际路径
收敛到一组变量，后续第 5、6、7、8 章的步骤保持一致。

## 1. 配置路径变量

先进入本次要测试的 CinderX 仓库目录，然后设置变量：

```bash
export CINDERX_REPO=${CINDERX_REPO:-$(pwd)}
export BASE_PYTHON=${BASE_PYTHON:-$(command -v python3.14 || true)}
export RUN_ROOT=${RUN_ROOT:-"$CINDERX_REPO/.pyperformance-cinderx"}
export DRIVER_VENV=${DRIVER_VENV:-"$RUN_ROOT/driver-venv"}
export DRIVER_PYTHON="$DRIVER_VENV/bin/python"
export JIT_LIST=${JIT_LIST:-"$RUN_ROOT/jit_list.txt"}
export RESULT_DIR=${RESULT_DIR:-"$RUN_ROOT/results"}
export PYPERF_VERSION=${PYPERF_VERSION:-1.13.0}
export PYPERF_WARMUP=${PYPERF_WARMUP:-3}
export EXPECTED_CINDERX_SOURCE=${EXPECTED_CINDERX_SOURCE:-"$CINDERX_REPO"}
```

如果 `python3.14` 不在 `PATH` 里，不要修改文档里的命令，直接把实际 Python 路径
赋给 `BASE_PYTHON`：

```bash
export BASE_PYTHON="<current-machine-python3.14>"
```

CPU 亲和性也不要写死。机器需要绑核时设置 `PYPERF_AFFINITY`，不需要时留空：

```bash
export PYPERF_AFFINITY=${PYPERF_AFFINITY:-}
```

生成可复用的 affinity 参数：

```bash
PYPERF_AFFINITY_ARGS=()
if [ -n "${PYPERF_AFFINITY:-}" ]; then
  PYPERF_AFFINITY_ARGS=(--affinity "$PYPERF_AFFINITY")
fi
```

生成 `--inherit-environ` 参数。这个函数必须在本次要传给 worker 的所有
`PYTHONJIT*` 变量都 `export` 之后调用：

```bash
build_pyperf_inherit_env() {
  local names=(http_proxy https_proxy LD_LIBRARY_PATH PYTHONPATH)
  local name

  while IFS='=' read -r name _; do
    case "$name" in
      PYTHONJIT*) names+=("$name") ;;
    esac
  done < <(env)

  (IFS=,; echo "${names[*]}")
}
```

检查变量是否有效：

```bash
test -n "$BASE_PYTHON" && test -x "$BASE_PYTHON"
"$BASE_PYTHON" -V
mkdir -p "$RUN_ROOT" "$RESULT_DIR"
```

## 2. 确认测试 checkout

默认测试当前 checkout，不在文档里固定某个 fork 或临时分支。进入仓库后先记录本轮
实际要测的提交：

```bash
cd "$CINDERX_REPO"
git status --short --branch
git rev-parse --show-toplevel
git rev-parse HEAD
```

如果仓库还不存在，先 clone 本轮明确要测试的目标仓库。`CINDERX_REMOTE` 必须由执行者
按本轮任务显式给出，不要在文档里写死：

```bash
export CINDERX_REMOTE="<repository-url-to-test>"
git clone "$CINDERX_REMOTE" "$CINDERX_REPO"
cd "$CINDERX_REPO"
```

只有在复现某个历史实验或远端临时分支时，才显式设置 `CINDERX_REF`。这会让本轮测试
离开当前 checkout，所以必须在 `findings.md` 里记录原因、remote、ref 和最终 commit：

```bash
cd "$CINDERX_REPO"
if [ -n "${CINDERX_REF:-}" ]; then
  git fetch "${CINDERX_REMOTE:-origin}" "$CINDERX_REF"
  git switch --detach FETCH_HEAD
  git rev-parse HEAD
fi
```

## 3. 构建或复用 CinderX

构建 CinderX 前先确认 C/C++ toolchain 满足当前要求：`GCC 13+` 或 `Clang 18+`。
不要只看机器上存在 `gcc` 或 `clang`；必须记录实际会被构建使用的编译器版本：

```bash
${CC:-gcc} --version
${CXX:-g++} --version
clang --version || true
clang++ --version || true
```

如果系统默认编译器版本不满足要求，先显式切到合格 toolchain，再执行后续
`pip install`。使用隔离 GCC prefix 时同时带上运行时库路径，避免构建或运行时加载旧
`libstdc++`：

```bash
export GCC_PREFIX="<gcc-13-or-newer-prefix>"
export CC="$GCC_PREFIX/bin/gcc"
export CXX="$GCC_PREFIX/bin/g++"
export PATH="$GCC_PREFIX/bin:$PATH"
export LD_LIBRARY_PATH="$GCC_PREFIX/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
gcc --version
g++ --version
```

正式测试前必须让 `BASE_PYTHON` 安装本轮 checkout，避免复用机器上残留的旧 wheel。
先选择一种安装方式。

默认构建：

```bash
cd "$CINDERX_REPO"
"$BASE_PYTHON" -m pip install --force-reinstall --no-deps "$CINDERX_REPO"
```

推荐性能构建：

```bash
cd "$CINDERX_REPO"
CMAKE_BUILD_TYPE=Release \
CINDERX_ENABLE_PGO=1 \
CINDERX_ENABLE_LTO=1 \
ENABLE_STATIC_PYTHON=0 \
"$BASE_PYTHON" -m pip install --force-reinstall --no-deps "$CINDERX_REPO"
```

安装后不能只看 `import` 是否成功；必须记录并校验包来源，确认它就是本轮要测的
checkout 或本轮明确指定的构建产物：

```bash
"$BASE_PYTHON" - <<'PY'
import importlib.metadata as metadata
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import cinderx
print("cinderx import ok", cinderx.__file__)

dist = metadata.distribution("cinderx")
print("cinderx distribution", dist.metadata.get("Name"), dist.version)

expected = Path(os.environ["EXPECTED_CINDERX_SOURCE"]).resolve()
direct_url = None
for file in dist.files or []:
    if (
        len(file.parts) >= 2
        and file.name == "direct_url.json"
        and file.parts[-2].endswith(".dist-info")
    ):
        path = Path(dist.locate_file(file))
        direct_url = json.loads(path.read_text())
        print("cinderx direct_url", direct_url)
        break

if not direct_url:
    raise SystemExit("cinderx direct_url.json missing; package provenance unknown")

url = direct_url.get("url", "")
if not url.startswith("file://"):
    raise SystemExit(f"cinderx source is not a local file URL: {url}")

actual = Path(unquote(urlparse(url).path)).resolve()
if actual != expected:
    raise SystemExit(f"cinderx source mismatch: {actual} != {expected}")
PY
```

如果 `BASE_PYTHON` 本身是 venv，后续 pyperformance worker venv 的
`--system-site-packages` 可能只能看到更底层 Python 的全局 site-packages，而看不到
`BASE_PYTHON` 这个 venv 里刚安装的 CinderX。为了让 driver 和 worker 都优先导入本轮
确认过来源的 CinderX，把它所在的 site-packages 放到 `PYTHONPATH` 最前面：

```bash
export CINDERX_SITE_PACKAGES=$("$BASE_PYTHON" - <<'PY'
from pathlib import Path
import cinderx

path = Path(cinderx.__file__).resolve()
for parent in path.parents:
    if parent.name == "site-packages":
        print(parent)
        break
else:
    raise SystemExit(f"could not locate site-packages for {path}")
PY
)
export PYTHONPATH="$CINDERX_SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
```

## 4. 创建 driver venv

driver venv 用来安装和修改 pyperformance。它必须带 `--system-site-packages`，
这样 driver Python 能看到基础 Python 环境里的 CinderX：

```bash
rm -rf "$DRIVER_VENV"
"$BASE_PYTHON" -m venv --system-site-packages "$DRIVER_VENV"
"$DRIVER_PYTHON" -m pip install "pyperformance==$PYPERF_VERSION"
```

验证 driver Python：

```bash
"$DRIVER_PYTHON" - <<'PY'
import cinderx
import pyperformance
print("driver cinderx import ok", cinderx.__file__)
print("pyperformance import ok", pyperformance.__file__)
PY
"$DRIVER_PYTHON" -m pyperformance --version
```

## 5. 固化 pyperformance worker venv 创建逻辑

这是最关键的一步。

pyperformance 会为 benchmark 创建独立 worker venv。worker venv 如果没有
`--system-site-packages`，就可能看不到已经安装好的 CinderX，导致测试进程里
`import cinderx` 失败或 fallback 成空实现。所有 pyperformance 性能测试都必须
先把 worker venv 创建逻辑修成带 `--system-site-packages`。

执行下面的幂等 patch：

```bash
"$DRIVER_PYTHON" - <<'PY'
from pathlib import Path
import pyperformance

venv_py = Path(pyperformance.__file__).with_name("_venv.py")
text = venv_py.read_text()

replacements = {
    'args = ["-m", "venv", root]':
        'args = ["-m", "venv", "--system-site-packages", root]',
    'args = ["-m", "venv", "--without-pip", root]':
        'args = ["-m", "venv", "--without-pip", "--system-site-packages", root]',
}

changed = False
for old, new in replacements.items():
    if old in text:
        text = text.replace(old, new)
        changed = True

expected = [
    'args = ["-m", "venv", "--system-site-packages", root]',
    'args = ["-m", "venv", "--without-pip", "--system-site-packages", root]',
]
missing = [line for line in expected if line not in text]
if missing:
    raise SystemExit(f"failed to patch {venv_py}; missing: {missing}")

if changed:
    venv_py.write_text(text)
    print(f"patched {venv_py}")
else:
    print(f"already patched {venv_py}")
PY
```

确认 patch 生效：

```bash
"$DRIVER_PYTHON" - <<'PY'
from pathlib import Path
import pyperformance

p = Path(pyperformance.__file__).with_name("_venv.py")
text = p.read_text()
expected = [
    'args = ["-m", "venv", "--system-site-packages", root]',
    'args = ["-m", "venv", "--without-pip", "--system-site-packages", root]',
]
for line in expected:
    print(line)
    if line not in text:
        raise SystemExit(f"pyperformance worker venv patch missing: {line}")
PY
```

如果之前已经在当前运行目录创建过 pyperformance worker venv，删除旧 worker venv，
让 pyperformance 按新逻辑重建。默认情况下它通常在运行目录的 `venv/` 下；如果你
使用了自定义 `--venv` 目录，就删除那个实际目录：

```bash
rm -rf "$CINDERX_REPO/venv"
```

## 6. 准备固定 jit_list

所有 pyperformance 测试统一使用同一份 JIT list。路径由 `JIT_LIST` 决定，内容固定：

```bash
mkdir -p "$(dirname "$JIT_LIST")"
cat > "$JIT_LIST" <<'EOF'
__main__:*
copy:*
pickle:*
tomli._parser:*
django.template:*
django.template.base:*
django.template.context:*
django.template.engine:*
django.template.library:*
django.template.defaulttags:*
django.template.defaultfilters:*
django.template.loader_tags:*
django.template.smartif:*
django.utils:*
django.utils.safestring:*
django.utils.encoding:*
django.utils.html:*
django.utils.itercompat:*
django.utils.text:*
django.utils.regex_helper:*
django.utils.autoreload:*
EOF
```

确认文件存在：

```bash
test -s "$JIT_LIST"
grep -q '^__main__:\*$' "$JIT_LIST"
```

## 7. 执行 pyperformance

所有正式 pyperformance 命令都必须：

```text
1. 使用 DRIVER_PYTHON 启动 pyperformance。
2. 传入 PYTHONJITLISTFILE="$JIT_LIST"。
3. 通过 --inherit-environ 传递 LD_LIBRARY_PATH、PYTHONPATH 和所有 PYTHONJIT* 变量。
4. affinity 只通过 PYPERF_AFFINITY_ARGS 注入，不在命令里写死。
5. 输出 JSON 到 RESULT_DIR。
```

单 benchmark 示例：

```bash
cd "$CINDERX_REPO"

export BENCH=${BENCH:-2to3}
export OUT_JSON=${OUT_JSON:-"$RESULT_DIR/${BENCH}-cinderx.json"}

export PYTHONJITTYPEANNOTATIONGUARDS=1
export PYTHONJITENABLEJITLISTWILDCARDS=1
export PYTHONJITENABLEHIRINLINER=1
export PYTHONJITAUTO=2
export PYTHONJITSPECIALIZEDOPCODES=1
export PYTHONJITLISTFILE="$JIT_LIST"
export PYPERF_INHERIT_ENV
PYPERF_INHERIT_ENV=$(build_pyperf_inherit_env)

"$DRIVER_PYTHON" -m pyperformance run \
  "${PYPERF_AFFINITY_ARGS[@]}" \
  -b "$BENCH" \
  --warmups "$PYPERF_WARMUP" \
  --inherit-environ "$PYPERF_INHERIT_ENV" \
  -o "$OUT_JSON"
```

全量或多 benchmark 测试也沿用同一命令形态，只调整 `-b` 或去掉 `-b`。不要为了
方便另外创建一套 pyperformance venv 或遗漏 `--inherit-environ`。

## 8. smoke 验证

正式性能测试前，先跑 `nbody` smoke。smoke 的目的不是给最终性能结论，而是确认
pyperformance worker venv 能继承 CinderX，JIT 环境变量能进入 worker，结果 JSON 能生成。

```bash
cd "$CINDERX_REPO"

export SMOKE_JSON=${SMOKE_JSON:-"$RESULT_DIR/nbody-smoke-cinderx.json"}

export PYTHONJITTYPEANNOTATIONGUARDS=1
export PYTHONJITENABLEJITLISTWILDCARDS=1
export PYTHONJITENABLEHIRINLINER=1
export PYTHONJITAUTO=2
export PYTHONJITSPECIALIZEDOPCODES=1
export PYTHONJITLISTFILE="$JIT_LIST"
export PYPERF_INHERIT_ENV
PYPERF_INHERIT_ENV=$(build_pyperf_inherit_env)

"$DRIVER_PYTHON" -m pyperformance run \
  --debug-single-value \
  "${PYPERF_AFFINITY_ARGS[@]}" \
  -b nbody \
  --inherit-environ "$PYPERF_INHERIT_ENV" \
  -o "$SMOKE_JSON"
```

验证结果 JSON：

```bash
"$DRIVER_PYTHON" - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["SMOKE_JSON"])
data = json.loads(path.read_text())
benchmarks = data.get("benchmarks", [])
if not benchmarks:
    raise SystemExit(f"no benchmarks in {path}")
print("result file ok", path)
print("benchmark_count", len(benchmarks))
PY
```

验证 worker Python 实际导入的 CinderX 来源。这个检查要在 smoke 之后执行，因为
pyperformance 会在 smoke 时创建 worker venv：

```bash
WORKER_PYTHON=$(find "$CINDERX_REPO/venv" -path '*/bin/python' | head -n 1)
test -x "$WORKER_PYTHON"
PYTHONPATH="$PYTHONPATH" "$WORKER_PYTHON" - <<'PY'
import importlib.metadata as metadata
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import cinderx
print("worker cinderx import ok", cinderx.__file__)

dist = metadata.distribution("cinderx")
expected = Path(os.environ["EXPECTED_CINDERX_SOURCE"]).resolve()
direct_url = None
for file in dist.files or []:
    if (
        len(file.parts) >= 2
        and file.name == "direct_url.json"
        and file.parts[-2].endswith(".dist-info")
    ):
        path = Path(dist.locate_file(file))
        direct_url = json.loads(path.read_text())
        print("worker cinderx direct_url", direct_url)
        break

if not direct_url:
    raise SystemExit("worker cinderx direct_url.json missing")

url = direct_url.get("url", "")
if not url.startswith("file://"):
    raise SystemExit(f"worker cinderx source is not a local file URL: {url}")

actual = Path(unquote(urlparse(url).path)).resolve()
if actual != expected:
    raise SystemExit(f"worker cinderx source mismatch: {actual} != {expected}")
PY
```

smoke 通过条件：

```text
1. pyperformance 命令 exit code 为 0。
2. 结果 JSON 存在且可解析。
3. JSON 至少包含一个 benchmark。
4. 日志中的 worker venv 创建命令应包含 --system-site-packages。
5. worker Python 导入的 CinderX 来源应匹配 `EXPECTED_CINDERX_SOURCE`。
```

`nbody` 的绝对耗时只能作为同一机器、同一构建、同一 affinity 下的经验信号。不同目录、
不同 Python 安装、debug-single-value、CPU 绑定和是否 Release/PGO/LTO 都会改变耗时，
不要把某个机器上的毫秒数写成通用通过标准。

## 9. 常见排查

基础 Python 不能导入 CinderX：

```bash
"$BASE_PYTHON" - <<'PY'
import cinderx
print(cinderx.__file__)
PY
```

driver Python 不能导入 CinderX：

```bash
"$DRIVER_PYTHON" - <<'PY'
import cinderx
print(cinderx.__file__)
PY
```

worker 不能导入或结果异常时，优先检查：

```text
1. 第 5 章 patch 后的 _venv.py 是否包含 --system-site-packages。
2. 旧 worker venv 是否已经删除并重建。
3. --inherit-environ 是否包含 LD_LIBRARY_PATH、PYTHONPATH 和所有 PYTHONJIT* 变量。
4. PYTHONJITLISTFILE 是否指向第 6 章生成的 JIT_LIST。
5. 当前 shell 的 BASE_PYTHON、DRIVER_PYTHON、CINDERX_REPO、RUN_ROOT 是否指向本轮实际目录。
```
