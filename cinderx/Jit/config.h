// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>

namespace jit {

// Lifetime diagram of the JIT compiler:
//
//   NotInitialized <---------+
//        |                   |
//        v                   |
//     Running <---> Paused   |
//        |            |      |
//        v            |      |
//    Finalizing <-----+      |
//        |                   |
//        |                   |
//        +-------------------+
enum class State : uint8_t {
  kNotInitialized,
  kRunning,
  kPaused,
  kFinalizing,
};

enum class FrameMode : uint8_t {
  kNormal,
  kShadow,
  kLightweight,
};

// List of HIR optimization passes to run.
struct HIROptimizations {
  bool begin_inlined_function_elim{true};
  bool builtin_load_method_elim{true};
  bool clean_cfg{true};
  bool dead_code_elim{true};
  bool dynamic_comparison_elim{true};
  bool guard_type_removal{true};
  bool guarded_load_elim{true};
  // TASK(T156009029): Inliner should be on by default.
  bool inliner{false};
  bool insert_update_prev_instr{true};
  bool phi_elim{true};
  bool simplify{true};
};

// List of LIR optimization passes to run.
struct LIROptimizations {
  bool inliner{true};
};

struct SimplifierConfig {
  // The maximum number of times the simplifier can process a function's CFG.
  size_t iteration_limit{100};
  // The maximum number of new blocks that can be added by the simplifier to a
  // function.
  size_t new_block_limit{1000};
};

struct GdbOptions {
  // Whether GDB support is enabled.
  bool supported{false};
  // Whether to write generated ELF objects to disk.
  bool write_elf_objects{false};
};

struct JitListOptions {
  // Name of the file loaded in as a JIT list.
  std::string filename;
  // Raise a Python error when a line fails to parse.
  bool error_on_parse{false};
  // Use line numbers or not when checking if a function is on a JIT list.
  bool match_line_numbers{false};
};

struct LogOptions {
  // Log general debug messages from the JIT.
  bool debug{false};
  // Log debug messages in the inlining pass.
  bool debug_inliner{false};
  // Log debug messages in the refcount insertion pass.
  bool debug_refcount{false};
  // Log debug messages in the register allocation pass.
  bool debug_regalloc{false};

  // Log HIR, before any passes are run.
  bool dump_hir_initial{false};
  // Log HIR after every pass is run.
  bool dump_hir_passes{false};
  // Log HIR after all passes have been run.
  bool dump_hir_final{false};

  // Log LIR, across all stages.
  bool dump_lir{false};
  // Show the originating HIR instruction for LIR instruction blocks.
  bool lir_origin{true};

  // Log disassembly of compiled functions.
  bool dump_asm{false};
  // Symbolize functions in disassembled call instructions.
  bool symbolize_funcs{true};

  // Log general JIT stats.
  bool dump_stats{false};

