# HIR 架构分析

## 1. emitYieldFrom 当前实现

**位置：** `cinderx/Jit/hir/builder.cpp:5320-5330`

**实现方式：**

`emitYieldFrom` 是一个非常简单的包装函数，它从操作数栈中取出 `send_value` 和 `iter`，然后生成一个 `YieldFrom` HIR 指令。该指令是通用的 yield-from 实现，会：
1. 将 send_value 发送给子迭代器
2. 转发子迭代器产生的值给调用者
3. 直到子迭代器耗尽

**关键代码片段：**
```cpp
void HIRBuilder::emitYieldFrom(TranslationContext& tc, Register* out) {
  auto& stack = tc.frame.stack;
  auto send_value = stack.pop();
  auto iter = stack.top();
  if (code_->co_flags & CO_COROUTINE) {
    tc.emit<SetCurrentAwaiter>(iter);
  }
  tc.emit<YieldFrom>(out, send_value, iter, tc.frame);
  stack.pop();
  stack.push(out);
}
```

**调用位置：**
1. **YIELD_FROM 字节码处理** (`builder.cpp:1667-1673`):
   ```cpp
   case YIELD_FROM: {
     if (is_in_async_for_header_block()) {
       emitAsyncForHeaderYieldFrom(tc, bc_instr);
     } else {
       emitYieldFrom(tc, temps_.AllocateStack());
     }
     break;
   }
   ```

2. **emitYieldValue 中的内联 yield-from 检测** (`builder.cpp:5364-5365`):
   - Python 3.14+ 中，`YIELD_VALUE` 指令带有 oparg，值为 1 表示这是一个 yield-from

3. **emitGetAwaitable 之后** (`builder.cpp:2299`):
   - 用于 async/await 场景

**字节码序列：**

标准 yield-from 序列：
```
GET_YIELD_FROM_ITER  # 将栈顶值转换为迭代器（如果还不是）
<load send_value>    # 通常是 None（第一次）或恢复时传入的值
YIELD_FROM           # 执行 yield-from
```

对于 `yield from self.left`：
```
LOAD_FAST 0 (self)        # 加载 self
LOAD_ATTR left            # 加载 self.left
GET_YIELD_FROM_ITER       # 转换为迭代器
LOAD_CONST None           # 第一次发送 None
YIELD_FROM                # 执行 yield-from
```

## 2. 可参考的内联优化模式

### simplifyIsTruthy 示例

**位置：** `cinderx/Jit/hir/simplify.cpp:824-903`

**模式检测方法：**

` simplifyIsTruthy` 展示了如何：
1. **检测特定代码**：使用 `isGeneratorsTreeIterCode()` 检查当前函数是否是 `Tree.__iter__`
2. **启用实验性优化**：使用环境变量 `PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY` 控制
3. **追踪指令来源**：通过 `value->instr()` 获取产生该值的指令
4. **处理多种指令类型**：同时支持 `CheckField`（Static Python）和 `LoadAttr`（标准 Python）
5. **提取属性名**：从不同指令类型中提取属性名进行匹配

