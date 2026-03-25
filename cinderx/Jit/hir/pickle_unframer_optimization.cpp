// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/hir/pickle_unframer_optimization.h"

#include "cinderx/Common/log.h"
#include "cinderx/Jit/hir/pass.h"
#include "cinderx/Jit/hir/printer.h"

#include <cstdlib>
#include <sstream>

namespace jit::hir {

namespace {

bool isPickleUnframerFunction(const Function& func) {
  return func.fullname == "pickle:_Unframer.read" ||
      func.fullname == "pickle:_Unframer.load_frame";
}

PyTypeObject* getKnownIoBytesIOType() {
  static PyTypeObject* bytesio_type = nullptr;
  if (bytesio_type != nullptr) {
    return bytesio_type;
  }

  PyObject* io_mod = PyImport_ImportModule("io");
  if (io_mod == nullptr) {
    PyErr_Clear();
    return nullptr;
  }

  PyObject* bytesio = PyObject_GetAttrString(io_mod, "BytesIO");
  Py_DECREF(io_mod);
  if (bytesio == nullptr || !PyType_Check(bytesio)) {
    Py_XDECREF(bytesio);
    PyErr_Clear();
    return nullptr;
  }

  bytesio_type = reinterpret_cast<PyTypeObject*>(bytesio);
  return bytesio_type;
}

bool isUnicodeName(BorrowedRef<> name, const char* expected) {
  if (name == nullptr) {
    return false;
  }
  int same = PyUnicode_CompareWithASCIIString(name, expected);
  if (same != 0) {
    PyErr_Clear();
    return false;
  }
  return true;
}

std::string renderBlock(const BasicBlock& block) {
  std::ostringstream os;
  os << block;
  return os.str();
}

struct DominatingCurrentFrame {
  Register* value{nullptr};
  Register* receiver{nullptr};
};

std::optional<DominatingCurrentFrame> findDominatingTruthyCurrentFrame(
    BasicBlock* block) {
  if (block == nullptr || block->in_edges().size() != 1) {
    return std::nullopt;
  }

  const BasicBlock* pred = (*block->in_edges().begin())->from();
  if (pred == nullptr || pred->GetTerminator() == nullptr ||
      !pred->GetTerminator()->IsCondBranch()) {
    return std::nullopt;
  }

  auto* branch = static_cast<const CondBranch*>(pred->GetTerminator());
  if (branch->true_bb() != block) {
    return std::nullopt;
  }

  Register* cond = branch->GetOperand(0);
  if (cond == nullptr || !cond->instr()->IsIsTruthy()) {
    return std::nullopt;
  }

  Register* value = chaseAssignOperand(cond->instr()->GetOperand(0));
  if (value == nullptr || !value->instr()->IsCheckField()) {
    return std::nullopt;
  }

  auto* check = static_cast<const CheckField*>(value->instr());
  if (!isUnicodeName(check->name(), "current_frame")) {
    return std::nullopt;
  }

  Register* maybe_attr = check->GetOperand(0);
  if (maybe_attr == nullptr || !maybe_attr->instr()->IsLoadField()) {
    return std::nullopt;
  }

  auto* load = static_cast<const LoadField*>(maybe_attr->instr());
  if (load->name() != "current_frame") {
    return std::nullopt;
  }

  return DominatingCurrentFrame{value, chaseAssignOperand(load->receiver())};
}

struct RedundantCurrentFrameChain {
  DeoptPatchpoint* patchpoint{nullptr};
  LoadField* valid_load{nullptr};
  Guard* valid_guard{nullptr};
  LoadField* current_frame_load{nullptr};
  CheckField* current_frame_check{nullptr};
  Snapshot* pre_load_method_snapshot{nullptr};
  Incref* incref{nullptr};
  LoadMethodCached* load_method{nullptr};
  GetSecondOutput* second_output{nullptr};
  Snapshot* pre_call_snapshot{nullptr};
  CallMethod* call_method{nullptr};
};

std::optional<RedundantCurrentFrameChain> matchRedundantCurrentFrameChain(
    BasicBlock* block) {
  if (block == nullptr) {
    return std::nullopt;
  }

  for (auto start = block->begin(); start != block->end(); ++start) {
    if (!start->IsDeoptPatchpoint()) {
      continue;
    }

    auto it = start;
    auto* patchpoint = static_cast<DeoptPatchpoint*>(&*it++);
    if (patchpoint->descr() != "SplitDictDeoptPatcher") {
      continue;
    }

    while (it != block->end() && it->IsUseType()) {
      ++it;
    }

    if (it == block->end() || !it->IsLoadField()) {
      continue;
    }
    auto* valid_load = static_cast<LoadField*>(&*it++);
    if (valid_load->name() != "inline_values.valid") {
      continue;
    }

    if (it == block->end() || !it->IsGuard()) {
      continue;
    }
    auto* valid_guard = static_cast<Guard*>(&*it++);
    if (valid_guard->descr() != "inline_values.valid" ||
        valid_guard->GetOperand(0) != valid_load->output()) {
      continue;
    }

    if (it == block->end() || !it->IsLoadField()) {
      continue;
    }
    auto* current_frame_load = static_cast<LoadField*>(&*it++);
    if (current_frame_load->name() != "current_frame") {
      continue;
    }

    if (it == block->end() || !it->IsCheckField()) {
      continue;
    }
    auto* current_frame_check = static_cast<CheckField*>(&*it++);
    if (
        !isUnicodeName(current_frame_check->name(), "current_frame") ||
        current_frame_check->GetOperand(0) != current_frame_load->output()) {
      continue;
    }

    Snapshot* pre_load_method_snapshot = nullptr;
    while (it != block->end() && it->IsSnapshot()) {
      if (pre_load_method_snapshot == nullptr) {
        pre_load_method_snapshot = static_cast<Snapshot*>(&*it);
      }
      ++it;
    }

    Incref* incref = nullptr;
    if (it != block->end() && it->IsIncref()) {
      incref = static_cast<Incref*>(&*it++);
      if (incref->GetOperand(0) != current_frame_check->output()) {
        continue;
      }
    }

    while (it != block->end() && it->IsSnapshot()) {
      ++it;
    }

    if (it == block->end() || !it->IsLoadMethodCached()) {
      continue;
    }
    auto* load_method = static_cast<LoadMethodCached*>(&*it++);
    if (
        !isUnicodeName(load_method->name(), "read") ||
        chaseAssignOperand(load_method->receiver()) !=
            current_frame_check->output()) {
      continue;
    }

    if (it == block->end() || !it->IsGetSecondOutput()) {
      continue;
    }
    auto* second_output = static_cast<GetSecondOutput*>(&*it++);
    if (second_output->GetOperand(0) != load_method->output()) {
      continue;
    }

    Snapshot* pre_call_snapshot = nullptr;
    while (it != block->end() && it->IsSnapshot()) {
      if (pre_call_snapshot == nullptr) {
        pre_call_snapshot = static_cast<Snapshot*>(&*it);
      }
      ++it;
    }

    if (it == block->end() || !it->IsCallMethod()) {
      continue;
    }
    auto* call_method = static_cast<CallMethod*>(&*it++);
    if (
        call_method->func() != load_method->output() ||
        call_method->self() != second_output->output()) {
      continue;
    }

    return RedundantCurrentFrameChain{
        patchpoint,
        valid_load,
        valid_guard,
        current_frame_load,
        current_frame_check,
        pre_load_method_snapshot,
        incref,
        load_method,
        second_output,
        pre_call_snapshot,
        call_method,
    };
  }

  return std::nullopt;
}

} // namespace

void PickleUnframerOptimization::Run(Function& func) {
  if (!isPickleUnframerFunction(func)) {
    return;
  }
  if (std::getenv("CINDERX_ISSUE63_DISABLE_BYTESIO_FASTPATH") != nullptr) {
    JIT_LOG("issue63 fast path disabled by env for {}", func.fullname);
    return;
  }

  JIT_LOG("issue63 pass visiting {}", func.fullname);

  PyTypeObject* bytesio_type = getKnownIoBytesIOType();
  if (bytesio_type == nullptr) {
    return;
  }
  Type bytesio_exact = Type::fromTypeExact(bytesio_type);

  for (BasicBlock& block : func.cfg.blocks) {
    auto dominating = findDominatingTruthyCurrentFrame(&block);
    if (!dominating.has_value()) {
      continue;
    }

    auto chain = matchRedundantCurrentFrameChain(&block);
    if (!chain.has_value()) {
      continue;
    }

    if (
        dominating->receiver == nullptr ||
        dominating->receiver !=
            chaseAssignOperand(chain->current_frame_load->receiver())) {
      continue;
    }

    auto* fast_path = func.cfg.AllocateBlock();
    auto* dispatch = CondBranchCheckType::create(
        dominating->value, bytesio_exact, &block, &block);
    dispatch->copyBytecodeOffset(*chain->current_frame_check);
    block.insert(dispatch, block.iterator_to(*chain->patchpoint));

    BasicBlock* slow_path = func.cfg.splitAfter(*dispatch);
    dispatch->set_true_bb(fast_path);
    dispatch->set_false_bb(slow_path);

    auto* slow_snapshot = Snapshot::create(*chain->current_frame_check->frameState());
    slow_snapshot->copyBytecodeOffset(*chain->current_frame_check);
    slow_path->push_front(slow_snapshot);

    Register* original_result = chain->call_method->output();
    Register* slow_result = func.env.AllocateRegister();
    chain->call_method->setOutput(slow_result);

    BasicBlock* join = func.cfg.splitAfter(*chain->call_method);
    slow_path->appendWithOff<Branch>(chain->call_method->bytecodeOffset(), join);

    Register* refined = func.env.AllocateRegister();
    fast_path->appendWithOff<RefineType>(
        chain->current_frame_check->bytecodeOffset(),
        refined,
        bytesio_exact,
        dominating->value);

    auto* load_snapshot =
        fast_path->appendWithOff<Snapshot>(chain->load_method->bytecodeOffset());
    load_snapshot->setFrameState(*chain->load_method->frameState());

    Register* fast_load_result = func.env.AllocateRegister();
    auto* fast_load =
        static_cast<LoadMethodCached*>(chain->load_method->clone());
    Register* slow_load_result = chain->load_method->output();
    fast_load->setOutput(fast_load_result);
    slow_load_result->set_instr(chain->load_method);
    fast_load->SetOperand(0, refined);
    fast_path->Append(fast_load);

    Register* fast_bound = func.env.AllocateRegister();
    auto* fast_second =
        static_cast<GetSecondOutput*>(chain->second_output->clone());
    Register* slow_bound = chain->second_output->output();
    fast_second->setOutput(fast_bound);
    slow_bound->set_instr(chain->second_output);
    fast_second->SetOperand(0, fast_load_result);
    fast_path->Append(fast_second);

    auto* call_snapshot =
        fast_path->appendWithOff<Snapshot>(chain->call_method->bytecodeOffset());
    call_snapshot->setFrameState(*chain->call_method->frameState());

    Register* fast_result = func.env.AllocateRegister();
    auto* fast_call = static_cast<CallMethod*>(chain->call_method->clone());
    fast_call->setOutput(fast_result);
    slow_result->set_instr(chain->call_method);
    fast_call->SetOperand(0, fast_load_result);
    fast_call->SetOperand(1, fast_bound);
    fast_path->Append(fast_call);
    fast_path->appendWithOff<Branch>(chain->call_method->bytecodeOffset(), join);

    std::unordered_map<BasicBlock*, Register*> phi_args{
        {slow_path, slow_result},
        {fast_path, fast_result},
    };
    auto* phi = Phi::create(original_result, phi_args);
    phi->copyBytecodeOffset(*chain->call_method);
    join->push_front(phi);
  }
}

} // namespace jit::hir
