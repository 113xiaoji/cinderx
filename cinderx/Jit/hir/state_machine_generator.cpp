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

std::unique_ptr<StateMachine> StateMachineGenerator::tryGenerateStateMachine(
    Register* iter_reg,
    const FrameState* frame_state) {
  // 检查深度限制
  if (!canFlatten(iter_reg, 0)) {
    return nullptr;
  }

  // 检测模式
  auto pattern = detectPattern(iter_reg);
  if (!pattern || !pattern->is_tree_pattern) {
    return nullptr;
  }

  // 构建状态机
  return buildStateMachine(*pattern, frame_state);
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
    for (Instr& instr : bb) {
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

std::unique_ptr<StateMachine> StateMachineGenerator::buildStateMachine(
    const YieldFromPatternInfo& pattern,
    const FrameState* frame_state) {
  auto sm = std::make_unique<StateMachine>();
  sm->func = func_;
  sm->pattern = &pattern;
  sm->frame_state = frame_state;

  // 查找 self 参数（arg 0）
  // 遍历所有寄存器，找到 LoadArg(0) 指令
  for (auto& [id, reg] : func_->env.GetRegisters()) {
    if (reg && reg->instr() && reg->instr()->opcode() == Opcode::kLoadArg) {
      auto* load_arg = static_cast<const LoadArg*>(reg->instr());
      if (load_arg->arg_idx() == 0) {
        sm->self_reg = reg.get();
        break;
      }
    }
  }

  if (!sm->self_reg) {
    JIT_DLOG("Cannot find self argument (arg 0)");
    return nullptr;
  }

  // 创建入口块
  sm->entry_block = createEntryBlock(sm.get());
  if (!sm->entry_block) {
    return nullptr;
  }

  // 创建分发块
  sm->dispatch_block = createDispatchBlock(sm.get());
  if (!sm->dispatch_block) {
    return nullptr;
  }

  // 创建完成块
  sm->done_block = createDoneBlock(sm.get());
  if (!sm->done_block) {
    return nullptr;
  }

  // 创建状态块
  int num_states = countStates(pattern.iter_regs[0]);
  for (int i = 0; i < num_states; i++) {
    BasicBlock* state_bb = createStateBlock(sm.get(), i);
    if (!state_bb) {
      return nullptr;
    }

    State state;
    state.id = i;
    state.bb = state_bb;
    sm->states.push_back(std::move(state));
  }

  return sm;
}

BasicBlock* StateMachineGenerator::createEntryBlock(StateMachine* sm) {
  // 创建入口块
  BasicBlock* entry = func_->cfg.AllocateUnlinkedBlock();

  // 加载当前状态
  sm->state_reg = func_->env.AllocateRegister();
  emitLoadState(entry, sm->state_reg);

  // 检查是否未初始化（state == -1）
  Register* uninit_const = func_->env.AllocateRegister();
  entry->append<LoadConst>(uninit_const, Type::fromCInt(-1, TCInt32));

  Register* is_uninit = func_->env.AllocateRegister();
  entry->append<PrimitiveCompare>(
      is_uninit,
      PrimitiveCompareOp::kEqual,
      sm->state_reg,
      uninit_const);

  // 创建初始化块
  BasicBlock* init_bb = func_->cfg.AllocateUnlinkedBlock();
  emitSaveState(init_bb, sm->state_reg, 0);  // 设置状态为 0
  init_bb->append<Branch>(sm->dispatch_block);

  // 条件跳转：如果未初始化则跳转到 init，否则跳转到 dispatch
  entry->append<CondBranch>(is_uninit, init_bb, sm->dispatch_block);

  return entry;
}

BasicBlock* StateMachineGenerator::createDispatchBlock(StateMachine* sm) {
  // 创建分发块
  BasicBlock* dispatch = func_->cfg.AllocateUnlinkedBlock();

  // 使用 CondBranch 链实现状态分发
  // 对于每个状态 i，检查 state == i，如果是则跳转到 states[i].bb

  BasicBlock* current_bb = dispatch;

  for (size_t i = 0; i < sm->states.size(); ++i) {
    // 创建常量 i
    Register* state_const = func_->env.AllocateRegister();
    current_bb->append<LoadConst>(
        state_const,
        Type::fromCInt(sm->states[i].id, TCInt32));

    // 比较 state == i
    Register* is_state = func_->env.AllocateRegister();
    current_bb->append<PrimitiveCompare>(
        is_state,
        PrimitiveCompareOp::kEqual,
        sm->state_reg,
        state_const);

    // 确定下一个块
    BasicBlock* next_bb = nullptr;
    if (i + 1 < sm->states.size()) {
      // 还有更多状态，创建一个新的检查块
      next_bb = func_->cfg.AllocateUnlinkedBlock();
    } else {
      // 这是最后一个状态，如果都不匹配则跳转到 done
      next_bb = sm->done_block;
    }

    // 条件跳转
    current_bb->append<CondBranch>(
        is_state,
        sm->states[i].bb,
        next_bb);

    current_bb = next_bb;
  }

  return dispatch;
}

BasicBlock* StateMachineGenerator::createDoneBlock(StateMachine* sm) {
  // 创建完成块
  BasicBlock* done = func_->cfg.AllocateUnlinkedBlock();

  // 创建 None 常量
  Register* none_reg = func_->env.AllocateRegister();
  done->append<LoadConst>(none_reg, Type::fromObject(Py_None));

  // 返回 None（表示迭代完成）
  done->append<Return>(none_reg, Type::fromObject(Py_None));

  return done;
}

BasicBlock* StateMachineGenerator::createStateBlock(
    StateMachine* sm,
    int state_id) {
  // 创建状态块
  BasicBlock* state_bb = func_->cfg.AllocateUnlinkedBlock();

  // TODO: 根据状态 ID 生成对应的逻辑
  // 当前实现：简化版本 - 返回 None（占位符）
  //
  // 完整实现需要：
  // 1. 从 pattern 中提取字段访问信息（字段名、偏移量）
  // 2. 根据状态 ID 决定访问哪个字段
  // 3. 生成 LoadField 指令
  // 4. 生成 YieldValue 指令（需要 FrameState）
  // 5. 保存下一个状态
  // 6. 跳转回 dispatch 块

  // 创建 None 常量
  Register* none_reg = func_->env.AllocateRegister();
  state_bb->append<LoadConst>(none_reg, Type::fromObject(Py_None));

  // 返回 None（占位符）
  // 注意：实际实现应该使用 YieldValue，但需要 FrameState 参数
  state_bb->append<Return>(none_reg, Type::fromObject(Py_None));

  return state_bb;
}

void StateMachineGenerator::emitLoadState(
    BasicBlock* bb,
    Register* state_reg) {
  // 生成 LoadState 指令
  bb->append<LoadState>(state_reg);
}

void StateMachineGenerator::emitSaveState(
    BasicBlock* bb,
    Register* state_reg,
    int new_state) {
  // 创建常量寄存器
  Register* const_reg = func_->env.AllocateRegister();
  bb->append<LoadConst>(const_reg, Type::fromCInt(new_state, TCInt32));

  // 生成 SaveState 指令
  bb->append<SaveState>(const_reg);
}

void StateMachineGenerator::emitStateSwitch(
    BasicBlock* bb,
    Register* state_reg,
    const std::vector<BasicBlock*>& targets) {
  // 生成 StateSwitch 指令
  bb->append<StateSwitch>(state_reg);

  // TODO: 添加到各个目标块的边
}

}  // namespace jit::hir
