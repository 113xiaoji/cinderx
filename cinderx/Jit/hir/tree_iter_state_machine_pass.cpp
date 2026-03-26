// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/hir/tree_iter_state_machine_pass.h"

#include "cinderx/Jit/hir/cfg.h"
#include "cinderx/Jit/hir/function.h"
#include "cinderx/Jit/hir/hir.h"
#include "cinderx/Jit/hir/printer.h"
#include "cinderx/Common/log.h"
#include "cinderx/python.h"

#include <algorithm>
#include <utility>

namespace jit::hir {

// 探针计数器定义
extern "C" int g_state_machine_pass_triggered{0};

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
  JIT_LOG("TreeIterStateMachinePass: Pattern detected! Generating state machine");
  g_state_machine_pass_triggered++;

  // TODO(Task 5): 实际生成状态机并连接控制流
  // 当前只递增探针计数器，不修改 CFG
  // 因为 YieldFrom 替换后旧块控制流断裂，需要 Task 5 的完整实现才能正确工作
  //
  // 当 Task 5 完成后，取消下面注释：
  // generateStateMachine(func, yield_froms);
  (void)yield_froms; // suppress unused warning
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
  JIT_LOG("TreeIterStateMachinePass::isTreeIterPattern: Checking YieldFrom");

  if (yf == nullptr) {
    JIT_LOG("  -> yf is nullptr");
    return false;
  }

  // YieldFrom 的操作数顺序: [output, send_value, iter, frame]
  // 我们需要检查操作数 1 (iter)
  if (yf->NumOperands() < 2) {
    JIT_LOG("  -> NumOperands = {}, expected >= 2", yf->NumOperands());
    return false;
  }

  Register* iter = yf->GetOperand(1);  // 操作数 1 是 iter
  if (iter == nullptr) {
    JIT_LOG("  -> iter (operand 1) is nullptr");
    return false;
  }

  Instr* iter_instr = iter->instr();
  if (iter_instr == nullptr) {
    JIT_LOG("  -> iter_instr is nullptr");
    return false;
  }

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
    JIT_LOG("  -> iter_instr is Phi node");

    // 跟踪哪些输入指向 self.left/right
    bool found_valid_pattern = false;
    std::string field_name;