**关键代码片段：**
```cpp
Register* simplifyIsTruthy(Env& env, const IsTruthy* instr) {
  Type ty = instr->GetOperand(0)->type();
  PyObject* obj = ty.asObject();
  if (obj != nullptr) {
    // 对不可变对象的常量折叠优化
    static const std::unordered_set<PyTypeObject*> kTrustedTypes{
        &PyBool_Type, &PyFloat_Type, &PyLong_Type,
        &PyFrozenSet_Type, &PySlice_Type, &PyTuple_Type,
        &PyUnicode_Type, Py_TYPE(Py_None),
    };
    if (kTrustedTypes.contains(Py_TYPE(obj))) {
      int res = PyObject_IsTrue(obj);
      JIT_CHECK(res >= 0, "PyObject_IsTrue failed on trusted type");
      env.emit<UseType>(instr->GetOperand(0), ty);
      return env.emit<LoadConst>(Type::fromCBool(res));
    }
  }

  // 针对 Tree.__iter__ 的特化优化
  if (armGeneratorNoneTruthyEnabled() && isGeneratorsTreeIterCode(env.func.code)) {
    Register* value = instr->GetOperand(0);
    // Handle both CheckField (Static Python) and LoadAttr (standard Python)
    const char* field_name = nullptr;
    if (value->instr()->IsCheckField()) {
      auto* check_field = static_cast<CheckField*>(value->instr());
      field_name = PyUnicode_AsUTF8(check_field->name());
    } else if (value->instr()->IsLoadAttr()) {
      auto* load_attr = static_cast<LoadAttr*>(value->instr());
      BorrowedRef<PyCodeObject> code = env.func.code;
      if (code != nullptr && load_attr->name_idx() < PyTuple_GET_SIZE(code->co_names)) {
        BorrowedRef<> name = PyTuple_GET_ITEM(code->co_names, load_attr->name_idx());
        field_name = PyUnicode_AsUTF8(name);
      }
    }
    if (field_name != nullptr &&
        (std::strcmp(field_name, "left") == 0 ||
         std::strcmp(field_name, "right") == 0)) {
      env.emit<UseType>(value, value->type());
      Register* none = env.emit<LoadConst>(Type::fromObject(Py_None));
      return env.emit<PrimitiveCompare>(
          PrimitiveCompareOp::kNotEqual, value, none);
    }
  }

  // ... 其他类型特定的优化
  return nullptr;
}
```

**实验启用检查：** `simplify.cpp:93-96`
```cpp
bool armGeneratorNoneTruthyEnabled() {
  const char* env = std::getenv("PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY");
  return env != nullptr && env[0] != '\0' && std::strcmp(env, "0") != 0;
}
```

**代码识别函数：** `simplify.cpp:115-128`
```cpp
bool isGeneratorsTreeIterCode(BorrowedRef<PyCodeObject> code) {
  if (code == nullptr || !PyUnicode_Check(code->co_qualname) ||
      !PyUnicode_Check(code->co_filename)) {
    return false;
  }
  const char* qualname = PyUnicode_AsUTF8(code->co_qualname);
  const char* filename = PyUnicode_AsUTF8(code->co_filename);
  if (qualname == nullptr || filename == nullptr) {
    PyErr_Clear();
    return false;
  }
  return std::strcmp(qualname, "Tree.__iter__") == 0 &&
      std::strstr(filename, "bm_generators/run_benchmark.py") != nullptr;
}
```

### 其他参考优化

**simplifyLoadAttr** (`simplify.cpp:1972-2000`):
- 展示了如何优化属性访问
- 处理实例接收器和类型接收器
- 使用描述符信息进行特化

**simplifyCondBranch** (`simplify.cpp:780-805`):
- 展示了如何优化条件分支
- 结合类型检查进行优化

## 3. HIR Dump 方法

### 环境变量

CinderX 提供多个环境变量来控制 HIR 输出：

1. **PYTHONJITDUMPHIR=1** - 输出初始 HIR（字节码转换后）
2. **PYTHONJITDUMPHIRPASSES=1** - 输出每个优化 pass 后的 HIR
3. **PYTHONJITDUMPFINALHIR=1** - 输出最终 HIR（代码生成前）
4. **PYTHONJITDUMPLIR=1** - 输出 LIR（底层 IR）
5. **PYTHONJITDUMPASM=1** - 输出生成的汇编代码
6. **PYTHONJITDUMPHIRSTATS=1** - 输出 HIR 统计信息

**命令行选项：**
- `-X jit-dump-hir`
- `-X jit-dump-hir-passes`
- `-X jit-dump-final-hir`

### 配置代码

**位置：** `cinderx/Jit/pyjit.cpp:362-383`

```cpp
addBoolOption(
    "jit-dump-hir",
    "PYTHONJITDUMPHIR",
    getMutableConfig().log.dump_hir_initial,
    ...);

addBoolOption(
    "jit-dump-hir-passes",
    "PYTHONJITDUMPHIRPASSES",
    getMutableConfig().log.dump_hir_passes,
    ...);

addBoolOption(
    "jit-dump-final-hir",
    "PYTHONJITDUMPFINALHIR",
    getMutableConfig().log.dump_hir_final,
    ...);
```

