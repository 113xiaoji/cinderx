// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/context.h"

#include "internal/pycore_interp.h"
#include "internal/pycore_pystate.h"

#include "cinderx/Common/log.h"
#include "cinderx/Common/py-portability.h"
#include "cinderx/Jit/elf/reader.h"
#include "cinderx/StaticPython/classloader.h"
#include "cinderx/module_state.h"
#include "cinderx/python_runtime.h"

#ifndef WIN32
#include <dlfcn.h>
#include <sys/mman.h>
#endif

#include <algorithm>
#include <cstring>

namespace jit {

AotContext g_aot_ctx;

constexpr std::size_t kDefaultDeoptBudget = 16;
constexpr std::size_t kCompileFailureBackoffThreshold = 1;
constexpr std::size_t kInitialCompileFailureBackoff = 2;
constexpr std::size_t kMaxCompileFailureBackoff = 8;
constexpr std::size_t kNoOsrEpoch = std::numeric_limits<std::size_t>::max();

const char* functionTierName(FunctionTier tier) {
  switch (tier) {
    case FunctionTier::kInterp:
      return "interp";
    case FunctionTier::kBaseline:
      return "baseline";
    case FunctionTier::kOptimized:
      return "optimized";
  }
  JIT_ABORT("Unknown function tier {}", static_cast<int>(tier));
}

const char* tierPolicyStateName(TierPolicyState state) {
  switch (state) {
    case TierPolicyState::kReady:
      return "ready";
    case TierPolicyState::kCompileFailureCooldown:
      return "compile_failure_cooldown";
    case TierPolicyState::kCompileFailureUnsupported:
      return "compile_failure_unsupported";
    case TierPolicyState::kDeoptBudgetExhausted:
      return "deopt_budget_exhausted";
  }
  JIT_ABORT("Unknown tier policy state {}", static_cast<int>(state));
}

namespace {

std::size_t compileFailureBackoffForStreak(std::size_t streak) {
  if (streak == 0) {
    return 0;
  }
  std::size_t backoff = kInitialCompileFailureBackoff;
  for (std::size_t i = 1; i < streak; i++) {
    backoff = std::min(backoff * 2, kMaxCompileFailureBackoff);
  }
  return backoff;
}

bool isUnsupportedCompileFailure(const char* reason) {
  return std::strcmp(reason, "cannot_specialize") == 0;
}

void clearPromotionBlock(FunctionTierState& state) {
  state.promotion_blocked = false;
  state.promotion_blocked_reason = "none";
  state.policy_state = TierPolicyState::kReady;
}

void blockPromotion(
    FunctionTierState& state,
    TierPolicyState policy_state,
    const char* reason,
    const char* event) {
  state.promotion_blocked = true;
  state.promotion_blocked_reason = reason;
  state.policy_state = policy_state;
  state.last_policy_event = event;
  state.last_policy_reason = reason;
}

bool hasCompileFailurePolicy(const FunctionTierState& state) {
  return state.compile_failure_streak != 0 ||
      state.compile_failure_backoff != 0 ||
      state.compile_failure_cooldown_remaining != 0 ||
      state.policy_state == TierPolicyState::kCompileFailureCooldown ||
      state.policy_state == TierPolicyState::kCompileFailureUnsupported ||
      state.promotion_blocked_reason == "compile_failure_cooldown";
}

bool hasDeoptBudgetPolicy(const FunctionTierState& state) {
  return state.deopt_budget != kDefaultDeoptBudget ||
      state.policy_state == TierPolicyState::kDeoptBudgetExhausted ||
      state.promotion_blocked_reason == "deopt_budget_exhausted";
}

void resetCompileFailurePolicy(FunctionTierState& state) {
  bool had_policy = hasCompileFailurePolicy(state);
  state.compile_failure_streak = 0;
  state.compile_failure_backoff = 0;
  state.compile_failure_cooldown_remaining = 0;
  state.compile_failure_last_osr_cooldown_epoch = kNoOsrEpoch;
  state.compile_failure_osr_resume_deferred = false;
  if (had_policy) {
    state.policy_resets++;
  }
  clearPromotionBlock(state);
}

void clearPendingFallback(FunctionTierState& state) {
  state.fallback_pending = false;
  state.fallback_pending_reason = "none";
}

bool shouldConsumeCompileFailureCooldown(
    FunctionTierState& state,
    const char* reason,
    std::size_t osr_epoch) {
  // Hot-loop OSR can re-check policy many times during one interpreted
  // activation. Age cooldown at most once per activation epoch so one hot loop
  // cannot burn through the backoff, while later interpreted calls can recover.
  if (std::strcmp(reason, "hot_loop_osr") != 0) {
    return true;
  }
  if (osr_epoch == kNoOsrEpoch ||
      state.compile_failure_last_osr_cooldown_epoch == osr_epoch) {
    return false;
  }
  state.compile_failure_last_osr_cooldown_epoch = osr_epoch;
  return true;
}

bool shouldDeferReadyHotLoopOsr(
    FunctionTierState& state,
    const char* reason,
    std::size_t osr_epoch) {
  if (!state.compile_failure_osr_resume_deferred) {
    return false;
  }
  if (std::strcmp(reason, "hot_loop_osr") != 0) {
    state.compile_failure_osr_resume_deferred = false;
    return false;
  }
  if (osr_epoch != kNoOsrEpoch) {
    state.compile_failure_osr_resume_deferred = false;
    return false;
  }
  return true;
}

} // namespace

PyObject* yieldFromValue(
    GenDataFooter* gen_footer,
    const GenYieldPoint* yield_point) {
  return yield_point->isYieldFrom()
      ? reinterpret_cast<PyObject*>(
            *(reinterpret_cast<uint64_t*>(gen_footer) +
              yield_point->yieldFromOffset()))
      : nullptr;
}

void Builtins::init() {
  ThreadedCompileSerialize guard;
  if (is_initialized_) {
    return;
  }
  // we want to check the exact function address, rather than relying on
  // modules which can be mutated.  First find builtins, which we have
  // to do a search for because PyEval_GetBuiltins() returns the
  // module dict.
  PyObject* mods =
      CI_INTERP_IMPORT_FIELD(_PyInterpreterState_GET(), modules_by_index);
  PyModuleDef* builtins = nullptr;
  for (Py_ssize_t i = 0; i < PyList_GET_SIZE(mods); i++) {
    PyObject* cur = PyList_GET_ITEM(mods, i);
    if (cur == Py_None) {
      continue;
    }
    PyModuleDef* def = PyModule_GetDef(cur);
    if (def == nullptr) {
      PyErr_Clear();
      continue;
    }
    if (std::strcmp(def->m_name, "builtins") == 0) {
      builtins = def;
      break;
    }
  }
  JIT_CHECK(builtins != nullptr, "could not find builtins module");

  auto add = [this](const std::string& name, PyMethodDef* meth) {
    cfunc_to_name_[meth] = name;
    name_to_cfunc_[name] = meth;
  };
  // Find all free functions.
  for (PyMethodDef* fdef = builtins->m_methods; fdef->ml_name != nullptr;
       fdef++) {
    add(fdef->ml_name, fdef);
  }
  // Find all methods on types.
  PyTypeObject* types[] = {
      &PyDict_Type,
      &PyList_Type,
      &PySet_Type,
      &PyTuple_Type,
      &PyUnicode_Type,
  };
  for (auto type : types) {
    for (PyMethodDef* fdef = type->tp_methods; fdef->ml_name != nullptr;
         fdef++) {
      add(fmt::format("{}.{}", type->tp_name, fdef->ml_name), fdef);
    }
  }
  // Only mark as initialized after everything is done to avoid concurrent
  // reads of an unfinished map.
  is_initialized_ = true;
}

bool Builtins::isInitialized() const {
  return is_initialized_;
}

std::optional<std::string> Builtins::find(PyMethodDef* meth) const {
  auto result = cfunc_to_name_.find(meth);
  if (result == cfunc_to_name_.end()) {
    return std::nullopt;
  }
  return result->second;
}

std::optional<PyMethodDef*> Builtins::find(const std::string& name) const {
  auto result = name_to_cfunc_.find(name);
  if (result == name_to_cfunc_.end()) {
    return std::nullopt;
  }
  return result->second;
}

Context::Context()
    : zero_(Ref<>::steal(PyLong_FromLong(0))),
#if PY_VERSION_HEX >= 0x030C0000
      str_build_class_(Ref<>::create(&_Py_ID(__build_class__)))
#else
      str_build_class_(
          Ref<>::steal(PyUnicode_InternFromString("__build_class__")))
#endif
{
#if PY_VERSION_HEX >= 0x030E0000
  PyObject** common_consts = PyThreadState_GET()->interp->common_consts;
  for (int i = 0; i < NUM_COMMON_CONSTANTS; i++) {
    common_constant_types_.emplace_back(
        hir::Type::fromObject(common_consts[i]));
  }
#endif
}

void Context::mlockProfilerDependencies() {
#ifndef WIN32
  for (auto& codert : code_runtimes_) {
    PyCodeObject* code = codert.frameState()->code().get();
    ::mlock(code, sizeof(PyCodeObject));
    ::mlock(code->co_qualname, Py_SIZE(code->co_qualname));
  }
  code_runtimes_.mlock();
#endif
}

Ref<> Context::pageInProfilerDependencies() {
  ThreadedCompileSerialize guard;
  Ref<> qualnames = Ref<>::steal(PyList_New(0));
  if (qualnames == nullptr) {
    return nullptr;
  }
  // We want to force the OS to page in the memory on the
  // code_rt->code->qualname path and keep the compiler from optimizing away
  // the code to do so. There are probably more efficient ways of doing this
  // but perf isn't a major concern.
  for (auto& code_rt : code_runtimes_) {
    BorrowedRef<> qualname = code_rt.frameState()->code()->co_qualname;
    if (qualname == nullptr) {
      continue;
    }
    if (PyList_Append(qualnames, qualname) < 0) {
      return nullptr;
    }
  }
  return qualnames;
}

void** Context::findFunctionEntryCache(PyFunctionObject* function) {
  auto result = function_entry_caches_.emplace(
      std::piecewise_construct,
      std::forward_as_tuple(function),
      std::forward_as_tuple());
  if (result.second) {
    result.first->second.ptr = pointer_caches_.allocate();
    // _PyClassLoader_HasPrimitiveArgs doesn't work well in multi-threaded
    // compile in 3.12+ due to access of a dictionary with non-key strings.
    // We fix this up post-compile in the multi-threaded case.
    if (!getThreadedCompileContext().compileRunning() &&
        _PyClassLoader_HasPrimitiveArgs((PyCodeObject*)function->func_code)) {
      result.first->second.arg_info =
          Ref<_PyTypedArgsInfo>::steal(_PyClassLoader_GetTypedArgsInfo(
              (PyCodeObject*)function->func_code, 1));
    }
  }
  return result.first->second.ptr;
}

void Context::clearFunctionEntryCache(BorrowedRef<PyFunctionObject> function) {
  function_entry_caches_.erase(function);
}

// See comments in findFunctionEntryCache.
void Context::fixupFunctionEntryCachePostMultiThreadedCompile() {
  for (auto& entry : function_entry_caches_) {
    BorrowedRef<PyCodeObject> code{entry.first->func_code};
    if (entry.second.arg_info.get() == nullptr &&
        _PyClassLoader_HasPrimitiveArgs(code)) {
      entry.second.arg_info = Ref<_PyTypedArgsInfo>::steal(
          _PyClassLoader_GetTypedArgsInfo(code, 1));
    }
  }
}

bool Context::hasFunctionEntryCache(PyFunctionObject* function) const {
  return function_entry_caches_.find(function) != function_entry_caches_.end();
}

_PyTypedArgsInfo* Context::findFunctionPrimitiveArgInfo(
    PyFunctionObject* function) {
  auto cache = function_entry_caches_.find(function);
  if (cache == function_entry_caches_.end()) {
    return nullptr;
  }
  return cache->second.arg_info.get();
}

void Context::recordDeopt(
    CodeRuntime* code_runtime,
    std::size_t idx,
    BorrowedRef<> guilty_value) {
#ifdef Py_GIL_DISABLED
  std::lock_guard<std::mutex> lock(deopt_stats_mutex_);
#endif
  DeoptStat& stat = deopt_stats_[code_runtime][idx];
  stat.count++;
  if (guilty_value != nullptr) {
    stat.types.recordType(Py_TYPE(guilty_value));
  }
}

const DeoptStat* Context::deoptStat(
    const CodeRuntime* code_runtime,
    std::size_t deopt_idx) const {
  auto map_it = deopt_stats_.find(code_runtime);
  if (map_it == deopt_stats_.end()) {
    return nullptr;
  }
  auto stat_it = map_it->second.find(deopt_idx);
  if (stat_it == map_it->second.end()) {
    return nullptr;
  }
  return &stat_it->second;
}

void Context::clearDeoptStats() {
#ifdef Py_GIL_DISABLED
  std::lock_guard<std::mutex> lock(deopt_stats_mutex_);
#endif
  deopt_stats_.clear();
}

void Context::recordOSR(CodeRuntime* code_runtime, BCOffset bc_offset) {
#ifdef Py_GIL_DISABLED
  std::lock_guard<std::mutex> lock(osr_stats_mutex_);
#endif
  OSRStat& stat = osr_stats_[code_runtime][bc_offset];
  stat.count++;
}

const OSRStat* Context::osrStat(
    const CodeRuntime* code_runtime,
    BCOffset bc_offset) const {
  auto map_it = osr_stats_.find(code_runtime);
  if (map_it == osr_stats_.end()) {
    return nullptr;
  }
  auto stat_it = map_it->second.find(bc_offset);
  if (stat_it == map_it->second.end()) {
    return nullptr;
  }
  return &stat_it->second;
}

void Context::clearOSRStats() {
#ifdef Py_GIL_DISABLED
  std::lock_guard<std::mutex> lock(osr_stats_mutex_);
#endif
  osr_stats_.clear();
}

InlineCacheStats Context::getAndClearLoadMethodCacheStats() {
  InlineCacheStats stats;
  for (auto& cache : load_method_caches_) {
    if (cache.cacheStats() == nullptr) {
      // Cache stat may not have been initialized if LoadMethodCached instr was
      // optimized away.
      continue;
    }
    stats.push_back(*cache.cacheStats());
    cache.clearCacheStats();
  }
  return stats;
}

InlineCacheStats Context::getAndClearLoadTypeMethodCacheStats() {
  InlineCacheStats stats;
  for (auto& cache : load_type_method_caches_) {
    if (cache.cacheStats() == nullptr) {
      // Cache stat may not have been initialized if LoadTypeMethod instr
      // was optimized away.
      continue;
    }
    stats.push_back(*cache.cacheStats());
    cache.clearCacheStats();
  }
  return stats;
}

void Context::setGuardFailureCallback(Context::GuardFailureCallback cb) {
  guard_failure_callback_ = cb;
}

void Context::guardFailed(const DeoptMetadata& deopt_meta) {
  if (guard_failure_callback_) {
    guard_failure_callback_(deopt_meta);
  }
}

void Context::clearGuardFailureCallback() {
  guard_failure_callback_ = nullptr;
}

void Context::addReference(BorrowedRef<> obj) {
  // Serialize as we modify the ref-count to obj which may be widely accessible.
  ThreadedCompileSerialize guard;
  references_.emplace(ThreadedRef<>::create(obj));
}

void Context::releaseReferences() {
  for (auto& code_rt : code_runtimes_) {
    code_rt.releaseReferences();
  }
  references_.clear();
  type_deopt_patchers_.clear();
  type_deopt_patcher_runtimes_.clear();
  code_runtime_funcs_.clear();
}

LoadAttrCache* Context::allocateLoadAttrCache() {
  return load_attr_caches_.allocate();
}

LoadTypeAttrCache* Context::allocateLoadTypeAttrCache() {
  return load_type_attr_caches_.allocate();
}

LoadMethodCache* Context::allocateLoadMethodCache() {
  return load_method_caches_.allocate();
}

LoadModuleAttrCache* Context::allocateLoadModuleAttrCache() {
  return load_module_attr_caches_.allocate();
}

LoadModuleMethodCache* Context::allocateLoadModuleMethodCache() {
  return load_module_method_caches_.allocate();
}

LoadTypeMethodCache* Context::allocateLoadTypeMethodCache() {
  return load_type_method_caches_.allocate();
}

StoreAttrCache* Context::allocateStoreAttrCache() {
  return store_attr_caches_.allocate();
}

const Builtins& Context::builtins() {
  // Lock-free fast path followed by single-lock slow path during
  // initialization.
  if (!builtins_.isInitialized()) {
    builtins_.init();
  }
  return builtins_;
}

void Context::watchType(
    BorrowedRef<PyTypeObject> type,
    TypeDeoptPatcher* patcher,
    CodeRuntime* code_runtime) {
  ThreadedCompileSerialize guard;
  type_deopt_patchers_[type].emplace_back(patcher);
  if (code_runtime != nullptr) {
    type_deopt_patcher_runtimes_[patcher] = code_runtime;
  }
  if constexpr (PY_VERSION_HEX >= 0x030C0000) {
    // In 3.12 we require the interpreter state in order to watch types
    if (getThreadedCompileContext().compileRunning()) {
      pending_watches_.emplace(type);
      return;
    }
  }

  JIT_CHECK(
      cinderx::getModuleState()->watcher_state.watchType(type) == 0,
      "Failed to watch type {}",
      type->tp_name);
}

BorrowedRef<> Context::zero() {
  return zero_.get();
}

BorrowedRef<> Context::strBuildClass() {
  return str_build_class_.get();
}

void Context::watchPendingTypes() {
  for (auto& type : pending_watches_) {
    JIT_CHECK(
        cinderx::getModuleState()->watcher_state.watchType(type) == 0,
        "Failed to watch pending type {}",
        type->tp_name);
  }
  pending_watches_.clear();
}

void Context::notifyTypeModified(
    BorrowedRef<PyTypeObject> lookup_type,
    BorrowedRef<PyTypeObject> new_type) {
  notifyICsTypeChanged(lookup_type);

  ThreadedCompileSerialize guard;
  auto it = type_deopt_patchers_.find(lookup_type);
  if (it == type_deopt_patchers_.end()) {
    return;
  }

  std::vector<TypeDeoptPatcher*> remaining_patchers;
  for (TypeDeoptPatcher* patcher : it->second) {
    bool was_patched = patcher->isPatched();
    if (!patcher->maybePatch(new_type)) {
      remaining_patchers.emplace_back(patcher);
      continue;
    }

    auto runtime_it = type_deopt_patcher_runtimes_.find(patcher);
    if (!was_patched && patcher->isPatched() &&
        runtime_it != type_deopt_patcher_runtimes_.end()) {
      recordTypeInvalidation(runtime_it->second, "type_modified");
    }
    type_deopt_patcher_runtimes_.erase(patcher);
  }

  if (remaining_patchers.empty()) {
    type_deopt_patchers_.erase(it);
    // don't unwatch type; shadowcode may still be watching it
  } else {
    it->second = std::move(remaining_patchers);
  }
}

bool Context::hasCompletedCompile(CompilationKey& key) {
  return completed_compiles_.contains(key);
}

void Context::finalizeMultiThreadedCompile() {
  fixupFunctionEntryCachePostMultiThreadedCompile();
  watchPendingTypes();

  for (auto& codes : completed_compiles_) {
    makeCompiledFunction(
        codes.second.second, codes.first, std::move(codes.second.first));
  }
  completed_compiles_.clear();
}

void Context::finalizeFunc(
    BorrowedRef<PyFunctionObject> func,
    const CompiledFunction& compiled) {
  ThreadedCompileSerialize guard;
  bool was_baseline = baseline_funcs_.contains(func);
  if (!addCompiledFunc(func)) {
    // Someone else compiled the function between when our caller checked and
    // called us.
    return;
  }

  // In case the function had previously been deopted.
  removeDeoptedFunc(func);
  FunctionTierState& state = tierStateFor(func);
  state.active_tier = FunctionTier::kOptimized;
  state.compiled = true;
  state.deopted = false;
  state.baseline_scheduled = false;
  state.deopt_budget = kDefaultDeoptBudget;
  resetCompileFailurePolicy(state);
  state.last_transition = was_baseline ? "baseline_to_optimized" : "optimized";
  code_runtime_funcs_[compiled.runtime()].emplace(func);
  baseline_funcs_.erase(func);
  baseline_scheduled_funcs_.erase(func);

  setVectorcall(func, compiled.vectorcallEntry());
  if (hasFunctionEntryCache(func)) {
    void** indirect = findFunctionEntryCache(func);
    *indirect = compiled.staticEntry();
  }
}

void Context::codeCompiled(
    BorrowedRef<PyFunctionObject> func,
    CompilationKey& key,
    CompiledFunctionData&& compiled_func) {
  addCompileTime(compiled_func.compile_time);

  if (getThreadedCompileContext().compileRunning()) {
    completed_compiles_.emplace(
        key,
        std::pair(
            std::move(compiled_func),
            ThreadedRef<PyFunctionObject>::create(func)));
    return;
  }

  makeCompiledFunction(func, key, std::move(compiled_func));
}

const hir::Type& Context::typeForCommonConstant([[maybe_unused]] int i) const {
#if PY_VERSION_HEX >= 0x030E0000
  return common_constant_types_.at(i);
#endif
  JIT_ABORT("Common constants are a feature of 3.14+");
}

#if PY_VERSION_HEX < 0x030C0000
// JIT generator data free-list globals
const size_t kGenDataFreeListMaxSize = 1024;
static size_t gen_data_free_list_size = 0;
static void* gen_data_free_list_tail;

jit::GenDataFooter* jitgen_data_allocate(size_t spill_words) {
  spill_words = std::max(spill_words, jit::kMinGenSpillWords);
  if (spill_words > jit::kMinGenSpillWords || !gen_data_free_list_size) {
    auto data =
        malloc(spill_words * sizeof(uint64_t) + sizeof(jit::GenDataFooter));
    auto footer = reinterpret_cast<jit::GenDataFooter*>(
        reinterpret_cast<uint64_t*>(data) + spill_words);
    footer->spillWords = spill_words;
    return footer;
  }

  // All free list entries are spill-word size 89, so we don't need to set
  // footer->spillWords again, it should still be set to 89 from previous use.
  JIT_DCHECK(spill_words == jit::kMinGenSpillWords, "invalid size");

  gen_data_free_list_size--;
  void* data = gen_data_free_list_tail;
  gen_data_free_list_tail = *reinterpret_cast<void**>(gen_data_free_list_tail);
  return reinterpret_cast<jit::GenDataFooter*>(
      reinterpret_cast<uint64_t*>(data) + spill_words);
}

void jitgen_data_free(PyGenObject* gen) {
  auto gen_data_footer =
      reinterpret_cast<jit::GenDataFooter*>(gen->gi_jit_data);
  gen->gi_jit_data = nullptr;
  auto gen_data = reinterpret_cast<uint64_t*>(gen_data_footer) -
      gen_data_footer->spillWords;

  if (gen_data_footer->spillWords != jit::kMinGenSpillWords ||
      gen_data_free_list_size == kGenDataFreeListMaxSize) {
    free(gen_data);
    return;
  }

  if (gen_data_free_list_size) {
    *reinterpret_cast<void**>(gen_data) = gen_data_free_list_tail;
  }
  gen_data_free_list_size++;
  gen_data_free_list_tail = gen_data;
}
#endif // PY_VERSION_HEX < 0x030C0000

void Context::forgetCode(BorrowedRef<PyFunctionObject> func) {
  compiled_codes_.erase(CompilationKey{func});
}

bool Context::didCompile(BorrowedRef<PyFunctionObject> func) {
  ThreadedCompileSerialize guard;
  return compiled_funcs_.contains(func);
}

CompiledFunction* Context::lookupFunc(BorrowedRef<PyFunctionObject> func) {
  return lookupCode(func->func_code, func->func_builtins, func->func_globals);
}

CodeRuntime* Context::lookupCodeRuntime(BorrowedRef<PyFunctionObject> func) {
  CompiledFunction* compiled = lookupFunc(func);
  if (compiled == nullptr) {
    return nullptr;
  }
  return compiled->runtime();
}

const UnorderedMap<CompilationKey, std::unique_ptr<CompiledFunction>>&
Context::compiledCodes() const {
  return compiled_codes_;
}

const UnorderedSet<BorrowedRef<PyFunctionObject>>& Context::compiledFuncs() {
  return compiled_funcs_;
}

const UnorderedSet<BorrowedRef<PyFunctionObject>>& Context::deoptedFuncs() {
  return deopted_funcs_;
}

const UnorderedSet<BorrowedRef<PyFunctionObject>>& Context::baselineFuncs() {
  return baseline_funcs_;
}

const UnorderedSet<BorrowedRef<PyFunctionObject>>&
Context::baselineScheduledFuncs() {
  return baseline_scheduled_funcs_;
}

const UnorderedSet<BorrowedRef<PyFunctionObject>>&
Context::deferredHelperPromotionFuncs() {
  return helper_promotion_deferred_funcs_;
}

void Context::addCompileTime(std::chrono::nanoseconds time) {
  auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(time);
  total_compile_time_ms_.fetch_add(ms.count(), std::memory_order_relaxed);
}

std::chrono::milliseconds Context::totalCompileTime() const {
  return std::chrono::milliseconds{
      total_compile_time_ms_.load(std::memory_order_relaxed)};
}

void Context::setCinderJitModule(Ref<> mod) {
  cinderjit_module_ = std::move(mod);
}

void Context::clearCache() {
  for (auto& entry : compiled_codes_) {
    orphaned_compiled_codes_.emplace_back(std::move(entry.second));
  }
  compiled_codes_.clear();
}

void Context::funcDestroyed(BorrowedRef<PyFunctionObject> func) {
  compiled_funcs_.erase(func);
  deopted_funcs_.erase(func);
  baseline_funcs_.erase(func);
  baseline_scheduled_funcs_.erase(func);
  helper_promotion_deferred_funcs_.erase(func);
  tier_states_.erase(func);
  for (const CodeRuntime* runtime : forgetCodeRuntimeOwner(func)) {
    forgetTypeDeoptPatchersForRuntime(runtime);
  }

  // This doesn't modify compiled_codes_, so if this is a nested function it can
  // easily be reopted later.
}

CompiledFunction* Context::lookupCode(
    BorrowedRef<PyCodeObject> code,
    BorrowedRef<PyDictObject> builtins,
    BorrowedRef<PyDictObject> globals) {
  ThreadedCompileSerialize guard;
  auto it = compiled_codes_.find(CompilationKey{code, builtins, globals});
  return it == compiled_codes_.end() ? nullptr : it->second.get();
}

void Context::addDeoptedFunc(BorrowedRef<PyFunctionObject> func) {
  deopted_funcs_.emplace(func);
  FunctionTierState& state = tierStateFor(func);
  state.active_tier = FunctionTier::kInterp;
  state.compiled = false;
  state.deopted = true;
  state.baseline_scheduled = false;
  state.last_transition = "deopt";
}

void Context::removeDeoptedFunc(BorrowedRef<PyFunctionObject> func) {
  deopted_funcs_.erase(func);
  tierStateFor(func).deopted = false;
}

bool Context::addBaselineFunc(BorrowedRef<PyFunctionObject> func) {
  ThreadedCompileSerialize guard;
  if (compiled_funcs_.contains(func)) {
    return false;
  }
  baseline_scheduled_funcs_.erase(func);
  helper_promotion_deferred_funcs_.erase(func);
  bool inserted = baseline_funcs_.emplace(func).second;
  FunctionTierState& state = tierStateFor(func);
  state.active_tier = FunctionTier::kBaseline;
  state.baseline_scheduled = false;
  state.compiled = false;
  state.deopted = false;
  state.helper_promotion_deferred = false;
  state.helper_promotion_threshold = 0;
  state.last_transition = "baseline";
  return inserted;
}

bool Context::removeBaselineFunc(BorrowedRef<PyFunctionObject> func) {
  ThreadedCompileSerialize guard;
  bool removed = baseline_funcs_.erase(func) == 1;
  if (removed) {
    FunctionTierState& state = tierStateFor(func);
    state.active_tier = FunctionTier::kInterp;
    state.last_transition = "baseline_removed";
  }
  return removed;
}

bool Context::isBaselineFunc(BorrowedRef<PyFunctionObject> func) {
  ThreadedCompileSerialize guard;
  return baseline_funcs_.contains(func);
}

bool Context::addBaselineScheduledFunc(BorrowedRef<PyFunctionObject> func) {
  ThreadedCompileSerialize guard;
  if (compiled_funcs_.contains(func) || baseline_funcs_.contains(func)) {
    return false;
  }
  bool inserted = baseline_scheduled_funcs_.emplace(func).second;
  FunctionTierState& state = tierStateFor(func);
  state.active_tier = FunctionTier::kInterp;
  state.baseline_scheduled = true;
  state.compiled = false;
  state.last_transition = "baseline_scheduled";
  return inserted;
}

bool Context::removeBaselineScheduledFunc(BorrowedRef<PyFunctionObject> func) {
  ThreadedCompileSerialize guard;
  bool removed = baseline_scheduled_funcs_.erase(func) == 1;
  if (removed) {
    FunctionTierState& state = tierStateFor(func);
    state.baseline_scheduled = false;
    if (state.active_tier == FunctionTier::kInterp) {
      state.last_transition = "baseline_unscheduled";
    }
  }
  return removed;
}

bool Context::isBaselineScheduledFunc(BorrowedRef<PyFunctionObject> func) {
  ThreadedCompileSerialize guard;
  return baseline_scheduled_funcs_.contains(func);
}

bool Context::addDeferredHelperPromotionFunc(
    BorrowedRef<PyFunctionObject> func,
    std::size_t threshold,
    const char* reason) {
  ThreadedCompileSerialize guard;
  if (compiled_funcs_.contains(func) || baseline_funcs_.contains(func)) {
    return false;
  }
  bool inserted = helper_promotion_deferred_funcs_.emplace(func).second;
  FunctionTierState& state = tierStateFor(func);
  state.active_tier = FunctionTier::kInterp;
  state.baseline_scheduled = false;
  state.compiled = false;
  state.deopted = false;
  state.helper_promotion_deferred = true;
  state.helper_promotion_threshold = threshold;
  state.helper_promotion_reason = reason;
  state.last_policy_event = "helper_promotion_deferred";
  state.last_policy_reason = reason;
  state.last_transition = "helper_promotion_deferred";
  return inserted;
}

bool Context::removeDeferredHelperPromotionFunc(
    BorrowedRef<PyFunctionObject> func,
    const char* reason) {
  ThreadedCompileSerialize guard;
  bool removed = helper_promotion_deferred_funcs_.erase(func) == 1;
  FunctionTierState& state = tierStateFor(func);
  if (removed || state.helper_promotion_deferred) {
    state.helper_promotion_deferred = false;
    state.helper_promotion_threshold = 0;
    state.helper_promotion_ready++;
    state.last_policy_event = reason;
    state.last_policy_reason = reason;
    if (state.active_tier == FunctionTier::kInterp) {
      state.last_transition = reason;
    }
  }
  return removed;
}

bool Context::isDeferredHelperPromotionFunc(BorrowedRef<PyFunctionObject> func) {
  ThreadedCompileSerialize guard;
  return helper_promotion_deferred_funcs_.contains(func);
}

std::optional<std::size_t> Context::deferredHelperPromotionThresholdIfDeferred(
    BorrowedRef<PyFunctionObject> func) {
  ThreadedCompileSerialize guard;
  if (!helper_promotion_deferred_funcs_.contains(func)) {
    return std::nullopt;
  }
  return tierStateFor(func).helper_promotion_threshold;
}

std::size_t Context::deferredHelperPromotionThreshold(
    BorrowedRef<PyFunctionObject> func) {
  ThreadedCompileSerialize guard;
  if (!helper_promotion_deferred_funcs_.contains(func)) {
    return 0;
  }
  return tierStateFor(func).helper_promotion_threshold;
}

void Context::clearBaselineScheduledTierState(const char* reason) {
  ThreadedCompileSerialize guard;
  for (BorrowedRef<PyFunctionObject> func : baseline_scheduled_funcs_) {
    FunctionTierState& state = tierStateFor(func);
    state.baseline_scheduled = false;
    if (state.active_tier == FunctionTier::kInterp) {
      state.last_transition = reason;
    }
  }
  baseline_scheduled_funcs_.clear();
}

void Context::noteUncompiledFunc(
    BorrowedRef<PyFunctionObject> func,
    const char* reason) {
  ThreadedCompileSerialize guard;
  compiled_funcs_.erase(func);
  deopted_funcs_.erase(func);
  baseline_funcs_.erase(func);
  baseline_scheduled_funcs_.erase(func);
  helper_promotion_deferred_funcs_.erase(func);
  FunctionTierState& state = tierStateFor(func);
  state.active_tier = FunctionTier::kInterp;
  state.baseline_scheduled = false;
  state.compiled = false;
  state.deopted = false;
  state.helper_promotion_deferred = false;
  state.helper_promotion_threshold = 0;
  clearPendingFallback(state);
  state.last_transition = reason;
  for (const CodeRuntime* runtime : forgetCodeRuntimeOwner(func)) {
    forgetTypeDeoptPatchersForRuntime(runtime);
  }
}

void Context::clearBaselineTierState(const char* reason) {
  ThreadedCompileSerialize guard;
  for (BorrowedRef<PyFunctionObject> func : baseline_funcs_) {
    FunctionTierState& state = tierStateFor(func);
    state.active_tier = FunctionTier::kInterp;
    state.baseline_scheduled = false;
    state.compiled = false;
    state.deopted = false;
    state.last_transition = reason;
  }
  for (BorrowedRef<PyFunctionObject> func : baseline_scheduled_funcs_) {
    FunctionTierState& state = tierStateFor(func);
    state.baseline_scheduled = false;
    if (state.active_tier == FunctionTier::kInterp) {
      state.last_transition = reason;
    }
  }
  for (BorrowedRef<PyFunctionObject> func : helper_promotion_deferred_funcs_) {
    FunctionTierState& state = tierStateFor(func);
    state.helper_promotion_deferred = false;
    state.helper_promotion_threshold = 0;
    if (state.active_tier == FunctionTier::kInterp) {
      state.last_transition = reason;
    }
  }
  baseline_funcs_.clear();
  baseline_scheduled_funcs_.clear();
  helper_promotion_deferred_funcs_.clear();
}

void Context::recordCompileFailure(
    BorrowedRef<PyFunctionObject> func,
    const char* reason) {
  ThreadedCompileSerialize guard;
  FunctionTierState& state = tierStateFor(func);
  state.compile_failures++;
  state.compile_failure_streak++;
  state.compile_failure_last_osr_cooldown_epoch = kNoOsrEpoch;
  state.compile_failure_osr_resume_deferred = false;
  state.last_compile_failure = reason;
  state.last_fallback_reason = reason;
  state.last_policy_event = "compile_failure";
  state.last_policy_reason = reason;
  state.last_transition = "compile_failed";
  if (isUnsupportedCompileFailure(reason)) {
    state.compile_failure_backoff = 0;
    state.compile_failure_cooldown_remaining = 0;
    blockPromotion(
        state,
        TierPolicyState::kCompileFailureUnsupported,
        "compile_failure_unsupported",
        "compile_failure_unsupported");
    return;
  }
  state.compile_failure_backoff =
      compileFailureBackoffForStreak(state.compile_failure_streak);
  state.compile_failure_cooldown_remaining = state.compile_failure_backoff;
  if (state.compile_failures >= kCompileFailureBackoffThreshold) {
    blockPromotion(
        state,
        TierPolicyState::kCompileFailureCooldown,
        "compile_failure_cooldown",
        "compile_failure_cooldown");
  }
}

void Context::resetFunctionTierPolicy(
    BorrowedRef<PyFunctionObject> func,
    const char* reason) {
  ThreadedCompileSerialize guard;
  FunctionTierState& state = tierStateFor(func);
  bool had_deopt_policy = hasDeoptBudgetPolicy(state);
  std::size_t resets_before = state.policy_resets;
  state.deopt_budget = kDefaultDeoptBudget;
  resetCompileFailurePolicy(state);
  if (had_deopt_policy && state.policy_resets == resets_before) {
    state.policy_resets++;
  }
  state.last_policy_event = "policy_reset";
  state.last_policy_reason = reason;
}

bool Context::shouldAttemptOptimizedPromotion(
    BorrowedRef<PyFunctionObject> func,
    const char* reason,
    std::size_t osr_epoch) {
  ThreadedCompileSerialize guard;
  FunctionTierState& state = tierStateFor(func);
  state.promotion_decisions++;
  state.last_promotion_reason = reason;
  if (state.policy_state == TierPolicyState::kCompileFailureCooldown &&
      state.promotion_blocked &&
      state.compile_failure_cooldown_remaining == 0) {
    clearPromotionBlock(state);
    state.last_policy_event = "compile_failure_cooldown_expired";
    state.last_policy_reason = reason;
  }
  if (state.deopt_budget == 0 && !state.promotion_blocked) {
    blockPromotion(
        state,
        TierPolicyState::kDeoptBudgetExhausted,
        "deopt_budget_exhausted",
        "deopt_budget_exhausted");
  }
  if (shouldDeferReadyHotLoopOsr(state, reason, osr_epoch)) {
    state.promotion_blocked_attempts++;
    state.last_promotion_decision = "blocked";
    state.last_policy_event = "compile_failure_cooldown_resume_deferred";
    state.last_policy_reason = reason;
    state.last_transition = "promotion_blocked";
    return false;
  }
  if (state.promotion_blocked) {
    bool cooldown_expired = false;
    if (state.policy_state == TierPolicyState::kCompileFailureCooldown &&
        state.compile_failure_cooldown_remaining > 0 &&
        shouldConsumeCompileFailureCooldown(state, reason, osr_epoch)) {
      state.compile_failure_cooldown_remaining--;
      if (state.compile_failure_cooldown_remaining == 0) {
        clearPromotionBlock(state);
        state.compile_failure_osr_resume_deferred =
            std::strcmp(reason, "hot_loop_osr") == 0;
        cooldown_expired = true;
      }
    }
    state.promotion_blocked_attempts++;
    state.last_promotion_decision = "blocked";
    state.last_policy_event =
        cooldown_expired ? "compile_failure_cooldown_expired"
                         : "promotion_blocked";
    state.last_policy_reason =
        cooldown_expired ? reason : state.promotion_blocked_reason;
    state.last_transition = "promotion_blocked";
    return false;
  }
  state.last_promotion_decision = "attempt";
  state.last_policy_event = "promotion_allowed";
  state.last_policy_reason = reason;
  return true;
}

void Context::recordPromotionAttempt(
    BorrowedRef<PyFunctionObject> func,
    const char* reason) {
  ThreadedCompileSerialize guard;
  FunctionTierState& state = tierStateFor(func);
  state.promotion_attempts++;
  state.last_promotion_decision = "attempt";
  state.last_promotion_reason = reason;
  state.last_policy_event = "promotion_attempt";
  state.last_policy_reason = reason;
  state.last_transition = "promotion_attempt";
}

void Context::recordRuntimeFallback(
    CodeRuntime* code_runtime,
    BorrowedRef<PyFunctionObject> func,
    const char* reason) {
  ThreadedCompileSerialize guard;
  auto owners_it = code_runtime_funcs_.find(code_runtime);
  if (owners_it == code_runtime_funcs_.end()) {
    return;
  }
  auto record_owner = [&](BorrowedRef<PyFunctionObject> owner) {
    FunctionTierState& state = tierStateFor(owner);
    state.runtime_fallbacks++;
    state.last_fallback_reason = reason;
    clearPendingFallback(state);
    state.last_policy_event = "runtime_fallback";
    state.last_policy_reason = reason;
    if (state.deopt_budget > 0) {
      state.deopt_budget--;
    }
    if (state.deopt_budget == 0) {
      blockPromotion(
          state,
          TierPolicyState::kDeoptBudgetExhausted,
          "deopt_budget_exhausted",
          "deopt_budget_exhausted");
    }
    state.last_transition = "runtime_fallback";
  };

  if (func != nullptr && owners_it->second.contains(func)) {
    record_owner(func);
    return;
  }

  if (owners_it->second.size() == 1) {
    record_owner(*owners_it->second.begin());
    return;
  }

  for (BorrowedRef<PyFunctionObject> owner : owners_it->second) {
    record_owner(owner);
  }
}

void Context::recordTypeInvalidation(
    CodeRuntime* code_runtime,
    const char* reason) {
  ThreadedCompileSerialize guard;
  auto owners_it = code_runtime_funcs_.find(code_runtime);
  if (owners_it == code_runtime_funcs_.end()) {
    return;
  }
  for (BorrowedRef<PyFunctionObject> func : owners_it->second) {
    FunctionTierState& state = tierStateFor(func);
    state.invalidations++;
    state.last_invalidation_reason = reason;
    state.last_fallback_reason = reason;
    state.fallback_pending = true;
    state.fallback_pending_reason = reason;
    state.last_policy_event = "type_invalidation";
    state.last_policy_reason = reason;
    state.last_transition = "type_invalidation";
  }
}

bool Context::hasCodeRuntimeOwners(const CodeRuntime* code_runtime) {
  ThreadedCompileSerialize guard;
  auto owners_it = code_runtime_funcs_.find(code_runtime);
  return owners_it != code_runtime_funcs_.end() && !owners_it->second.empty();
}

FunctionTierState Context::getFunctionTierState(
    BorrowedRef<PyFunctionObject> func) {
  ThreadedCompileSerialize guard;
  FunctionTierState state;
  auto state_it = tier_states_.find(func);
  if (state_it != tier_states_.end()) {
    state = state_it->second;
  }
  state.compiled = compiled_funcs_.contains(func);
  state.deopted = deopted_funcs_.contains(func);
  state.baseline_scheduled = baseline_scheduled_funcs_.contains(func);
  state.helper_promotion_deferred =
      helper_promotion_deferred_funcs_.contains(func);
  if (state.compiled) {
    state.active_tier = FunctionTier::kOptimized;
  } else if (baseline_funcs_.contains(func)) {
    state.active_tier = FunctionTier::kBaseline;
  } else {
    state.active_tier = FunctionTier::kInterp;
  }
  return state;
}

bool Context::addCompiledFunc(BorrowedRef<PyFunctionObject> func) {
  bool inserted = compiled_funcs_.emplace(func).second;
  if (inserted) {
    FunctionTierState& state = tierStateFor(func);
    state.active_tier = FunctionTier::kOptimized;
    state.compiled = true;
    state.deopted = false;
    state.baseline_scheduled = false;
    state.helper_promotion_deferred = false;
    state.helper_promotion_threshold = 0;
    helper_promotion_deferred_funcs_.erase(func);
    clearPendingFallback(state);
    state.last_transition = "optimized";
  }
  return inserted;
}

bool Context::removeCompiledFunc(BorrowedRef<PyFunctionObject> func) {
  bool removed = compiled_funcs_.erase(func) == 1;
  if (removed) {
    FunctionTierState& state = tierStateFor(func);
    state.compiled = false;
    if (!baseline_funcs_.contains(func)) {
      state.active_tier = FunctionTier::kInterp;
    }
    clearPendingFallback(state);
    for (const CodeRuntime* runtime : forgetCodeRuntimeOwner(func)) {
      forgetTypeDeoptPatchersForRuntime(runtime);
    }
  }
  return removed;
}

FunctionTierState& Context::tierStateFor(BorrowedRef<PyFunctionObject> func) {
  return tier_states_[func];
}

std::vector<const CodeRuntime*> Context::forgetCodeRuntimeOwner(
    BorrowedRef<PyFunctionObject> func) {
  std::vector<const CodeRuntime*> orphaned_runtimes;
  for (auto it = code_runtime_funcs_.begin(); it != code_runtime_funcs_.end();) {
    it->second.erase(func);
    if (it->second.empty()) {
      orphaned_runtimes.emplace_back(it->first);
      it = code_runtime_funcs_.erase(it);
    } else {
      ++it;
    }
  }
  return orphaned_runtimes;
}

void Context::forgetTypeDeoptPatchersForRuntime(const CodeRuntime* runtime) {
  if (runtime == nullptr) {
    return;
  }
  for (auto it = type_deopt_patchers_.begin();
       it != type_deopt_patchers_.end();) {
    auto& patchers = it->second;
    for (auto patcher_it = patchers.begin(); patcher_it != patchers.end();) {
      auto runtime_it = type_deopt_patcher_runtimes_.find(*patcher_it);
      if (runtime_it != type_deopt_patcher_runtimes_.end() &&
          runtime_it->second == runtime) {
        type_deopt_patcher_runtimes_.erase(runtime_it);
        patcher_it = patchers.erase(patcher_it);
      } else {
        ++patcher_it;
      }
    }
    if (patchers.empty()) {
      it = type_deopt_patchers_.erase(it);
    } else {
      ++it;
    }
  }
}

bool Context::addActiveCompile(CompilationKey& key) {
  return active_compiles_.insert(key).second;
}

void Context::removeActiveCompile(CompilationKey& key) {
  active_compiles_.erase(key);
}

CompiledFunction* Context::makeCompiledFunction(
    BorrowedRef<PyFunctionObject> func,
    const CompilationKey& key,
    CompiledFunctionData&& compiled_func) {
  auto compiled = std::make_unique<CompiledFunction>(std::move(compiled_func));

  auto pair = compiled_codes_.emplace(key, std::move(compiled));
  JIT_CHECK(pair.second, "CompilationKey already present");
  // If we have a function go ahead and initialize it
  if (func != nullptr) {
    finalizeFunc(func, *pair.first->second.get());
  }
  return pair.first->second.get();
}

#ifndef WIN32
void AotContext::init(void* bundle_handle) {
  JIT_CHECK(
      bundle_handle_ == nullptr,
      "Trying to register AOT bundle at {} but already have one at {}",
      bundle_handle,
      bundle_handle_);
  bundle_handle_ = bundle_handle;
}

void AotContext::destroy() {
  if (bundle_handle_ == nullptr) {
    return;
  }

  // TASK(T183003853): Unmap compiled functions and empty out private data
  // structures.

  dlclose(bundle_handle_);
  bundle_handle_ = nullptr;
}

void AotContext::registerFunc(const elf::Note& note) {
  elf::CodeNoteData note_data = elf::parseCodeNote(note);
  JIT_LOG("  Function {}", note.name);
  JIT_LOG("    File: {}", note_data.file_name);
  JIT_LOG("    Line: {}", note_data.lineno);
  JIT_LOG("    Hash: {:#x}", note_data.hash);
  JIT_LOG("    Size: {}", note_data.size);
  JIT_LOG("    Normal Entry: +{:#x}", note_data.normal_entry_offset);
  JIT_LOG(
      "    Static Entry: {}",
      note_data.static_entry_offset
          ? fmt::format("+{:#x}", *note_data.static_entry_offset)
          : "");

  // This could use std::piecewise_construct for better efficiency.
  auto [it, inserted] = funcs_.emplace(note.name, FuncState{});
  JIT_CHECK(inserted, "Duplicate ELF note for function '{}'", note.name);
  it->second.note = std::move(note_data);

  // Compute the compiled function's address after dynamic linking.
  void* address = dlsym(bundle_handle_, note.name.c_str());
  JIT_CHECK(
      address != nullptr,
      "Cannot find AOT-compiled function with name '{}' despite successfully "
      "loading the AOT bundle",
      note.name);
  it->second.compiled_code = {
      reinterpret_cast<const std::byte*>(address), it->second.note.size};
  JIT_LOG("    Address: {}", address);
}

const AotContext::FuncState* AotContext::lookupFuncState(
    BorrowedRef<PyFunctionObject> func) {
  std::string name = funcFullname(func);
  auto it = funcs_.find(name);
  return it != funcs_.end() ? &it->second : nullptr;
}
#endif

Context* getContext() {
  auto state = cinderx::getModuleState();
  if (state == nullptr) {
    return nullptr;
  }
  return static_cast<Context*>(state->jit_context.get());
}

} // namespace jit
