// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/hir/tree_iter_state_machine_pass.h"

#include "cinderx/Jit/hir/cfg.h"
#include "cinderx/Jit/hir/function.h"
#include "cinderx/Jit/hir/hir.h"
#include "cinderx/Jit/hir/printer.h"
#include "cinderx/Common/log.h"
#include "cinderx/python.h"

#include <algorithm>

namespace jit::hir {

void TreeIterStateMachinePass::Run(Function& func) {
  JIT_DLOG("TreeIterStateMachinePass: Running on function");

  // 检查是否是树遍历生成器
  if (!isTreeIterGenerator(func)) {
    JIT_DLOG("TreeIterStateMachinePass: Not a tree iter generator, skipping");
    return;
  }

  // 收集所有 YieldFrom 指令
  std::vector<const YieldFrom*> yield_froms;
  collectYieldFromInstrs(func, yield_froms);

  if (yield_froms.empty()) {
    JIT_DLOG("TreeIterStateMachinePass: No YieldFrom instructions found");
    return;
  }

  JIT_DLOG(
      "TreeIterStateMachinePass: Found {} YieldFrom instructions",
      yield_froms.size());

  // 生成状态机
  generateStateMachine(func, yield_froms);
}

bool TreeIterStateMachinePass::isTreeIterGenerator(const Function& func) const {
  // 检查函数是否是 __iter__ 方法
  if (func.code == nullptr) {
    return false;
  }

  // 检查 co_names 中是否包含 left/right
  if (func.code->co_names == nullptr) {
    return false;
  }

  Py_ssize_t num_names = PyTuple_GET_SIZE(func.code->co_names);
  bool has_left = false;
  bool has_right = false;

  for (Py_ssize_t i = 0; i < num_names; i++) {
    PyObject* name = PyTuple_GET_ITEM(func.code->co_names, i);
    if (PyUnicode_Check(name)) {
      const char* name_str = PyUnicode_AsUTF8(name);
      if (name_str != nullptr) {
        if (strcmp(name_str, "left") == 0) {
          has_left = true;
        } else if (strcmp(name_str, "right") == 0) {
          has_right = true;
        }
      }
    }
  }

  return has_left && has_right;
}

void TreeIterStateMachinePass::collectYieldFromInstrs(
    const Function& func,
    std::vector<const YieldFrom*>& out) const {
  for (const auto& block : func.cfg.blocks) {
    for (const auto& instr : block) {
      if (instr.opcode() == Opcode::kYieldFrom) {
        out.push_back(static_cast<const YieldFrom*>(&instr));
      }
    }
  }
}

bool TreeIterStateMachinePass::isTreeIterPattern(const YieldFrom* yf) const {
  if (yf == nullptr) {
    return false;
  }

  // 获取 iter 操作数
  if (yf->NumOperands() < 2) {
    return false;
  }

  Register* iter = yf->GetOperand(1);
  if (iter == nullptr) {
    return false;
  }

  Instr* iter_instr = iter->instr();
  if (iter_instr == nullptr) {
    return false;
  }

  // 检查是否是 GetIter 指令
  if (iter_instr->opcode() != Opcode::kGetIter) {
    return false;
  }

  // 获取 GetIter 的源
  if (iter_instr->NumOperands() < 1) {
    return false;
  }

  Register* source = iter_instr->GetOperand(0);
  if (source == nullptr) {
    return false;
  }

  Instr* source_instr = source->instr();
  if (source_instr == nullptr) {
    return false;
  }

  // 检查是否是 LoadField（self.left 或 self.right）
  if (source_instr->opcode() == Opcode::kLoadField) {
    return true;
  }

  // 检查是否是 LoadAttr（也可以接受）
  if (source_instr->opcode() == Opcode::kLoadAttr) {
    return true;
  }

  return false;
}

void TreeIterStateMachinePass::generateStateMachine(
    Function& func,
    const std::vector<const YieldFrom*>& yield_froms) {
  JIT_DLOG(
      "TreeIterStateMachinePass: Generating state machine for {} YieldFroms",
      yield_froms.size());

  // 状态机结构:
  //   entry -> init (state=0) -> dispatch
  //   dispatch -> state[0], state[1], ..., done
  //   state[i] -> yield / next_state
  //   done -> return None

  // 创建基本块
  BasicBlock* entry_block = func.cfg.AllocateUnlinkedBlock();
  BasicBlock* init_block = func.cfg.AllocateUnlinkedBlock();
  BasicBlock* dispatch_block = func.cfg.AllocateUnlinkedBlock();
  BasicBlock* done_block = func.cfg.AllocateUnlinkedBlock();

  // 分配状态寄存器
  Register* state_reg = func.env.AllocateRegister();

  // === Entry Block ===
  // 加载当前状态
  entry_block->append<LoadState>(state_reg);

  // 检查是否未初始化 (state == -1)
  Register* uninit_const = func.env.AllocateRegister();
  entry_block->append<LoadConst>(uninit_const, Type::fromCInt(-1, TCInt32));

  Register* is_uninit = func.env.AllocateRegister();
  entry_block->append<PrimitiveCompare>(
      is_uninit, PrimitiveCompareOp::kEqual, state_reg, uninit_const);

  // 条件跳转到 init 或 dispatch
  entry_block->append<CondBranch>(is_uninit, init_block, dispatch_block);

  // === Init Block ===
  // 保存初始状态 (state = 0)
  Register* init_const = func.env.AllocateRegister();
  init_block->append<LoadConst>(init_const, Type::fromCInt(0, TCInt32));
  init_block->append<SaveState>(init_const);

  // 跳转到 dispatch
  init_block->append<Branch>(dispatch_block);

  // === Done Block ===
  // 返回 None
  Register* none_reg = func.env.AllocateRegister();
  done_block->append<LoadConst>(none_reg, Type::fromObject(Py_None));
  done_block->append<Return>(none_reg, Type::fromObject(Py_None));

  // === Dispatch Block ===
  // 创建状态块
  std::vector<BasicBlock*> state_blocks;
  int num_states = static_cast<int>(yield_froms.size());

  for (int i = 0; i < num_states; i++) {
    BasicBlock* state_bb = func.cfg.AllocateUnlinkedBlock();
    state_blocks.push_back(state_bb);

    const YieldFrom* yf = yield_froms[i];

    // 状态块内容:
    // 1. 保存下一个状态 (state = i + 1)
    Register* next_state = func.env.AllocateRegister();
    state_bb->append<LoadConst>(next_state, Type::fromCInt(i + 1, TCInt32));
    state_bb->append<SaveState>(next_state);

    // 2. 从 YieldFrom 指令提取 yield value
    // YieldFrom 的操作数: [send_value, iter]
    // 我们需要获取 iter 的当前值并 yield
    //
    // 对于树遍历模式，iter 来自 GetIter(LoadField(self, "left/right"))
    // 我们应该 yield LoadField 的结果（即子树的值）
    //
    // 但 YieldFrom 本身会处理迭代，所以我们这里简化处理：
    // 生成一个占位符的 YieldValue 指令

    // 获取 send_value (YieldFrom 的第一个操作数)
    Register* send_value = yf->GetOperand(0);

    // 获取 FrameState (用于 YieldValue 指令)
    const FrameState* frame_state = yf->frameState();
    if (frame_state == nullptr) {
      JIT_DLOG("TreeIterStateMachinePass: No FrameState for YieldFrom, skipping");
      continue;
    }

    // 生成 YieldValue 指令
    // YieldValue(send_value) -> yield send_value to caller
    Register* yield_result = func.env.AllocateRegister();
    state_bb->append<YieldValue>(yield_result, send_value, *frame_state);

    // 3. YieldValue 返回后，跳转回 dispatch 继续下一次迭代
    state_bb->append<Branch>(dispatch_block);
  }

  // 构建分发块的条件分支链
  // state == 0 -> state[0], state == 1 -> state[1], ...
  BasicBlock* current_bb = dispatch_block;

  for (int i = 0; i < num_states; i++) {
    Register* state_const = func.env.AllocateRegister();
    current_bb->append<LoadConst>(state_const, Type::fromCInt(i, TCInt32));

    Register* is_state = func.env.AllocateRegister();
    current_bb->append<PrimitiveCompare>(
        is_state, PrimitiveCompareOp::kEqual, state_reg, state_const);

    BasicBlock* next_check = (i + 1 < num_states)
        ? func.cfg.AllocateUnlinkedBlock()
        : done_block;

    current_bb->append<CondBranch>(is_state, state_blocks[i], next_check);
    current_bb = next_check;
  }

  JIT_DLOG(
      "TreeIterStateMachinePass: Generated {} state blocks",
      state_blocks.size());

  // TODO: 将原始 YieldFrom 指令替换为跳转到 entry_block
  // 目前只是生成状态机框架，实际替换需要在后续步骤中完成
}

}  // namespace jit::hir
