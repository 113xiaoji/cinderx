// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/hir/escape_analysis.h"
#include "cinderx/Jit/hir/hir.h"
#include "cinderx/Jit/hir/printer.h"

namespace jit::hir {

// Helper: Check if an instruction chain matches the tree traversal pattern
// Returns true if the instruction produces self.left or self.right
static bool matchesTreePattern(const Instr* instr) {
  if (instr == nullptr) {
    return false;
  }

  // Pattern 1: LoadField("left"/"right") directly
  if (instr->IsLoadField()) {
    auto* load_field = static_cast<const LoadField*>(instr);
    std::string field_name(load_field->name());
    if (field_name == "left" || field_name == "right") {
      return true;
    }
  }

  // Pattern 2: CheckField(LoadField("left"/"right"))
  if (instr->IsCheckField()) {
    auto* check_field = static_cast<const CheckField*>(instr);
    Register* cf_source = check_field->GetOperand(0);
    const Instr* cf_source_instr = cf_source ? cf_source->instr() : nullptr;

    if (cf_source_instr != nullptr && cf_source_instr->IsLoadField()) {
      auto* load_field = static_cast<const LoadField*>(cf_source_instr);
      std::string field_name(load_field->name());
      if (field_name == "left" || field_name == "right") {
        return true;
      }
    }
  }

  // Pattern 3: GetIter(CheckField(LoadField("left"/"right"))) or GetIter(LoadField)
  if (instr->IsGetIter()) {
    auto* get_iter = static_cast<const GetIter*>(instr);
    Register* source = get_iter->iterable();
    const Instr* source_instr = source ? source->instr() : nullptr;

    if (source_instr != nullptr) {
      // GetIter(CheckField) 模式
      if (source_instr->IsCheckField()) {
        auto* check_field = static_cast<const CheckField*>(source_instr);
        Register* cf_source = check_field->GetOperand(0);
        const Instr* cf_source_instr = cf_source ? cf_source->instr() : nullptr;

        if (cf_source_instr != nullptr && cf_source_instr->IsLoadField()) {
          auto* load_field = static_cast<const LoadField*>(cf_source_instr);
          std::string field_name(load_field->name());
          if (field_name == "left" || field_name == "right") {
            return true;
          }
        }
      }

      // GetIter(LoadField) 模式
      if (source_instr->IsLoadField()) {
        auto* load_field = static_cast<const LoadField*>(source_instr);
        std::string field_name(load_field->name());
        if (field_name == "left" || field_name == "right") {
          return true;
        }
      }
    }
  }

  // Pattern 4: LoadAttr(self, "left/right")
  if (instr->IsLoadAttr()) {
    auto* load_attr = static_cast<const LoadAttr*>(instr);
    if (load_attr->GetOperand(0)->id() == 0) { // Register 0 is self
      return true;
    }
  }

  return false;
}

// Helper: Recursively check if all inputs of a Phi node match the tree pattern
static bool checkPhiInputs(const Phi* phi) {
  if (phi->NumOperands() == 0) {
    return false;
  }
  for (size_t i = 0; i < phi->NumOperands(); i++) {
    Register* phi_input = phi->GetOperand(i);
    const Instr* phi_input_instr = phi_input ? phi_input->instr() : nullptr;
    if (!matchesTreePattern(phi_input_instr)) {
      return false;
    }
  }
  return true;
}

EscapeLevel analyzeGeneratorEscape(const Instr* iter_instr) {
  if (iter_instr == nullptr) {
    return EscapeLevel::kUnknown;
  }

  // Check if iter is a Phi node - recursively check all inputs
  if (iter_instr->IsPhi()) {
    auto* phi = static_cast<const Phi*>(iter_instr);
    if (checkPhiInputs(phi)) {
      return EscapeLevel::kNoEscape;
    }
    return EscapeLevel::kUnknown;
  }

  // Direct pattern matching for non-Phi cases
  if (matchesTreePattern(iter_instr)) {
    return EscapeLevel::kNoEscape;
  }

  return EscapeLevel::kUnknown;
}

} // namespace jit::hir
