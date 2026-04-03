# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 语言偏好 / Language Preference

**重要**: 本项目使用中文进行所有交流和文档编写。

- 所有对话、注释、文档、提交信息统一使用中文
- 代码中的注释使用中文
- 技术文档和报告使用中文编写
- Git提交信息使用中文

**Note**: Code variable names, function names, and technical terms remain in English as per standard programming conventions.

## MCP工具使用 / MCP Tool Usage

**MCP工具策略**: 优先使用claude-mem记忆工具，其他MCP工具暂时禁用。

- ✅ **claude-mem**: 用于访问持久化记忆和跨会话上下文
- ❌ **其他MCP工具**: 暂时不使用，除非：
  - 遇到无法通过本地资源解决的技术问题
  - 用户明确要求使用特定MCP工具

**使用claude-mem的场景**:
- 访问之前的对话和决策历史
- 查找相关技术问题的解决方案
- 回顾项目上下文和背景信息

## Project Overview

CinderX is a Python extension that improves the performance of the Python runtime through:
- **JIT Compiler**: Just-in-time compilation of Python bytecode to native machine code
- **Static Python**: A stricter form/subset of Python with type safety and compile-time optimizations

It is used in production at Meta (e.g., Instagram Django services) and is published weekly to PyPI.

## Requirements

- Python 3.14.3 or later
- Linux (x86_64) - primary platform
- GCC 13+ or Clang 18+
- macOS: builds and imports but most features disabled at runtime
- Windows: not supported

## Build Commands

### Standard Build
```bash
# Build wheel
python -m build --wheel

# Install locally
pip install .
# or
pip install dist/*.whl
```

### Build with Optimizations
```bash
# Enable PGO (Profile-Guided Optimization)
CINDERX_ENABLE_PGO=1 python -m build --wheel

# Enable LTO (Link-Time Optimization)
CINDERX_ENABLE_LTO=1 python -m build --wheel

# Control parallelism
CINDERX_BUILD_JOBS=4 python -m build --wheel
```

### Environment Variables for Build
- `CINDERX_ENABLE_PGO`: Enable profile-guided optimization (1/0)
- `CINDERX_ENABLE_LTO`: Enable link-time optimization (1/0)
- `CINDERX_BUILD_JOBS`: Number of parallel build jobs (default: CPU count)
- `CINDERX_VERSION_PATCH`: Override patch version number for same-day releases
- `CC` / `CXX`: Override C/C++ compiler paths
- `CMAKE_BUILD_TYPE`: Build type (default: RelWithDebInfo)

## Testing

### Python Tests
```bash
# Install pytest
pip install pytest

# Run all Python tests
pytest cinderx/PythonLib/test_cinderx/test*.py

# Run specific test file
pytest cinderx/PythonLib/test_cinderx/test_cinderjit.py

# Run specific test
pytest cinderx/PythonLib/test_cinderx/test_cinderjit.py::TestCinderJIT::test_simple
```

### C++ Unit Tests
C++ tests are in `cinderx/RuntimeTests/` and built via CMake. They require the extension to be built first.

### Integration Tests
Integration tests in `tests/` directory validate build configuration and feature detection.

## Code Architecture

### High-Level Structure

```
cinderx/
├── Jit/                    # JIT compiler implementation
│   ├── hir/               # High-level IR (intermediate representation)
│   ├── lir/               # Low-level IR
│   ├── codegen/           # Code generation
│   └── *.cpp/h            # Core JIT components
├── StaticPython/          # Static Python compiler and runtime
├── Common/                # Shared utilities (logging, memory, etc.)
├── PythonLib/             # Python-side implementation
│   ├── cinderx/          # Python API modules (jit.py, static.py, etc.)
│   └── test_cinderx/     # Python test suite
├── RuntimeTests/          # C++ unit tests
└── Interpreter/           # Interpreter modifications

cinderx/PythonLib/cinderx/
├── __init__.py           # Main module initialization
├── jit.py                # JIT Python API
├── static.py             # Static Python API
└── compiler/             # Compiler Python modules
```

### Key Components

1. **JIT Compiler** (`cinderx/Jit/`)
   - Compiles Python bytecode to native code
   - Uses HIR (High-level IR) → LIR (Low-level IR) → native codegen pipeline
   - Entry point: `pyjit.cpp`
   - Deoptimization support: `deopt.cpp`

2. **Static Python** (`cinderx/StaticPython/`)
   - Specialized bytecode compiler using type annotations
   - Generates optimized opcodes (e.g., `LOAD_FIELD` instead of `LOAD_ATTR`)
   - Runtime type checking with zero-cost abstractions when types match

3. **Python API** (`cinderx/PythonLib/cinderx/`)
   - `jit.py`: JIT control (`cinderx.jit.auto()`, `force_compile()`, etc.)
   - `static.py`: Static Python decorators and utilities
   - `__init__.py`: Module initialization and feature detection

### Build System

- **setuptools** (`setup.py`): Python package build
  - `BuildCommand`: Handles PGO builds (3 stages: instrument → profile → optimize)
  - `BuildExt`: CMake integration for C++ extension
  - `BuildPy`: Python module compilation and opcode generation

- **CMake** (`CMakeLists.txt`): C++ build
  - Builds `_cinderx` native extension
  - Handles compiler detection, LTO, PGO flags
  - Feature flags control optional components

### Opcode System
Python opcodes are version-specific:
- Located in `cinderx/PythonLib/opcodes/{version}/opcode.py`
- Copied to `cinderx/opcode.py` during build
- Static Python adds specialized opcodes (e.g., `LOAD_FIELD`, `STORE_FIELD`)