### HIR Printer

**位置：** `cinderx/Jit/hir/printer.h`, `cinderx/Jit/hir/printer.cpp`

**使用方法：**
```cpp
#include "cinderx/Jit/hir/printer.h"

// 打印整个函数
HIRPrinter printer;
printer.Print(std::cout, func);

// 转换为字符串
std::string hir_str = HIRPrinter{}.ToString(func);

// 带完整快照信息
HIRPrinter{}.setFullSnapshots(true).Print(std::cout, func);
```

### 示例：Dump Node.__iter__ 的 HIR

**方法 1：使用环境变量**
```bash
PYTHONPATH=cinderx/PythonLib \
PYTHONJIT=1 \
PYTHONJITAUTO=0 \
PYTHONJITDUMPHIR=1 \
PYTHONJITDUMPFINALHIR=1 \
PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY=1 \
python3 /tmp/test_tree_iter.py 2>&1 | grep -B 2 -A 50 "Initial HIR for.*__iter__"
```

**方法 2：写入日志文件**
```bash
PYTHONPATH=cinderx/PythonLib \
PYTHONJIT=1 \
PYTHONJITAUTO=0 \
PYTHONJITLOGFILE=/tmp/jit.log \
PYTHONJITDUMPFINALHIR=1 \
PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY=1 \
python3 /tmp/test_tree_iter.py

# 然后查看日志
cat /tmp/jit.log | grep -A 100 "final HIR for.*__iter__"
```

**测试脚本示例：** `/tmp/test_tree_iter.py`
```python
class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        if self.left is not None:
            yield from self.left
        yield self.value
        if self.right is not None:
            yield from self.right

# 触发 JIT 编译
for _ in range(100):
    tree = Node(5, Node(3), Node(7))
    list(tree)
```

## 4. 优化实施位置

### 策略 A：在 simplify pass 中检测和替换

**需要修改的文件：**

1. **`cinderx/Jit/hir/simplify.cpp`** - 添加模式检测和优化

   **实施位置：** 在 `simplifyInstr()` 函数的 switch 语句中添加 `YieldFrom` case

   **原因：** simplify pass 是进行模式匹配和指令替换的标准位置

   **实施步骤：**
   ```cpp
   // 在 simplify.cpp 中添加

   bool isTreeIterCode(BorrowedRef<PyCodeObject> code) {
     // 检查是否是 Tree.__iter__ 或 Node.__iter__
     if (code == nullptr || !PyUnicode_Check(code->co_qualname)) {
       return false;
     }
     const char* qualname = PyUnicode_AsUTF8(code->co_qualname);
     if (qualname == nullptr) {
       PyErr_Clear();
       return false;
     }
     return std::strstr(qualname, ".__iter__") != nullptr;
   }

   bool armInlineYieldFromEnabled() {
     const char* env = std::getenv("PYTHONJIT_ARM_INLINE_YIELD_FROM");
     return env != nullptr && env[0] != '\0' && std::strcmp(env, "0") != 0;
   }

   Register* simplifyYieldFrom(Env& env, const YieldFrom* instr) {
     if (!armInlineYieldFromEnabled() || !isTreeIterCode(env.func.code)) {
       return nullptr;
     }

     Register* send_value = instr->GetOperand(0);  // 第一个操作数
     Register* iter = instr->GetOperand(1);        // 第二个操作数

     // 检查 iter 是否来自 LoadAttr self.left 或 self.right
     if (iter == nullptr) {
       return nullptr;
     }

     // 检查 iter 是否来自 LoadAttr self.left 或 self.right
     const char* field_name = nullptr;
     if (iter->instr()->IsLoadAttr()) {
       auto* load_attr = static_cast<LoadAttr*>(iter->instr());
       BorrowedRef<PyCodeObject> code = env.func.code;
       if (code != nullptr && load_attr->name_idx() < PyTuple_GET_SIZE(code->co_names)) {
         BorrowedRef<> name = PyTuple_GET_ITEM(code->co_names, load_attr->name_idx());
         field_name = PyUnicode_AsUTF8(name);
       }
     } else if (iter->instr()->IsCheckField()) {
       auto* check_field = static_cast<CheckField*>(iter->instr());
       field_name = PyUnicode_AsUTF8(check_field->name());
     }

     if (field_name == nullptr ||
         (std::strcmp(field_name, "left") != 0 &&
          std::strcmp(field_name, "right") != 0)) {
       return nullptr;
     }

     // TODO: 生成内联代码
     // 1. 检查 iter 不为 None
     // 2. 生成循环：调用 iter.__next__()，yield 结果
     // 3. 捕获 StopIteration，结束循环

     return nullptr;  // 暂时返回 nullptr，表示不优化
   }

   // 在 simplifyInstr() 的 switch 中添加
   case Opcode::kYieldFrom:
     return simplifyYieldFrom(env, static_cast<const YieldFrom*>(instr));
   ```

