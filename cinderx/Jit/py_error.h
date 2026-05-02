// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

#include "internal/pycore_pyerrors.h"
#include "internal/pycore_pystate.h"

namespace jit {

inline void clearPyErrIfPresent() {
  PyThreadState* tstate = _PyThreadState_GET();
  if (tstate != nullptr) {
    _PyErr_Clear(tstate);
  }
}

} // namespace jit
