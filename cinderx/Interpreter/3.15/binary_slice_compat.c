// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/python.h"

static PyObject* ci_binary_slice_fallback(
    PyObject* container,
    PyObject* start,
    PyObject* stop) {
  PyObject* slice = PySlice_New(start, stop, NULL);
  if (slice == NULL) {
    return NULL;
  }
  PyObject* result = PyObject_GetItem(container, slice);
  Py_DECREF(slice);
  return result;
}

PyObject* _CiList_BinarySlice(PyObject* container, PyObject* start, PyObject* stop) {
  return ci_binary_slice_fallback(container, start, stop);
}

PyObject* _CiTuple_BinarySlice(
    PyObject* container,
    PyObject* start,
    PyObject* stop) {
  return ci_binary_slice_fallback(container, start, stop);
}

PyObject* _CiUnicode_BinarySlice(
    PyObject* container,
    PyObject* start,
    PyObject* stop) {
  return ci_binary_slice_fallback(container, start, stop);
}