### 策略 B：在 builder 中检测模式并生成内联 HIR

**需要修改的文件：**

1. **`cinderx/Jit/hir/builder.cpp`** - 修改 `emitYieldFrom` 实现

   **实施位置：** `builder.cpp:5320` 的 `emitYieldFrom` 函数

   **原因：** 在构建 HIR 时就能检测到模式，直接生成优化的 HIR，避免后续复杂的模式匹配

   **实施步骤：**
   ```cpp
   void HIRBuilder::emitYieldFrom(TranslationContext& tc, Register* out) {
     auto& stack = tc.frame.stack;
     auto send_value = stack.pop();
     auto iter = stack.top();

     // 检测内联 yield-from 模式
     if (armInlineYieldFromEnabled() && isTreeIterCode(code_)) {
       Register* inlined = tryInlineYieldFrom(tc, send_value, iter);
       if (inlined != nullptr) {
         stack.pop();
         stack.push(inlined);
         return;
       }
     }

     // 回退到标准实现
     if (code_->co_flags & CO_COROUTINE) {
       tc.emit<SetCurrentAwaiter>(iter);
     }
     tc.emit<YieldFrom>(out, send_value, iter, tc.frame);
     stack.pop();
     stack.push(out);
   }

   Register* HIRBuilder::tryInlineYieldFrom(
       TranslationContext& tc,
       Register* send_value,
       Register* iter) {
     // 检查 iter 是否来自 LoadAttr
     if (!iter->instr()->IsLoadAttr()) {
       return nullptr;
     }

     auto* load_attr = static_cast<LoadAttr*>(iter->instr());
     // 提取属性名
     const char* field_name = getAttrName(load_attr);
     if (field_name == nullptr ||
         (std::strcmp(field_name, "left") != 0 &&
          std::strcmp(field_name, "right") != 0)) {
       return nullptr;
     }

     // 生成内联代码
     // 1. 检查 iter 不为 None
     // 2. 创建循环块
     // 3. 调用 __next__()
     // 4. yield 结果
     // 5. 处理 StopIteration

     // TODO: 实现内联代码生成
     return nullptr;
   }
   ```

2. **`cinderx/Jit/hir/builder.h`** - 添加辅助函数声明

   ```cpp
   private:
     Register* tryInlineYieldFrom(
         TranslationContext& tc,
         Register* send_value,
         Register* iter);
   ```

### 推荐策略

**建议使用策略 A（在 simplify pass 中优化）：**

**优点：**
1. 更清晰的关注点分离
2. simplify pass 已经有完善的模式匹配基础设施
3. 可以参考 `simplifyIsTruthy` 的实现模式
4. 不影响 HIR 构建的性能
5. 可以在优化过程中多次应用

**缺点：**
1. 需要匹配 `YieldFrom` 指令并理解其上下文
2. 可能需要在 simplify pass 中创建新的基本块和控制流

**策略 B 的优点：**
1. 在构建时就生成优化的 HIR
2. 可以直接访问字节码上下文

**策略 B 的缺点：**
1. builder 代码已经很长（5000+ 行）
2. 增加了 builder 的复杂度
3. 错过了一些优化机会（例如，后续的类型推断可能改变优化决策）

## 5. 安全性检查需求

**必须检查：**

