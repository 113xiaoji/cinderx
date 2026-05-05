import json
import math
import subprocess
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write_summary(path: Path, rows: list[tuple[str, float]]) -> None:
    payload = {
        "benchmarks": [
            {
                "name": name,
                "samples": [median],
                "median": median,
                "min": median,
                "max": median,
            }
            for name, median in rows
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_compare_pyperf_subset_reports_ratios_and_geomean(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    current = tmp_path / "current.json"
    output = tmp_path / "compare.json"
    write_summary(base, [("alpha", 1.0), ("beta", 4.0)])
    write_summary(current, [("alpha", 0.5), ("beta", 4.0)])

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "arm" / "compare_pyperf_subset.py"),
            "--base",
            str(base),
            "--current",
            str(current),
            "--output",
            str(output),
        ],
        check=True,
        cwd=ROOT,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    rows = {row["name"]: row for row in payload["rows"]}
    assert rows["alpha"]["time_ratio"] == 0.5
    assert rows["alpha"]["speedup_pct"] == 50.0
    assert rows["beta"]["time_ratio"] == 1.0
    assert rows["beta"]["speedup_pct"] == 0.0
    assert math.isclose(payload["geomean_time_ratio"], math.sqrt(0.5))
    assert math.isclose(
        payload["geomean_speedup_pct"], (1.0 - math.sqrt(0.5)) * 100.0
    )


def test_run_pyperf_subset_supports_explicit_nojit_worker_mode() -> None:
    text = (ROOT / "scripts" / "arm" / "run_pyperf_subset.sh").read_text(
        encoding="utf-8"
    )
    assert 'MODE="${MODE:-autojit}"' in text
    assert "MODE must be one of: autojit, nojit, jitlist, jitlist-autojit" in text
    assert 'inherit_env="PYTHONPATH' in text
    assert "CINDERX_DISABLE" in text
    assert 'CINDERX_DISABLE="0"' in text
    assert 'inherit_env="PYTHONPATH,CINDERX_ENABLE_SPECIALIZED_OPCODES,CINDERX_DISABLE"' in text
    assert 'worker_env+=(CINDERX_DISABLE="1")' in text
    assert 'CINDERX_JITLIST_AUTOJIT="$AUTOJIT"' in text
    assert 'PYTHONJITFILTERTINY="${PYTHONJITFILTERTINY:-}"' in text
    assert "add_optional_env PYTHONJITFILTERTINY" in text
    assert (
        'PYTHONJITSHAPEPROFITFILTER="${PYTHONJITSHAPEPROFITFILTER:-}"' in text
    )
    assert "add_optional_env PYTHONJITSHAPEPROFITFILTER" in text
    assert 'PYTHONJITADMITSTATEHELPERS="${PYTHONJITADMITSTATEHELPERS:-}"' in text
    assert "add_optional_env PYTHONJITADMITSTATEHELPERS" in text
    assert (
        'PYTHONJITADMITCALLINGSTATEHELPERS="${PYTHONJITADMITCALLINGSTATEHELPERS:-}"'
        in text
    )
    assert "add_optional_env PYTHONJITADMITCALLINGSTATEHELPERS" in text
    assert (
        'PYTHONJITDEFERFILTEREDHELPERS="${PYTHONJITDEFERFILTEREDHELPERS:-}"'
        in text
    )
    assert "add_optional_env PYTHONJITDEFERFILTEREDHELPERS" in text
    assert (
        'PYTHONJITDEFERCONTAINSHELPERS="${PYTHONJITDEFERCONTAINSHELPERS:-}"'
        in text
    )
    assert "add_optional_env PYTHONJITDEFERCONTAINSHELPERS" in text
    assert (
        'CINDERX_PYPERF_HOOK_PROBE_FILE="${CINDERX_PYPERF_HOOK_PROBE_FILE:-}"'
        in text
    )
    assert "add_optional_env CINDERX_PYPERF_HOOK_PROBE_FILE" in text
    assert 'INSTALL_CINDERX_WHEEL="${INSTALL_CINDERX_WHEEL:-1}"' in text
    assert "-m pyperformance venv create" in text
    assert '"$PYVENV_PATH/bin/python" -m pip install' in text
    assert 'PYTHONJITDEBUG="${PYTHONJITDEBUG:-}"' in text
    assert 'PYTHONJITLOGFILE="${PYTHONJITLOGFILE:-}"' in text
    assert "add_optional_env PYTHONJITDEBUG" in text
    assert "add_optional_env PYTHONJITLOGFILE" in text
    assert 'PYTHONJITFILTERGENERATED="${PYTHONJITFILTERGENERATED:-}"' in text
    assert "add_optional_env PYTHONJITFILTERGENERATED" in text
    assert 'PYTHONJITENABLEHIRINLINER="${PYTHONJITENABLEHIRINLINER:-}"' in text
    assert "add_optional_env PYTHONJITENABLEHIRINLINER" in text
    assert (
        'PYTHONJITENABLEMETHODVALUEINLINER="${PYTHONJITENABLEMETHODVALUEINLINER:-}"'
        in text
    )
    assert "add_optional_env PYTHONJITENABLEMETHODVALUEINLINER" in text
    assert (
        'PYTHONJITENABLESPECIALIZEDCONTAINS="${PYTHONJITENABLESPECIALIZEDCONTAINS:-}"'
        in text
    )
    assert "add_optional_env PYTHONJITENABLESPECIALIZEDCONTAINS" in text
    assert (
        'PYTHONJITDYNAMICMETHODCACHESPLIT="${PYTHONJITDYNAMICMETHODCACHESPLIT:-}"'
        in text
    )
    assert "add_optional_env PYTHONJITDYNAMICMETHODCACHESPLIT" in text
    assert (
        'PYTHONJITENABLEKWPYFUNCVECTORCALL="${PYTHONJITENABLEKWPYFUNCVECTORCALL:-}"'
        in text
    )
    assert "add_optional_env PYTHONJITENABLEKWPYFUNCVECTORCALL" in text
    assert (
        'PYTHONJITZEROARGMWVDELAYEDLOOKUP="${PYTHONJITZEROARGMWVDELAYEDLOOKUP:-}"'
        in text
    )
    assert "add_optional_env PYTHONJITZEROARGMWVDELAYEDLOOKUP" in text
    assert 'PYTHONJITEXACTDICTSUBSCR="${PYTHONJITEXACTDICTSUBSCR:-}"' in text
    assert "add_optional_env PYTHONJITEXACTDICTSUBSCR" in text
    assert (
        'PYTHONJITMETHODDESCRFASTVECTORCALL="${PYTHONJITMETHODDESCRFASTVECTORCALL:-}"'
        in text
    )
    assert "add_optional_env PYTHONJITMETHODDESCRFASTVECTORCALL" in text
    assert 'PYTHONJITINLINELISTITERNEXT="${PYTHONJITINLINELISTITERNEXT:-}"' in text
    assert "add_optional_env PYTHONJITINLINELISTITERNEXT" in text
    assert (
        'PYTHONJITSTOREATTRINSTANCEVALUEEXISTING="${PYTHONJITSTOREATTRINSTANCEVALUEEXISTING:-}"'
        in text
    )
    assert "add_optional_env PYTHONJITSTOREATTRINSTANCEVALUEEXISTING" in text


def test_pyperf_hook_can_delay_jitlist_compilation(monkeypatch) -> None:
    calls = []
    fake_pkg = types.ModuleType("cinderx")
    fake_pkg.__path__ = []
    fake_jit = types.ModuleType("cinderx.jit")
    fake_jit.enable = lambda: calls.append(("enable", None))
    fake_jit.enable_specialized_opcodes = lambda: calls.append(("specialized", None))
    fake_jit.compile_after_n_calls = lambda n: calls.append(("compile_after", n))
    fake_jit.append_jit_list = lambda entry: calls.append(("jitlist", entry))

    monkeypatch.setitem(sys.modules, "cinderx", fake_pkg)
    monkeypatch.setitem(sys.modules, "cinderx.jit", fake_jit)
    monkeypatch.setattr(sys, "argv", ["run_benchmark.py"])
    monkeypatch.setattr(sys, "orig_argv", ["python", "run_benchmark.py"], raising=False)
    monkeypatch.setenv("PYPERFORMANCE_RUNID", "test-run")
    monkeypatch.setenv("CINDERX_ENABLE_SPECIALIZED_OPCODES", "1")
    monkeypatch.setenv("CINDERX_JITLIST_ENTRIES", "__main__:*")
    monkeypatch.setenv("CINDERX_JITLIST_AUTOJIT", "50")

    import importlib.util

    hook = ROOT / "scripts" / "arm" / "pyperf_env_hook" / "sitecustomize.py"
    spec = importlib.util.spec_from_file_location("pyperf_hook_under_test", hook)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert ("compile_after", 50) in calls
    assert ("compile_after", 0) not in calls
    assert ("jitlist", "__main__:*") in calls


def test_pyperf_hook_can_write_worker_probe(monkeypatch, tmp_path: Path) -> None:
    calls = []
    fake_pkg = types.ModuleType("cinderx")
    fake_pkg.__path__ = []
    fake_jit = types.ModuleType("cinderx.jit")
    fake_func = lambda: None
    fake_func.__module__ = "bench"
    fake_func.__qualname__ = "hot"
    fake_jit.enable = lambda: calls.append(("enable", None))
    fake_jit.enable_specialized_opcodes = lambda: calls.append(("specialized", None))
    fake_jit.compile_after_n_calls = lambda n: calls.append(("compile_after", n))
    fake_jit.append_jit_list = lambda entry: calls.append(("jitlist", entry))
    fake_jit.is_enabled = lambda: True
    fake_jit.get_compile_after_n_calls = lambda: 50
    fake_jit.get_compiled_functions = lambda: [fake_func]

    probe = tmp_path / "probe.jsonl"
    monkeypatch.setitem(sys.modules, "cinderx", fake_pkg)
    monkeypatch.setitem(sys.modules, "cinderx.jit", fake_jit)
    monkeypatch.setattr(sys, "argv", ["run_benchmark.py"])
    monkeypatch.setattr(sys, "orig_argv", ["python", "run_benchmark.py"], raising=False)
    monkeypatch.setenv("PYPERFORMANCE_RUNID", "probe-run")
    monkeypatch.setenv("CINDERX_ENABLE_SPECIALIZED_OPCODES", "1")
    monkeypatch.setenv("CINDERX_WORKER_PYTHONJITAUTO", "50")
    monkeypatch.setenv("PYTHONJITADMITCALLINGSTATEHELPERS", "1")
    monkeypatch.setenv("CINDERX_PYPERF_HOOK_PROBE_FILE", str(probe))
    monkeypatch.delenv("CINDERX_DISABLE", raising=False)

    import importlib.util

    hook = ROOT / "scripts" / "arm" / "pyperf_env_hook" / "sitecustomize.py"
    spec = importlib.util.spec_from_file_location("pyperf_hook_probe_under_test", hook)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    payloads = [json.loads(line) for line in probe.read_text(encoding="utf-8").splitlines()]
    assert payloads
    payload = payloads[-1]
    assert payload["phase"] == "enabled"
    assert payload["env"]["CINDERX_DISABLE"] is None
    assert payload["env"]["CINDERX_WORKER_PYTHONJITAUTO"] == "50"
    assert payload["env"]["PYTHONJITADMITCALLINGSTATEHELPERS"] == "1"
    assert payload["jit_enabled"] is True
    assert payload["compile_after"] == 50
    assert payload["compiled_count"] == 1
    assert payload["compiled_sample"] == ["bench:hot"]
