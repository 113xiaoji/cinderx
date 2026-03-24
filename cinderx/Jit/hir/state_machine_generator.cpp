// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/hir/state_machine_generator.h"

#include "cinderx/Jit/hir/hir.h"
#include "cinderx/Jit/hir/cfg.h"
#include "cinderx/Jit/hir/function.h"
#include "cinderx/Common/log.h"

#include <algorithm>

namespace jit::hir {

StateMachineGenerator::StateMachineGenerator(Function* func)
    : func_(func) {}

std::vector<BasicBlock*> StateMachineGenerator::tryGenerateStateMachine(
    Register* iter_reg) {
  // 检查深度限制
  if (!canFlatten(iter_reg, 0)) {
    return {};
  }

  // 检测模式
  auto pattern = detectPattern(iter_reg);
  if (!pattern || !pattern->is_tree_pattern) {
    return {};
  }

  // 生成状态机
  return generateStateMachine(*pattern);
}

bool StateMachineGenerator::canFlatten(Register* iter_reg, int depth) const {
  // 检查深度限制
  if (depth > StateMachineConfig::kMaxFlattenDepth) {
    JIT_DLOG(
        "Cannot flatten: depth {} exceeds max {}",
        depth,
        StateMachineConfig::kMaxFlattenDepth);
    return false;
  }

  // 检查状态数限制
  int state_count = countStates(iter_reg);
  if (state_count > StateMachineConfig::kMaxStates) {
    JIT_DLOG(
        "Cannot flatten: state count {} exceeds max {}",
        state_count,
        StateMachineConfig::kMaxStates);
    return false;
  }

  // 检查是否是树遍历模式
  if (!isTreePattern(iter_reg)) {
    JIT_DLOG("Cannot flatten: not a tree pattern");
    return false;
  }

  return true;
}

std::unique_ptr<YieldFromPatternInfo> StateMachineGenerator::detectPattern(
    Register* iter_reg) {
  auto pattern = std::make_unique<YieldFromPatternInfo>();

  // 检查是否是树遍历模式
  pattern->is_tree_pattern = isTreePattern(iter_reg);
  if (!pattern->is_tree_pattern) {
    return nullptr;
  }

  // 提取迭代器链和字段信息
  Register* current = iter_reg;
  int depth = 0;

  while (current != nullptr && depth <= StateMachineConfig::kMaxFlattenDepth) {
    Instr* instr = current->instr();
    if (instr == nullptr) {
      break;
    }

    // 检查是否是 GetIter 指令
    if (instr->opcode() != Opcode::kGetIter) {
      break;
    }

    pattern->iter_regs.push_back(current);

    // 提取字段信息（尝试识别 LoadField 模式）
    if (instr->NumOperands() > 0) {
      Register* source = instr->GetOperand(0);
      Instr* source_instr = source->instr();

      if (source_instr != nullptr && source_instr->opcode() == Opcode::kLoadField) {
        // 找到了 LoadField 指令，提取字段信息
        YieldFromPatternInfo::FieldInfo field_info;
        field_info.base = source_instr->GetOperand(0);

        // 尝试从 LoadField 指令获取字段索引
        // 注意：LoadField 的字段索引可能存储在指令中
        // 这里使用简化版本，假设字段索引可以通过指令顺序推断
        field_info.field_idx = static_cast<int>(pattern->fields.size());

        pattern->fields.push_back(field_info);
      }
    }

    // 移动到下一个迭代器（通过查找 YieldFrom 指令）
    // TODO: 实现完整的链提取逻辑
    // 当前简化版本：只处理单层
    break;
  }

  pattern->depth = pattern->iter_regs.size();

  // 验证模式完整性
  if (pattern->depth == 0 || pattern->fields.empty()) {
    pattern->is_tree_pattern = false;
    return nullptr;
  }

  return pattern;
}

bool StateMachineGenerator::isTreePattern(Register* iter_reg) const {
  // 基本检查：iter_reg 必须来自 GetIter 指令
  Instr* instr = iter_reg->instr();
  if (instr == nullptr) {
    return false;
  }

  // 检查是否是 GetIter 指令
  if (instr->opcode() != Opcode::kGetIter) {
    return false;
  }

  // 检查 GetIter 的源是否来自 LoadField
  if (instr->NumOperands() == 0) {
    return false;
  }

  Register* source = instr->GetOperand(0);
  Instr* source_instr = source->instr();

  if (source_instr == nullptr) {
    return false;
  }

  // 检查源是否是 LoadField 指令（表示 "self.left" / "self.right"）
  if (source_instr->opcode() == Opcode::kLoadField) {
    return true;
  }

  // 也可能是 LoadAttr 指令（在某些情况下）
  if (source_instr->opcode() == Opcode::kLoadAttr) {
    return true;
  }

  return false;
}

int StateMachineGenerator::countStates(Register* iter_reg) const {
  // 状态计数逻辑：
  // 每个深度为 d 的树遍历生成器产生大约 2^d 个状态
  // 但我们只计算当前层的直接状态

  if (!isTreePattern(iter_reg)) {
    return 0;
  }

  // 查找函数中的 YieldFrom 指令数量
  int yield_from_count = 0;
  int yield_value_count = 0;

  // 遍历函数的所有基本块
  for (BasicBlock& bb : func_->cfg.blocks) {
    for (auto& instr : bb) {
      if (instr.opcode() == Opcode::kYieldFrom ||
          instr.opcode() == Opcode::kOptimizedYieldFrom ||
          instr.opcode() == Opcode::kInlineIter) {
        yield_from_count++;
      } else if (instr.opcode() == Opcode::kYieldValue) {
        yield_value_count++;
      }
    }
  }

  // 估算状态数：
  // - 每个 yield-from 产生 2 个状态（检查 + 执行）
  // - 每个 yield-value 产生 1 个状态
  int estimated_states = yield_from_count * 2 + yield_value_count + 2;  // +2 for init/done

  return estimated_states;
}

std::vector<BasicBlock*> StateMachineGenerator::generateStateMachine(
    const YieldFromPatternInfo& pattern) {
  std::vector<BasicBlock*> blocks;

  // TODO: 实现状态机生成
  // 1. 创建状态分发块
  // 2. 为每个状态创建基本块
  // 3. 添加状态转换逻辑

  return blocks;
}

BasicBlock* StateMachineGenerator::createDispatchBlock(
    const YieldFromPatternInfo& pattern) {
  // TODO: 实现状态分发块生成
  return nullptr;
}

BasicBlock* StateMachineGenerator::createStateBlock(
    const YieldFromPatternInfo& pattern,
    int state_id) {
  // TODO: 实现状态基本块生成
  return nullptr;
}

}  // namespace jit::hir
