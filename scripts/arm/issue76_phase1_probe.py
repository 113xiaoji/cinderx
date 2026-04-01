import cinderx.jit as jit


def hot(n: int, acc: int) -> int:
    while n > 0:
        acc = acc + n
        n = n - 1
    return acc


def main() -> None:
    jit.enable()
    jit.enable_specialized_opcodes()
    jit.compile_after_n_calls(1000000)
    jit.get_and_clear_runtime_stats()
    result = hot(50000, 0)
    stats = jit.get_and_clear_runtime_stats()
    osr = [
        entry for entry in stats.get("osr", [])
        if entry["normal"]["func_qualname"] == "hot"
    ]
    print(f"result={result}")
    print(f"osr_entries={osr}")
    if result != (50000 * 50001) // 2:
        raise SystemExit("wrong result")
    if not osr:
        raise SystemExit("no osr stats")
    if sum(entry["int"]["count"] for entry in osr) <= 0:
        raise SystemExit("osr count did not increase")


if __name__ == "__main__":
    main()
