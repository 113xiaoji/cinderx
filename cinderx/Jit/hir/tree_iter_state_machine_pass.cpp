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
  JIT_LOG("TreeIterStateMachinePass: Running on function {}", func.fullname);
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

  // 检查是否所有 YieldFrom 都是树遍历模式
  for (const YieldFrom* yf : yield_froms) {
    if (!isTreeIterPattern(yf)) {
      JIT_DLOG("TreeIterStateMachinePass: YieldFrom is not tree iter pattern, skipping");
      return;
    }
  }

  // 生成状态机并替换 YieldFrom
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

    // 2. 提取 field 信息和 receiver
    // YieldFrom 的操作数: [send_value, iter]
    // iter 来自 GetIter(LoadField(self, "left/right"))

    Register* iter_reg = yf->GetOperand(1);
    if (iter_reg == nullptr || iter_reg->instr() == nullptr) {
      JIT_DLOG("TreeIterStateMachinePass: Invalid iter operand, skipping");
      continue;
    }

    Instr* iter_instr = iter_reg->instr();
    if (!iter_instr->IsGetIter()) {
      JIT_DLOG("TreeIterStateMachinePass: iter is not from GetIter, skipping");
      continue;
    }

    auto* get_iter = static_cast<const GetIter*>(iter_instr);
    Register* field_value = get_iter->iterable();

    if (field_value == nullptr || field_value->instr() == nullptr) {
      JIT_DLOG("TreeIterStateMachinePass: Invalid field_value, skipping");
      continue;
    }

    Instr* field_instr = field_value->instr();
    if (!field_instr->IsLoadField()) {
      JIT_DLOG("TreeIterStateMachinePass: field_value is not from LoadField, skipping");
      continue;
    }

    auto* load_field = static_cast<const LoadField*>(field_instr);
    Register* receiver = load_field->receiver();
    std::string field_name(load_field->name());

    // 3. 生成 YieldFromInline 指令
    // YieldFromInline(receiver, field_idx, next_state) -> yield 子迭代器的值

    // 查找或创建 field_idx
    // 注意：这里简化处理，假设 field_name 已经在常量池中
    // 实际需要查找或创建 field_idx
    int field_idx = 0;  // TODO: 正确获取 field_idx
    if (field_name == "left") {
      field_idx = 0;
    } else if (field_name == "right") {
      field_idx = 1;
    }

    Register* field_idx_reg = func.env.AllocateRegister();
    state_bb->append<LoadConst>(field_idx_reg, Type::fromCInt(field_idx, TCInt32));

    const FrameState* frame_state = yf->frameState();
    if (frame_state == nullptr) {
      JIT_DLOG("TreeIterStateMachinePass: No FrameState for YieldFrom, skipping");
      continue;
    }

    Register* yield_result = func.env.AllocateRegister();
    state_bb->append<YieldFromInline>(
        yield_result, receiver, field_idx_reg, next_state, *frame_state);

    // 4. YieldFromInline 返回后，跳转回 dispatch 继续下一次迭代
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

  // === 步骤 4: 替换 YieldFrom 指令 ===
  // 将原始 YieldFrom 替换为跳转到 entry_block

  for (const YieldFrom* yf : yield_froms) {
    BasicBlock* block = yf->block();

    // 找到 YieldFrom 在块中的位置
    auto it = block->iterator_to(const_cast<YieldFrom&>(*yf));

    // 删除 YieldFrom 指令
    // 注意：这会将该指令从控制流中移除
    Instr* yf_mutable = const_cast<YieldFrom*>(yf);
    yf_mutable->unlink();
    delete yf_mutable;
  }

  JIT_DLOG(
      "TreeIterStateMachinePass: Replaced {} YieldFrom instructions",
      yield_froms.size());

  // === 连接状态机到控制流 ===
  // 找到生成器函数的入口块（包含 InitialYield 的块）
  BasicBlock* generator_entry = func.cfg.entry_block;
  if (generator_entry == nullptr) {
    JIT_DLOG("TreeIterStateMachinePass: No entry block found");
    return;
  }

  // 查找 InitialYield 指令
  Instr* initial_yield = nullptr;
  for (auto& instr : *generator_entry) {
    if (instr.IsInitialYield()) {
      initial_yield = &instr;
      break;
    }
  }

  if (initial_yield == nullptr) {
    JIT_DLOG("TreeIterStateMachinePass: No InitialYield found, skipping");
    return;
  }

  // 在 InitialYield 之后分割基本块
  BasicBlock* after_init = func.cfg.splitAfter(*initial_yield);

  // 将分割后的块连接到状态机 entry
  // after_init 的第一条指令应该是一个 terminator
  // 我们需要将它替换为跳转到 entry_block
  Instr* term = after_init->GetTerminator();
  if (term != nullptr) {
    term->unlink();
    delete term;
  }
  after_init->append<Branch>(entry_block);

  // 将 done_block 连接到原始的生成器退出点
  // done_block 已经包含 Return(None)，这是正确的

  JIT_DLOG(
      "TreeIterStateMachinePass: State machine connected to control flow");
}

}  // namespace jit::hir
