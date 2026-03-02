// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/codegen/gen_asm_utils.h"

#include "cinderx/Jit/codegen/arch.h"
#include "cinderx/Jit/codegen/code_section.h"
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

bool isInColdSection(const Environ& env) {
  auto* cold = env.as->code()->sectionByName(codeSectionName(CodeSection::kCold));
  if (cold == nullptr) {
    return false;
  }

  for (auto* node = env.as->cursor(); node != nullptr; node = node->prev()) {
    if (node->type() == asmjit::NodeType::kSection) {
      auto* section_node = node->as<asmjit::SectionNode>();
      return section_node->id() == cold->id();
    }
  }

  return false;
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
  if (isInColdSection(env)) {
    // Cold blocks can be placed >1MiB from hot text under MCS. Avoid
    // ldr-literal call lowering here because its imm19 displacement cannot
    // reach hot literals in that layout.
    env.as->mov(arch::reg_scratch_br, func);
    env.as->blr(arch::reg_scratch_br);
  } else {
    auto& target = getOrCreateCallTarget(env, func);
    emitIndirectCallThroughLiteral(env, target);
  }
#else
  CINDER_UNSUPPORTED
#endif
  recordDebugEntry(env, instr);
}

} // namespace jit::codegen
