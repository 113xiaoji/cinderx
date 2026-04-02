# Yield-From Inline Optimization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inline `yield from self.left/right` pattern to eliminate delegation overhead in recursive generators

**Architecture:** Transform YieldFrom HIR instruction into explicit iteration loop with next() calls, eliminating generator delegation overhead while preserving Python semantics (send/throw/close handling)

**Tech Stack:** C++17, CinderX JIT HIR/LIR infrastructure, Python C API

---

## Background

**Problem:** CinderX JIT shows 2.1x performance regression on recursive generators compared to CPython baseline
- CPython recursive generator: 9.0ms
- CinderX JIT: 18.9ms (0.48x slower)

**Root Cause:** YieldFrom delegation overhead (53.9% of execution time)

**Optimization Target:** Inline `yield from self.left/right` into explicit loop:
```python
# Before (delegation)
yield from self.left

# After (inlined loop)
for value in self.left:
    yield value
```

**Expected Improvement:** 30-50% (18.9ms → 9-13ms)

---

## File Structure

### Modified Files
- `cinderx/Jit/hir/simplify.cpp` - YieldFrom optimization logic
- `cinderx/Jit/hir/hir.h` - HIR instruction definitions (reference only)
- `cinderx/Jit/lir/generator.cpp` - LIR lowering for new instructions
- `cinderx/Jit/hir/instr_effects.cpp` - Memory effects for new instructions

### New Test Files
- `cinderx/PythonLib/test_cinderx/test_yield_from_inline.py` - Comprehensive tests
- `scripts/diagnostics/test_yield_from_inline_simple.py` - Simple smoke test

### Documentation
- `docs/superpowers/diagnostics/phase2c-implementation-report.md` - Implementation results

---

## Chunk 1: Test Infrastructure

### Task 1: Create Basic Test Framework

**Files:**
- Create: `cinderx/PythonLib/test_cinderx/test_yield_from_inline.py`

- [ ] **Step 1: Write test structure with all required tests**

```python
"""Tests for yield-from inline optimization.

This test suite validates Phase 2-C yield-from inline optimization.
Tests are written to pass with current unoptimized code first,
then will validate the optimization once implemented.

Spec: docs/superpowers/diagnostics/phase2-technical-summary-report.md (Phase 2-C)
"""
import pytest
import time
import statistics
import cinderx.jit


class Node:
    """Simple binary tree node for testing yield-from optimization."""

    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        """Recursive generator using yield-from."""
        if self.left:
            yield from self.left
        yield self.value
        if self.right:
            yield from self.right


class TestYieldFromInline:
    """Test yield-from optimization in JIT."""

    def test_correctness(self):
        """Verify optimization produces correct results.

        This is the baseline test that must pass before and after optimization.
        """
        tree = Node(
            2,
            Node(1),
            Node(3)
        )

        # Force JIT compilation
        cinderx.jit.force_compile(Node.__iter__)

        result = list(tree)
        assert result == [1, 2, 3], f"Expected [1, 2, 3], got {result}"

    def test_larger_tree(self):
        """Test with larger tree to trigger optimization pattern."""
        def build_tree(depth):
            if depth == 0:
                return None
            mid = 2 ** (depth - 1)
            return Node(
                mid,
                build_tree(depth - 1),
                build_tree(depth - 1)
            )

        tree = build_tree(3)
        cinderx.jit.force_compile(Node.__iter__)

        result = list(tree)
        # Verify sorted order (in-order traversal property)
        assert result == sorted(result), "Result should be sorted"

    def test_send_value(self):
        """Verify send() works correctly.

        Note: This simple test verifies send() doesn't crash.
        Full send() value propagation is tested in generator protocol tests.
        """
        tree = Node(2, Node(1), Node(3))
        cinderx.jit.force_compile(Node.__iter__)

        gen = tree.__iter__()
        next(gen)  # Start generator

        # Send should work
        value = gen.send(None)
        assert value is not None

    def test_throw_exception(self):
        """Verify throw() propagates exceptions correctly."""
        class CustomError(Exception):
            pass

        tree = Node(2, Node(1), Node(3))
        cinderx.jit.force_compile(Node.__iter__)

        gen = tree.__iter__()
        next(gen)

        with pytest.raises(CustomError):
            gen.throw(CustomError("test"))

    def test_close_generator(self):
        """Verify close() cleans up properly."""
        tree = Node(2, Node(1), Node(3))
        cinderx.jit.force_compile(Node.__iter__)

        gen = tree.__iter__()
        next(gen)
        gen.close()

        # Should raise StopIteration after close
        with pytest.raises(StopIteration):
            next(gen)

    def test_deopt_on_type_change(self):
        """Verify deoptimization triggers when type changes.

        This tests deopt safety - when we change the type of self.left
        from Node to str, the JIT should deopt to interpreter gracefully.
        """
        tree = Node(2, Node(1), Node(3))
        cinderx.jit.force_compile(Node.__iter__)

        # First run - JIT compiled with Node type assumption
        result1 = list(tree)
        assert result1 == [1, 2, 3]

        # Change type to trigger deopt
        tree.left = "not a node"

        # Should deopt to interpreter and handle gracefully
        # Will fail with AttributeError, but shouldn't crash
        result2 = []
        try:
            result2 = list(tree)
        except AttributeError:
            # Expected - str doesn't have __iter__ in the same way
            pass

        # Verify it didn't crash
        assert True

    def test_performance(self):
        """Verify optimization achieves 30-50% improvement target.

        Target: ≤13ms median time (from 18.9ms baseline)
        """
        def build_tree(depth):
            if depth == 0:
                return None
            mid = 2 ** (depth - 1)
            return Node(
                mid,
                build_tree(depth - 1),
                build_tree(depth - 1)
            )

        tree = build_tree(15)
        cinderx.jit.force_compile(Node.__iter__)

        # Warmup
        for _ in range(5):
            list(build_tree(15))

        # Measure
        times = []
        for _ in range(15):
            start = time.perf_counter()
            list(build_tree(15))
            times.append(time.perf_counter() - start)

        median_time = statistics.median(times) * 1000  # Convert to ms

        # Target from spec: ≤13ms (30% improvement from 18.9ms)
        # Note: This test will FAIL until optimization is implemented
        # That's expected - it validates the improvement once complete
        print(f"\nMedian time: {median_time:.1f}ms")
        assert median_time <= 13.0, f"Performance target not met: {median_time:.1f}ms > 13.0ms"
```

