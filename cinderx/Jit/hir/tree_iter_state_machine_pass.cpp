// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/hir/tree_iter_state_machine_pass.h"

#include "cinderx/Jit/hir/cfg.h"
#include "cinderx/Jit/hir/function.h"
#include "cinderx/Jit/hir/hir.h"
#include "cinderx/Jit/hir/pass.h"
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

  if (!isTreeIterGenerator(func)) {
    return;
  }

  std::vector<const YieldFrom*> yield_froms;
  collectYieldFromInstrs(func, yield_froms);

  if (yield_froms.empty()) {
    return;
  }

  for (const YieldFrom* yf : yield_froms) {
    if (!isTreeIterPattern(yf)) {
      return;
    }
  }

  JIT_LOG("TreeIterStateMachinePass: Pattern detected! Generating state machine");
  g_state_machine_pass_triggered++;

  generateStateMachine(func, yield_froms);
}

bool TreeIterStateMachinePass::isTreeIterGenerator(const Function& func) const {
  if (func.code == nullptr) {
    return false;
  }
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
  for (auto& block : func.cfg.blocks) {
    for (auto& instr : block) {
      if (instr.IsYieldFrom()) {
        out.push_back(static_cast<const YieldFrom*>(&instr));
      }
    }
  }
}

bool TreeIterStateMachinePass::isTreeIterPattern(const YieldFrom* yf) const {
  auto* send_instr = yf->GetOperand(0)->instr();
  if (send_instr == nullptr || !send_instr->IsSend()) {
    return false;
  }

  auto* iter_reg = static_cast<const Send*>(send_instr)->GetOperand(0);
  Instr* iter_instr = iter_reg->instr();
  if (iter_instr == nullptr) {
    return false;
  }

  auto* get_iter = findGetIter(iter_reg);
  if (get_iter == nullptr) {
    return false;
  }

  auto* source = get_iter->GetOperand(0)->instr();
  if (source == nullptr || !source->IsCheckField()) {
    return false;
  }

  auto* check_field = static_cast<const CheckField*>(source);
  auto* load_field_instr = check_field->GetOperand(0)->instr();
  if (load_field_instr == nullptr || !load_field_instr->IsLoadField()) {
    return false;
  }

  std::string field_name(static_cast<const LoadField*>(load_field_instr)->name());
  return field_name == "left" || field_name == "right";
}

