#!/usr/bin/env python3
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path


DICT = {
    "ads_flags": 0,
    "age": 18,
    "birthday": "1980-05-07",
    "comment_count": 0,
    "country": "BR",
    "favorite_count": 9,
    "first_name": "",
    "flags": 412317970704,
    "friend_count": 0,
    "gender": "m",
    "id": 302935349,
    "locale_preference": "pt_BR",
    "member": 0,
    "tags": ["a", "b", "c", "d", "e", "f", "g"],
    "profile_foo_id": 827119638,
    "session_number": 2,
    "status": "A",
    "theme": 1,
    "time_created": 1225237014,
    "time_updated": 1233134493,
    "unread_message_count": 0,
    "user_group": "0",
    "username": "collinwinter",
    "play_count": 9,
    "view_count": 7,
    "zip": "",
}

TUPLE = ([i for i in range(20)], 60)
DICT_GROUP = [dict(DICT, id=DICT["id"] + i) for i in range(3)]


def bench_unpickle_pure_python(loops: int) -> None:
    sys.modules["_pickle"] = None
    import pickle as pure_pickle

    pickled_dict = pure_pickle.dumps(DICT, pure_pickle.HIGHEST_PROTOCOL)
    pickled_tuple = pure_pickle.dumps(TUPLE, pure_pickle.HIGHEST_PROTOCOL)
    pickled_dict_group = pure_pickle.dumps(DICT_GROUP, pure_pickle.HIGHEST_PROTOCOL)
    objs = (pickled_dict, pickled_tuple, pickled_dict_group)
    loads = pure_pickle.loads
    for _ in range(loops):
        for obj in objs:
            for _ in range(20):
                loads(obj)


def main() -> int:
    loops = int(sys.argv[1]) if len(sys.argv) > 1 else 20

    sys.modules["_pickle"] = None
    import pickle as pure_pickle

    import cinderx
    import cinderx.jit as jit

    cinderx.jit.enable_specialized_opcodes()
    jit.enable()
    jit.compile_after_n_calls(1000000)

    targets = []
    for qualname in ("_Unframer.read", "_Unframer.load_frame", "_Unpickler.load_frame"):
        owner_name, func_name = qualname.split(".")
        owner = getattr(pure_pickle, owner_name, None)
        fn = getattr(owner, func_name, None) if owner is not None else None
        if fn is not None:
            targets.append((qualname, fn))

    compiled_targets = []
    for qualname, fn in targets:
        try:
            ok = bool(jit.force_compile(fn))
        except Exception:
            ok = False
        compiled_targets.append({"qualname": qualname, "forced": ok})

    bench_unpickle_pure_python(loops)

    stats = jit.get_and_clear_runtime_stats()
    funcs = []
    for fn in jit.get_compiled_functions():
        qualname = f"{fn.__module__}:{fn.__qualname__}"
        if "_Unframer" not in qualname and "_Unpickler" not in qualname:
            continue
        funcs.append(
            {
                "qualname": qualname,
                "compilation_time": jit.get_function_compilation_time(fn),
                "opcode_counts": jit.get_function_hir_opcode_counts(fn),
            }
        )

    payload = {
        "loops": loops,
        "forced_targets": compiled_targets,
        "deopt": stats.get("deopt", []),
        "compiled": funcs,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