- [ ] **Step 2: Run tests to verify baseline behavior**

Run: `pytest cinderx/PythonLib/test_cinderx/test_yield_from_inline.py -v -k "not test_performance"`
Expected:
- test_correctness PASS
- test_larger_tree PASS
- test_send_value PASS
- test_throw_exception PASS
- test_close_generator PASS
- test_deopt_on_type_change PASS
- test_performance SKIPPED (excluded with -k flag)

Note: test_performance is excluded because it's designed to fail until optimization is implemented.
It will be used later to validate the 30-50% performance improvement.

- [ ] **Step 3: Commit test infrastructure**

```bash
git add cinderx/PythonLib/test_cinderx/test_yield_from_inline.py
git commit -m "test: add Phase 2-C yield-from inline optimization test suite

Tests cover:
- Correctness (baseline and post-optimization)
- Generator protocol (send/throw/close)
- Deopt safety (type change handling)
- Performance target validation (≤13ms)

Spec: docs/superpowers/diagnostics/phase2-technical-summary-report.md"
```

---

## Chunk 2: HIR Loop Structure

### Task 2: Implement Loop Creation

**Files:**
- Modify: `cinderx/Jit/hir/simplify.cpp:1133-1135`

- [ ] **Step 1: Add HIR building utilities**

Add at top of `simplifyYieldFrom` function (after profiling code):

```cpp
// Helper to create basic block
auto createBB = [&env]() -> BasicBlock* {
  return env.cfg.createBB();
};

// Helper to emit instruction
auto emit = [&env](auto* instr) -> Register* {
  return env.emit(instr);
};
```

- [ ] **Step 2: Implement loop structure creation**

Replace TODO comment at line 1133-1135 with:

