import faulthandler

import cinderx.jit as jit


faulthandler.enable()
jit.enable()


def helper(x):
    return x + 1


print("tier0", jit.get_function_tier(helper), flush=True)
jit.baseline_compile_after_n_calls(1)
jit.compile_after_n_calls(3)

for index, value in enumerate((7, 8, 9, 10), 1):
    print(f"before{index}", jit.get_function_tier(helper), flush=True)
    print(f"call{index}", helper(value), flush=True)
    print(f"after{index}", jit.get_function_tier(helper), flush=True)

print("compiled", jit.is_jit_compiled(helper), flush=True)
print("uncompile", jit.force_uncompile(helper), flush=True)
print("tier_end", jit.get_function_tier(helper), flush=True)
