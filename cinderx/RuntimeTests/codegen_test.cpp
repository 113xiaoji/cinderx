// Copyright (c) Meta Platforms, Inc. and affiliates.

#include <gtest/gtest.h>

#include "cinderx/Jit/bytecode.h"
#include "cinderx/Jit/compiler.h"
#include "cinderx/Jit/codegen/arch.h"
#include "cinderx/Jit/codegen/gen_asm.h"
#include "cinderx/Jit/frame.h"
#include "cinderx/RuntimeTests/fixtures.h"

#include <unordered_set>

using namespace jit::codegen;

namespace jit::codegen {

namespace {

std::unordered_set<int> collectLoopHeaderOffsets(BorrowedRef<PyCodeObject> code) {
  std::unordered_set<int> offsets;
  jit::BytecodeInstructionBlock instrs{code};
  for (const jit::BytecodeInstruction& instr : instrs) {
    switch (instr.opcode()) {
      case JUMP_BACKWARD:
      case JUMP_BACKWARD_NO_INTERRUPT:
        offsets.emplace(instr.getJumpTarget().value());
        break;
      default:
        break;
    }
  }
  return offsets;
}

jit::hir::BasicBlock* findLoopHeaderBlock(jit::hir::Function& irfunc) {
  auto loop_headers = collectLoopHeaderOffsets(irfunc.code);
  jit::hir::BasicBlock* header = nullptr;
  for (auto& block : irfunc.cfg.blocks) {
    auto* snapshot = block.entrySnapshot();
    if (snapshot == nullptr || snapshot->frameState() == nullptr) {
      continue;
    }
    auto bc_offset = snapshot->frameState()->cur_instr_offs.value();
    if (!loop_headers.contains(bc_offset)) {
      continue;
    }
    if (header != nullptr) {
      return nullptr;
    }
    header = &block;
  }
  return header;
}

void insertFailingGuardAtLoopHeader(jit::hir::Function& irfunc) {
  auto* loop_header = findLoopHeaderBlock(irfunc);
  JIT_CHECK(loop_header != nullptr, "Expected exactly one loop header block");
  auto* reg = irfunc.env.AllocateRegister();
  for (auto& instr : *loop_header) {
    if (instr.IsSnapshot()) {
      continue;
    }
    auto guard = jit::hir::Guard::create(reg);
    guard->InsertBefore(instr);
    return;
  }
  JIT_ABORT("Loop header block had no insertion point for failing guard");
}

} // namespace

class CodegenTest : public RuntimeTest {};

TEST_F(CodegenTest, TestPhyRegisterSet) {
  auto set = PhyRegisterSet(2) | PhyRegisterSet(3) | PhyRegisterSet(5);

  ASSERT_EQ(set.Empty(), false);
  ASSERT_EQ(set.count(), 3);
  ASSERT_EQ(set.GetFirst(), 2);
  ASSERT_EQ(set.GetLast(), 5);
  ASSERT_EQ(set.Has(3), true);

  set.RemoveFirst();

  ASSERT_EQ(set.Empty(), false);
  ASSERT_EQ(set.count(), 2);
  ASSERT_EQ(set.GetFirst(), 3);
  ASSERT_EQ(set.GetLast(), 5);
  ASSERT_EQ(set.Has(3), true);

  set.RemoveLast();

  ASSERT_EQ(set.Empty(), false);
  ASSERT_EQ(set.count(), 1);
  ASSERT_EQ(set.GetFirst(), 3);
  ASSERT_EQ(set.GetLast(), 3);
  ASSERT_EQ(set.Has(3), true);

  set.RemoveFirst();

  ASSERT_EQ(set.Empty(), true);
  ASSERT_EQ(set.count(), 0);
  ASSERT_EQ(set.Has(3), false);
}

TEST_F(CodegenTest, Phase0ExportsLoopHeaderOsrEntry) {
  const char* src = R"(
def hot(n, acc):
  while n > 0:
    acc = acc + n
    n = n - 1
  return acc
)";

  Ref<PyFunctionObject> func(compileAndGet(src, "hot"));
  ASSERT_NE(func, nullptr);

  auto irfunc = buildHIR(func);
  ASSERT_NE(irfunc, nullptr);
  jit::Compiler::runPasses(*irfunc, PassConfig::kAllExceptInliner);
  irfunc->reifier =
      ThreadedRef<>::create(makeFrameReifier(func->func_code).get());

  NativeGenerator gen(irfunc.get());
  ASSERT_NE(gen.getVectorcallEntry(), nullptr);

  const auto& osr_entries = gen.codeRuntime()->osrEntries();
  ASSERT_FALSE(osr_entries.empty());
}