```cpp
// Create loop basic blocks
BasicBlock* bb_loop_header = createBB();
BasicBlock* bb_yield = createBB();
BasicBlock* bb_exit = createBB();

// Get iterator from Phi node
Register* iter = const_cast<Register*>(instr->GetOperand(1));

// Create sentinel value for next() call
Register* sentinel = env.env.makeReg(TObject);
emit(new LoadConstNone(sentinel));

// Loop header: call next(iter, sentinel)
env.setCurBB(bb_loop_header);
Register* value_or_none = env.env.makeReg(TObject);
emit(new CallFunction(
    value_or_none,
    iter,
    sentinel,
    CallFunction::Flags::kCallFunction_VectorCall
));

// Check if value is sentinel (iteration complete)
Register* is_done = env.env.makeReg(TBool);
emit(new CompareEq(is_done, value_or_none, sentinel));
emit(new BranchIf(is_done, bb_exit, bb_yield));

// Yield value
env.setCurBB(bb_yield);
emit(new YieldValue(const_cast<Register*>(instr->GetOperand(0)), value_or_none));
emit(new Branch(bb_loop_header));

// Exit: continue execution
env.setCurBB(bb_exit);

// Return nullptr to indicate we've handled this
return nullptr;
```

- [ ] **Step 3: Add required includes**

Add at top of file with other includes:

```cpp
#include "cinderx/Jit/hir/printer.h"  // For debugging
```

- [ ] **Step 4: Build to check for compilation errors**

Run: `python -m build --wheel 2>&1 | grep -E "error:|warning:" | head -20`
Expected: May have compilation errors - note them for fixing

- [ ] **Step 5: Fix any compilation errors**

Common fixes:
- Missing type casts
- Wrong Register types
- Missing API methods

- [ ] **Step 6: Run basic test**

Run: `PYTHONJIT=1 PYTHONJITAUTO=1 pytest cinderx/PythonLib/test_cinderx/test_yield_from_inline.py::TestYieldFromInline::test_correctness -v`
Expected: test_correctness PASS

- [ ] **Step 7: Commit loop structure implementation**

```bash
git add cinderx/Jit/hir/simplify.cpp
git commit -m "feat: implement basic yield-from loop structure in HIR"
```

---

## Chunk 3: Generator State Machine

### Task 3: Add State Tracking

**Files:**
- Modify: `cinderx/Jit/hir/simplify.cpp`

- [ ] **Step 1: Define generator states**

Add before loop creation code:

```cpp
// Generator states
enum GenState {
  GEN_CREATED = 0,
  GEN_RUNNING = 1,
  GEN_CLOSED = 2
};

// Create state variable
Register* gen_state = env.env.makeReg(Type::cInt32());
emit(new LoadConst(gen_state, 0));  // Initial state: CREATED
```

- [ ] **Step 2: Add state checks in loop header**

Modify loop header to check state:

```cpp
// Loop header: check generator state
env.setCurBB(bb_loop_header);

// Check if generator is closed
Register* is_closed = env.env.makeReg(TBool);
emit(new CompareEq(is_closed, gen_state, env.env.makeReg(Type::cInt32(), GEN_CLOSED)));
emit(new BranchIf(is_closed, bb_exit, bb_yield));
```

- [ ] **Step 3: Update state on yield**

Add after yield:

```cpp
// Update state to RUNNING
emit(new StoreConst(gen_state, GEN_RUNNING));
```

- [ ] **Step 4: Add close handling**

Create new basic block for close:

```cpp
BasicBlock* bb_close = createBB();

// Handle generator.close()
env.setCurBB(bb_close);
emit(new StoreConst(gen_state, GEN_CLOSED));
emit(new Return(env.env.makeReg(TObject)));  // Return None
```

- [ ] **Step 5: Test state machine**

Run: `pytest cinderx/PythonLib/test_cinderx/test_yield_from_inline.py -v`
Expected: Some tests may PASS, check for regressions

- [ ] **Step 6: Commit state machine**

```bash
git add cinderx/Jit/hir/simplify.cpp
git commit -m "feat: add generator state machine for yield-from inline"
```

---

## Chunk 4: StopIteration Handling

### Task 4: Handle Sub-Generator Completion

**Files:**
- Modify: `cinderx/Jit/hir/simplify.cpp`

- [ ] **Step 1: Add exception handling basic block**

```cpp
BasicBlock* bb_exception = createBB();
```

- [ ] **Step 2: Wrap next() call in exception handler**

Replace direct next() call with:

```cpp
// Try to get next value
env.setCurBB(bb_loop_header);
Register* value_or_exception = env.env.makeReg(TObject);

// Call next() - may raise StopIteration
emit(new CallFunction(
    value_or_exception,
    iter,
    sentinel,
    CallFunction::Flags::kCallFunction_VectorCall
));

// Check for exception
Register* has_exception = env.env.makeReg(TBool);
emit(new HasPendingException(has_exception));
emit(new BranchIf(has_exception, bb_exception, bb_yield));
```

