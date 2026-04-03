#!/bin/bash
# 使用 lldb 运行 Python 测试脚本

echo "=== 使用 lldb 调试 CinderX JIT ==="
echo ""

# 设置环境变量
export PYTHONJITHUGEPAGES=0
export PYTHONJIT=1
export PYTHONJITTREEITERSTATEMACHINE=1

# 运行 lldb
echo "启动 lldb..."
echo ""

lldb -s lldb_commands.txt -- .venv/bin/python3 test_lldb_debug.py
