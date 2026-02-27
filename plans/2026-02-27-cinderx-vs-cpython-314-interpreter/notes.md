# 备注：CinderX 3.14 vs CPython 3.14 解释器

## 文件清单
- CinderX：
  - `cinderx/Interpreter/3.14/interpreter.c`
  - `cinderx/Interpreter/3.14/borrowed-ceval.c.template`
  - `cinderx/Interpreter/3.14/Includes/ceval_macros.h`
  - `cinderx/Interpreter/3.14/Includes/generated_cases.c.h`
  - `cinderx/Interpreter/3.14/cinder-bytecodes.c`
  - `cinderx/Interpreter/3.14/cinder_opcode_ids.h`
  - `cinderx/PythonLib/opcodes/3.14/opcode.py`
- 上游 CPython 基线：
  - 仓库：`https://github.com/python/cpython.git`
  - 分支：`3.14`
  - 提交：`a58ea8c21239a23b03446aecd030995bbe40b7a7`（2026-02-27）
  - 文件：
    - `artifacts/cpython-3.14-upstream/Python/ceval.c`
    - `artifacts/cpython-3.14-upstream/Python/ceval_macros.h`
    - `artifacts/cpython-3.14-upstream/Python/bytecodes.c`
    - `artifacts/cpython-3.14-upstream/Python/generated_cases.c.h`

## 关键差异
- PEP523 判断语义发生变化：
  - CinderX 使用 `IS_PEP523_HOOKED(tstate)`：
    - `cinderx/Interpreter/3.14/Includes/ceval_macros.h:170`
    - 定义为 `eval_frame != NULL && eval_frame != Ci_EvalFrame`。
  - 上游主要判断 `tstate->interp->eval_frame == NULL`：
    - `artifacts/cpython-3.14-upstream/Python/ceval_macros.h:178`
    - `artifacts/cpython-3.14-upstream/Python/bytecodes.c:3777`, `4654`。
- 自适应解释器门控进入热路径：
  - `adaptive_enabled` 状态与阈值：
    - `cinderx/Interpreter/3.14/interpreter.c:37-42`
  - tail-call 签名携带 `adaptive_enabled`：
    - `cinderx/Interpreter/3.14/Includes/ceval_macros.h:76-80`
    - 上游无该参数：`artifacts/cpython-3.14-upstream/Python/ceval_macros.h:74-78`。
  - CinderX 中 `ADVANCE_ADAPTIVE_COUNTER` 是条件执行：
    - `cinderx/Interpreter/3.14/Includes/ceval_macros.h:283-286`
    - 上游总是执行：`artifacts/cpython-3.14-upstream/Python/ceval_macros.h:288-291`。
  - 新增 `CI_UPDATE_CALL_COUNT` 与 `CI_SET_ADAPTIVE_INTERPRETER_ENABLED_STATE`：
    - 定义：`cinderx/Interpreter/3.14/Includes/ceval_macros.h:434-461`
    - 生成代码调用点：
      - `CI_UPDATE_CALL_COUNT`：12 处（如 `675`, `1816`, `14108`）
      - `CI_SET_ADAPTIVE_INTERPRETER_ENABLED_STATE`：5 处（`9124`, `9184`, `12203`, `12234`, `13941`）
    - 上游无等价宏调用。
- 扩展 opcode 分发：
  - 额外目标 `EXTENDED_OPCODE`：
    - `cinderx/Interpreter/3.14/Includes/generated_cases.c.h:5691`
  - 作为多 opcode 合并入口处理 static/primitive 指令：
    - 起始于 `cinderx/Interpreter/3.14/cinder-bytecodes.c:507`
    - 分支包括 `STORE_LOCAL`、`LOAD_FIELD`、`INVOKE_FUNCTION`、`TP_ALLOC`、`RETURN_PRIMITIVE` 等（`519..1246`）。
  - 目标数量对比：
    - CinderX：229
    - CPython：227
    - CinderX 独有：`EXTENDED_OPCODE`、`EAGER_IMPORT_NAME`。
- 核心 opcode 被 Cinder 行为覆盖：
  - 调用/内联帧：`_DO_CALL`、`_CHECK_PEP_523`、`_PUSH_FRAME`、`_DO_CALL_KW`、`_DO_CALL_FUNCTION_EX`、`_SEND`
  - 集合构建：
    - `MAP_ADD` 使用 `Ci_DictOrChecked_SetItem`
    - `LIST_APPEND` 使用 `Ci_ListOrCheckedList_Append`
  - 返回/yield 退出点：`RETURN_VALUE`、`RETURN_GENERATOR`、`YIELD_VALUE`
- 可等待对象/协程路径分叉：
  - CinderX 使用 JIT 协程辅助：
    - `borrowed-ceval.c.template:107-108`, `123-131`
  - 上游使用 `_PyCoro_GetAwaitableIter` 与 `_PyGen_yf`。

## 性能假设
- H1：`start_frame` 与 `_PUSH_FRAME` 上的 `CI_UPDATE_CALL_COUNT` 对高调用负载有可测开销。
- H2：`if (adaptive_enabled)` 条件分支会提升特化热点循环的分支压力。
- H3：`EXTENDED_OPCODE` 大型 switch 增加 I-cache 占用与分支误预测成本。
- H4：PEP523 额外比较（`eval_frame != Ci_EvalFrame`）在热检查中有小但高频开销。
- H5：在未使用 checked 类型时，`MAP_ADD`/`LIST_APPEND` 包装路径可能拖慢纯 Python 集合构建。

## 验证思路
- A/B 构建开关：
  - 关闭/短路 `CI_UPDATE_CALL_COUNT` + `CI_SET_ADAPTIVE...`
  - 固定 `adaptive_enabled=true` 去除门控分支
- 微基准：
  - 高调用负载（`richards`、嵌套调用循环）
  - 高集合负载（`list.append`、dict comp / map-add）
  - 高 ext-op 负载（static-python）
- perf 计数器：
  - `branch-misses`、`branches`、`icache.misses`、`cycles`、`instructions`
- 行为回归保护：
  - 运行 `test_cinderx` static/strict 相关套件与 `test_oss_quick.py`