const GetIter* TreeIterStateMachinePass::findGetIter(Register* iter_reg) const {
  Instr* iter_instr = iter_reg->instr();
  if (iter_instr == nullptr) {
    return nullptr;
  }

  if (iter_instr->IsGetIter()) {
    return static_cast<const GetIter*>(iter_instr);
  }

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
  // 提取字段信息
  struct FieldInfo {
    std::string name;
    std::size_t offset{0};
  };
  std::unordered_map<std::string, FieldInfo> field_map;

  for (auto& block : func.cfg.blocks) {
    for (auto& instr : block) {
      if (instr.IsLoadField()) {
        auto* lf = static_cast<LoadField*>(&instr);
        std::string fname(lf->name());
        if (fname == "left" || fname == "right" || fname == "value") {
          if (field_map.find(fname) == field_map.end()) {
            field_map[fname] = {fname, lf->offset()};
          }
        }
      }
    }
  }

  if (field_map.count("left") == 0 || field_map.count("right") == 0 ||
      field_map.count("value") == 0) {
    return;
  }

  JIT_LOG(
      "Field offsets: left={}, right={}, value={}",
      field_map["left"].offset,
      field_map["right"].offset,
      field_map["value"].offset);

  // 找到 self 寄存器和 InitialYield
  Register* self_reg = nullptr;
  Instr* initial_yield = nullptr;

  for (auto& block : func.cfg.blocks) {
    for (auto& instr : block) {
      if (instr.IsLoadArg()) {
        auto* la = static_cast<LoadArg*>(&instr);
        if (la->arg_idx() == 0 && self_reg == nullptr) {
          self_reg = la->output();
        }
      }
      if (instr.IsInitialYield()) {
        initial_yield = &instr;
      }
    }
  }

  if (self_reg == nullptr || initial_yield == nullptr) {
    return;
  }

  // 在 generateStateMachine 之前保存 init_block 指针
  auto* init_block = initial_yield->block();

  // 找到原始 YieldValue 的 FrameState
  FrameState* yield_frame_state = nullptr;
  for (auto& block : func.cfg.blocks) {
    for (auto& instr : block) {
      if (instr.IsYieldValue()) {
        auto* yv = static_cast<YieldValue*>(&instr);
        yield_frame_state = yv->frameState();
        break;
      }
    }
    if (yield_frame_state != nullptr) {
      break;
    }
  }
  JIT_LOG("TreeIterStateMachinePass: yield_frame_state={}",
          (void*)yield_frame_state);

  StateMachineContext ctx;
  ctx.func = &func;
  ctx.self_reg = self_reg;
  ctx.max_depth = static_cast<int>(yield_froms.size());
  ctx.stack_size = StateMachineConfig::kStateSize;
  ctx.yield_frame_state = yield_frame_state;
  ctx.init_block = init_block;

  // CFG 集成：先 splitAfter，再生成状态机
  // 这样 Generate() 可以安全地在 init_block 中添加 LoadConst
  auto* tail = func.cfg.splitAfter(*initial_yield);
  // init_block 现在只包含 [LoadArg, InitialYield]，没有终止符

  StateMachineGenerator generator(ctx);
  generator.Generate(
      field_map["left"].offset,
      field_map["right"].offset,
      field_map["value"].offset);

  // init_block 分支到状态机入口 (bb_loop)
  init_block->append<Branch>(generator.bb_loop());

  removeUnreachableBlocks(func);

  // 重新推断所有寄存器类型 — 状态机 pass 在 Simplify 之后运行，
  // 新创建的指令没有经过类型推断，寄存器默认为 TTop。
  // TTop 在 LIR 的 hirTypeToDataType 中匹配不到任何整数类型，
  // 会返回 kObject，导致 RefcountInsertion 为原始值插入 XDecref。
  reflowTypes(func);

  JIT_LOG("TreeIterStateMachinePass: State machine generated and integrated");
}

// === StateMachineGenerator ===

namespace {

Register* CreateIntConst(Function& func, BasicBlock* bb, int value) {
  Register* reg = func.env.AllocateRegister();
  bb->append<LoadConst>(reg, Type::fromCInt(value, TCInt32));
  return reg;
}

Register* CreatePhaseConst(Function& func, BasicBlock* bb, TreeIterPhase phase) {
  return CreateIntConst(func, bb, static_cast<int>(phase));
}

} // anonymous namespace

