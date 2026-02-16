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
const Environ::Aarch64CallTarget& getOrCreateCallTarget(Environ& env, uint64_t func) {
  auto it = env.call_target_literals.find(func);
  if (it != env.call_target_literals.end()) {
    return it->second;
  }
  Environ::Aarch64CallTarget target{
      env.as->newLabel(), // helper_stub
      env.as->newLabel(), // literal
  };
  auto inserted = env.call_target_literals.emplace(func, target);
  return inserted.first->second;
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
  // Deduplicate absolute call targets. Emit one shared helper stub per target,
  // and callsites branch directly to that helper.
  const auto& target = getOrCreateCallTarget(env, func);
  env.as->bl(target.helper_stub);
#else
  CINDER_UNSUPPORTED
#endif
  recordDebugEntry(env, instr);
}

} // namespace jit::codegen
