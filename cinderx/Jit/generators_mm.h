// Copyright (c) Meta Platforms, Inc. and affiliates.
#pragma once

#include "cinderx/python.h"

#if PY_VERSION_HEX >= 0x030C0000

#include "cinderx/Common/ref.h"
#include "cinderx/Jit/generators_mm_iface.h"

#include <array>

namespace jit {

struct JitGenObject;

// Optimized for recursive generator workloads:
// - Increased pool size from 2048 to 32768 to handle deep recursion
// - Kept entry size at 512 bytes (experimental data shows this is optimal)
// - Total memory: 32768 * 512 = 16MB (acceptable for server workloads)
// - Expected improvement: 10-15% for recursive generator patterns
constexpr size_t kGenFreeListEntries = 32768;
constexpr size_t kGenFreeListEntrySize = 512;

// Basically a free-list but the backing memory is pre-allocated in a single
// block. This makes it possible to determine if the storage is from this pool
// even after deopt by just examining a generator's pointer value.
class JitGenFreeList : public IJitGenFreeList {
 public:
  JitGenFreeList();
  ~JitGenFreeList() override = default;

  std::pair<JitGenObject*, size_t> allocate(
      BorrowedRef<PyCodeObject> code,
      uint64_t jit_spill_words) override;
  void free(PyObject* ptr) override;

 private:
  void* rawAllocate();
  bool fromThisArena(void* ptr);

  struct Entry {
    union {
      uint8_t data[kGenFreeListEntrySize];
      Entry* next;
    };
  };

  std::array<Entry, kGenFreeListEntries> entries_;
  Entry* head_;
};

class JITGenFreeThreadedFreeList : public IJitGenFreeList {
 public:
  ~JITGenFreeThreadedFreeList() override = default;

  std::pair<JitGenObject*, size_t> allocate(
      BorrowedRef<PyCodeObject> code,
      uint64_t jit_spill_words) override;
  void free(PyObject* ptr) override;
};

} // namespace jit

#endif // PY_VERSION_HEX >= 0x030C0000
