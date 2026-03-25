#!/usr/bin/env python3
"""调试脚本：验证 TreeIterStateMachinePass 是否运行"""

import os
import sys

# 设置环境变量（必须在导入 cinderx 之前）
os.environ['PYTHONJITHUGEPAGES'] = '0'
os.environ['PYTHONJIT'] = '1'
os.environ['PYTHONJITTREEITERSTATEMACHINE'] = '1'

# 导入并启用 JIT
from cinderx import jit
jit.auto()

# 定义树遍历生成器
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

# 多次调用触发 JIT 编译
for i in range(150):
    tree = Node(2, Node(1), Node(3))
    result = list(tree)
    if i == 0:
        print(f"第一次迭代: {result}")
    elif i == 149:
        print(f"最后一次迭代: {result}")

print("\n完成！请检查上面的 JIT 日志输出，查找 'TreeIterStateMachinePass' 字样")