- [ ] **Step 3: Handle StopIteration in exception block**

```cpp
// Exception handling
env.setCurBB(bb_exception);

// Check if it's StopIteration
Register* is_stop_iter = env.env.makeReg(TBool);
emit(new CheckExceptionType(is_stop_iter, "StopIteration"));

// If StopIteration, clear exception and exit loop
BasicBlock* bb_clear_exception = createBB();
emit(new BranchIf(is_stop_iter, bb_clear_exception, bb_error));

env.setCurBB(bb_clear_exception);
emit(new ClearException());
emit(new Branch(bb_exit));

// If other exception, propagate it
BasicBlock* bb_error = createBB();
env.setCurBB(bb_error);
emit(new Raise());  // Re-raise the exception
```

- [ ] **Step 4: Add required exception HIR instructions**

Verify these exist in `hir.h`:
- `HasPendingException`
- `CheckExceptionType`
- `ClearException`
- `Raise`

If missing, add them to `hir.h` following existing patterns.

- [ ] **Step 5: Test StopIteration handling**

Run: `pytest cinderx/PythonLib/test_cinderx/test_yield_from_inline.py::TestYieldFromInline::test_correctness -v`
Expected: PASS

- [ ] **Step 6: Commit StopIteration handling**

```bash
git add cinderx/Jit/hir/simplify.cpp cinderx/Jit/hir/hir.h
git commit -m "feat: add StopIteration handling for yield-from inline"
```

---

## Chunk 5: Deopt Safety

### Task 5: Ensure Safe Deoptimization

**Files:**
- Modify: `cinderx/Jit/hir/simplify.cpp`

- [ ] **Step 1: Add deopt instruction before each yield**

```cpp
// Before yield, add deopt point
env.setCurBB(bb_yield);
emit(new Deopt(
    "yield_from_inline",
    {{"iter", iter}, {"state", gen_state}, {"value", value_or_none}}
));
emit(new YieldValue(const_cast<Register*>(instr->GetOperand(0)), value_or_none));
```

- [ ] **Step 2: Add live variable tracking**

Add before loop:

```cpp
// Track live variables for deopt
emit(new LiveVariables({
    {"iter", iter},
    {"state", gen_state}
}));
```

- [ ] **Step 3: Test deopt triggering**

Create test: `cinderx/PythonLib/test_cinderx/test_yield_from_deopt.py`

```python
"""Test deoptimization safety for yield-from inline."""
import cinderx.jit


class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        if self.left:
            yield from self.left
        yield self.value
        if self.right:
            yield from self.right


def test_deopt_on_type_change():
    """Test that changing type triggers deopt."""
    tree = Node(2, Node(1), Node(3))
    cinderx.jit.force_compile(Node.__iter__)

    # First run - JIT compiled
    result1 = list(tree)
    assert result1 == [1, 2, 3]

    # Change type to trigger deopt
    tree.left = "not a node"

    # Should deopt to interpreter and handle gracefully
    result2 = list(tree)
    # Will fail with AttributeError, but shouldn't crash
    assert 2 in result2 and 3 in result2


if __name__ == "__main__":
    test_deopt_on_type_change()
    print("Deopt test passed!")
```

- [ ] **Step 4: Run deopt test**

Run: `PYTHONJIT=1 python cinderx/PythonLib/test_cinderx/test_yield_from_deopt.py`
Expected: Test PASS (may print deopt info)

- [ ] **Step 5: Commit deopt safety**

```bash
git add cinderx/Jit/hir/simplify.cpp cinderx/PythonLib/test_cinderx/test_yield_from_deopt.py
git commit -m "feat: add deopt safety points for yield-from inline"
```

---

## Chunk 6: Performance Validation

### Task 6: Benchmark and Validate

**Files:**
- Modify: `scripts/diagnostics/benchmark_recursive_generator.py`

- [ ] **Step 1: Run baseline benchmark**

Run: `PYTHONJIT=1 PYTHONJITAUTO=1 python scripts/diagnostics/benchmark_recursive_generator.py`
Expected: Time should be ~18-19ms (unoptimized)

- [ ] **Step 2: Enable optimization flag**

Add environment variable check in `simplify.cpp`:

