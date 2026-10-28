import contextlib
import io
import os
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
SCRIPTS = BASE / 'skills' / 'month-end' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import compare_runs
import monthend


class MonthEndTests(unittest.TestCase):
    def call_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / 'monthend.py'), *args], text=True, capture_output=True)

    def test_exact_excerpt_preserves_line(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'case.py'
            path.write_text('a=1\ncritical_anchor = "must_stay_exact"\nz=3\n')
            p = self.call_cli('excerpt', str(path), '--pattern', 'critical_anchor', '--context', '0')
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn('critical_anchor = "must_stay_exact"', p.stdout)
            self.assertIn('exact=true', p.stdout)

    def test_refuses_truncated_long_code_line(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'case.py'
            path.write_text('ANCHOR = "'+('x'*1000)+'"\n')
            p = self.call_cli('excerpt', str(path), '--pattern', 'ANCHOR', '--max-bytes', '128')
            self.assertEqual(p.returncode, 3)
            self.assertNotIn('ANCHOR =', p.stdout)
            self.assertIn('No truncated code returned', p.stderr)

    def test_search_only_reports_paths(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'app.py'
            path.write_text('SECRET_NEEDLE\n')
            p = self.call_cli('locate', 'SECRET_NEEDLE', '--root', td)
            self.assertEqual(p.returncode, 0)
            self.assertIn('app.py', p.stdout)
            self.assertNotIn('SECRET_NEEDLE', p.stdout)

    def test_run_failure_propagates_exit(self):
        p = self.call_cli('run', '--kind', 'tests', '--', sys.executable,
                          '-c', 'import sys; print("FAIL assertion failed"); sys.exit(7)')
        self.assertEqual(p.returncode, 7)
        self.assertIn('exit=7', p.stdout)
        self.assertIn('FAIL', p.stdout)
        self.assertIn('NOT a substitute', p.stdout)

    def test_run_success_summarizes_without_hiding_status(self):
        p = self.call_cli('run', '--kind', 'tests', '--', sys.executable,
                          '-c', 'print("line\\n"*100); print("20 passed")')
        self.assertEqual(p.returncode, 0)
        self.assertIn('20 passed', p.stdout)
        self.assertIn('exit=0', p.stdout)
        self.assertIn('excerpt=true', p.stdout)

    def test_huge_failing_single_line_signals_missing_diagnostics(self):
        p = self.call_cli('run', '--kind', 'tests', '--max-bytes', '200', '--', sys.executable,
                          '-c', 'import sys; print("ERROR "+"x"*10000); sys.exit(4)')
        self.assertEqual(p.returncode, 4)
        self.assertIn('candidate line(s)', p.stdout)
        self.assertIn('OMITTED', p.stdout)

    def test_log_opt_in_keeps_unfiltered_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / 'run.log'
            p = self.call_cli('run', '--kind', 'tests', '--log', str(log), '--', sys.executable,
                              '-c', 'print("original_log_line")')
            self.assertEqual(p.returncode, 0)
            self.assertIn(b'original_log_line', log.read_bytes())

    def test_audit_no_contents(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'AGENTS.md').write_text('secret private instruction')
            p = self.call_cli('audit', '--root', td)
            self.assertEqual(p.returncode, 0)
            self.assertIn('AGENTS.md', p.stdout)
            self.assertNotIn('secret private instruction', p.stdout)

    def test_metric_paired_and_success(self):
        rows, missing = compare_runs.load(BASE / 'examples' / 'benchmark_runs.csv')
        self.assertEqual(len(rows), 3)
        self.assertFalse(missing)
        self.assertTrue(rows[0][1]['success'])
        self.assertFalse(rows[1][2]['success'])

    def test_reject_duplicate_pair(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'data.csv'
            path.write_text('task_id,arm,success\na,baseline,1\na,baseline,1\na,month-end,1\n')
            with self.assertRaises(ValueError):
                compare_runs.load(path)

    def test_excerpt_rejects_invalid_utf8_and_binary(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'source.py'
            for raw in (b'ANCHOR = "\xff"\n', b'ANCHOR\x00\n'):
                with self.subTest(raw=raw):
                    path.write_bytes(raw)
                    p = self.call_cli('excerpt', str(path), '--pattern', 'ANCHOR')
                    self.assertEqual(p.returncode, 2)
                    self.assertNotIn('exact=true', p.stdout)
                    self.assertNotIn('ANCHOR', p.stdout)

    def test_excerpt_keeps_unicode_line_separators_inside_source_line(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'source.py'
            source = 'ANCHOR = "left\u2028right"'
            path.write_bytes((source + '\r\nnext = 1\r\n').encode('utf-8'))
            p = self.call_cli('excerpt', str(path), '--pattern', 'ANCHOR', '--context', '0')
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn(source, p.stdout)
            self.assertIn('     1 | ', p.stdout)

    def test_excerpt_refuses_zero_match_budget(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'source.py'
            path.write_text('ANCHOR = 1\n')
            p = self.call_cli('excerpt', str(path), '--pattern', 'ANCHOR', '--max-matches', '0')
            self.assertEqual(p.returncode, 2)
            self.assertNotIn('exact=true', p.stdout)

    def test_audit_finds_hidden_agent_configs_and_ignores_vendor(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            expected = ['.agents/skills/demo/SKILL.md', '.claude/settings.json',
                        '.codex/AGENTS.md', '.gemini/GEMINI.md']
            for name in expected + ['node_modules/demo/SKILL.md', '.git/AGENTS.md']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('private contents')
            p = self.call_cli('audit', '--root', td)
            self.assertEqual(p.returncode, 0, p.stderr)
            for name in expected:
                self.assertIn(name, p.stdout)
            self.assertNotIn('node_modules', p.stdout)
            self.assertNotIn('.git/', p.stdout)
            self.assertNotIn('private contents', p.stdout)

    def test_locate_stdout_contains_paths_only(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'space ü.py').write_text('NEEDLE\n')
            p = self.call_cli('locate', 'NEEDLE', '--root', td)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(len(p.stdout.splitlines()), 1)
            self.assertEqual(Path(p.stdout.strip()).name, 'space ü.py')
            self.assertIn('matches_shown=1', p.stderr)

    def test_fallback_search_skips_symlinks_binary_and_vendor(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside:
            root = Path(td)
            external = Path(outside) / 'private.py'
            external.write_text('NEEDLE')
            (root / 'linked.py').symlink_to(external)
            (root / 'binary.dat').write_bytes(b'NEEDLE\x00')
            (root / '.env').write_text('NEEDLE=private')
            (root / 'vendor').mkdir()
            (root / 'vendor' / 'ignored.py').write_text('NEEDLE')
            (root / 'real.py').write_text('NEEDLE')
            output = io.StringIO()
            with mock.patch.object(monthend.shutil, 'which', return_value=None), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(monthend.main(['locate', 'NEEDLE', '--root', td]), 0)
            self.assertEqual(output.getvalue().splitlines(), ['real.py'])

    def test_bad_log_path_prevents_command_side_effects(self):
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / 'command-ran'
            log = Path(td) / 'absent' / 'run.log'
            code = 'from pathlib import Path; Path(' + repr(str(marker)) + ').touch()'
            with mock.patch.object(monthend.subprocess, 'Popen') as launch, \
                    contextlib.redirect_stderr(io.StringIO()):
                result = monthend.main(['run', '--log', str(log), '--', sys.executable, '-c', code])
            self.assertEqual(result, 2)
            launch.assert_not_called()
            self.assertFalse(marker.exists())

    def test_run_passes_arguments_without_a_shell(self):
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / 'unexpected'
            argument = '$(touch ' + str(marker) + '); echo shell'
            p = self.call_cli('run', '--', sys.executable, '-c',
                              'import sys; print(sys.argv[1])', argument)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn(argument, p.stdout)
            self.assertFalse(marker.exists())

    def test_run_prioritizes_ansi_diagnostics_over_prelude(self):
        code = ('import sys; [print(str(i) + "x" * 60) for i in range(3)]; '
                'print("ER\\x1b[31mROR\\x1b[0m: middle failure"); '
                'print("boring\\n" * 100); sys.exit(9)')
        p = self.call_cli('run', '--kind', 'tests', '--max-bytes', '128', '--',
                          sys.executable, '-c', code)
        self.assertEqual(p.returncode, 9)
        self.assertIn('middle failure', p.stdout)

    def test_middle_error_survives_many_earlier_summaries(self):
        code = ('import sys; [print("1 passed") for _ in range(500)]; '
                'print("ERROR: important middle diagnostic"); '
                '[print("ordinary output") for _ in range(20_000)]; sys.exit(8)')
        p = self.call_cli('run', '--kind', 'tests', '--max-bytes', '128', '--',
                          sys.executable, '-c', code)
        self.assertEqual(p.returncode, 8)
        self.assertIn('important middle diagnostic', p.stdout)

    @unittest.skipUnless(os.name == 'posix', 'POSIX signal semantics')
    def test_run_preserves_signal_exit(self):
        p = self.call_cli('run', '--', sys.executable, '-c',
                          'import os, signal; os.kill(os.getpid(), signal.SIGTERM)')
        self.assertEqual(p.returncode, -15)
        self.assertIn('exit=-15', p.stdout)

    def test_binary_and_oversized_raw_log_is_complete(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / 'raw.log'
            raw = b'\xff\x00binary\n' + b'x' * 10_000 + b'\nlast line\n'
            p = self.call_cli('run', '--max-bytes', '128', '--log', str(log), '--',
                              sys.executable, '-c',
                              'import sys; sys.stdout.buffer.write(' + repr(raw) + ')')
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(log.read_bytes(), raw)
            self.assertIn('binary or invalid UTF-8', p.stdout)
            self.assertIn('last line', p.stdout)
            self.assertIn('lines=3 excerpt=true', p.stdout)

    def test_run_flags_warning_even_when_line_is_omitted(self):
        p = self.call_cli('run', '--max-bytes', '128', '--', sys.executable,
                          '-c', 'print("WARNING " + "x" * 10000)')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('Warning/error-like text was present', p.stdout)
        self.assertIn('OMITTED', p.stdout)

    def test_run_bounds_memory_for_five_megabyte_line(self):
        output = io.StringIO()
        tracemalloc.start()
        try:
            with contextlib.redirect_stdout(output):
                result = monthend.main(['run', '--max-bytes', '512', '--', sys.executable,
                                        '-c', 'import sys; sys.stdout.write("x" * 5_000_000)'])
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(result, 0)
        self.assertLess(peak, 2_000_000, f'Captured {peak} bytes for an oversized line')
        self.assertIn('raw_bytes=5000000', output.getvalue())
        self.assertIn('OMITTED', output.getvalue())

    def test_run_counts_inserted_newline_in_displayed_bytes(self):
        p = self.call_cli('run', '--', sys.executable, '-c', 'print("abc", end="")')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('raw_bytes=3 displayed_bytes=4', p.stdout)
        self.assertIn('excerpt=false', p.stdout)

    def test_reject_incomplete_and_malformed_ledgers(self):
        cases = [
            'task_id,arm,success\na,baseline,1\na,month-end,1\nb,baseline,0\n',
            'task_id,arm,success\na,baseline\na,month-end,1\n',
            'task_id,arm,success\na,baseline,1,extra\na,month-end,1\n',
            'task_id,arm,success,success\na,baseline,1,0\na,month-end,1,0\n',
            'task_id,arm,success,input_tokens\na,baseline,1,1.5\na,month-end,1,1\n',
            'task_id,arm,success,cost_usd\na,baseline,1,nan\na,month-end,1,1\n',
            'task_id,arm,success,cost_usd\na,baseline,1,-1\na,month-end,1,1\n',
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'runs.csv'
            for content in cases:
                with self.subTest(content=content):
                    path.write_text(content)
                    with self.assertRaises(ValueError):
                        compare_runs.load(path)

    def test_cost_includes_failed_attempts_and_missing_cost_stays_unknown(self):
        rows, _ = compare_runs.load(BASE / 'examples' / 'benchmark_runs.csv')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            compare_runs.summarize(rows, 'month-end')
        self.assertIn('billed_total_usd=$1.1700', output.getvalue())
        self.assertIn('billed_usd_per_success=$0.5850', output.getvalue())
        rows[0][2]['cost_usd'] = None
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            compare_runs.summarize(rows, 'month-end')
        self.assertIn('UNAVAILABLE', output.getvalue())
        self.assertNotIn('billed_total_usd=', output.getvalue())
        p = subprocess.run([sys.executable, str(SCRIPTS / 'compare_runs.py'),
                            str(BASE / 'examples' / 'benchmark_runs.csv')], text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('QUALITY GATE: NOT MET', p.stdout)


if __name__ == '__main__':
    unittest.main()
