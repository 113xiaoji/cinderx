# 儿池化机制发现报告

**日期**: 2026-03-18 18:10
**发现**: CinderX已经实现了帧池化机制！
**状态**: 需要检查是否启用和配置是否最优

---

## 关键发现

经过深入研究，我发现CinderX **已经实现了帧池化机制**！

### 现有实现

**文件**: `cinderx/Jit/generators_mm.h` 和 `cinderx/Jit/generators_mm.cpp`

**类**: `JitGenFreeList`

**关键代码**:
```cpp
// generators_mm.h
class JitGenFreeList : public IJitGenFreeList {
 public:
  std::pair<JitGenObject*, size_t> allocate(
      BorrowedRef<PyCodeObject> code,
      uint64_t jit_spill_words) override;

  void free(PyObject* ptr) override;

 private:
  std::array<Entry, kGenFreeListEntries> entries_;
  std::vector<size_t> free_list_;
};

// generators_mm.cpp
std::pair<JitGenObject*, size_t> JitGenFreeList::allocate(
    BorrowedRef<PyCodeObject> code,
    uint64_t jit_spill_words) {
  size_t slots = computeSlots(code, jit_spill_words);

  if (!free_list_.empty()) {
    size_t idx = free_list_.back();
    free_list_.pop_back();
    Entry& entry = entries_[idx];
    // 重用池中的条目
    return {reinterpret_cast<JitGenObject*>(entry.storage), slots};
  }

  // 池为空，分配新的
  void* raw = rawAllocate();
  // ...
}

void JITGenFreeThreadedFreeList::free(PyObject* ptr) {
  // 将条目放回池中
  size_t idx = entry_index;
  free_list_.push_back(idx);
}
```

### 配置参数

**文件**: `cinderx/Jit/generators_mm.h:20-26`

```cpp
// 每个条目的大小（字节）
constexpr size_t kGenFreeListEntrySize = 512;

// 池中的条目数量
constexpr size_t kGenFreeListEntries = 2048;

// 最大条目大小约400字节，但实际中看到的是~512字节
// 性能实验显示512比1024更好
// 更大的大小会带来固定的内存开销，不值得
```

**当前配置**:
- 池大小: 2048个条目
- 每个条目: 512字节
- 总内存: ~1MB (2048 * 512)

---

## 分析

### 优点

✅ **已经实现**: 不需要从头实现
✅ **线程安全**: 使用thread-local storage
✅ **自动管理**: 生成器销毁时自动归还池

### 当前状态检查

让我检查：
1. 是否启用了池化
2. 池的命中率（多少生成器使用了池）
3. 是否有优化空间

---

## 下一步

我需要：
1. **检查是否启用**: 查看配置和统计数据
2. **评估性能**: 检查池的命中率
3. **优化配置**: 如果需要，调整池大小或策略

让我先检查启用状态和统计数据。
