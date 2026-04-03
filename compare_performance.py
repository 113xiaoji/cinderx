#!/usr/bin/env python3
"""
性能对比脚本：对比 JIT 启用和禁用的性能差异
"""

# 数据来自 benchmark_state_machine.py 的运行结果

# JIT 启用 (PYTHONJIT=1)
jit_enabled = {
    1: 0.0023,
    2: 0.0004,
    3: 0.0009,
    5: 0.0052,
    7: 0.0266,
    10: 0.3392,
}

# JIT 禁用 (PYTHONJIT=0) - 基线
jit_disabled = {
    1: 0.0002,
    2: 0.0006,
    3: 0.0013,
    5: 0.0070,
    7: 0.0349,
    10: 0.3390,
}

print("=" * 80)
print("Phase 2 性能对比：JIT 启用 vs 禁用")
print("=" * 80)
print()
print(f"{'Depth':<8} {'Nodes':<8} {'JIT On (ms)':<15} {'JIT Off (ms)':<15} {'Speedup':<10} {'Status'}")
print("-" * 80)

for depth in sorted(jit_enabled.keys()):
    nodes = 2**depth - 1
    time_on = jit_enabled[depth]
    time_off = jit_disabled[depth]

    # 计算加速比
    if time_on > 0 and time_off > 0:
        speedup = time_off / time_on
        if speedup > 1:
            status = f"✓ {speedup:.2f}x faster"
            status_color = "green"
        elif speedup < 1:
            slowdown = 1 / speedup
            status = f"✗ {slowdown:.2f}x slower"
            status_color = "red"
        else:
            status = "= No change"
            status_color = "yellow"
    else:
        speedup = 0
        status = "N/A"

    print(f"{depth:<8} {nodes:<8} {time_on:<15.4f} {time_off:<15.4f} {speedup:<10.2f} {status}")

print("-" * 80)
print()

# 分析结果
print("性能分析:")
print("-" * 80)

# 计算平均加速比
speedups = []
for depth in jit_enabled:
    if jit_enabled[depth] > 0 and jit_disabled[depth] > 0:
        speedups.append(jit_disabled[depth] / jit_enabled[depth])

avg_speedup = sum(speedups) / len(speedups) if speedups else 1.0
print(f"平均加速比: {avg_speedup:.2f}x")
print()

# 分析小树（depth ≤ 5）
print("小树 (depth ≤ 5):")
for depth in [1, 2, 3, 5]:
    speedup = jit_disabled[depth] / jit_enabled[depth]
    print(f"  depth={depth}: {speedup:.2f}x")
print()

# 分析大树（depth > 5）
print("大树 (depth > 5):")
for depth in [7, 10]:
    speedup = jit_disabled[depth] / jit_enabled[depth]
    print(f"  depth={depth}: {speedup:.2f}x")
print()

print("结论:")
print("-" * 80)
print("1. JIT 编译对于生成器遍历有一定的性能影响")
print("2. 对于小树 (depth ≤ 5)，性能差异不大，有时甚至变慢")
print("3. 对于大树 (depth > 5)，JIT 略有优势")
print()
print("⚠ 注意:")
print("  - 当前 JIT 还没有实现 Phase 2 的状态机优化")
print("  - 预期在状态机优化后，depth ≤ 5 应该有 4-6x 改进")
print("  - 当前结果仅反映了现有 JIT 的性能表现")
print()
