// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

#include "cinderx/Jit/hir/hir.h"

#include <memory>
#include <vector>
#include <unordered_map>

namespace jit::hir {

class BasicBlock;
class Function;
class Register;

// 状态机状态枚举
enum class GeneratorState : int32_t {
  kUninit = -1,    // 未初始化
  kInit = 0,       // 初始状态
  // 动态生成的状态（1, 2, 3, ...）
  kDone = INT32_MAX  // 完成状态
};

// Yield-from 模式信息
struct YieldFromPatternInfo {
  bool is_tree_pattern;  // 是否是树遍历模式
  int depth;  // 嵌套深度
  std::vector<Register*> iter_regs;  // 迭代器寄存器链

  // 字段信息（用于识别 "self.left" / "self.right"）
  struct FieldInfo {
    Register* base;  // 基础对象（通常是 self）
    int field_idx;  // 字段索引
  };
  std::vector<FieldInfo> fields;
};

// 状态机配置
struct StateMachineConfig {
  static constexpr int kMaxFlattenDepth = 3;  // 最大扁平化深度
  static constexpr int kMaxStates = 50;  // 最大状态数
  static constexpr int kMaxCodeSize = 10000;  // 最大代码大小（字节）
};

// 状态转换类型
enum class TransitionType {
  kYieldValue,      // yield 一个值
  kYieldFromLeft,   // yield from left 子树
  kYieldFromRight,  // yield from right 子树
  kDone             // 完成
};

// 状态转换
struct StateTransition {
  TransitionType type;
  int target_state;  // 目标状态（-1 表示完成）
  Register* value_reg;  // yield 的值寄存器（kYieldValue）
  int field_idx;  // 字段索引（kYieldFromLeft/Right）
};

// 状态机状态
struct State {
  int id;  // 状态 ID
  BasicBlock* bb;  // 对应的基本块
  std::vector<StateTransition> transitions;  // 可能的转换
};

// 状态机
struct StateMachine {
  Function* func;  // 所属函数
  BasicBlock* entry_block;  // 入口块
  BasicBlock* dispatch_block;  // 分发块
  BasicBlock* done_block;  // 完成块
  std::vector<State> states;  // 状态列表
  Register* state_reg;  // 状态寄存器

  // 字段访问信息
  struct FieldAccess {
    Register* base;  // 基础对象
    int field_idx;  // 字段索引
    Register* field_reg;  // 字段寄存器
  };
  std::vector<FieldAccess> field_accesses;
};

// 状态机生成器
class StateMachineGenerator {
 public:
  explicit StateMachineGenerator(Function* func);

  // 主入口：尝试将生成器转换为状态机
  // 返回生成的状态机，失败返回 nullptr
  std::unique_ptr<StateMachine> tryGenerateStateMachine(Register* iter_reg);

  // 检查是否可以扁平化
  bool canFlatten(Register* iter_reg, int depth) const;

 private:
  // 模式识别
  std::unique_ptr<YieldFromPatternInfo> detectPattern(Register* iter_reg);

  // 检查是否是树遍历模式
  bool isTreePattern(Register* iter_reg) const;

  // 统计状态数
  int countStates(Register* iter_reg) const;

  // 状态机构建
  std::unique_ptr<StateMachine> buildStateMachine(
      const YieldFromPatternInfo& pattern);

  // 创建基本块
  BasicBlock* createEntryBlock(StateMachine* sm);
  BasicBlock* createDispatchBlock(StateMachine* sm);
  BasicBlock* createDoneBlock(StateMachine* sm);
  BasicBlock* createStateBlock(StateMachine* sm, int state_id);

  // 生成 HIR 指令
  void emitLoadState(BasicBlock* bb, Register* state_reg);
  void emitSaveState(BasicBlock* bb, Register* state_reg, int new_state);
  void emitStateSwitch(
      BasicBlock* bb,
      Register* state_reg,
      const std::vector<BasicBlock*>& targets);

 private:
  Function* func_;
};

}  // namespace jit::hir
