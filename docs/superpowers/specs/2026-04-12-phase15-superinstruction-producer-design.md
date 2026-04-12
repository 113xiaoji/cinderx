# CinderX Phase 1.5 Superinstruction Producer 补齐设计

> 状态：草案  
> 分支：`codex/interpreter-optimization-design`  
> 范围：只补齐 Phase 1 superinstruction pilot 的真实 producer 与验收证据，不扩展到 PIC、tier2、JIT 主线

## 背景

当前分支已经完成了 Phase 1 的大部分基础设施：

- Phase 1 pilot workload registry
- `bench_compare_modes.py` 的命名 workload 支持
- Phase 1 shortlist
- `3.14` / `3.15` 对三条双下划线 superinstruction 的 interpreter wiring
- 统一 ARM 入口下的 pilot driver 与 `findings.md` 证据

但整体验收发现一个关键缺口：

**当前只有 consumer，没有 producer。**

也就是说：

- 解释器层已经能识别并执行：
  - `LOAD_FAST__LOAD_FAST`
  - `STORE_FAST__LOAD_FAST`
  - `LOAD_CONST__LOAD_FAST`
- 但普通源码在当前真实执行链路下，并不会被发射成这 3 个 opcode

已有证据表明：

- `scripts/arm/bench_compare_modes.py` 当前通过普通 module load 拿到 workload 函数对象
- 这条路径不会进入 Cinder Python compiler
- 当前可见的 superinstruction producer 仍在 `cinderx/PythonLib/cinderx/compiler/pyassem.py`
- 该 producer 目前只发射旧的单下划线形式：
  - `LOAD_FAST_LOAD_FAST`
  - `STORE_FAST_LOAD_FAST`
  - `STORE_FAST_STORE_FAST`
- 并且没有 `LOAD_CONST + LOAD_FAST` 对应的 producer

因此，当前分支的远端成功证据只能证明：

- pilot driver 能跑完
- 统一入口能产出 6 个 JSON artifact
- interpreter consumer wiring 与静态 contract 成立

但还**不能**证明：

- 新增的双下划线 superinstruction 被真实发射
- benchmark 实际测到了这批新 opcode

本设计的目标，就是补上这条缺失的 producer 路径，并让 Phase 1 的验收升级为：

**已发射 + 已执行 + 已留证**

## 目标

### 近目标

在不扩大到 quickening / PIC / tier2 的前提下：

- 给双下划线 superinstruction 增加真实 producer
- 让 Phase 1 pilot workload 在 `cinderx` 侧走 producer 路径
- 为 `3.14` 提供可验证的“真实发射证据”
- 保持当前已完成的 interpreter wiring 不回退

### 中目标

- 将 Phase 1 的验收从“静态 contract + artifact 存在”升级为：
  - 编译后 opcode 证据存在
  - 新 superinstruction 被实际执行
  - 远端统一入口下能留下证据

## 非目标

本设计明确不包含：

- interpreter quickening producer
- PIC
- tier2 / executor 准入调整
- JIT 侧任何改造
- 在本轮把 `3.15` producer/runtime 也一并跑通

本轮优先级是：

**先把 `3.14` 上的新双下划线 opcode 发射与验证闭环补齐。**

## 问题定义

当前存在两个根因级问题。

### 问题 1：producer 路径不对

现有 pilot workload 是普通 Python 源码函数。

在 `bench_compare_modes.py --runtime cinderx --mode interp` 的当前链路里：

- workload 通过普通 import/loader 得到函数对象
- 计时逻辑直接执行该函数
- 没有任何一步会把普通 `LOAD_FAST` / `STORE_FAST` / `LOAD_CONST` 邻接对改写成新双下划线 opcode

因此当前 benchmark 不可能真实命中新 superinstruction。

### 问题 2：验收证据不够

当前 evidence 更接近：

- “脚本能跑”
- “artifact 存在”
- “JSON 的 runtime / mode / workload 字段对”

但缺少以下信息：