## Using the JIT

```python
import cinderx.jit

# Automatic compilation (recommended)
cinderx.jit.auto()

# Or compile after N calls
cinderx.jit.compile_after_n_calls(10)

# Or manual compilation
def foo(): ...
cinderx.jit.force_compile(foo)
cinderx.jit.lazy_compile(bar)
```

## Development Workflow

### Making Changes
1. Build: `python -m build --wheel`
2. Install: `pip install --force-reinstall dist/*.whl`
3. Test: `pytest cinderx/PythonLib/test_cinderx/test*.py`

### Platform-Specific Code
- Check `MACOS` define in CMake for macOS-specific code
- Use `sys.platform == "darwin"` in Python
- Most features are Linux-only; check feature flags in `setup.py`

### Debugging JIT Issues
- `PYTHONJIT=0`: Disable JIT
- `PYTHONJIT=1`: Enable JIT
- `PYTHONJITAUTO=N`: Auto-compile after N calls
- `PYTHONJITDEBUG=1`: Enable debug logging
- `PYTHONJITLOGFILE=/path/to/log`: Write JIT log to file
- `PYTHONJITLISTFILE=/path/to/list`: Compile only listed functions
- `PYTHONJITDUMPASM=1`: Dump assembly alongside HIR to see compiled code

### Feature Flags
Controlled via environment variables during build (see `setup.py`):
- `ENABLE_STATIC_PYTHON`: Static Python support (default: ON)
- `ENABLE_ADAPTIVE_STATIC_PYTHON`: Adaptive type specialization (Python 3.14 ARM only)
- `ENABLE_LIGHTWEIGHT_FRAMES`: Lightweight interpreter frames
- `ENABLE_PARALLEL_GC`: Parallel garbage collector

## Important Notes

### Version Management
- Version format: `YYYY.MM.DD.PP` (date-based with patch number)
- Automatically generated from UTC date during build
- Use `CINDERX_VERSION_PATCH` for multiple releases same day

### Code Style
- C++: Follow `.clang-format` in `cinderx/` directory
- Python: Standard Python style, type annotations where appropriate
- Use `# pyre-strict` for type-checked Python files

### Compatibility
- Python 3.14 is the first version supporting stock CPython
- Earlier versions (3.10-3.12) required Meta's forked runtime
- Extension imports on macOS but most features disabled

### Testing Philosophy
- Python tests in `cinderx/PythonLib/test_cinderx/` test end-to-end functionality
- C++ tests in `cinderx/RuntimeTests/` test internal components
- Integration tests in `tests/` validate build setup
- Many tests use `skip_module_if_oss()` for Meta-specific features

## Adding a New HIR Instruction

The JIT's HIR (High-level IR) is defined in `cinderx/Jit/hir/`. Adding a new instruction requires updates to all of these files:

1. **`Jit/hir/opcode.h`** - Add to `FOREACH_OPCODE` macro (auto-generates enum + `Is<Opcode>()` predicates)
2. **`Jit/hir/hir.h`** - Define the instruction class using `DEFINE_SIMPLE_INSTR` or `INSTR_CLASS` with template parameters (`HasOutput`, `Operands<N>`, `DeoptBase`, etc.)
3. **`Jit/lir/generator.cpp`** - Add a lowering case in `TranslateOneBasicBlock()` (use `bbb.appendCallInstruction()` for runtime calls or `bbb.appendInstr()` for inline codegen)
4. **`Jit/hir/instr_effects.cpp`** - Add to both `memoryEffects()` and `hasArbitraryExecution()` switch statements
5. **`Jit/hir/hir.cpp`** - Add to `isReplayable()` and `isPassthrough()`
6. **`Jit/hir/printer.cpp`** - Add to `format_immediates()`
7. **`Jit/hir/pass.cpp`** - Add to `outputType()`
8. **`Jit/hir/parser.cpp`** - Add parsing support in `parseInstr()` if test HIR parsing is needed

If a custom runtime helper is needed: declare in `Jit/jit_rt.h`, implement in `Jit/jit_rt.cpp`.

## Non-Public Python APIs ("Borrowing")

CinderX has an automated system for copying upstream CPython internal code ("borrowing") to avoid forking Python. **Always prefer automated borrowing over manual copying.**

- Implementation: `cinderx/UpstreamBorrow/UpstreamBorrow.py`
- Borrow directives per Python version: `borrowed-3.14.c.template`, `borrowed-3.14.free-threading.c.template`, etc.
- Shared header: `borrowed.h`

The CinderX interpreter (`cinderx/Interpreter/<version>/`) is the exception — it mixes manually copied code, borrowed code, and Python interpreter generator tool overrides:
- `borrowed-ceval.c.template`: local borrows for the interpreter
- `cinder-bytecodes.c`: override implementations and new CinderX bytecodes
- Upstream base: `<python source>/Python/bytecodes.c`

## Multi-Version Python Support

In C/C++ code use `PY_VERSION_HEX` and `Py_GIL_DISABLED` macros to select version-specific code. Utilities in `cinderx/Common/` abstract commonly-changed features across Python versions.

## References

- JIT guide: `cinderx/Jit/guide.md`
- Deoptimization: `cinderx/Jit/deoptimization.md`
- Static Python docs: `cinderx/Docs/StaticPython/README.md`
- ARM bring-up guide: `arm_jit_guide.md`
