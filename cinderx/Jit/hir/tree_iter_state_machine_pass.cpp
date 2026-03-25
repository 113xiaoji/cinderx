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
  // 写入调试文件
  FILE* debug_file = fopen("/tmp/tree_iter_debug.log", "a");
  if (debug_file) {
    fprintf(debug_file, "TreeIterStateMachinePass::Run() called for %s\n", func.fullname.c_str());
    fclose(debug_file);
  }

  JIT_LOG("TreeIterStateMachinePass: Running on function {}", func.fullname);
  JIT_DLOG("TreeIterStateMachinePass: Running on function");

  // 检查是否是树遍历生成器
  if (!isTreeIterGenerator(func)) {
    if (debug_file) {
      debug_file = fopen("/tmp/tree_iter_debug.log", "a");
      fprintf(debug_file, "  -> Not a tree iter generator, skipping\n");
      fclose(debug_file);
    }
    JIT_DLOG("TreeIterStateMachinePass: Not a tree iter generator, skipping");
    return;
  }
  if (debug_file) {
    debug_file = fopen("/tmp/tree_iter_debug.log", "a");
    fprintf(debug_file, "  -> isTreeIterGenerator returned TRUE!\n");
    fclose(debug_file);
  }

  // CRASH DEBUG: 检查函数状态
  debug_file = fopen("/tmp/tree_iter_debug.log", "a");
  fprintf(debug_file, "  -> func.cfg.blocks is valid, proceeding with pass...\n");
  fclose(debug_file);

  // CRASH DEBUG: 强制输出到 stderr
  fprintf(stderr, "=== BEFORE collectYieldFromInstrs ===\n");
  fflush(stderr);

  // 收集所有 YieldFrom 指令
  debug_file = fopen("/tmp/tree_iter_debug.log", "a");
  fprintf(debug_file, "  -> About to call collectYieldFromInstrs...\n");
  fclose(debug_file);

  std::vector<const YieldFrom*> yield_froms;
  collectYieldFromInstrs(func, yield_froms);

  fprintf(stderr, "=== AFTER collectYieldFromInstrs: found %zu ===\n", yield_froms.size());
  fflush(stderr);

  debug_file = fopen("/tmp/tree_iter_debug.log", "a");
  fprintf(debug_file, "  -> collectYieldFromInstrs returned, found %zu YieldFrom\n", yield_froms.size());
  fclose(debug_file);

  debug_file = fopen("/tmp/tree_iter_debug.log", "a");
  fprintf(debug_file, "  -> collectYieldFromInstrs found %zu YieldFrom instructions\n", yield_froms.size());
  fclose(debug_file);

  if (yield_froms.empty()) {
    JIT_DLOG("TreeIterStateMachinePass: No YieldFrom instructions found");
    debug_file = fopen("/tmp/tree_iter_debug.log", "a");
    fprintf(debug_file, "  -> No YieldFrom found, returning\n");
    fclose(debug_file);
    return;
  }

  debug_file = fopen("/tmp/tree_iter_debug.log", "a");
  fprintf(debug_file, "  -> Found %zu YieldFrom instructions, checking patterns...\n", yield_froms.size());
  fclose(debug_file);

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
  fprintf(stderr, "TreeIterStateMachinePass: ✅ Pattern detected! Generating state machine...\n");
  fflush(stderr);
  generateStateMachine(func, yield_froms);
}

bool TreeIterStateMachinePass::isTreeIterGenerator(const Function& func) const {
  // 检查函数是否是 __iter__ 方法
  if (func.code == nullptr) {
    JIT_LOG(
        "TreeIterStateMachinePass::isTreeIterGenerator: func.code is nullptr");
    return false;
  }

  // 检查 co_names 中是否包含 left/right
  if (func.code->co_names == nullptr) {
    JIT_LOG(
        "TreeIterStateMachinePass::isTreeIterGenerator: co_names is nullptr");
    return false;
  }

  Py_ssize_t num_names = PyTuple_GET_SIZE(func.code->co_names);
  bool has_left = false;
  bool has_right = false;

  JIT_LOG(
      "TreeIterStateMachinePass::isTreeIterGenerator: Checking {} names in co_names",
      num_names);

  for (Py_ssize_t i = 0; i < num_names; i++) {
    PyObject* name = PyTuple_GET_ITEM(func.code->co_names, i);
    if (PyUnicode_Check(name)) {
      const char* name_str = PyUnicode_AsUTF8(name);
      if (name_str != nullptr) {
        JIT_LOG("  co_names[{}] = '{}'", i, name_str);
        if (strcmp(name_str, "left") == 0) {
          has_left = true;
          JIT_LOG("    -> Found 'left'!");
        } else if (strcmp(name_str, "right") == 0) {
          has_right = true;
          JIT_LOG("    -> Found 'right'!");
        }
      }
    }
  }

  JIT_LOG(
      "TreeIterStateMachinePass::isTreeIterGenerator: has_left={}, has_right={}",
      has_left,
      has_right);

  return has_left && has_right;
}

