from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REMOTE_HELPER = ROOT / "scripts" / "arm" / "remote_update_build_test.sh"


class RemoteUpdateBuildTestScriptTests(unittest.TestCase):
    def _helper_text(self) -> str:
        return REMOTE_HELPER.read_text(encoding="utf-8")

    def test_build_uses_no_isolation(self) -> None:
        text = self._helper_text()
        self.assertIn('"$PY" -m build --wheel -n', text)

    def test_driver_venv_pip_commands_disable_cinderx_autoload(self) -> None:
        text = self._helper_text()
        self.assertIn(
            "CINDERX_DISABLE=1 PYTHONJIT=0 python -m pip install -q -U pip",
            text,
        )
        self.assertIn(
            'CINDERX_DISABLE=1 PYTHONJIT=0 python -m pip install -q --force-reinstall "$WHEEL"',
            text,
        )
        self.assertIn(
            "CINDERX_DISABLE=1 PYTHONJIT=0 python -m pip install -q -U pyperformance",
            text,
        )

    def test_driver_venv_pyperformance_management_disables_cinderx_autoload(
        self,
    ) -> None:
        text = self._helper_text()
        self.assertIn(
            'CINDERX_DISABLE=1 PYTHONJIT=0 "${cmd[@]}"',
            text,
        )
        self.assertIn(
            'CINDERX_DISABLE=1 PYTHONJIT=0 python -m pyperformance venv show',
            text,
        )

    def test_skip_pyperf_exits_before_pyperformance_setup(self) -> None:
        text = self._helper_text()
        skip_pos = text.index('if [[ "$SKIP_PYPERF" == "1" ]]')
        ensure_pos = text.index('echo ">> ensure pyperformance venv exists"')
        self.assertLess(skip_pos, ensure_pos)

    def test_pyperformance_venv_creation_is_scoped_to_requested_benchmark(
        self,
    ) -> None:
        text = self._helper_text()
        self.assertIn(
            'PYPERF_VENV_BENCHMARKS="${PYPERF_VENV_BENCHMARKS:-$BENCH}"',
            text,
        )
        self.assertIn(
            'cmd=(python -m pyperformance venv recreate -b "$PYPERF_VENV_BENCHMARKS")',
            text,
        )
        self.assertIn(
            'cmd=(python -m pyperformance venv create -b "$PYPERF_VENV_BENCHMARKS")',
            text,
        )

    def test_autojit_gate_uses_driver_threshold_instead_of_global_disable(
        self,
    ) -> None:
        text = self._helper_text()
        self.assertIn(
            'env PYTHONJITAUTO="1000000" CINDERX_WORKER_PYTHONJITAUTO="$AUTOJIT_GATE"',
            text,
        )
        self.assertNotIn(
            'env PYTHONJITDISABLE=1 CINDERX_WORKER_PYTHONJITAUTO="$AUTOJIT_GATE"',
            text,
        )
        self.assertIn(
            'CINDERX_DEFER_WORKER_JIT="$DEFER_WORKER_JIT"',
            text,
        )

    def test_pyperf_cfg_rewrite_passes_path_before_heredoc(self) -> None:
        text = self._helper_text()
        self.assertIn(
            'python - "$PYVENV_PATH/pyvenv.cfg" <<\'PY\'',
            text,
        )
        self.assertNotIn(
            'python - <<\'PY\' "$PYVENV_PATH/pyvenv.cfg"',
            text,
        )

    def test_autojit_log_is_written_to_helper_artifact_dir(self) -> None:
        text = self._helper_text()
        self.assertIn(
            'LOG="/root/work/arm-sync/${BENCH}_autojit${AUTOJIT_GATE}_${RUN_ID}.log"',
            text,
        )
        self.assertNotIn(
            'LOG="/tmp/jit_${BENCH}_autojit${AUTOJIT_GATE}_${RUN_ID}.log"',
            text,
        )

    def test_compile_summary_heredoc_passes_args_before_redirect(self) -> None:
        text = self._helper_text()
        self.assertIn(
            'python - "$COMPILE_SUMMARY_JSON" "$BENCH" "$AUTOJIT_GATE" "$AUTOJIT_USE_JITLIST_FILTER" <<\'PY\' \\',
            text,
        )
        self.assertNotIn(
            'python - <<\'PY\' "$COMPILE_SUMMARY_JSON" "$BENCH" "$AUTOJIT_GATE" "$AUTOJIT_USE_JITLIST_FILTER" \\',
            text,
        )

    def test_only_richards_defaults_to_deferred_worker_jit(self) -> None:
        text = self._helper_text()
        self.assertIn('DEFER_WORKER_JIT="${DEFER_WORKER_JIT:-}"', text)
        self.assertIn('if [[ -z "$DEFER_WORKER_JIT" ]]; then', text)
        self.assertIn('if [[ "$BENCH" == "richards" ]]; then', text)
        self.assertIn('DEFER_WORKER_JIT=1', text)
        self.assertIn('DEFER_WORKER_JIT=0', text)

    def test_go_defaults_to_lower_worker_autojit_gate(self) -> None:
        text = self._helper_text()
        self.assertIn('AUTOJIT_GATE="${AUTOJIT_GATE:-}"', text)
        self.assertIn('if [[ -z "$AUTOJIT_GATE" ]]; then', text)
        self.assertIn('if [[ "$BENCH" == "go" ]]; then', text)
        self.assertIn('AUTOJIT_GATE=20', text)
        self.assertIn('AUTOJIT_GATE="$AUTOJIT"', text)

    def test_richards_defaults_to_focused_jitlist(self) -> None:
        text = self._helper_text()
        self.assertIn('BENCH_JITLIST_ENTRIES="${BENCH_JITLIST_ENTRIES:-}"', text)
        self.assertIn('if [[ -z "$BENCH_JITLIST_ENTRIES" ]]; then', text)
        self.assertIn('if [[ "$BENCH" == "richards" ]]; then', text)
        self.assertIn('__main__:schedule', text)
        self.assertIn('__main__:HandlerTask.fn', text)
        self.assertIn('__main__:DeviceTask.fn', text)
        self.assertIn('__main__:IdleTask.fn', text)
        self.assertIn('__main__:Richards.run', text)
        self.assertIn('JITLIST_ENTRIES="${CINDERX_JITLIST_ENTRIES:-$BENCH_JITLIST_ENTRIES}"', text)
        self.assertIn('AUTOJIT_JITLIST_ENTRIES="$BENCH_JITLIST_ENTRIES"', text)
        self.assertNotIn('AUTOJIT_JITLIST_ENTRIES="__main__:*"', text)

    def test_autojit_gate_uses_configured_worker_jit_deferral(self) -> None:
        text = self._helper_text()
        self.assertIn('CINDERX_DEFER_WORKER_JIT="$DEFER_WORKER_JIT"', text)
        self.assertNotIn('CINDERX_DEFER_WORKER_JIT=1 \\', text)

    def test_autojit_timed_run_avoids_debug_logging(self) -> None:
        text = self._helper_text()
        self.assertIn(
            'python -m pyperformance run --debug-single-value -b "$BENCH" \\',
            text,
        )
        self.assertIn(
            'AUTOJIT_JSON="/root/work/arm-sync/${BENCH}_autojit${AUTOJIT_GATE}_${RUN_ID}.json"',
            text,
        )
        self.assertIn(
            '-o "$AUTOJIT_JSON"',
            text,
        )
        self.assertIn(
            'AUTOJIT_PROOF_JSON="/root/work/arm-sync/${BENCH}_autojit${AUTOJIT_GATE}_${RUN_ID}_proof.json"',
            text,
        )

    def test_autojit_compile_proof_run_uses_debug_logging(self) -> None:
        text = self._helper_text()
        self.assertIn(
            'PYTHONJITDEBUG=1 PYTHONJITLOGFILE="$LOG"',
            text,
        )
        self.assertIn(
            '-o "$AUTOJIT_PROOF_JSON"',
            text,
        )


if __name__ == "__main__":
    unittest.main()
