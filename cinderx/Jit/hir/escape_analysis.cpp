// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/hir/escape_analysis.h"

#include "cinderx/Jit/hir/cfg.h"
#include "cinderx/Jit/hir/function.h"
#include "cinderx/Common/log.h"

namespace jit::hir {

void EscapeAnalysisPass::Run(Function& func) {
  JIT_LOG("EscapeAnalysisPass: Running on function {}", func.fullname);
  func_ = &func;
  
  // 逃逸分析是一个分析 pass，不修改 HIR
  // 主要用于收集信息，供后续优化 pass 使用
}

EscapeAnalysisResult EscapeAnalysisPass::analyzeGenerator(
    const Register* gen_reg) {
  if (gen_reg == nullptr) {
    return {EscapeLevel::kUnknown, "null register"};
  }

  // 检查各种逃逸情况
  
  // 1. 检查是否被返回
  if (isReturned(gen_reg)) {
    return {EscapeLevel::kEscapes, "returned to caller"};
  }

  // 2. 检查是否被存储到外部
  if (isStoredExternally(gen_reg)) {
    return {EscapeLevel::kEscapes, "stored externally"};
  }

  // 3. 检查是否被传递给未知函数
  if (isPassedToUnknownFunction(gen_reg)) {
    return {EscapeLevel::kEscapes, "passed to unknown function"};
  }

  // 4. 检查是否被直接消费
  if (isDirectlyConsumed(gen_reg)) {
    return {EscapeLevel::kNoEscape, "directly consumed"};
  }

  // 保守处理：未知情况回退到标准路径
  return {EscapeLevel::kUnknown, "unknown usage pattern"};
}

bool EscapeAnalysisPass::isReturned(const Register* gen_reg) {
  if (func_ == nullptr) {
    return false;
  }

  // 遍历所有基本块，查找 Return 指令
  for (const auto& block : func_->cfg.blocks) {
    for (const auto& instr : block) {
      if (instr.opcode() == Opcode::kReturn) {
        // 检查返回值是否是 gen_reg
        const Return* ret_instr = static_cast<const Return*>(&instr);
        if (ret_instr && ret_instr->GetOperand(0) == gen_reg) {
          JIT_LOG("  -> Generator is returned");
          return true;
        }
      }
    }
  }

  return false;
}

bool EscapeAnalysisPass::isStoredExternally(const Register* gen_reg) {
  if (func_ == nullptr) {
    return false;
  }

  // 遍历所有基本块，查找存储操作
  for (const auto& block : func_->cfg.blocks) {
    for (const auto& instr : block) {
      // 检查是否存储到实例字段
      if (instr.opcode() == Opcode::kStoreField) {
        const StoreField* store = static_cast<const StoreField*>(&instr);
        if (store && store->GetOperand(1) == gen_reg) {
          JIT_LOG("  -> Generator is stored to field");
          return true;
        }
      }
    }
  }

  return false;
}

bool EscapeAnalysisPass::isPassedToUnknownFunction(const Register* gen_reg) {
  if (func_ == nullptr) {
    return false;
  }

  // 遍历所有基本块，查找函数调用
  for (const auto& block : func_->cfg.blocks) {
    for (const auto& instr : block) {
      if (instr.opcode() == Opcode::kCall) {
        // 检查参数中是否包含 gen_reg
        const Call* call = static_cast<const Call*>(&instr);
        if (call) {
          for (size_t i = 0; i < call->NumOperands(); i++) {
            if (call->GetOperand(i) == gen_reg) {
              JIT_LOG("  -> Generator is passed to function");
              return true;
            }
          }
        }
      }
    }
  }

  return false;
}

bool EscapeAnalysisPass::isDirectlyConsumed(const Register* gen_reg) {
  if (func_ == nullptr) {
    return false;
  }

  // 检查是否被 list/set/tuple 等内置函数直接消费
  // 这些函数会立即消费生成器，不会逃逸

  for (const auto& block : func_->cfg.blocks) {
    for (const auto& instr : block) {
      if (instr.opcode() == Opcode::kCall) {
        const Call* call = static_cast<const Call*>(&instr);
        if (!call || call->NumOperands() < 2) {
          continue;
        }

        Register* func_reg = call->GetOperand(0);
        if (!func_reg || !func_reg->instr()) {
          continue;
        }

        Instr* func_instr = func_reg->instr();
        
        // 检查是否是 LoadGlobal 或 LoadBuiltin 指令
        if (func_instr->opcode() == Opcode::kLoadGlobal) {
          const LoadGlobal* load_global = static_cast<const LoadGlobal*>(func_instr);
          if (load_global) {
            const std::string& name = load_global->name();
            // 检查是否是 list, set, tuple
            if (name == "list" || name == "set" || name == "tuple") {
              // 检查第一个参数是否是 gen_reg
              if (call->NumOperands() >= 2 && call->GetOperand(1) == gen_reg) {
                JIT_LOG("  -> Generator is directly consumed by {}", name);
                return true;
              }
            }
          }
        }
      }
    }
  }

  return false;
}

} // namespace jit::hir
