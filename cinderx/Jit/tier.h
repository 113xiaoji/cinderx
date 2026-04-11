// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

#include <string_view>

namespace jit {

enum class CompileTier {
  kBaseline,
  kOptimized,
};

inline constexpr std::string_view tierName(CompileTier tier) {
  switch (tier) {
    case CompileTier::kBaseline:
      return "baseline";
    case CompileTier::kOptimized:
      return "optimized";
  }
  return "unknown";
}

} // namespace jit
