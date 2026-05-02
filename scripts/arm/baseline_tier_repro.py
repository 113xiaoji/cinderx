import faulthandler

import cinderx.jit as jit


faulthandler.enable()
jit.enable()

print("baseline_gate0", jit.get_baseline_compile_after_n_calls(), flush=True)
print("set_baseline_gate_1", flush=True)
jit.baseline_compile_after_n_calls(1)
print("baseline_gate1", jit.get_baseline_compile_after_n_calls(), flush=True)
print("clear_baseline_gate", flush=True)
jit.baseline_compile_after_n_calls(None)
print("baseline_gate2", jit.get_baseline_compile_after_n_calls(), flush=True)


def helper(x):
    return x + 1


print("tier0", jit.get_function_tier(helper), flush=True)
print("baseline_ret", jit.force_compile_baseline(helper), flush=True)
print("tier1", jit.get_function_tier(helper), flush=True)
print("before_force_compile", flush=True)
print("force_ret", jit.force_compile(helper), flush=True)
print("tier2", jit.get_function_tier(helper), flush=True)
