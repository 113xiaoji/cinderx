#!/usr/bin/env python3
"""
TreeIterStateMachinePass 性能基准测试

单次运行，输出 ON/OFF 两组数据到 stdout（逗号分隔），
方便外部脚本对比分析。

用法:
  PYTHONJITTREEITERSTATEMACHINE=1 python bench_tree_iter.py > sm_on.csv
  PYTHONJITTREEITERSTATEMACHINE=0 python bench_tree_iter.py > sm_off.csv
"""

import os
import time
import statistics

os.environ['PYTHONJITHUGEPAGES'] = '0'
os.environ['PYTHONJIT'] = '1'
os.environ['PYTHONJITDEBUG'] = '0'

from cinderx import jit
jit.compile_after_n_calls(1)


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


def build_tree(depth):
    if depth == 0:
        return None
    return Node(depth, build_tree(depth - 1), build_tree(depth - 1))


def benchmark(tree, warmup=3, repeats=10):
    for _ in range(warmup):
        list(tree)
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter_ns()
        result = list(tree)
        t1 = time.perf_counter_ns()
        times.append(t1 - t0)
    return statistics.median(times), len(result)


def main():
    sm = os.environ.get('PYTHONJITTREEITERSTATEMACHINE', '0') == '1'
    print(f"# {'ON' if sm else 'OFF'}")
    print(f"depth,nodes,median_us")

    for d in range(1, 13):
        tree = build_tree(d)
        if tree is None:
            continue
        list(tree)  # trigger JIT compile
        median_ns, n = benchmark(tree)
        print(f"{d},{n},{median_ns/1000:.2f}")


if __name__ == '__main__':
    main()
