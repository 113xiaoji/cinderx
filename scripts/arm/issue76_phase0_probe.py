import cinderx.jit as jit


def hot(n: int, acc: int) -> int:
    while n > 0:
        acc = acc + n
        n = n - 1
    return acc


def main() -> None:
    jit.enable()
    ok = jit.force_compile(hot)
    print(f"force_compile={ok}")
    if not ok:
        raise SystemExit("force_compile failed")

    entries = jit.get_osr_entries(hot)
    print(f"osr_entries={entries}")
    if not entries:
        raise SystemExit("no osr entries exported")

    result = jit.run_osr_test_entry(hot, (3, 10))
    print(f"osr_result={result}")
    if result != 16:
        raise SystemExit(f"unexpected osr result: {result}")


if __name__ == "__main__":
    main()
