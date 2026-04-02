// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

#include "cinderx/Jit/hir/pass.h"
#include "cinderx/Jit/hir/hir.h"

#include <string>

namespace jit::hir {

// 逃逸级别 - 表示生成器的逃逸程度
enum class EscapeLevel {
  kUnknown, // 未知（保守处理，回退到标准路径）
  kNoEscape, // 不可逃逸（可优化）
  kEscapes // 可逃逸（不可优化）
};

// 逃逸分析结果
struct EscapeAnalysisResult {
  EscapeLevel level;
  std::string reason; // 原因描述（用于调试）

  bool canOptimize() const {
    return level == EscapeLevel::kNoEscape;
  }
};

// 逃逸分析 Pass
// 分析生成器的使用模式，确定是否可以优化
class EscapeAnalysisPass : public Pass {
 public:
  EscapeAnalysisPass() : Pass("escape_analysis") {}

  void Run(Function& func) override;

  // 分析特定生成器表达式的逃逸级别
  EscapeAnalysisResult analyzeGenerator(const Register* gen_reg);

 private:
  // 检查生成器是否被返回
  bool isReturned(const Register* gen_reg);

  // 检查生成器是否被存储到外部变量
  bool isStoredExternally(const Register* gen_reg);

  // 检查生成器是否被传递给未知函数
  bool isPassedToUnknownFunction(const Register* gen_reg);

  // 检查生成器是否被 list/set/tuple 直接消费
  bool isDirectlyConsumed(const Register* gen_reg);

  // 分析函数
  Function* func_ = nullptr;
};

} // namespace jit::hir
