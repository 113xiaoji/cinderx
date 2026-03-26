// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

#include "cinderx/Jit/hir/pass.h"
#include "cinderx/Jit/hir/hir.h"

#include <vector>

namespace jit::hir {

// TreeIterStateMachinePass: 检测树遍历模式并生成状态机
//
// 这个 pass 在 simplifyYieldFrom 之后运行，用于将树遍历生成器
// 转换为显式状态机，消除生成器帧切换开销。
//
// 输入: 包含 YieldFrom 指令的 HIR（已被 simplifyYieldFrom 简化）
// 输出: 包含状态机基本块集合的 HIR
//
// 状态机结构:
//   entry -> init (设置 state = 0) -> dispatch
//   dispatch -> state[0] / state[1] / ... / done
//   state[i] -> (yield value) -> dispatch / done
//   done -> return None
class TreeIterStateMachinePass : public Pass {
 public:
  TreeIterStateMachinePass() : Pass("TreeIterStateMachinePass") {}

  void Run(Function& func) override;

 private:
  // 检测函数是否是树遍历生成器
  bool isTreeIterGenerator(const Function& func) const;

  // 收集函数中的所有 YieldFrom 指令
  void collectYieldFromInstrs(const Function& func, std::vector<const YieldFrom*>& out) const;

  // 检测 YieldFrom 指令是否是树遍历模式
  bool isTreeIterPattern(const YieldFrom* yf) const;

  // 生成状态机
  void generateStateMachine(Function& func, const std::vector<const YieldFrom*>& yield_froms);
};

// Phase 枚举：表示状态机的当前阶段
enum class TreeIterPhase : int {
  kLeft = 0,      // 进入左子树
  kYield = 1,     // 产生当前值
  kRight = 2,     // 进入右子树
  kBacktrack = 3  // 回溯到父节点
};

// 状态机配置常量
struct StateMachineConfig {
  static constexpr int kMaxInlineDepth = 12;       // 最大内联深度
  static constexpr int kStateSize = 256;           // 状态栈大小（字节）
  static constexpr int kNodeOffset = 0;            // 当前节点偏移
  static constexpr int kPhaseOffset = 8;           // 当前阶段偏移
  static constexpr int kStackBase = 16;            // 栈帧开始偏移
  static constexpr int kStackEntrySize = 16;      // 每个栈条目大小
  static constexpr int kUninitializedState = -1;  // 未初始化状态值
};

// 状态机生成器上下文
struct StateMachineContext {
  Function* func;
  Register* self_reg{nullptr};
  Register* current_node_reg{nullptr};
  Register* phase_reg{nullptr};
  Register* stack_top_reg{nullptr};

  int max_depth{0};
  int stack_size{0};

  BasicBlock* bb_init{nullptr};
  BasicBlock* bb_loop{nullptr};
  BasicBlock* bb_left{nullptr};
  BasicBlock* bb_yield{nullptr};
  BasicBlock* bb_right{nullptr};
  BasicBlock* bb_backtrack{nullptr};
  BasicBlock* bb_done{nullptr};
};

// 状态机生成器类
class StateMachineGenerator {
 public:
  explicit StateMachineGenerator(StateMachineContext& ctx) : ctx_(ctx) {}

  // 生成完整状态机
  void Generate();

  // 生成各个阶段的基本块
  BasicBlock* GenerateInitBlock();
  BasicBlock* GenerateLoopBlock();
  BasicBlock* GenerateLeftBlock();
  BasicBlock* GenerateYieldBlock();
  BasicBlock* GenerateRightBlock();
  BasicBlock* GenerateBacktrackBlock();

 private:
  StateMachineContext& ctx_;

  // 辅助方法
  void GenerateStackPush(Register* node, TreeIterPhase phase);
  std::pair<Register*, Register*> GenerateStackPop();

  Register* CreatePhaseConst(BasicBlock* bb, TreeIterPhase phase);
  Register* CreateIntConst(BasicBlock* bb, int value);

  // 成员变量（用于跟踪生成的基本块）
  BasicBlock* bb_init_{nullptr};
  BasicBlock* bb_loop_{nullptr};
  BasicBlock* bb_left_{nullptr};
  BasicBlock* bb_yield_{nullptr};
  BasicBlock* bb_right_{nullptr};
  BasicBlock* bb_backtrack_{nullptr};
  BasicBlock* bb_done_{nullptr};
};

}  // namespace jit::hir

// 探针计数器：验证状态机 pass 是否被触发
// 当 TreeIterStateMachinePass 检测到树遍历模式并生成状态机时递增
extern "C" int g_state_machine_pass_triggered;