void TreeIterStateMachinePass::collectYieldFromInstrs(
    const Function& func,
    std::vector<const YieldFrom*>& out) const {
  JIT_LOG("TreeIterStateMachinePass::collectYieldFromInstrs: Collecting YieldFrom instructions");

  for (const auto& block : func.cfg.blocks) {
    for (const auto& instr : block) {
      if (instr.opcode() == Opcode::kYieldFrom) {
        const YieldFrom* yf = static_cast<const YieldFrom*>(&instr);
        out.push_back(yf);
        JIT_LOG("  Found YieldFrom instruction at {:p}", (void*)&instr);
      }
    }
  }

  JIT_LOG("TreeIterStateMachinePass::collectYieldFromInstrs: Found {} YieldFrom instructions total", out.size());
}

bool TreeIterStateMachinePass::isTreeIterPattern(const YieldFrom* yf) const {
  fprintf(stderr, "=== isTreeIterPattern called ===\n");
  fflush(stderr);

  JIT_LOG("TreeIterStateMachinePass::isTreeIterPattern: Checking YieldFrom");

  if (yf == nullptr) {
    fprintf(stderr, "  -> yf is nullptr, returning false\n");
    fflush(stderr);
    JIT_LOG("  -> yf is nullptr");
    return false;
  }

  fprintf(stderr, "  -> yf is not null, checking operands...\n");
  fflush(stderr);

  // YieldFrom 的操作数顺序: [output, send_value, iter, frame]
  // 我们需要检查操作数 1 (iter)
  if (yf->NumOperands() < 2) {
    fprintf(stderr, "  -> NumOperands = %d, expected >= 2, returning false\n", yf->NumOperands());
    fflush(stderr);
    JIT_LOG("  -> NumOperands = {}, expected >= 2", yf->NumOperands());
    return false;
  }

  fprintf(stderr, "  -> NumOperands >= 2, getting operand 1 (iter)...\n");
  fflush(stderr);

  Register* iter = yf->GetOperand(1);  // 操作数 1 是 iter
  if (iter == nullptr) {
    fprintf(stderr, "  -> iter (operand 1) is nullptr, returning false\n");
    fflush(stderr);
    JIT_LOG("  -> iter (operand 1) is nullptr");
    return false;
  }

  fprintf(stderr, "  -> iter register found at %p\n", (void*)iter);
  fflush(stderr);

  Instr* iter_instr = iter->instr();
  if (iter_instr == nullptr) {
    fprintf(stderr, "  -> iter_instr is nullptr, returning false\n");
    fflush(stderr);
    JIT_LOG("  -> iter_instr is nullptr");
    return false;
  }

  fprintf(stderr, "  -> iter_instr found, opcode = %d\n",
          static_cast<int>(iter_instr->opcode()));
  fflush(stderr);

  // 打印 iter_instr 的所有操作数
  fprintf(stderr, "  -> iter_instr has %zu operands:\n", iter_instr->NumOperands());
  for (size_t i = 0; i < iter_instr->NumOperands(); i++) {
    Register* op = iter_instr->GetOperand(i);
    if (op && op->instr()) {
      fprintf(stderr, "    operand[%zu]: opcode=%d\n",
              i, static_cast<int>(op->instr()->opcode()));
    }
  }
  fflush(stderr);

  JIT_LOG("  -> iter_instr opcode: {}", static_cast<int>(iter_instr->opcode()));

  // === 辅助函数: 检查 register 是否引用 self (LoadArg 0) ===
  std::function<bool(Register*)> is_self_register = [&](Register* reg) -> bool {
    if (reg == nullptr) return false;
    Instr* instr = reg->instr();
    if (instr == nullptr) return false;

    // Direct LoadArg 0 = self
    if (instr->IsLoadArg()) {
      auto* load_arg = static_cast<const LoadArg*>(instr);
      return load_arg->arg_idx() == 0;
    }

    // Phi node: check if all inputs reference self
    if (instr->IsPhi()) {
      auto* phi = static_cast<const Phi*>(instr);
      for (size_t j = 0; j < phi->NumOperands(); j++) {
        if (!is_self_register(phi->GetOperand(j))) {
          return false;
        }
      }
      return phi->NumOperands() > 0;  // True if all inputs are self
    }

    // For other instructions with inputs, check if the first input references self
    // (e.g., Cast, BitCast, etc.)
    if (instr->NumOperands() > 0) {
      return is_self_register(instr->GetOperand(0));
    }

    return false;
  };

  // === 处理 Phi 节点情况 - 追踪 GetIter->LoadField 链 ===
  if (iter_instr->IsPhi()) {
    auto* phi = static_cast<const Phi*>(iter_instr);
    fprintf(stderr, "  -> iter_instr is Phi node with %zu operands\n", phi->NumOperands());
    fflush(stderr);
    JIT_LOG("  -> iter_instr is Phi node");

    // 跟踪哪些输入指向 self.left/right
    bool found_valid_pattern = false;
    std::string field_name;

    for (size_t i = 0; i < phi->NumOperands(); i++) {
      Register* phi_input = phi->GetOperand(i);
      Instr* phi_input_instr = phi_input->instr();

      fprintf(stderr, "    -> Checking Phi input %zu: opcode = %d\n",
              i, static_cast<int>(phi_input_instr->opcode()));
      fflush(stderr);
      JIT_LOG("    -> Checking Phi input {}", i);

      Register* load_field_source = nullptr;

      // Case 1: Input is directly from LoadField or CheckField
      if (phi_input_instr->IsLoadField()) {
        fprintf(stderr, "      -> Phi input is LoadField\n");
        fflush(stderr);
        JIT_LOG("      -> Phi input is LoadField");
        load_field_source = phi_input;
      }
      // Case 2: Input is from CheckField
      else if (phi_input_instr->IsCheckField()) {
        fprintf(stderr, "      -> Phi input is CheckField\n");
        fflush(stderr);
        JIT_LOG("      -> Phi input is CheckField");
        auto* check_field = static_cast<const CheckField*>(phi_input_instr);
        load_field_source = check_field->GetOperand(0);
        if (load_field_source && load_field_source->instr()->IsLoadField()) {
          fprintf(stderr, "      -> CheckField source is LoadField\n");
          fflush(stderr);
          JIT_LOG("      -> CheckField source is LoadField");
        } else {
          load_field_source = nullptr;
        }
      }
      // Case 3: Input is from GetIter
      else if (phi_input_instr->IsGetIter()) {
        fprintf(stderr, "      -> Phi input is GetIter\n");
        fflush(stderr);
        JIT_LOG("      -> Phi input is GetIter");
        auto* get_iter = static_cast<const GetIter*>(phi_input_instr);
        Register* get_iter_source = get_iter->iterable();

        fprintf(stderr, "      -> GetIter source opcode = %d\n",
                static_cast<int>(get_iter_source->instr()->opcode()));
        fflush(stderr);
        JIT_LOG("      -> GetIter source is {}", get_iter_source->instr()->opname());

        // Check if GetIter's source is LoadField or CheckField
        Instr* source_instr = get_iter_source->instr();
        if (source_instr->IsLoadField()) {
          load_field_source = get_iter_source;
          fprintf(stderr, "      -> GetIter source is LoadField\n");
          fflush(stderr);
          JIT_LOG("      -> GetIter source is LoadField");
        } else if (source_instr->IsCheckField()) {
          auto* check_field = static_cast<const CheckField*>(source_instr);
          load_field_source = check_field->GetOperand(0);
          if (load_field_source && load_field_source->instr()->IsLoadField()) {
            fprintf(stderr, "      -> GetIter->CheckField->LoadField chain found\n");
            fflush(stderr);
            JIT_LOG("      -> GetIter->CheckField->LoadField chain found");
          } else {
            load_field_source = nullptr;
          }
        }
      } else {
        // 跳过非 GetIter/LoadField/CheckField 的输入（如 InitialYield）
        fprintf(stderr, "      -> Phi input is not GetIter/LoadField/CheckField, skipping\n");
        fflush(stderr);
        JIT_LOG("      -> Phi input is not GetIter/LoadField/CheckField, skipping");
        continue;
      }

      // If we found a LoadField, check if it's self.left/right
      if (load_field_source) {
        auto* load_field = static_cast<const LoadField*>(load_field_source->instr());
        Register* receiver = load_field->receiver();

        fprintf(stderr, "      -> LoadField receiver opcode = %d\n",
                static_cast<int>(receiver->instr()->opcode()));
        fflush(stderr);

        // Check if receiver ultimately references self (LoadArg 0)
        // This handles both direct LoadArg and Phi node cases
        bool is_self = is_self_register(receiver);

        fprintf(stderr, "      -> is_self = %s\n", is_self ? "true" : "false");
        fflush(stderr);

        if (is_self) {  // self
          std::string current_field_name(load_field->name());
          fprintf(stderr, "      -> Field name = '%s'\n", current_field_name.c_str());
          fflush(stderr);

          if (current_field_name == "left" || current_field_name == "right") {
            if (!found_valid_pattern) {
              // First valid input
              field_name = current_field_name;
              found_valid_pattern = true;
              fprintf(stderr, "      -> Phi input %zu matches pattern! field=%s\n",
                      i, field_name.c_str());
              fflush(stderr);
              JIT_LOG(
                  "      -> Phi input {} matches pattern! field={}",
                  i,
                  field_name);
            } else if (field_name != current_field_name) {
              // Inconsistent field names across inputs
              fprintf(stderr, "      -> Inconsistent field names (%s vs %s)\n",
                      field_name.c_str(), current_field_name.c_str());
              fflush(stderr);
              JIT_LOG(
                  "      -> Inconsistent field names ({} vs {})",
                  field_name,
                  current_field_name);
              found_valid_pattern = false;
              break;
            }
            continue;  // This input is valid
          }
        }
      }

      // This input doesn't match the pattern (and is not InitialYield)
      fprintf(stderr, "      -> Phi input %zu doesn't match pattern\n", i);
      fflush(stderr);
      JIT_LOG("      -> Phi input {} doesn't match pattern", i);
      // Don't break - we can skip non-matching inputs like InitialYield
    }

    if (found_valid_pattern) {
      fprintf(stderr, "  -> ✅ All Phi inputs match pattern! field=%s, pattern MATCHES!\n",
              field_name.c_str());
      fflush(stderr);
      JIT_LOG(
          "  -> ✅ All Phi inputs match pattern! field={}",
          field_name);
      return true;
    } else {
      fprintf(stderr, "  -> Phi node doesn't match pattern\n");
      fflush(stderr);
      JIT_LOG("  -> Phi node doesn't match pattern");
      return false;
    }
  }

  // === 非Phi 情况：直接检查 GetIter -> LoadField/LoadAttr 链 ===
  fprintf(stderr, "  -> iter_instr is NOT Phi, checking GetIter chain...\n");
  fflush(stderr);
  JIT_LOG("  -> iter_instr is NOT Phi, checking GetIter chain...");

  // 检查是否是 GetIter 指令
  if (iter_instr->opcode() != Opcode::kGetIter) {
    fprintf(stderr, "  -> iter_instr is NOT GetIter, skipping\n");
    fflush(stderr);
    JIT_LOG("  -> iter_instr is NOT GetIter, skipping");
    return false;
  }

  fprintf(stderr, "  -> iter_instr is GetIter, checking source...\n");
  fflush(stderr);
  JIT_LOG("  -> iter_instr is GetIter, checking source...");

  // 获取 GetIter 的源
  if (iter_instr->NumOperands() < 1) {
    fprintf(stderr, "  -> GetIter has no operands\n");
    fflush(stderr);
    JIT_LOG("  -> GetIter has no operands");
    return false;
  }

  Register* source = iter_instr->GetOperand(0);
  if (source == nullptr) {
    fprintf(stderr, "  -> source is nullptr\n");
    fflush(stderr);
    JIT_LOG("  -> source is nullptr");
    return false;
  }

  fprintf(stderr, "  -> source register found\n");
  fflush(stderr);

  Instr* source_instr = source->instr();
  if (source_instr == nullptr) {
    fprintf(stderr, "  -> source_instr is nullptr\n");
    fflush(stderr);
    JIT_LOG("  -> source_instr is nullptr");
    return false;
  }

  fprintf(stderr, "  -> source_instr opcode: %d\n",
          static_cast<int>(source_instr->opcode()));
  fflush(stderr);
  JIT_LOG("  -> source_instr opcode: {}", static_cast<int>(source_instr->opcode()));

  // 检查是否是 LoadField（self.left 或 self.right）
  if (source_instr->opcode() == Opcode::kLoadField) {
    fprintf(stderr, "  -> source_instr is LoadField, pattern MATCHES!\n");
    fflush(stderr);
    JIT_LOG("  -> source_instr is LoadField, pattern MATCHES!");
    return true;
  }

  // 检查是否是 LoadAttr（也可以接受）
  if (source_instr->opcode() == Opcode::kLoadAttr) {
    fprintf(stderr, "  -> source_instr is LoadAttr, pattern MATCHES!\n");
    fflush(stderr);
    JIT_LOG("  -> source_instr is LoadAttr, pattern MATCHES!");
    return true;
  }

  fprintf(stderr, "  -> source_instr is neither LoadField nor LoadAttr, pattern does NOT match\n");
  fflush(stderr);
  JIT_LOG("  -> source_instr is neither LoadField nor LoadAttr, pattern does NOT match");
  return false;
}