- [x] **类型检查（确保 self.left/right 是正确类型）**
  - 在 simplify pass 中，可以通过 `Register::type()` 获取类型信息
  - 如果类型已知且是 Tree/Node 类型，可以进行优化
  - 如果类型未知，需要生成运行时类型检查

- [x] **空值检查（确保 self.left/right 不为 None）**
  - 在 `yield from self.left` 之前，已经有 `if self.left is not None` 检查
  - 但在 HIR 中，这个检查可能被优化掉或分离到不同基本块
  - 需要确认 None 检查和 yield-from 在同一个控制流路径上

- [x] **迭代器协议检查**
  - 需要确保 `self.left` 实现了 `__iter__` 或 `__next__` 方法
  - 如果是 Tree/Node 类型，已知实现了 `__iter__`

- [x] **异常处理**
  - 需要正确处理 `StopIteration` 异常
  - 内联代码需要捕获 `StopIteration` 并正常返回

- [x] **生成器状态管理**
  - 需要正确处理生成器的 send/throw/close 操作
  - 内联代码需要维护生成器状态

- [x] **递归深度**
  - 内联 yield-from 会增加代码大小
  - 需要设置合理的内联深度限制

- [x] **Deopt 安全性**
  - 如果内联后类型信息改变，需要能够 deopt
  - 需要保存足够的 frame state 信息

**检查实现示例：**

```cpp
Register* simplifyYieldFrom(Env& env, const YieldFrom* instr) {
  if (!armInlineYieldFromEnabled() || !isTreeIterCode(env.func.code)) {
    return nullptr;
  }

  Register* send_value = instr->GetOperand(0);  // 第一个操作数
  Register* iter = instr->GetOperand(1);        // 第二个操作数

  // 1. 检查 iter 的来源
  if (iter == nullptr || !iter->instr()->IsLoadAttr()) {
    return nullptr;
  }

  auto* load_attr = static_cast<LoadAttr*>(iter->instr());
  const char* field_name = getAttrName(load_attr);
  if (field_name == nullptr) {
    return nullptr;
  }

  // 2. 验证属性名
  if (std::strcmp(field_name, "left") != 0 &&
      std::strcmp(field_name, "right") != 0) {
    return nullptr;
  }

  // 3. 检查是否有 None 检查保护
  // 查找前面的 IsTruthy 或 PrimitiveCompare 指令
  if (!isGuardedByNoneCheck(instr, load_attr)) {
    // 如果没有 None 检查保护，需要生成运行时检查
    // 这可能不值得优化，直接返回 nullptr
    return nullptr;
  }

  // 4. 类型检查
  Type iter_type = iter->type();
  if (!iter_type.isSubType(TObject)) {
    // 类型不兼容，不能优化
    return nullptr;
  }

  // 5. 生成内联代码
  // TODO: 实现内联代码生成

  return nullptr;
}

bool isGuardedByNoneCheck(const YieldFrom* yield_from, const LoadAttr* load_attr) {
  // 查找包含 yield_from 的基本块
  BasicBlock* block = yield_from->block();
  if (block == nullptr) {
    return false;
  }

  // 查找控制流前驱，检查是否有 None 检查
  // 这是一个简化的检查，实际实现需要数据流分析
  for (auto it = block->rbegin(); it != block->rend(); ++it) {
    if (it->IsCondBranch() || it->IsCondBranchCheckType()) {
      // 检查条件是否是比较 load_attr 的结果和 None
      Register* cond = it->GetOperand(0);
      if (cond != nullptr && cond->instr() == load_attr) {
        return true;
      }
    }
  }

  return false;
}
```

## 6. 后续步骤

1. **实现 simplifyYieldFrom 函数**
   - 从简单的模式检测开始
   - 逐步添加内联代码生成

2. **添加测试用例**
   - 在 `cinderx/PythonLib/test_cinderx/test_arm_runtime.py` 中添加测试
   - 覆盖各种边界情况

3. **性能验证**
   - 使用 bm_generators benchmark 验证性能提升
   - 对比优化前后的 HIR dump

4. **扩展到其他模式**
   - 支持更多的 yield-from 模式
   - 考虑更通用的内联策略
