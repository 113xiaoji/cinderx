# CinderX 集成 pyperformance 测试方法

本文档说明如何在远端测试机上构建或复用已安装的 CinderX，并让
`pyperformance` 创建的 benchmark worker 虚拟环境能够无感加载 CinderX。

当前已验证远端：

```text
host: root@124.70.162.35
date: 2026-05-07
arch: aarch64
verified python: /opt/python-3.14/bin/python3.14
```

原始测试环境可能使用 `/home/pybin/bin/python3.14`。为避免路径写死，建议统一用下面的变量入口：

```bash
export PYTHON_BIN=${PYTHON_BIN:-/home/pybin/bin/python3.14}
if [ ! -x "$PYTHON_BIN" ] && [ -x /opt/python-3.14/bin/python3.14 ]; then
  export PYTHON_BIN=/opt/python-3.14/bin/python3.14
fi

export CINDERX_REPO=${CINDERX_REPO:-$HOME/cinderx}
export JIT_LIST=${JIT_LIST:-/home/jit_list.txt}
export PYPERF_AFFINITY=${PYPERF_AFFINITY:-0}
```

说明：

```text
PYTHON_BIN       用来安装 CinderX 和启动 pyperformance 的 Python。
CINDERX_REPO     CinderX 源码目录。
JIT_LIST         pyperformance worker 继承使用的 JIT list。
PYPERF_AFFINITY  测试绑定 CPU 核。原环境可用 100；当前 8 核远端已验证用 0。
```

## 1. 前置检查

确认 Python、pip 和动态库路径可用：

```bash
$PYTHON_BIN -V
$PYTHON_BIN -m pip -V
echo "$LD_LIBRARY_PATH"
```

如果 CinderX 使用 GCC 14 构建，运行 pyperformance worker 时必须能加载
GCC 14 对应的 `libstdc++.so.6`。建议先确认：

```bash
ldconfig -p | grep libstdc++.so.6 || true
```

如果 `libstdc++.so.6` 不在系统默认搜索路径中，需要把 GCC 14 的库目录加入
`LD_LIBRARY_PATH`，并在后续 pyperformance 命令中通过 `--inherit-environ` 传给 worker。

## 2. 获取 CinderX 源码

当前测试代码位于个人仓库分支：

```bash
git config --global http.sslVerify false
git clone https://github.com/113xiaoji/cinderx.git "$CINDERX_REPO"
cd "$CINDERX_REPO"
git checkout bench-cur-7c361dce
```

如果仓库已经存在，更新到目标分支：

```bash
cd "$CINDERX_REPO"
git fetch origin
git checkout bench-cur-7c361dce
git pull --ff-only
```

## 3. 构建 CinderX

默认构建：

```bash
cd "$CINDERX_REPO"
$PYTHON_BIN -m pip install .
```

推荐性能构建：

```bash
cd "$CINDERX_REPO"
CMAKE_BUILD_TYPE="Release" \
CINDERX_ENABLE_PGO=1 \
CINDERX_ENABLE_LTO=1 \
ENABLE_STATIC_PYTHON=0 \
$PYTHON_BIN -m pip install .
```

该方式开启 Release、PGO、LTO，并关闭 Static Python 路径，适合正式性能测试。

构建后先验证基础解释器能导入 CinderX：

```bash
$PYTHON_BIN - <<'PY'
import cinderx
print("cinderx import ok", cinderx.__file__)
PY
```

如果远端已经有可用的 CinderX 安装，可以跳过本节构建步骤，直接从下一节的
driver venv 开始。本次远端 smoke 使用的就是 `/opt/python-3.14/bin/python3.14`
中已安装的 CinderX。

## 4. 创建 pyperformance driver venv

推荐单独创建一个 driver venv，用来安装和修改 `pyperformance`，避免污染基础 Python：