  // The file where to write logs to.
  FILE* output_file{stderr};
};

enum class AsmSyntax : uint8_t {
  ATT,
  Intel,
};

// Collection of configuration values for the JIT.
//
// Note: It's fine to store non-trivially destructible objects like std::string
// in this.  It is *not fine* to store Python objects in this because it has
// process lifetime and outlives the Python runtime.
struct Config {
  // Current lifetime state of the JIT.
  State state{State::kNotInitialized};
  // Ignore other CLI arguments and environment variables, force the JIT
  // to be initialized or uninitialized.  Intended for testing.
  std::optional<bool> force_init;
  FrameMode frame_mode{
#ifdef ENABLE_LIGHTWEIGHT_FRAMES
      FrameMode::kLightweight
#else
      FrameMode::kNormal
#endif
  };
  bool allow_jit_list_wildcards{false};
  bool compile_all_static_functions{false};
  // Opt-in policy experiment: skip scheduling tiny functions with no loop
  // backedge for auto/JIT-list compilation. Explicit force_compile() is not
  // routed through the scheduler and remains unaffected.
  bool filter_tiny_no_backedge_functions{false};
  // Opt-in policy experiment: admit only shapes that have shown a positive
  // signal in the pyperformance matrix, while leaving call-heavy/object-heavy
  // functions interpreted until the optimized tier is more profitable.
  bool filter_unprofitable_shapes{false};
  // Opt-in policy experiment: skip generated comprehension/generator helper
  // code during auto/JIT-list scheduling. These helpers are often too cold or
  // short-lived to amortize optimized compile cost in pyperformance-style
  // single-value runs.
  bool filter_generated_functions{false};
  // Opt-in policy experiment: when filtering no-backedge helpers, still admit
  // small object-state methods that read/write container-like self state.
  bool admit_state_helpers{false};
  // Opt-in policy experiment: admit tiny object-state methods that also call
  // other helpers. These are often dispatcher/path-compression methods where
  // deferred interpretation keeps a hot object operation outside compiled code.
  bool admit_calling_state_helpers{false};
  // Opt-in policy experiment: keep filtered no-backedge helpers interpreted at
  // first, but leave a call-counting entrypoint so very hot helpers can promote
  // after they prove themselves at runtime.
  bool defer_filtered_no_backedge_helpers{false};
  // Opt-in extension for deferred helpers: include simple membership
  // predicates such as "value in self.values".
  bool defer_contains_state_helpers{false};
  bool multiple_code_sections{false};
  bool multithreaded_compile_test{false};
  bool use_huge_pages{true};
  // Assume that data found in the Python frame is unchanged across function
  // calls.  This includes the code object, and the globals and builtins
  // dictionaries (but not their contents).
  bool stable_frame{true};
  // Use inline caches for attribute accesses.
  bool attr_caches{
#ifdef Py_GIL_DISABLED
      // TODO(T250369692): FT support for inline-caches.
      false
#else
      true
#endif
  };
  // Collect stats information about attribute caches.
  bool collect_attr_cache_stats{false};
  // Split dynamic LoadMethodCached into a monomorphic type-check fast path and
  // a cache-fill slow path even when the receiver type is not statically known.
  bool dynamic_method_cache_split{false};
  // Use type annotations to create runtime checks.
  bool emit_type_annotation_guards{false};
  // Whether or not to JIT specialized opcodes or to fall back to their generic
  // counterparts.
  bool specialized_opcodes{true};
  // Whether specialized CONTAINS_OP_SET/DICT may lower directly to exact
  // set/dict helper calls instead of generic PySequence_Contains.
  bool specialized_contains_op{true};
  // Whether CALL_KW to exact PyFunction objects may use the exact Python
  // function vectorcall helper instead of the generic vectorcall entrypoint.
  bool specialized_kw_pyfunc_vectorcall{true};
  // Whether zero-argument method-with-values calls may delay generic lookup
  // until fallback when the caller has no uninitialized localsplus entries.
  bool zero_arg_mwv_delayed_lookup{true};
  // Whether exact dict subscripts should use a direct PyDict_GetItemRef helper
  // instead of dispatching through the mapping slot.
  bool exact_dict_subscr_helper{false};
  // Whether exact method descriptors with METH_FASTCALL shapes beyond the
  // legacy one-explicit-argument case may use a direct helper.
  bool method_descr_fast_vectorcall{false};
  // Whether list iterator hot iterations may lower directly in LIR while
  // preserving the generic InvokeIterNext helper for fallback/exhaustion.
  bool inline_list_iter_next{false};
  // Whether exact list.pop() with the default index may call a direct helper
  // instead of going through method-descriptor vectorcall.
  bool list_pop_last_helper{true};
  // Whether safe LOAD_METHOD/CALL pairs may fuse method-cache lookup and the
  // method-shaped call into a single runtime helper.
  bool cached_method_call_helper{false};
  // Whether STORE_ATTR_INSTANCE_VALUE may lower to direct StoreField when the
  // inline value slot already contains an object.
  bool store_attr_instance_value_existing{false};
  // Support instrumentation (monitoring/tracing/profiling) by falling back to
  // the interpreter
  bool support_instrumentation{false};

  // Add RefineType instructions for Static Python values before they get
  // typechecked.  Enabled by default as HIR doesn't pass through Static Python
  // types very well right now.  Disable to expose new typing opportunities in
  // HIR.
  //
  // TASK(T195042385): Replace this with actual typing.
  bool refine_static_python{true};
  HIROptimizations hir_opts;
  LIROptimizations lir_opts;
  SimplifierConfig simplifier;
  // Limit on how much the inliner can inline.  The number here is internal to
  // the inliner, doesn't have any specific meaning, and can change as the
  // inliner's algorithm changes.
  size_t inliner_cost_limit{2000};
  // Enable only the profiled method-value subset of the HIR inliner. This keeps
  // global/function inlining disabled while allowing warmed object method calls
  // to use the narrow inliner path.
  bool method_value_inliner{false};
  // Number of workers to use for batch compilation, like in precompile_all().
  // If this number isn't configured then batch compilation will happen inline
  // on the calling thread.
  size_t batch_compile_workers{0};
  // When a function is being compiled, this is the maximum number of dependent
  // functions called by it that can be compiled along with it.
  size_t preload_dependent_limit{99};
  size_t tiny_no_backedge_instruction_limit{8};
  size_t deferred_no_backedge_helper_threshold{32};
  // Sizes (in bytes) of the hot and cold code sections. Only applicable if
  // multiple code sections are enabled.
  size_t cold_code_section_size{0};
  size_t hot_code_section_size{0};
  // Memory threshold after which we stop jitting.
  size_t max_code_size{0};
  // Size (in number of entries) of the LoadAttrCached and StoreAttrCached
  // inline caches used by the JIT.
  uint32_t attr_cache_size{4};
  std::optional<uint32_t> baseline_compile_after_n_calls;
  std::optional<uint32_t> compile_after_n_calls;
  GdbOptions gdb;
  JitListOptions jit_list;
  LogOptions log;
  bool compile_perf_trampoline_prefork{false};
  bool dump_hir_stats{false};

  // The ASM syntax the JIT should use when disassembling.
  AsmSyntax asm_syntax{AsmSyntax::ATT};
};

// Get the JIT's current config object.
const Config& getConfig();

// Get the JIT's current config object with the intent of modifying it.
Config& getMutableConfig();

// Check that the JIT is initialized.  Though it might be paused and or
// finalizing, it's not necessarily usable.
bool isJitInitialized();

// Check that the JIT is initialized and is currently usable.
bool isJitUsable();

// Check that the JIT is initialized but currently paused and unusable.
bool isJitPaused();

} // namespace jit
