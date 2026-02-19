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
Environ::Aarch64CallTarget& getOrCreateCallTarget(Environ& env, uint64_t func) {
  auto it = env.call_target_literals.find(func);
  if (it != env.call_target_literals.end()) {
    return it->second;
  }
  Environ::Aarch64CallTarget target;
  target.literal = env.as->newLabel();
  auto inserted = env.call_target_literals.emplace(func, target);
  return inserted.first->second;
}

void emitIndirectCallThroughLiteral(
    Environ& env,
    const Environ::Aarch64CallTarget& target) {
  env.as->ldr(arch::reg_scratch_br, asmjit::a64::ptr(target.literal));
  env.as->blr(arch::reg_scratch_br);
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
  auto& target = getOrCreateCallTarget(env, func);
  if (instr == nullptr) {
    // One-off runtime scaffolding calls are typically unique callsites. Emit
    // them directly through the literal to avoid materializing an extra helper
    // stub for each target.
    emitIndirectCallThroughLiteral(env, target);
  } else {
    // Deduplicate hot absolute call targets through one shared helper stub per
    // target. Callsites branch directly to that helper.
    if (!target.uses_helper_stub) {
      target.helper_stub = env.as->newLabel();
      target.uses_helper_stub = true;
    }
    env.as->bl(target.helper_stub);
  }
#else
  CINDER_UNSUPPORTED
#endif
  recordDebugEntry(env, instr);
}

} // namespace jit::codegen