TEST_F(CodegenTest, Phase0ResolvesLoopHeaderOsrEntryAddress) {
  const char* src = R"(
def hot(n, acc):
  while n > 0:
    acc = acc + n
    n = n - 1
  return acc
)";

  Ref<PyFunctionObject> func(compileAndGet(src, "hot"));
  ASSERT_NE(func, nullptr);

  auto irfunc = buildHIR(func);
  ASSERT_NE(irfunc, nullptr);
  jit::Compiler::runPasses(*irfunc, PassConfig::kAllExceptInliner);
  irfunc->reifier =
      ThreadedRef<>::create(makeFrameReifier(func->func_code).get());

  NativeGenerator gen(irfunc.get());
  auto* vectorcall_entry = gen.getVectorcallEntry();
  ASSERT_NE(vectorcall_entry, nullptr);

  const auto& osr_entries = gen.codeRuntime()->osrEntries();
  ASSERT_FALSE(osr_entries.empty());
  ASSERT_NE(osr_entries.front().entry_address, 0);
  ASSERT_NE(
      reinterpret_cast<void*>(osr_entries.front().entry_address),
      vectorcall_entry);
}

TEST_F(CodegenTest, Phase0SyntheticStateOsrExecutesLoop) {
  const char* src = R"(
def hot(n, acc):
  while n > 0:
    acc = acc + n
    n = n - 1
  return acc
)";

  Ref<PyFunctionObject> func(compileAndGet(src, "hot"));
  ASSERT_NE(func, nullptr);

  auto irfunc = buildHIR(func);
  ASSERT_NE(irfunc, nullptr);
  jit::Compiler::runPasses(*irfunc, PassConfig::kAllExceptInliner);
  irfunc->reifier =
      ThreadedRef<>::create(makeFrameReifier(func->func_code).get());

  NativeGenerator gen(irfunc.get());
  ASSERT_NE(gen.getVectorcallEntry(), nullptr);

  const auto& osr_entries = gen.codeRuntime()->osrEntries();
  ASSERT_FALSE(osr_entries.empty());
  ASSERT_NE(osr_entries.front().test_entry_address, 0);

  auto n = Ref<>::steal(PyLong_FromLong(3));
  auto acc = Ref<>::steal(PyLong_FromLong(10));
  ASSERT_NE(n, nullptr);
  ASSERT_NE(acc, nullptr);

  PyObject* localsplus[] = {n, acc};
  auto osr_entry =
      reinterpret_cast<vectorcallfunc>(osr_entries.front().test_entry_address);
  Ref<> result = Ref<>::steal(osr_entry(
      reinterpret_cast<PyObject*>(func.get()),
      localsplus,
      2,
      nullptr));

  ASSERT_NE(result, nullptr);
  EXPECT_TRUE(isIntEquals(result, 16));
}

TEST_F(CodegenTest, Phase0SyntheticStateOsrThenDeoptResumesCorrectly) {
  const char* src = R"(
def hot(n, acc):
  while n > 0:
    acc = acc + n
    n = n - 1
  return acc
)";

  Ref<PyFunctionObject> func(compileAndGet(src, "hot"));
  ASSERT_NE(func, nullptr);

  auto irfunc = buildHIR(func);
  ASSERT_NE(irfunc, nullptr);
  insertFailingGuardAtLoopHeader(*irfunc);
  jit::Compiler::runPasses(*irfunc, PassConfig::kAllExceptInliner);
  irfunc->reifier =
      ThreadedRef<>::create(makeFrameReifier(func->func_code).get());

  NativeGenerator gen(irfunc.get());
  ASSERT_NE(gen.getVectorcallEntry(), nullptr);

  const auto& osr_entries = gen.codeRuntime()->osrEntries();
  ASSERT_FALSE(osr_entries.empty());
  ASSERT_NE(osr_entries.front().test_entry_address, 0);

  auto n = Ref<>::steal(PyLong_FromLong(3));
  auto acc = Ref<>::steal(PyLong_FromLong(10));
  ASSERT_NE(n, nullptr);
  ASSERT_NE(acc, nullptr);

  PyObject* localsplus[] = {n, acc};
  auto osr_entry =
      reinterpret_cast<vectorcallfunc>(osr_entries.front().test_entry_address);
  Ref<> result = Ref<>::steal(osr_entry(
      reinterpret_cast<PyObject*>(func.get()),
      localsplus,
      2,
      nullptr));

  ASSERT_NE(result, nullptr);
  EXPECT_TRUE(isIntEquals(result, 16));
}

} // namespace jit::codegen
