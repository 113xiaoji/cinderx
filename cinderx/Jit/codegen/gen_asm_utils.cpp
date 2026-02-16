// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/codegen/gen_asm_utils.h"

#include "cinderx/Jit/codegen/arch.h"
#include "cinderx/Jit/codegen/environ.h"

namespace jit::codegen {

namespace {
void recordDebugEntry(Environ& env, const jit::lir::Instruction* instr) {
  if (instr == nullptr || instr->origin() == nullptr) {
    return;
  }
  asmjit::Label addr = env.as->newLabel();
  env.as->bind(addr);
  env.pending_debug_locs.emplace_back(addr, instr->origin());
}

#if defined(CINDER_AARCH64)
asmjit::Label getOrCreateCallTargetLiteral(Environ& env, uint64_t func) {
  auto it = env.call_target_literals.find(func);
  if (it != env.call_target_literals.end()) {
    return it->second;
  }
  asmjit::Label label = env.as->newLabel();
  env.call_target_literals.emplace(func, label);
  return label;
}
#endif
} // namespace

void emitCall(
    Environ& env,
    asmjit::Label label,
    const jit::lir::Instruction* instr) {
#if defined(CINDER_X86_64)
  env.as->call(label);
#elif defined(CINDER_AARCH64)
  env.as->bl(label);
#else
  CINDER_UNSUPPORTED
#endif
  recordDebugEntry(env, instr);
}

void emitCall(Environ& env, uint64_t func, const jit::lir::Instruction* instr) {
#if defined(CINDER_X86_64)
  env.as->call(func);
#elif defined(CINDER_AARCH64)
  // Deduplicate absolute call targets and load them through a literal pool.
  // This avoids repeated movz/movk materialization at each callsite.
  auto literal = getOrCreateCallTargetLiteral(env, func);
  env.as->ldr(arch::reg_scratch_br, asmjit::a64::ptr(literal));
  env.as->blr(arch::reg_scratch_br);
#else
  CINDER_UNSUPPORTED
#endif
  recordDebugEntry(env, instr);
}

} // namespace jit::codegen