```bash
export DRIVER_VENV=${DRIVER_VENV:-/tmp/cinderx-pyperf-driver}
rm -rf "$DRIVER_VENV"
$PYTHON_BIN -m venv --system-site-packages "$DRIVER_VENV"
export PYTHON_BIN="$DRIVER_VENV/bin/python"
```

再次确认 driver venv 仍能看到 CinderX：

```bash
$PYTHON_BIN - <<'PY'
import cinderx
print("driver python import ok", cinderx.__file__)
PY
```

安装指定版本 pyperformance：

```bash
$PYTHON_BIN -m pip install pyperformance==1.13.0
$PYTHON_BIN -m pyperformance --version
```

## 5. 修改 pyperformance venv 创建逻辑

pyperformance 会为 benchmark 创建独立 worker venv。为了让 worker venv 能够使用
基础 Python 环境中的 CinderX，需要让 venv 创建命令携带 `--system-site-packages`。

使用下面的幂等脚本修改当前 driver venv 中的 `pyperformance/_venv.py`：

```bash
$PYTHON_BIN - <<'PY'
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

if "--system-site-packages" not in text:
    raise SystemExit(f"failed to patch {venv_py}: target lines not found")

if changed:
    venv_py.write_text(text)
    print(f"patched {venv_py}")
else:
    print(f"already patched {venv_py}")
PY
```

确认修改结果：

```bash
$PYTHON_BIN - <<'PY'
from pathlib import Path
import pyperformance

p = Path(pyperformance.__file__).with_name("_venv.py")
for line in p.read_text().splitlines():
    if '"-m", "venv"' in line or "--system-site-packages" in line:
        print(line)
PY
```

如果此前已经创建过 pyperformance worker venv，建议删除旧环境，让它按新逻辑重建：

```bash
rm -rf "$CINDERX_REPO"/venv/*
```

## 6. 准备 jit_list

写入测试使用的 JIT list：

```bash
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

## 7. 执行性能测试

执行 pyperformance 时要把 CinderX/JIT 相关变量以及 `LD_LIBRARY_PATH` 传给 worker。
否则 worker 可能无法导入 CinderX C 扩展，导致接口 fallback 为空实现，影响测试结果。

示例命令：

```bash
cd "$CINDERX_REPO"

PYTHONJITTYPEANNOTATIONGUARDS=1 \
PYTHONJITENABLEJITLISTWILDCARDS=1 \
PYTHONJITENABLEHIRINLINER=1 \
PYTHONJITAUTO=2 \
PYTHONJITSPECIALIZEDOPCODES=1 \
PYTHONJITLISTFILE="$JIT_LIST" \
$PYTHON_BIN -m pyperformance run \
  --affinity="$PYPERF_AFFINITY" \
  -b 2to3 \
  --warmup 3 \
  --inherit-environ http_proxy,https_proxy,LD_LIBRARY_PATH,PYTHONJITAUTO,PYTHONJITSPECIALIZEDOPCODES,PYTHONJITLISTFILE,PYTHONJITENABLEJITLISTWILDCARDS,PYTHONJITENABLEHIRINLINER,PYTHONJITTYPEANNOTATIONGUARDS \
  -o pyperformance-2to3-cinderx.json
```

参数说明：

```text
--affinity           绑定测试 CPU 核，按测试环境调整。
-b                   指定测试用例；不指定则执行全量测试。
--warmup             预热轮数。
-o                   输出测试结果 JSON 文件；不指定则仅打印到屏幕。
--inherit-environ    传递环境变量到 pyperformance worker 进程。
```

## 8. 快速 smoke 验证

建议先用 `nbody` 做快速验证。为了减少 smoke 时间，可以加 `--debug-single-value`：

```bash
cd "$CINDERX_REPO"