- 编译后的 opcode 序列
- 是否真的出现新双下划线 opcode
- 哪个 workload 命中了哪个 superinstruction
- 哪些 workload 仍然是普通 opcode 路径

## 方案对比

### 方案 A：补 Cinder compiler producer，并让 pilot workload 显式走该链路

做法：

- 修改 `pyassem.py` / `opcodes.py`
- 让现有 superinstruction producer 发射双下划线形式
- 补上 `LOAD_CONST + LOAD_FAST` 的 producer
- 在 benchmark 里增加显式 producer 选项，让 `cinderx` 侧可走 Cinder compiler

优点：

- 改动面最小
- 与当前分支已做的 interpreter consumer wiring 连续
- 验证最直接
- 最适合当前 Phase 1 收口

缺点：

- 首先闭环的是“走 Cinder compiler 的代码路径”
- 不是所有普通 Python 代码都会自动受益

### 方案 B：补 interpreter quickening producer

做法：

- 在解释器/adaptive 路径中识别普通 opcode 邻接对
- 动态改写成双下划线 superinstruction

优点：

- 更接近“纯解释执行优化”
- 不依赖 Cinder compiler 特殊入口

缺点：

- 改动面明显更大
- 风险更高
- 超出本轮 Phase 1.5 最小闭环范围

### 方案 C：做验证专用 producer

做法：

- 单独为 benchmark/pilot 增加一个局部 bytecode rewrite helper
- 只服务本轮验证

优点：

- 出结果最快

缺点：

- 工程价值最弱
- 很容易把验证路径做成实验特供
- 后续很难复用

## 推荐方案

推荐采用 **方案 A**：

**补 Cinder compiler producer，并让 pilot workload 显式走该链路。**

推荐理由：

- 它是当前最小、最稳、最容易证明有效的闭环
- 它不推翻已经完成的 interpreter consumer wiring
- 它能直接回答当前验收 blocker：新 opcode 到底有没有被真实发射

同时，范围进一步收敛为：

- `3.14`：本轮要求真实 producer + runtime + remote evidence 全闭环
- `3.15`：本轮仍保留静态 wiring + contract，暂不承诺 runtime producer 闭环

## 设计

### 1. Workload registry 升级为“源码真相”

当前 `scripts/arm/interp_superinstruction_workloads.py` 只提供：

- workload 名称
- target pair
- callable

这不足以驱动 Cinder compiler producer。

建议升级为：

- `name`
- `target_pair`
- `entry_name`
- `source`

并提供两类 helper：

- 普通路径：
  - 从 source 构造普通 callable
- Cinder compiler 路径：
  - 通过 `exec_cinder()` 从同一份 source 产出函数

这样可以保证：

- workload 的源码只有一份
- default producer 和 cinder producer 都从同一份源码出发
- 后续 findings 和测试不会因为两套 workload 实现而漂移

### 2. 补齐双下划线 producer

修改核心文件：

- `cinderx/PythonLib/cinderx/compiler/pyassem.py`
- `cinderx/PythonLib/cinderx/compiler/opcodes.py`

目标：

- 将原本发射：
  - `LOAD_FAST_LOAD_FAST`
  - `STORE_FAST_LOAD_FAST`
  的逻辑改为发射：
  - `LOAD_FAST__LOAD_FAST`
  - `STORE_FAST__LOAD_FAST`
- 新增 `LOAD_CONST + LOAD_FAST -> LOAD_CONST__LOAD_FAST`

同时需要补齐：

- stack effect / popped / pushed 元数据
- load-fast analysis / borrow-path logic 中对新 opcode 的识别
- 如有必要，保留旧单下划线形式仅作兼容，不再作为 Phase 1 pilot 的目标

### 3. Benchmark 增加显式 producer 维度

修改：

- `scripts/arm/bench_compare_modes.py`

新增概念：

- `--producer default`
- `--producer cinder`

建议行为：

- `default`
  - 继续走现有普通 producer
- `cinder`
  - 仅允许 `--runtime cinderx`
  - 使用 `exec_cinder()` 从 workload source 编译出函数

