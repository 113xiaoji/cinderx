// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

#include "cinderx/Jit/hir/pass.h"
#include "cinderx/Jit/hir/hir.h"

#include <optional>
#include <string>
#include <vector>

namespace jit::hir {

// 树遍历字段信息
struct TreeIterFieldInfo {
  std::string name;
  std::size_t offset{0};
  int name_idx{-1};
};

// TreeIterStateMachinePass: 检测树遍历模式并生成状态机
class TreeIterStateMachinePass : public Pass {
 public:
  TreeIterStateMachinePass() : Pass("TreeIterStateMachinePass") {}

  void Run(Function& func) override;

 private:
  bool isTreeIterGenerator(const Function& func) const;
  void collectYieldFromInstrs(const Function& func, std::vector<const YieldFrom*>& out) const;
  bool isTreeIterPattern(const YieldFrom* yf) const;
  const GetIter* findGetIter(Register* iter_reg) const;
  std::optional<TreeIterFieldInfo> extractValueField(const Function& func) const;
  void generateStateMachine(Function& func, const std::vector<const YieldFrom*>& yield_froms);
};

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

  // 原始入口块（包含 InitialYield 和 self_reg 定义）
  BasicBlock* init_block{nullptr};

  // 从原始 HIR 的 YieldValue 指令获取的 FrameState
  // 用于为状态机的 YieldValue 提供正确的帧信息
  FrameState* yield_frame_state{nullptr};

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

  // 生成完整状态机（含字段偏移量）
  void Generate(
      std::size_t left_offset,
      std::size_t right_offset,
      std::size_t value_offset);

  // 返回入口基本块（用于 CFG 集成）
  BasicBlock* bb_init() const { return bb_init_; }
  BasicBlock* bb_loop() const { return bb_loop_; }

  // 生成各个阶段的基本块（保留用于兼容性）
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

  // 生成的关键块指针
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