    for (size_t i = 0; i < phi->NumOperands(); i++) {
      Register* phi_input = phi->GetOperand(i);
      Instr* phi_input_instr = phi_input->instr();

      JIT_LOG("    -> Checking Phi input {}", i);

      Register* load_field_source = nullptr;

      // Case 1: Input is directly from LoadField or CheckField
      if (phi_input_instr->IsLoadField()) {
        JIT_LOG("      -> Phi input is LoadField");
        load_field_source = phi_input;
      }
      // Case 2: Input is from CheckField
      else if (phi_input_instr->IsCheckField()) {
        JIT_LOG("      -> Phi input is CheckField");
        auto* check_field = static_cast<const CheckField*>(phi_input_instr);
        load_field_source = check_field->GetOperand(0);
        if (load_field_source && load_field_source->instr()->IsLoadField()) {
          JIT_LOG("      -> CheckField source is LoadField");
        } else {
          load_field_source = nullptr;
        }
      }
      // Case 3: Input is from GetIter
      else if (phi_input_instr->IsGetIter()) {
        JIT_LOG("      -> Phi input is GetIter");
        auto* get_iter = static_cast<const GetIter*>(phi_input_instr);
        Register* get_iter_source = get_iter->iterable();

        JIT_LOG("      -> GetIter source is {}", get_iter_source->instr()->opname());

        // Check if GetIter's source is LoadField or CheckField
        Instr* source_instr = get_iter_source->instr();
        if (source_instr->IsLoadField()) {
          load_field_source = get_iter_source;
          JIT_LOG("      -> GetIter source is LoadField");
        } else if (source_instr->IsCheckField()) {
          auto* check_field = static_cast<const CheckField*>(source_instr);
          load_field_source = check_field->GetOperand(0);
          if (load_field_source && load_field_source->instr()->IsLoadField()) {
            JIT_LOG("      -> GetIter->CheckField->LoadField chain found");
          } else {
            load_field_source = nullptr;
          }
        }
      } else {
        // 跳过非 GetIter/LoadField/CheckField 的输入（如 InitialYield）
        JIT_LOG("      -> Phi input is not GetIter/LoadField/CheckField, skipping");
        continue;
      }

      // If we found a LoadField, check if it's self.left/right
      if (load_field_source) {
        auto* load_field = static_cast<const LoadField*>(load_field_source->instr());
        Register* receiver = load_field->receiver();

        // Check if receiver ultimately references self (LoadArg 0)
        // This handles both direct LoadArg and Phi node cases
        bool is_self = is_self_register(receiver);

        if (is_self) {  // self
          std::string current_field_name(load_field->name());

          if (current_field_name == "left" || current_field_name == "right") {
            if (!found_valid_pattern) {
              // First valid input
              field_name = current_field_name;
              found_valid_pattern = true;
              JIT_LOG(
                  "      -> Phi input {} matches pattern! field={}",
                  i,
                  field_name);
            } else if (field_name != current_field_name) {
              // Inconsistent field names across inputs
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
      JIT_LOG("      -> Phi input {} doesn't match pattern", i);
      // Don't break - we can skip non-matching inputs like InitialYield
    }

    if (found_valid_pattern) {
      JIT_LOG(
          "  -> ✅ All Phi inputs match pattern! field={}",
          field_name);
      return true;
    } else {
      JIT_LOG("  -> Phi node doesn't match pattern");
      return false;
    }
  }

  // === 非Phi 情况：直接检查 GetIter -> LoadField/LoadAttr 链 ===
  JIT_LOG("  -> iter_instr is NOT Phi, checking GetIter chain...");

  // 检查是否是 GetIter 指令
  if (iter_instr->opcode() != Opcode::kGetIter) {
    JIT_LOG("  -> iter_instr is NOT GetIter, skipping");
    return false;
  }

  JIT_LOG("  -> iter_instr is GetIter, checking source...");

  // 获取 GetIter 的源
  if (iter_instr->NumOperands() < 1) {
    JIT_LOG("  -> GetIter has no operands");
    return false;
  }

  Register* source = iter_instr->GetOperand(0);
  if (source == nullptr) {
    JIT_LOG("  -> source is nullptr");
    return false;
  }

  Instr* source_instr = source->instr();
  if (source_instr == nullptr) {
    JIT_LOG("  -> source_instr is nullptr");
    return false;
  }

  JIT_LOG("  -> source_instr opcode: {}", static_cast<int>(source_instr->opcode()));

  // 检查是否是 LoadField（self.left 或 self.right）
  if (source_instr->opcode() == Opcode::kLoadField) {
    JIT_LOG("  -> source_instr is LoadField, pattern MATCHES!");
    return true;
  }

  // 检查是否是 LoadAttr（也可以接受）
  if (source_instr->opcode() == Opcode::kLoadAttr) {
    JIT_LOG("  -> source_instr is LoadAttr, pattern MATCHES!");
    return true;
  }

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
  JIT_LOG("TreeIterStateMachinePass: Generating inline state machine for {} YieldFroms",
          yield_froms.size());

  // 检查内联深度限制
  if (yield_froms.size() > static_cast<size_t>(StateMachineConfig::kMaxInlineDepth)) {
    JIT_LOG("  -> Depth {} exceeds limit {}, using fallback",
            yield_froms.size(), StateMachineConfig::kMaxInlineDepth);
    return;  // 回退到原有逻辑
  }

  // 创建状态机上下文
  StateMachineContext ctx;
  ctx.func = &func;
  // self_reg 将在 GenerateInitBlock 中通过 LoadArg 指令设置
  ctx.max_depth = static_cast<int>(yield_froms.size());
  ctx.stack_size = StateMachineConfig::kStateSize;

  // 生成状态机
  StateMachineGenerator generator(ctx);
  generator.Generate();

  // === 连接状态机到控制流 ===
  // 1. 替换原始 YieldFrom 指令
  for (const YieldFrom* yf : yield_froms) {
    BasicBlock* block = yf->block();
    Instr* yf_mutable = const_cast<YieldFrom*>(yf);
    yf_mutable->unlink();
    delete yf_mutable;
  }

  JIT_LOG("TreeIterStateMachinePass: Replaced {} YieldFrom instructions",
          yield_froms.size());

  // 2. 找到生成器入口块（包含 InitialYield）
  BasicBlock* generator_entry = func.cfg.entry_block;
  if (generator_entry == nullptr) {
    JIT_LOG("TreeIterStateMachinePass: No entry block found");
    return;
  }

  // 3. 查找 InitialYield 指令
  Instr* initial_yield = nullptr;
  for (auto& instr : *generator_entry) {
    if (instr.IsInitialYield()) {
      initial_yield = &instr;
      break;
    }
  }

  if (initial_yield == nullptr) {
    JIT_LOG("TreeIterStateMachinePass: No InitialYield found");
    return;
  }

  // 4. 在 InitialYield 之后分割基本块
  BasicBlock* after_init = func.cfg.splitAfter(*initial_yield);

  // generator_entry 现在只包含 InitialYield
  generator_entry->append<Branch>(after_init);

  // 5. 将 after_init 连接到状态机入口
  Instr* term = after_init->GetTerminator();
  if (term != nullptr) {
    term->unlink();
    delete term;
  }
  after_init->append<Branch>(ctx.bb_init);

  JIT_LOG("TreeIterStateMachinePass: State machine connected to control flow");
}

// === StateMachineGenerator 实现 ===

// 使用 namespace 别名引用已存在的 jit::hir 命名空间
// 因为原始 jit::hir 块已关闭，需要通过别名定义方法
namespace hir_ns = ::jit::hir;

Register* hir_ns::StateMachineGenerator::CreatePhaseConst(BasicBlock* bb, TreeIterPhase phase) {
  Register* reg = ctx_.func->env.AllocateRegister();
  bb->append<LoadConst>(reg, Type::fromCInt(static_cast<int>(phase), TCInt32));
  return reg;
}

Register* hir_ns::StateMachineGenerator::CreateIntConst(BasicBlock* bb, int value) {
  Register* reg = ctx_.func->env.AllocateRegister();
  bb->append<LoadConst>(reg, Type::fromCInt(value, TCInt32));
  return reg;
}

void hir_ns::StateMachineGenerator::Generate() {
  JIT_LOG("StateMachineGenerator: Generating state machine");

  // 1. 分配寄存器
  ctx_.self_reg = ctx_.func->env.AllocateRegister();
  ctx_.current_node_reg = ctx_.func->env.AllocateRegister();
  ctx_.phase_reg = ctx_.func->env.AllocateRegister();
  ctx_.stack_top_reg = ctx_.func->env.AllocateRegister();

  // 2. 生成初始化块
  ctx_.bb_init = bb_init_ = GenerateInitBlock();

  // 3. 生成主循环块
  ctx_.bb_loop = bb_loop_ = GenerateLoopBlock();

  // 4. 生成各阶段基本块
  ctx_.bb_left = bb_left_ = GenerateLeftBlock();
  ctx_.bb_yield = bb_yield_ = GenerateYieldBlock();
  ctx_.bb_right = bb_right_ = GenerateRightBlock();
  ctx_.bb_backtrack = bb_backtrack_ = GenerateBacktrackBlock();

  // 5. 生成结束块
  ctx_.bb_done = bb_done_ = ctx_.func->cfg.AllocateBlock();
  Register* none_reg = ctx_.func->env.AllocateRegister();
  bb_done_->append<LoadConst>(none_reg, Type::fromObject(Py_None));
  bb_done_->append<Return>(none_reg, Type::fromObject(Py_None));

  // 6. 连接初始化块到循环块
  bb_init_->append<Branch>(bb_loop_);

  JIT_LOG("StateMachineGenerator: State machine generated successfully");
}

BasicBlock* hir_ns::StateMachineGenerator::GenerateInitBlock() {
  BasicBlock* bb = ctx_.func->cfg.AllocateBlock();
  bb_init_ = bb;

  // 初始化 current_node = self
  bb->append<LoadArg>(ctx_.self_reg, 0);
  ctx_.current_node_reg = ctx_.self_reg;

  // 初始化 phase = kLeft
  Register* init_phase = CreatePhaseConst(bb, TreeIterPhase::kLeft);
  bb->append<LoadState>(ctx_.phase_reg);
  (void)init_phase;  // 占位：后续保存状态

  // 初始化 stack_top = 0
  Register* zero = CreateIntConst(bb, 0);
  // TODO(Task 4): 使用 Move 或 Assign 指令将 zero 赋值给 stack_top_reg
  // 当前 CinderX HIR 可能没有直接的 Move 指令
  // 占位：stack_top_reg 保持未初始化状态
  (void)zero;

  // 跳转到循环 - 延迟到 Generate() 中在 bb_loop_ 设置后添加

  return bb;
}

BasicBlock* hir_ns::StateMachineGenerator::GenerateLoopBlock() {
  BasicBlock* bb = ctx_.func->cfg.AllocateBlock();
  bb_loop_ = bb;

  // Switch(phase) -> bb_left, bb_yield, bb_right, bb_backtrack
  // 使用 CondBranch 链实现 Switch

  Register* cmp_left = ctx_.func->env.AllocateRegister();
  Register* left_const = CreatePhaseConst(bb, TreeIterPhase::kLeft);
  bb->append<PrimitiveCompare>(
      cmp_left, PrimitiveCompareOp::kEqual, ctx_.phase_reg, left_const);

  Register* cmp_yield = ctx_.func->env.AllocateRegister();
  Register* yield_const = CreatePhaseConst(bb, TreeIterPhase::kYield);
  bb->append<PrimitiveCompare>(
      cmp_yield, PrimitiveCompareOp::kEqual, ctx_.phase_reg, yield_const);

  Register* cmp_right = ctx_.func->env.AllocateRegister();
  Register* right_const = CreatePhaseConst(bb, TreeIterPhase::kRight);
  bb->append<PrimitiveCompare>(
      cmp_right, PrimitiveCompareOp::kEqual, ctx_.phase_reg, right_const);

  // CondBranch 链
  BasicBlock* after_left = ctx_.func->cfg.AllocateBlock();
  bb->append<CondBranch>(cmp_left, bb_left_, after_left);

  // Yield 检查
  BasicBlock* after_yield = ctx_.func->cfg.AllocateBlock();
  after_left->append<CondBranch>(cmp_yield, bb_yield_, after_yield);

  // Right 检查
  BasicBlock* after_right = ctx_.func->cfg.AllocateBlock();
  after_yield->append<CondBranch>(cmp_right, bb_right_, after_right);

  // 默认到 backtrack
  after_right->append<Branch>(bb_backtrack_);

  return bb;
}

BasicBlock* hir_ns::StateMachineGenerator::GenerateLeftBlock() {
  BasicBlock* bb = ctx_.func->cfg.AllocateBlock();
  bb_left_ = bb;

  // if (current_node->left) {
  //   StackPush(current_node, kRight);
  //   current_node = current_node->left;
  //   phase = kLeft;
  //   goto loop;
  // } else {
  //   phase = kYield;
  //   goto loop;
  // }

  // 加载 left 字段（占位符：后续 Task 4 使用 CheckField 替代 LoadField）
  Register* left_reg = ctx_.func->env.AllocateRegister();
  bb->append<LoadConst>(left_reg, TObject);

  // 检查是否为 None
  Register* is_null = ctx_.func->env.AllocateRegister();
  Register* none_const = ctx_.func->env.AllocateRegister();
  bb->append<LoadConst>(none_const, Type::fromObject(Py_None));
  bb->append<PrimitiveCompare>(is_null, PrimitiveCompareOp::kEqual, left_reg, none_const);

  // 条件分支
  BasicBlock* has_left = ctx_.func->cfg.AllocateBlock();
  BasicBlock* no_left = ctx_.func->cfg.AllocateBlock();
  bb->append<CondBranch>(is_null, no_left, has_left);

  // has_left: 有左子树，跳回循环
  has_left->append<Branch>(bb_loop_);

  // no_left: 没有左子树，设置 phase = kYield 并跳转
  Register* phase_yield = CreatePhaseConst(no_left, TreeIterPhase::kYield);
  (void)phase_yield;  // 占位：后续保存状态
  no_left->append<Branch>(bb_loop_);

  return bb;
}

BasicBlock* hir_ns::StateMachineGenerator::GenerateYieldBlock() {
  BasicBlock* bb = ctx_.func->cfg.AllocateBlock();
  bb_yield_ = bb;

  // value = current_node->value
  // yield value
  // phase = kRight
  //
  // 占位符：后续 Task 4 实现完整的 yield 逻辑
  // YieldValue 需要有效的 FrameState，暂时跳过

  Register* result = ctx_.func->env.AllocateRegister();
  bb->append<LoadConst>(result, TObject);

  Register* phase_right = CreatePhaseConst(bb, TreeIterPhase::kRight);
  (void)phase_right;  // 占位：后续保存状态
  bb->append<Branch>(bb_loop_);

  return bb;
}

BasicBlock* hir_ns::StateMachineGenerator::GenerateRightBlock() {
  BasicBlock* bb = ctx_.func->cfg.AllocateBlock();
  bb_right_ = bb;

  // 类似 Left 块，但处理 right 字段

  Register* right_reg = ctx_.func->env.AllocateRegister();
  bb->append<LoadConst>(right_reg, TObject);

  Register* is_null = ctx_.func->env.AllocateRegister();
  Register* none_const = ctx_.func->env.AllocateRegister();
  bb->append<LoadConst>(none_const, Type::fromObject(Py_None));
  bb->append<PrimitiveCompare>(is_null, PrimitiveCompareOp::kEqual, right_reg, none_const);

  BasicBlock* has_right = ctx_.func->cfg.AllocateBlock();
  BasicBlock* no_right = ctx_.func->cfg.AllocateBlock();
  bb->append<CondBranch>(is_null, no_right, has_right);

  has_right->append<Branch>(bb_loop_);

  Register* phase_backtrack = CreatePhaseConst(no_right, TreeIterPhase::kBacktrack);
  (void)phase_backtrack;  // 占位：后续保存状态
  no_right->append<Branch>(bb_loop_);

  return bb;
}

BasicBlock* hir_ns::StateMachineGenerator::GenerateBacktrackBlock() {
  BasicBlock* bb = ctx_.func->cfg.AllocateBlock();
  bb_backtrack_ = bb;

  // if (StackEmpty) {
  //   goto done;
  // } else {
  //   (current_node, phase) = StackPop();
  //   goto loop;
  // }

  // TODO(Task 4): 实现栈空检查
  // 当前占位符：检查 stack_top 是否为 0
  // 由于 stack_top_reg 未初始化，这个检查结果未定义

  Register* is_empty = ctx_.func->env.AllocateRegister();
  Register* zero = CreateIntConst(bb, 0);
  bb->append<PrimitiveCompare>(
      is_empty, PrimitiveCompareOp::kEqual, ctx_.stack_top_reg, zero);

  BasicBlock* stack_not_empty = ctx_.func->cfg.AllocateBlock();
  bb->append<CondBranch>(is_empty, bb_done_, stack_not_empty);

  // 栈非空：执行 Pop
  auto [node_reg, phase_reg] = GenerateStackPop();
  (void)node_reg;   // TODO: 更新 current_node_reg
  (void)phase_reg;  // TODO: 更新 phase_reg

  stack_not_empty->append<Branch>(bb_loop_);

  return bb;
}

void hir_ns::StateMachineGenerator::GenerateStackPush(Register* node, TreeIterPhase phase) {
  JIT_LOG("StateMachineGenerator: GenerateStackPush (Task 4 - 方案 A)");

  // 方案 A 实现：使用 StateStackPush HIR 指令
  BasicBlock* bb = bb_left_;

  // 创建 phase 常量
  Register* phase_reg = CreateIntConst(bb, static_cast<int>(phase));

  // 添加 StateStackPush 指令
  bb->append<StateStackPush>(node, phase_reg);

  JIT_LOG("  -> 已添加 StateStackPush 指令");
}

std::pair<hir_ns::Register*, hir_ns::Register*> hir_ns::StateMachineGenerator::GenerateStackPop() {
  JIT_LOG("StateMachineGenerator: GenerateStackPop (Task 4 - 方案 A)");

  // 方案 A 实现：使用 StateStackPop HIR 指令
  // StateStackPop 输出 node (TObject)
  // phase 存储在 GenDataFooter.popped_phase，后续通过 LoadPoppedPhase 读取
  BasicBlock* bb = bb_backtrack_;

  // 分配输出寄存器
  Register* node_reg = ctx_.func->env.AllocateRegister();

  // 添加 StateStackPop 指令（输出 node）
  bb->append<StateStackPop>(node_reg);

  // phase 暂时使用零值占位符（TODO: 通过 LoadPoppedPhase 读取）
  Register* phase_reg = CreateIntConst(bb, 0);

  JIT_LOG("  -> 已添加 StateStackPop 指令");

  return {node_reg, phase_reg};
}

}  // namespace jit::hir