这样后续 benchmark JSON 至少应新增：

- `producer`
- `emitted_superinstructions`

并保持：

- `cpython` baseline 仍然可以和 `default` producer 对比
- `cinderx` 可分别对比 default producer 与 cinder producer

### 4. 发射证据要进入 contract 和 artifact

本轮新增的验证不应再只检查：

- `runtime`
- `mode`
- `workload`

而要新增真实发射证据，例如：

- code object 反汇编后的 opcode 名称列表
- 命中的双下划线 opcode 名称集合

最低要求：

- 对每个 Phase 1 workload，至少能断言：
  - 是否出现预期 superinstruction

这部分可以先在本地 contract test 中做，
再在远端 artifact 中输出。

### 5. Pilot driver 扩展为“基准 + 发射证据”

修改：

- `scripts/arm/interp_superinstruction_pilot.sh`

新增职责：

- 继续生成 benchmark JSON
- 同时生成一份发射证据 JSON 或文本摘要

建议输出：

- `${workload}.cpython.json`
- `${workload}.cinderx.default.json`
- `${workload}.cinderx.cinder.json`
- `${workload}.cinder.emitted.json`

如果本轮想控制复杂度，也可以只保留：

- `cpython`
- `cinderx + cinder producer`
- `emitted evidence`

关键是：

**artifact 必须能证明新 opcode 被真实发射。**

## 实施顺序

### Step 1

升级 workload registry，加入 source / entry_name，保证两条 producer 路径共用同一份源码。

### Step 2

修改 `pyassem.py` / `opcodes.py`，让 Cinder compiler producer 发射双下划线形式，并补 `LOAD_CONST__LOAD_FAST`。

### Step 3

修改 `bench_compare_modes.py`，增加 `--producer cinder` 并输出发射证据。

### Step 4

扩展 pilot driver，增加 emitted evidence artifact。

### Step 5

通过统一入口在 ARM 上重新验证，并更新 `findings.md`：

- 哪个 workload 发射到了哪个新 opcode
- 对应 artifact 路径
- 是否完成 `3.14` runtime producer 闭环

## 验收标准

本轮通过标准应改为：

### `3.14`

- 至少一个 Phase 1 workload 通过真实 producer 发射出目标双下划线 opcode
- 发射证据被写入本地测试和远端 artifact
- `scripts/push_to_arm.ps1` 统一入口下能产出包含发射证据的 artifact

### `3.15`

- 静态 wiring 和 contract 继续保持通过
- 不要求本轮必须拿到 runtime producer 证据

### 不再接受的“伪完成”

以下情况不再算完成：

- 只有 interpreter consumer wiring
- 只有 JSON artifact 存在
- 只有 `runtime/mode/workload` spot-check 正确
- 没有任何 emitted opcode 证据

## 风险

### 风险 1：producer 改动会影响现有旧单下划线路径

需要明确：

- 是直接替换
- 还是短期兼容两套名字

建议：

- 本轮优先让 Phase 1 pilot 的 producer 发射双下划线形式
- 如需兼容旧单下划线，必须有清晰边界，避免两套语义长期并存

### 风险 2：`LOAD_CONST__LOAD_FAST` 没有现成先例

这是本轮新增 producer 中风险最高的一项。

建议：

- 单独加测试
- 单独记录 emitted evidence
- 不要把它和 `LOAD_FAST__LOAD_FAST` / `STORE_FAST__LOAD_FAST` 混成一个不可分解的大验证项

### 风险 3：pilot workload 未必稳定命中 producer

需要针对 workload 源码做小幅约束，确保：

- pair 在热点循环里
- pair 不会被其他 pass 轻易改写掉

## 结论

当前 Phase 1 没有真正失败，失败的是验收口径暴露出了缺失的一半：

- consumer 已有
- producer 未补

Phase 1.5 的正确目标不是推翻现在的工作，而是：

**补上双下划线 superinstruction 的真实 producer，并把验收升级为“已发射 + 已执行 + 已留证”。**
