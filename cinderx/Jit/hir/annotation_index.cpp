// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/hir/annotation_index.h"

#include "cinderx/Jit/config.h"

namespace jit::hir {

std::unique_ptr<AnnotationIndex> AnnotationIndex::from_function(
    BorrowedRef<PyFunctionObject> func) {
  if (getMutableConfig().emit_type_annotation_guards ||
      getConfig().specialized_opcodes) {
#if PY_VERSION_HEX >= 0x030E0000
    // On 3.14+, PyFunction_GetAnnotations() may materialize lazy annotations
    // by executing Python code. Avoid re-entering Python from the compiler/OSR
    // path; only use annotations that have already been realized as a dict.
    BorrowedRef<> annotations{func->func_annotations};
    if (annotations == nullptr || !PyDict_Check(annotations)) {
      return nullptr;
    }
    BorrowedRef<PyDictObject> dict_annotations{annotations};
    return std::unique_ptr<AnnotationIndex>(
        new AnnotationIndex(dict_annotations));
#else
    if (func->func_annotations == nullptr ||
        !PyTuple_Check(func->func_annotations)) {
      return nullptr;
    }
    BorrowedRef<PyTupleObject> tuple_annotations{func->func_annotations};
    return std::unique_ptr<AnnotationIndex>(
        new AnnotationIndex(tuple_annotations));
#endif
  }
  return nullptr;
}

} // namespace jit::hir