PYTHONJITTYPEANNOTATIONGUARDS=1 \
PYTHONJITENABLEJITLISTWILDCARDS=1 \
PYTHONJITENABLEHIRINLINER=1 \
PYTHONJITAUTO=2 \
PYTHONJITSPECIALIZEDOPCODES=1 \
PYTHONJITLISTFILE="$JIT_LIST" \
$PYTHON_BIN -m pyperformance run \
  --debug-single-value \
  --affinity="$PYPERF_AFFINITY" \
  -b nbody \
  --inherit-environ http_proxy,https_proxy,LD_LIBRARY_PATH,PYTHONJITAUTO,PYTHONJITSPECIALIZEDOPCODES,PYTHONJITLISTFILE,PYTHONJITENABLEJITLISTWILDCARDS,PYTHONJITENABLEHIRINLINER,PYTHONJITTYPEANNOTATIONGUARDS \
  -o pyperformance-nbody-cinderx.json
```

验证结果文件可读：

```bash
$PYTHON_BIN - <<'PY'
import json
from pathlib import Path

path = Path("pyperformance-nbody-cinderx.json")
data = json.loads(path.read_text())
benchmarks = data.get("benchmarks", [])
print("result file ok", path)
print("benchmark_count", len(benchmarks))
PY
```

经验判断：

```text
完整性能构建、固定 CPU、非 debug-single-value 时，nbody 约 50ms 通常表示 CinderX/JIT 已成功使能。
如果同一环境中 nbody 约 100ms，通常需要检查环境变量、LD_LIBRARY_PATH 或 jit_list。
不同机器、不同 affinity、debug-single-value、是否复用已安装 CinderX 都会改变绝对耗时。
因此 smoke 的硬性通过条件应是：worker venv 使用 --system-site-packages、worker 能看到 CinderX、结果 JSON 正常生成。
```

## 9. 已验证远端 smoke 结果

2026-05-07 在 `root@124.70.162.35` 上按本文档的 driver venv 和 worker venv 逻辑完成 smoke：

```text
base python: /opt/python-3.14/bin/python3.14
driver venv: /tmp/cinderx-doc-verify/driver-venv
pyperformance: 1.13.0
worker venv creation: python -m venv --without-pip --system-site-packages ...
benchmark: nbody
mode: --debug-single-value
affinity: 0
exit code: 0
result file: /tmp/cinderx-doc-verify/run/pyperformance-nbody-cinderx.json
benchmark_count: 1
nbody: 159 ms
```

这次 smoke 的 `159 ms` 是在 `--debug-single-value`、`affinity=0`、复用远端已安装 CinderX 的条件下得到，
不能直接和正式多样本性能构建的 `50ms/100ms` 经验阈值比较；它证明的是 pyperformance worker
venv 能通过 `--system-site-packages` 继承并加载 CinderX，且 benchmark 能完整跑通并产出 JSON。

## 10. 常见问题排查

如果基础 Python 无法导入 CinderX：

```bash
LD_LIBRARY_PATH="$LD_LIBRARY_PATH" \
$PYTHON_BIN - <<'PY'
import cinderx
print(cinderx.__file__)
PY
```

如果基础 Python 能导入，但 pyperformance worker 不能导入，优先检查：

```text
1. pyperformance/_venv.py 是否已经加入 --system-site-packages。
2. 旧的 pyperformance worker venv 是否已经删除并重建。
3. --inherit-environ 是否包含 LD_LIBRARY_PATH 和所有 PYTHONJIT* 变量。
4. PYTHONJITLISTFILE 指向的文件是否存在，且包含 __main__:*。
5. 当前 shell 是否设置了正确的 PYTHON_BIN、CINDERX_REPO、JIT_LIST 和 PYPERF_AFFINITY。
```

可以用最小 worker 继承检查：

```bash
PYTHONJITAUTO=2 \
PYTHONJITLISTFILE="$JIT_LIST" \
$PYTHON_BIN -m pyperformance run \
  --debug-single-value \
  --affinity="$PYPERF_AFFINITY" \
  -b nbody \
  --inherit-environ LD_LIBRARY_PATH,PYTHONJITAUTO,PYTHONJITLISTFILE \
  -o pyperformance-worker-env-check.json
```
