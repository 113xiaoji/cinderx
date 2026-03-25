// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

#include "cinderx/Jit/hir/pass.h"

namespace jit::hir {

class PickleUnframerOptimization : public Pass {
 public:
  PickleUnframerOptimization() : Pass("PickleUnframerOptimization") {}

  void Run(Function& func) override;

  static std::unique_ptr<PickleUnframerOptimization> Factory() {
    return std::make_unique<PickleUnframerOptimization>();
  }

 private:
  DISALLOW_COPY_AND_ASSIGN(PickleUnframerOptimization);
};

} // namespace jit::hir
