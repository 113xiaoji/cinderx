// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

#include "cinderx/Jit/hir/hir.h"

#include <memory>
#include <vector>

namespace jit::hir {

class BasicBlock;
class Function;
class Register;

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

// 状态机生成器配置
struct StateMachineConfig {
  static constexpr int kMaxFlattenDepth = 3;  // 最大扁平化深度
  static constexpr int kMaxStates = 50;  // 最大状态数
  static constexpr int kMaxCodeSize = 10000;  // 最大代码大小（字节）
};

// 状态机生成器
class StateMachineGenerator {
 public:
  explicit StateMachineGenerator(Function* func);

  // 主入口：尝试将生成器转换为状态机
  // 返回生成的状态机基本块，失败返回 nullptr
  std::vector<BasicBlock*> tryGenerateStateMachine(Register* iter_reg);

  // 检查是否可以扁平化
  bool canFlatten(Register* iter_reg, int depth) const;

 private:
  // 模式识别
  std::unique_ptr<YieldFromPatternInfo> detectPattern(Register* iter_reg);

  // 检查是否是树遍历模式
  bool isTreePattern(Register* iter_reg) const;

  // 统计状态数
  int countStates(Register* iter_reg) const;

  // 生成状态机
  std::vector<BasicBlock*> generateStateMachine(
      const YieldFromPatternInfo& pattern);

  // 生成状态分发块
  BasicBlock* createDispatchBlock(const YieldFromPatternInfo& pattern);

  // 生成状态基本块
  BasicBlock* createStateBlock(
      const YieldFromPatternInfo& pattern,
      int state_id);

 private:
  Function* func_;
};

}  // namespace jit::hir
