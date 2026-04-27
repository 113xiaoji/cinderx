// Copyright (c) Meta Platforms, Inc. and affiliates.
#pragma once

#include "cinderx/Common/ref.h"
#include "cinderx/Jit/code_patcher.h"
#include "cinderx/Jit/threaded_compile.h"

#include <string>
#include <string_view>

namespace jit {

// Patch a DeoptPatchpoint when the given PyTypeObject changes at all. This
// should only be used (instead of a more specific subclass) in cases where it
// is impossible to check the property we care about in maybePatch() (e.g., if
// the change to the type happens after PyType_Modified() is called).
class TypeDeoptPatcher : public JumpPatcher {
 public:
  TypeDeoptPatcher(
      BorrowedRef<PyTypeObject> type,
      std::string owner_func_qualname,
      std::string description);

  virtual bool maybePatch(BorrowedRef<PyTypeObject> new_ty);

  // Access the type being watched.
  BorrowedRef<PyTypeObject> type() const;
  std::string_view ownerFuncQualname() const;
  virtual std::string_view kind() const;
  std::string_view description() const;

 protected:
  void onUnpatch() override;

  // The type being watched.  It outlives this object because this object will
  // be cleaned up by a type watcher notification.
  BorrowedRef<PyTypeObject> type_;
  std::string owner_func_qualname_;
  std::string description_;
};

// Patch a DeoptPatchpoint when the given PyTypeObject no longer has the given
// PyObject* at the specified name.
class TypeAttrDeoptPatcher : public TypeDeoptPatcher {
 public:
  TypeAttrDeoptPatcher(
      BorrowedRef<PyTypeObject> type,
      BorrowedRef<PyUnicodeObject> attr_name,
      BorrowedRef<> target_object,
      std::string owner_func_qualname,
      std::string description);

  bool maybePatch(BorrowedRef<PyTypeObject> new_ty) override;
  std::string_view kind() const override;

 private:
  void onPatch() override;

  ThreadedRef<PyUnicodeObject> attr_name_;
  ThreadedRef<> target_object_;
};

class SplitDictDeoptPatcher : public TypeDeoptPatcher {
 public:
  SplitDictDeoptPatcher(
      BorrowedRef<PyTypeObject> type,
      BorrowedRef<PyUnicodeObject> attr_name,
      PyDictKeysObject* keys,
      std::string owner_func_qualname,
      std::string description);

  bool maybePatch(BorrowedRef<PyTypeObject> new_ty) override;
  std::string_view kind() const override;

 private:
  void onPatch() override;

  ThreadedRef<PyUnicodeObject> attr_name_;

  // We don't need to hold a strong reference to keys_ like we do for
  // attr_name_ because calls to PyTypeModified() happen before the old keys
  // object is decrefed.
  PyDictKeysObject* keys_;
};

} // namespace jit
