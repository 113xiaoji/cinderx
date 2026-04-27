// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/type_deopt_patchers.h"

#include "cinderx/Common/type.h"
#include "cinderx/Common/util.h"

#include <utility>

namespace jit {

template <typename Body>
bool shouldPatchForAttr(
    BorrowedRef<PyTypeObject> old_ty,
    BorrowedRef<PyTypeObject> new_ty,
    BorrowedRef<PyUnicodeObject> attr_name,
    Body body) {
  if (new_ty != old_ty) {
    // new_ty is not the same as old_ty (it's either nullptr or a new type). If
    // new_ty has the same attribute with the same properties, we could watch
    // it as well and leave the specialized code in place, but that would
    // increase complexity and memory usage for what should be a vanishingly
    // rare situation.
    return true;
  }

  // Similarly to the JIT code using this patcher, we want to avoid triggering
  // user-visible side-effects, so we do the lookup using typeLookupSafe(). If
  // that succeeds and returns an object that still satisfies our requirements,
  // we attempt to give the type a new version tag before declaring success.
  BorrowedRef<> attr{typeLookupSafe(new_ty, attr_name)};
  return body(attr) || !PyUnstable_Type_AssignVersionTag(new_ty);
}

TypeDeoptPatcher::TypeDeoptPatcher(
    BorrowedRef<PyTypeObject> type,
    BorrowedRef<PyCodeObject> owner_code,
    BorrowedRef<PyDictObject> owner_builtins,
    BorrowedRef<PyDictObject> owner_globals,
    std::string owner_func_qualname,
    std::string description)
    : type_{type},
      owner_code_{owner_code},
      owner_builtins_{owner_builtins},
      owner_globals_{owner_globals},
      owner_func_qualname_{std::move(owner_func_qualname)},
      description_{std::move(description)} {}

bool TypeDeoptPatcher::maybePatch(BorrowedRef<PyTypeObject>) {
  patch();
  return true;
}

BorrowedRef<PyTypeObject> TypeDeoptPatcher::type() const {
  return type_;
}

bool TypeDeoptPatcher::ownerMatches(BorrowedRef<PyFunctionObject> func) const {
  return func->func_code == owner_code_ &&
      func->func_builtins == owner_builtins_ &&
      func->func_globals == owner_globals_;
}

std::string_view TypeDeoptPatcher::ownerFuncQualname() const {
  return owner_func_qualname_;
}

std::string_view TypeDeoptPatcher::kind() const {
  return "type";
}

std::string_view TypeDeoptPatcher::description() const {
  return description_;
}

void TypeDeoptPatcher::onUnpatch() {
  JIT_ABORT(
      "TypeDeoptPatcher for type {} being unpatched but that's not supported!",
      type_->tp_name);
}

TypeAttrDeoptPatcher::TypeAttrDeoptPatcher(
    BorrowedRef<PyTypeObject> type,
    BorrowedRef<PyUnicodeObject> attr_name,
    BorrowedRef<> target_object,
    BorrowedRef<PyCodeObject> owner_code,
    BorrowedRef<PyDictObject> owner_builtins,
    BorrowedRef<PyDictObject> owner_globals,
    std::string owner_func_qualname,
    std::string description)
    : TypeDeoptPatcher{
          type,
          owner_code,
          owner_builtins,
          owner_globals,
          std::move(owner_func_qualname),
          std::move(description)} {
  ThreadedCompileSerialize guard;
  attr_name_.reset(attr_name);
  target_object_.reset(target_object);
}

bool TypeAttrDeoptPatcher::maybePatch(BorrowedRef<PyTypeObject> new_ty) {
  bool should_patch =
      shouldPatchForAttr(type_, new_ty, attr_name_, [&](BorrowedRef<> attr) {
        return attr != target_object_;
      });
  if (should_patch) {
    patch();
  }
  return should_patch;
}

std::string_view TypeAttrDeoptPatcher::kind() const {
  return "type_attr";
}

void TypeAttrDeoptPatcher::onPatch() {
  attr_name_.reset();
  target_object_.reset();
}

SplitDictDeoptPatcher::SplitDictDeoptPatcher(
    BorrowedRef<PyTypeObject> type,
    BorrowedRef<PyUnicodeObject> attr_name,
    PyDictKeysObject* keys,
    BorrowedRef<PyCodeObject> owner_code,
    BorrowedRef<PyDictObject> owner_builtins,
    BorrowedRef<PyDictObject> owner_globals,
    std::string owner_func_qualname,
    std::string description)
    : TypeDeoptPatcher{
          type,
          owner_code,
          owner_builtins,
          owner_globals,
          std::move(owner_func_qualname),
          std::move(description)},
      keys_{keys} {
  ThreadedCompileSerialize guard;
  attr_name_.reset(attr_name);
}

bool SplitDictDeoptPatcher::maybePatch(BorrowedRef<PyTypeObject> new_ty) {
  bool should_patch =
      shouldPatchForAttr(type_, new_ty, attr_name_, [&](BorrowedRef<> attr) {
        if (attr != nullptr) {
          // This is more conservative than strictly necessary: the split dict
          // lookup would still be OK if attr isn't a data descriptor, but we'd
          // have to watch attr's type to safely rely on that fact.
          return true;
        }

        if (!PyType_HasFeature(new_ty, Py_TPFLAGS_HEAPTYPE)) {
          return true;
        }

        BorrowedRef<PyHeapTypeObject> ht(new_ty);
        return ht->ht_cached_keys != keys_;
      });
  if (should_patch) {
    patch();
  }
  return should_patch;
}

std::string_view SplitDictDeoptPatcher::kind() const {
  return "split_dict";
}

void SplitDictDeoptPatcher::onPatch() {
  attr_name_.reset();
}

} // namespace jit