// 辅助函数：从 Phi 节点或直接指令中提取 GetIter
// 用于处理 iter 寄存器可能来自 Phi 节点的情况
const GetIter* extractGetIterFromPhi(Register* iter_reg) {
  if (iter_reg == nullptr || iter_reg->instr() == nullptr) {
    return nullptr;
  }

  Instr* iter_instr = iter_reg->instr();

  // 情况 1：直接是 GetIter
  if (iter_instr->IsGetIter()) {
    return static_cast<const GetIter*>(iter_instr);
  }

  // 情况 2：是 Phi 节点，遍历输入查找 GetIter
  if (iter_instr->IsPhi()) {
    auto* phi = static_cast<const Phi*>(iter_instr);
    for (size_t i = 0; i < phi->NumOperands(); i++) {
      Instr* input = phi->GetOperand(i)->instr();
      if (input != nullptr && input->IsGetIter()) {
        return static_cast<const GetIter*>(input);
      }
    }
  }

  return nullptr;
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
    // iter 可能来自 Phi 节点或直接来自 GetIter(LoadField(self, "left/right"))

    Register* iter_reg = yf->GetOperand(1);
    if (iter_reg == nullptr) {
      JIT_DLOG("TreeIterStateMachinePass: Invalid iter operand, skipping");
      state_bb->append<Branch>(done_block);
      continue;
    }

    // 使用辅助函数提取 GetIter（处理 Phi 节点情况）
    const GetIter* get_iter = extractGetIterFromPhi(iter_reg);
    if (get_iter == nullptr) {
      JIT_DLOG("TreeIterStateMachinePass: Could not extract GetIter from iter, skipping");
      state_bb->append<Branch>(done_block);
      continue;
    }

    Register* field_value = get_iter->iterable();

    if (field_value == nullptr || field_value->instr() == nullptr) {
      JIT_DLOG("TreeIterStateMachinePass: Invalid field_value, skipping");
      state_bb->append<Branch>(done_block);
      continue;
    }

    Instr* field_instr = field_value->instr();
    if (!field_instr->IsLoadField()) {
      JIT_DLOG("TreeIterStateMachinePass: field_value is not from LoadField, skipping");
      state_bb->append<Branch>(done_block);
      continue;
    }

    auto* load_field = static_cast<const LoadField*>(field_instr);
    Register* receiver = load_field->receiver();

    // 3. 生成 YieldFromInline 指令
    // YieldFromInline(iter, next_state) -> yield 子迭代器的值
    // iter 已经是 GetIter(LoadField(...)) 的结果

    const FrameState* frame_state = yf->frameState();
    if (frame_state == nullptr) {
      JIT_DLOG("TreeIterStateMachinePass: No FrameState for YieldFrom, skipping");
      state_bb->append<Branch>(done_block);
      continue;
    }

    Register* yield_result = func.env.AllocateRegister();
    state_bb->append<YieldFromInline>(
        yield_result, iter_reg, next_state, *frame_state);

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

  // generator_entry (Block 0) 现在只包含 InitialYield，需要添加跳转到 after_init
  generator_entry->append<Branch>(after_init);

  // 将 after_init 连接到状态机 entry
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
