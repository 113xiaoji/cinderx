# 任务计划：CinderX 3.14 与 CPython 3.14 解释执行路径对比

## 目标
识别 CinderX 3.14 与上游 CPython 3.14 在解释器执行路径上的差异，并给出 CinderX 解释器优化机会的优先级排序。

## 范围
- 解释器分发 / eval 循环
- 帧执行与 trampoline
- opcode 特化 / inline cache 行为
- quickening 与 deopt 交互
- 影响解释器热路径的运行时 hook

## 阶段
1. 定位相关源码与基线版本
2. 对比 CinderX 与 CPython 3.14 的解释器路径
3. 提炼行为差异与性能影响
4. 输出优化优先级建议

## 状态
- [x] 阶段 1
- [x] 阶段 2
- [x] 阶段 3
- [x] 阶段 4

## 备注
- 上游基线：CPython `3.14` 分支 HEAD `a58ea8c21239a23b03446aecd030995bbe40b7a7`（2026-02-27）。
- 本地分支：`bench-cur-7c361dce` @ `ed681292cab44e007effb96471999d172a90448d`。
- 对比重点文件：`interpreter.c`、`borrowed-ceval.c.template`、`Includes/ceval_macros.h`、`Includes/generated_cases.c.h`、`cinder-bytecodes.c` 及 opcode 定义。
