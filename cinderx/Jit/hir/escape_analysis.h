// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

#include "cinderx/Jit/hir/hir.h"

namespace jit::hir {

// Escape analysis for generator iterators.
enum class EscapeLevel {
  kUnknown, // Unknown (conservative - fall back to standard path)
  kNoEscape, // Non-escaping (can use InlineIter)
  kEscapes // Escaping (must use standard generator)
};

// Analyze whether a generator expression is non-escaping.
EscapeLevel analyzeGeneratorEscape(const Instr* iter_instr);

} // namespace jit::hir