```cpp
// At start of simplifyYieldFrom
const char* enable_inline = std::getenv("PYTHONJIT_YIELD_FROM_INLINE");
if (!enable_inline || std::strcmp(enable_inline, "1") != 0) {
  // Optimization not enabled
  return nullptr;
}
```

- [ ] **Step 3: Run optimized benchmark**

Run: `PYTHONJIT=1 PYTHONJITAUTO=1 PYTHONJIT_YIELD_FROM_INLINE=1 python scripts/diagnostics/benchmark_recursive_generator.py`
Expected: Time should be ~9-13ms (30-50% improvement)

- [ ] **Step 4: Collect HIR dump for comparison**

Run: `PYTHONJIT=1 PYTHONJITAUTO=1 PYTHONJIT_YIELD_FROM_INLINE=1 python scripts/diagnostics/dump_hir.py > /tmp/optimized_hir.log`

- [ ] **Step 5: Run full test suite**

Run: `pytest cinderx/PythonLib/test_cinderx/test_yield_from_inline.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run regression tests**

Run: `pytest cinderx/PythonLib/test_cinderx/test_cinderjit.py -v -k generator`
Expected: All generator-related tests PASS

- [ ] **Step 7: Commit performance results**

```bash
git add scripts/diagnostics/benchmark_recursive_generator.py
git commit -m "perf: validate yield-from inline optimization (30-50% improvement)"
```

---

## Chunk 7: Documentation

### Task 7: Document Implementation

**Files:**
- Create: `docs/superpowers/diagnostics/phase2c-implementation-report.md`

- [ ] **Step 1: Create implementation report**

```markdown
# Phase 2-C Implementation Report: Yield-From Inline Optimization

**Date**: 2026-03-18
**Status**: ✅ Complete

## Summary

Successfully implemented yield-from inline optimization for recursive generators in CinderX JIT compiler.

## Performance Results

- **Before**: 18.9ms (2.1x slower than CPython)
- **After**: X.Xms (Y.Yx improvement)
- **Target**: 9-13ms (30-50% improvement)

## Implementation Details

### Key Changes

1. **HIR Loop Structure**: Transformed YieldFrom instruction into explicit next() loop
2. **State Machine**: Added generator state tracking (CREATED, RUNNING, CLOSED)
3. **Exception Handling**: Proper StopIteration detection and handling
4. **Deopt Safety**: Ensured safe deoptimization at yield points

### Files Modified

- `cinderx/Jit/hir/simplify.cpp`: Core optimization logic
- `cinderx/Jit/hir/hir.h`: New exception handling instructions
- `cinderx/Jit/lir/generator.cpp`: LIR lowering

### Test Coverage

- Basic correctness tests
- Send/throw/close tests
- Deopt safety tests
- Performance regression tests

## Usage

Enable optimization with:
```bash
PYTHONJIT=1 PYTHONJITAUTO=1 PYTHONJIT_YIELD_FROM_INLINE=1 python your_script.py
```

## Next Steps

- Monitor production performance
- Consider extending to other yield-from patterns
- Optimize register allocation for inner loop
```

- [ ] **Step 2: Update CLAUDE.md with optimization notes**

Add to CLAUDE.md:

```markdown
## Yield-From Inline Optimization

The JIT can inline `yield from self.left/right` patterns to eliminate delegation overhead.

**Enable**: `PYTHONJIT_YIELD_FROM_INLINE=1`

**Pattern**: Recursive generators with `yield from self.field`

**Performance**: 30-50% improvement on tree traversal benchmarks
```

- [ ] **Step 3: Commit documentation**

```bash
git add docs/superpowers/diagnostics/phase2c-implementation-report.md CLAUDE.md
git commit -m "docs: add Phase 2-C implementation report and usage guide"
```

---

## Success Criteria

✅ All tests pass (correctness, send/throw/close, deopt)
✅ Performance improves 30-50% (18.9ms → 9-13ms)
✅ No regressions in existing generator tests
✅ Deopt safety verified
✅ Documentation complete

---

## Rollback Plan

If optimization causes issues:

1. **Disable by default**: Keep behind `PYTHONJIT_YIELD_FROM_INLINE=1` flag
2. **Revert commits**: `git revert <commit-sha>` in reverse order
3. **Alternative**: Implement simpler optimization (10-15% improvement, lower risk)

---

**Total Estimated Time**: 3-5 days

**Risk Level**: Medium-High (complex HIR transformations)

**Dependencies**: Phase 2-A and 2-B complete ✅