void StateMachineGenerator::Generate(
    std::size_t left_offset,
    std::size_t right_offset,
    std::size_t value_offset) {
  Function& func = *ctx_.func;
  auto& env = func.env;
  auto& cfg = func.cfg;

  JIT_LOG("StateMachineGenerator: Generating GenDataFooter-based state machine");

  // === 分配所有基本块 ===
  bb_init_ = ctx_.init_block;
  BasicBlock* bb_loop = cfg.AllocateBlock();
  BasicBlock* bb_check_yield = cfg.AllocateBlock();
  BasicBlock* bb_check_right = cfg.AllocateBlock();
  BasicBlock* bb_left = cfg.AllocateBlock();
  BasicBlock* bb_check_null_left = cfg.AllocateBlock();
  BasicBlock* bb_has_left = cfg.AllocateBlock();
  BasicBlock* bb_no_left = cfg.AllocateBlock();
  BasicBlock* bb_yield = cfg.AllocateBlock();
  BasicBlock* bb_after_yield = cfg.AllocateBlock();
  BasicBlock* bb_right = cfg.AllocateBlock();
  BasicBlock* bb_check_null_right = cfg.AllocateBlock();
  BasicBlock* bb_has_right = cfg.AllocateBlock();
  BasicBlock* bb_no_right = cfg.AllocateBlock();
  BasicBlock* bb_backtrack = cfg.AllocateBlock();
  BasicBlock* bb_pop = cfg.AllocateBlock();
  BasicBlock* bb_done = cfg.AllocateBlock();

  bb_loop_ = bb_loop;
  bb_done_ = bb_done;

  // === bb_init_: 保存初始状态到 GenDataFooter ===
  // 关键: SaveCurrentNode 必须在 InitialYield 之前！
  // InitialYield 会导致 yield/resume，clobber 所有调用者保存寄存器。
  // 如果 SaveCurrentNode 在 InitialYield 之后，self_reg 会被覆盖为垃圾值。
  auto init_iter = bb_init_->begin();
  ++init_iter; // skip LoadArg, point to InitialYield
  auto* save_node = SaveCurrentNode::create(ctx_.self_reg);
  bb_init_->insert(save_node, init_iter);
  Register* init_phase = env.AllocateRegister();
  auto* load_phase = LoadConst::create(
      init_phase,
      Type::fromCInt(static_cast<int>(TreeIterPhase::kLeft), TCInt32));
  bb_init_->insert(load_phase, init_iter);
  auto* save_phase = SavePhase::create(init_phase);
  bb_init_->insert(save_phase, init_iter);
  // (Branch to bb_loop is added by generateStateMachine after this call)

  // === bb_loop: 从 GenDataFooter 加载 phase 并 dispatch ===
  // 注意：不在 bb_loop 中加载 current，因为 LoadPhase 是 C 函数调用
  // 会 clobber 调用者保存的寄存器。每个块独立加载自己需要的值。
  Register* phase = env.AllocateRegister();
  bb_loop->append<LoadPhase>(phase);

  // phase == kLeft?
  Register* kLeft_const = CreatePhaseConst(func, bb_loop, TreeIterPhase::kLeft);
  Register* cmp_left = env.AllocateRegister();
  bb_loop->append<PrimitiveCompare>(
      cmp_left, PrimitiveCompareOp::kEqual, phase, kLeft_const);
  bb_loop->append<CondBranch>(cmp_left, bb_left, bb_check_yield);

  // === bb_check_yield: phase == kYield? ===
  Register* phase_cy = env.AllocateRegister();
  bb_check_yield->append<LoadPhase>(phase_cy);
  Register* kYield_const =
      CreatePhaseConst(func, bb_check_yield, TreeIterPhase::kYield);
  Register* cmp_yield = env.AllocateRegister();
  bb_check_yield->append<PrimitiveCompare>(
      cmp_yield, PrimitiveCompareOp::kEqual, phase_cy, kYield_const);
  bb_check_yield->append<CondBranch>(cmp_yield, bb_yield, bb_check_right);

  // === bb_check_right: phase == kRight? ===
  Register* phase_cr = env.AllocateRegister();
  bb_check_right->append<LoadPhase>(phase_cr);
  Register* kRight_const =
      CreatePhaseConst(func, bb_check_right, TreeIterPhase::kRight);
  Register* cmp_right = env.AllocateRegister();
  bb_check_right->append<PrimitiveCompare>(
      cmp_right, PrimitiveCompareOp::kEqual, phase_cr, kRight_const);
  bb_check_right->append<CondBranch>(cmp_right, bb_right, bb_backtrack);

  // === bb_left: 加载 current，检查 left 子树 ===
  Register* current_left = env.AllocateRegister();
  bb_left->append<LoadCurrentNode>(current_left);
  Register* left_child = env.AllocateRegister();
  bb_left->append<LoadField>(
      left_child, current_left, "left", left_offset, TOptObject);
  // Python 中 None 存储为 Py_None 指针（非 StaticPython），不是 nullptr
  // 先比较 Py_None，若不匹配再比较 nullptr（兼容 StaticPython 内联存储）
  Register* none_left = env.AllocateRegister();
  bb_left->append<LoadConst>(none_left, Type::fromObject(Py_None));
  Register* cmp_none_left = env.AllocateRegister();
  bb_left->append<PrimitiveCompare>(
      cmp_none_left, PrimitiveCompareOp::kEqual, left_child, none_left);
  bb_left->append<CondBranch>(cmp_none_left, bb_no_left, bb_check_null_left);

  // === bb_check_null_left: 也检查 nullptr（兼容 StaticPython 内联存储） ===
  Register* null_left = env.AllocateRegister();
  bb_check_null_left->append<LoadConst>(null_left, Type::fromCInt(0, TCInt64));
  Register* cmp_null_left = env.AllocateRegister();
  bb_check_null_left->append<PrimitiveCompare>(
      cmp_null_left, PrimitiveCompareOp::kEqual, left_child, null_left);
  bb_check_null_left->append<CondBranch>(cmp_null_left, bb_no_left, bb_has_left);

  // === bb_has_left: push parent(kYield) → save child → phase=kLeft ===
  // 关键: 先 push parent 再 save child，否则 push 的是 child 而非 parent
  // push 的 phase 是 kYield（不是 kRight），因为中序遍历是:
  //   左子树 → yield 当前节点 → 右子树
  // 所以从左子树返回后应该先 yield，再处理右子树
  Register* current_load = env.AllocateRegister();
  bb_has_left->append<LoadCurrentNode>(current_load);
  Register* left_child_hl = env.AllocateRegister();
  bb_has_left->append<LoadField>(
      left_child_hl, current_load, "left", left_offset, TOptObject);
  // 先 push parent（current_load 仍是 parent），phase=kYield
  Register* kYield_push =
      CreatePhaseConst(func, bb_has_left, TreeIterPhase::kYield);
  bb_has_left->append<StateStackPush>(current_load, kYield_push);
  // 再 save child 为新的 current
  bb_has_left->append<SaveCurrentNode>(left_child_hl);
  Register* kLeft_hl =
      CreatePhaseConst(func, bb_has_left, TreeIterPhase::kLeft);
  bb_has_left->append<SavePhase>(kLeft_hl);
  bb_has_left->append<Branch>(bb_loop);

  // === bb_no_left: phase=kYield → loop ===
  Register* kYield_nl =
      CreatePhaseConst(func, bb_no_left, TreeIterPhase::kYield);
  bb_no_left->append<SavePhase>(kYield_nl);
  bb_no_left->append<Branch>(bb_loop);

  // === bb_yield: 加载 current，yield current.value ===
  Register* current_yield = env.AllocateRegister();
  bb_yield->append<LoadCurrentNode>(current_yield);
  // 加载 current.value 字段
  Register* yield_value = env.AllocateRegister();
  bb_yield->append<LoadField>(
      yield_value, current_yield, "value", value_offset, TObject);
  Register* yield_result = env.AllocateRegister();
  if (ctx_.yield_frame_state != nullptr) {
    bb_yield->append<YieldValue>(
        yield_result, yield_value, *ctx_.yield_frame_state);
  } else {
    bb_yield->append<YieldValue>(yield_result, yield_value, FrameState{});
  }
  bb_yield->append<Branch>(bb_after_yield);

  // === bb_after_yield: phase=kRight → loop ===
  Register* kRight_ay =
      CreatePhaseConst(func, bb_after_yield, TreeIterPhase::kRight);
  bb_after_yield->append<SavePhase>(kRight_ay);
  bb_after_yield->append<Branch>(bb_loop);

  // === bb_right: 加载 current，检查 right 子树 ===
  Register* current_right = env.AllocateRegister();
  bb_right->append<LoadCurrentNode>(current_right);
  Register* right_child = env.AllocateRegister();
  bb_right->append<LoadField>(
      right_child, current_right, "right", right_offset, TOptObject);
  // Python 中 None 存储为 Py_None 指针（非 StaticPython），不是 nullptr
  // 先比较 Py_None，若不匹配再比较 nullptr（兼容 StaticPython 内联存储）
  Register* none_right = env.AllocateRegister();
  bb_right->append<LoadConst>(none_right, Type::fromObject(Py_None));
  Register* cmp_none_right = env.AllocateRegister();
  bb_right->append<PrimitiveCompare>(
      cmp_none_right, PrimitiveCompareOp::kEqual, right_child, none_right);
  bb_right->append<CondBranch>(cmp_none_right, bb_no_right, bb_check_null_right);

  // === bb_check_null_right: 也检查 nullptr ===
  Register* null_right = env.AllocateRegister();
  bb_check_null_right->append<LoadConst>(null_right, Type::fromCInt(0, TCInt64));
  Register* cmp_null_right = env.AllocateRegister();
  bb_check_null_right->append<PrimitiveCompare>(
      cmp_null_right, PrimitiveCompareOp::kEqual, right_child, null_right);
  bb_check_null_right->append<CondBranch>(cmp_null_right, bb_no_right, bb_has_right);

  // === bb_has_right: 重新加载字段（避免跨块寄存器被 C 调用 clobber），save + phase ===
  Register* current_hr = env.AllocateRegister();
  bb_has_right->append<LoadCurrentNode>(current_hr);
  // 重新加载 right 子节点
  Register* right_child_hr = env.AllocateRegister();
  bb_has_right->append<LoadField>(
      right_child_hr, current_hr, "right", right_offset, TOptObject);
  bb_has_right->append<SaveCurrentNode>(right_child_hr);
  Register* kLeft_hr =
      CreatePhaseConst(func, bb_has_right, TreeIterPhase::kLeft);
  bb_has_right->append<SavePhase>(kLeft_hr);
  bb_has_right->append<Branch>(bb_loop);

  // === bb_no_right: phase=kBacktrack → loop ===
  Register* kBacktrack_nr =
      CreatePhaseConst(func, bb_no_right, TreeIterPhase::kBacktrack);
  bb_no_right->append<SavePhase>(kBacktrack_nr);
  bb_no_right->append<Branch>(bb_loop);

  // === bb_backtrack: if stack empty → done / pop ===
  Register* stack_top = env.AllocateRegister();
  bb_backtrack->append<LoadStackTop>(stack_top);
  Register* zero_const = CreateIntConst(func, bb_backtrack, 0);
  Register* cmp_stack = env.AllocateRegister();
  bb_backtrack->append<PrimitiveCompare>(
      cmp_stack, PrimitiveCompareOp::kEqual, stack_top, zero_const);
  bb_backtrack->append<CondBranch>(cmp_stack, bb_done, bb_pop);

  // === bb_pop: pop → save popped state → loop ===
  Register* popped_node = env.AllocateRegister();
  bb_pop->append<StateStackPop>(popped_node);
  Register* popped_phase = env.AllocateRegister();
  bb_pop->append<LoadPoppedPhase>(popped_phase);
  bb_pop->append<SaveCurrentNode>(popped_node);
  bb_pop->append<SavePhase>(popped_phase);
  bb_pop->append<Branch>(bb_loop);

  // === bb_done: return None ===
  Register* none_result = env.AllocateRegister();
  bb_done->append<LoadConst>(none_result, Type::fromObject(Py_None));
  bb_done->append<Return>(none_result, TObject);

  JIT_LOG(
      "StateMachineGenerator: GenDataFooter-based state machine generated (no Phi)");
}

// 兼容性方法
BasicBlock* StateMachineGenerator::GenerateInitBlock() {
  return bb_init_;
}
BasicBlock* StateMachineGenerator::GenerateLoopBlock() {
  return bb_loop_;
}
BasicBlock* StateMachineGenerator::GenerateLeftBlock() {
  return bb_left_;
}
BasicBlock* StateMachineGenerator::GenerateYieldBlock() {
  return bb_yield_;
}
BasicBlock* StateMachineGenerator::GenerateRightBlock() {
  return bb_right_;
}
BasicBlock* StateMachineGenerator::GenerateBacktrackBlock() {
  return bb_backtrack_;
}

void StateMachineGenerator::GenerateStackPush(Register*, TreeIterPhase) {
}
std::pair<Register*, Register*> StateMachineGenerator::GenerateStackPop() {
  return {nullptr, nullptr};
}

}  // namespace jit::hir

extern "C" int g_state_machine_pass_triggered;
