"""Behavioral tests of the offline paired-runner contract."""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills' / 'month-end' / 'scripts'))
import benchmark
import compare_runs
import integrations


class BenchmarkTests(unittest.TestCase):
    def fixture(self, candidate=None, repeats=1, warm=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / 'source'
        source.mkdir()
        (source / 'app.py').write_text('VALUE = 0\n')
        script = candidate or ('from pathlib import Path; p=Path("app.py"); '
                               'assert p.read_text()=="VALUE = 0\\n"; p.write_text("VALUE = 7\\n")')
        arm = {'argv': ['{python}', '-c', script]}
        if warm:
            arm['warmup_argv'] = ['{python}', '-c', 'print("local warmup fixture")']
        data = dict(version=1, data_kind='local-mechanism', model='local-fixture', repeats=repeats,
                    cache_states=['cold', 'warm'] if warm else ['cold'], timeout_seconds=5,
                    arms={'baseline': dict(arm), 'month-end': dict(arm)},
                    tasks=[dict(id='behavior', category='isolation', prompt='Set VALUE to 7.',
                                source_dir='source', source_sha256=benchmark.fingerprint(source),
                                grader=['{python}', '-c', 'import app; assert app.VALUE == 7'])])
        path = root / 'suite.json'
        path.write_text(json.dumps(data))
        return root, path, data

    def test_plan_is_deterministic_and_never_executes(self):
        root, path, _ = self.fixture('from pathlib import Path; Path("command-ran").touch()', repeats=3, warm=True)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(benchmark.main([str(path)]), 0)
        plan = json.loads(stdout.getvalue())
        self.assertEqual(plan['mode'], 'plan-only')
        self.assertFalse((root / 'source' / 'command-ran').exists())
        manifest = benchmark.load_manifest(path)
        first = benchmark.schedule(manifest, 3)
        self.assertEqual(first, benchmark.schedule(manifest, 3))
        self.assertNotEqual(first, benchmark.schedule(manifest, 4))
        self.assertEqual(len(first), 12)
        for index in range(0, len(first), 2):
            self.assertEqual({first[index]['arm'], first[index+1]['arm']}, {'baseline', 'month-end'})
            self.assertEqual(first[index]['repeat'], first[index+1]['repeat'])
            self.assertEqual(first[index]['cache_state'], first[index+1]['cache_state'])

    def test_real_execution_isolates_each_arm_repeat_and_cache_trial(self):
        root, path, _ = self.fixture(repeats=3, warm=True)
        output = root / 'results'
        summary = benchmark.execute(benchmark.load_manifest(path), output, seed=5)
        self.assertEqual(summary['trials'], 12)
        self.assertEqual(summary['successes'], 12)
        self.assertEqual((root / 'source' / 'app.py').read_text(), 'VALUE = 0\n')
        pairs, incomplete = compare_runs.load(output / 'runs.csv', require_metadata=True)
        self.assertEqual(len(pairs), 6)
        self.assertFalse(incomplete)
        self.assertEqual(len(compare_runs.task_clusters(pairs)), 1)
        self.assertIsNone(compare_runs.cost_per_success_delta(pairs))
        self.assertTrue(all(row[1]['cost_usd'] is None for row in pairs))
        receipts = list(output.glob('*/receipt.json'))
        self.assertEqual(len(receipts), 12)
        self.assertTrue(all(json.loads(path.read_text())['grader_exit'] == 0 for path in receipts))

    def test_successful_command_with_wrong_patch_is_failed_by_independent_grade(self):
        root, path, _ = self.fixture('print("agent says task finished")')
        output = root / 'results'
        summary = benchmark.execute(benchmark.load_manifest(path), output)
        self.assertEqual(summary['successes'], 0)
        receipts = [json.loads(path.read_text()) for path in output.glob('*/receipt.json')]
        self.assertTrue(all(row['candidate_exit'] == 0 and row['grader_exit'] != 0 for row in receipts))

    def test_retries_keep_failed_spending_in_the_total(self):
        usage = {'format': 'month-end-usage-v1', 'provider': 'openai',
                 'responses': [{'object':'response', 'id':'fixture-only', 'model':'local-fixture',
                                'usage': {'input_tokens':10,'output_tokens':3}}],
                 'billing': {'currency':'USD','cost_usd':0.75,'source':'synthetic test invoice',
                             'reference':'fixture; not real billing'}}
        code = ('from pathlib import Path; import json,uuid; data=' + repr(usage) + '; '
                'data["responses"][0]["id"]=str(uuid.uuid4()); '
                'Path("usage.json").write_text(json.dumps(data))')
        root, path, data = self.fixture(code)
        data['max_attempts'] = 2
        for arm in data['arms'].values():
            arm.update(provider='openai', usage_file='usage.json')
        path.write_text(json.dumps(data))
        output = root / 'results'
        summary = benchmark.execute(benchmark.load_manifest(path), output)
        self.assertEqual(summary['successes'], 0)
        for receipt in output.glob('*/receipt.json'):
            row = json.loads(receipt.read_text())
            self.assertEqual(row['attempts'], 2)
            self.assertEqual(row['cost_usd'], 1.5)
            self.assertEqual(row['input_tokens'], 20)
            self.assertEqual(row['calls'], 2)
            self.assertTrue(any('not independently reconciled' in warning for warning in row['usage_warnings']))

    def test_source_drift_stops_before_execution(self):
        root, path, _ = self.fixture()
        (root / 'source' / 'app.py').write_text('changed after preregistration\n')
        with self.assertRaisesRegex(ValueError, 'fingerprint mismatch'):
            benchmark.load_manifest(path)
        self.assertFalse((root / 'results').exists())

    def test_installed_usage_benchmark_remains_reversibly_managed(self):
        usage = {'object': 'response', 'model': 'local-fixture',
                 'usage': {'input_tokens': 10, 'output_tokens': 3}}
        code = ('from pathlib import Path; import json,uuid; data=' + repr(usage) + '; '
                'data["id"]=str(uuid.uuid4()); Path("usage.json").write_text(json.dumps(data)); '
                'Path("app.py").write_text("VALUE = 7\\n")')
        root, path, data = self.fixture(code)
        for arm in data['arms'].values():
            arm.update(provider='openai', usage_file='usage.json')
        path.write_text(json.dumps(data))
        integrations.install(root, 'codex')
        installed = root / '.agents/skills/month-end'
        result = subprocess.run([sys.executable, str(installed / 'scripts/benchmark.py'), str(path),
                                 '--execute', '--output', str(root / 'results')],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((root / 'results/summary.json').read_text())['measurement_failures'], 0)
        self.assertFalse(list(installed.rglob('*.pyc')))
        integrations.uninstall(root, 'codex')
        self.assertFalse(installed.exists())

    def test_replayed_usage_is_not_counted_as_new_spending(self):
        usage = {'object':'response', 'id':'same-exported-call', 'model':'local-fixture',
                 'usage': {'input_tokens':10,'output_tokens':3}}
        code = ('from pathlib import Path; '
                'Path("app.py").write_text("VALUE = 7\\n"); '
                'Path("usage.json").write_text(' + repr(json.dumps(usage)) + ')')
        root, path, data = self.fixture(code)
        for arm in data['arms'].values():
            arm.update(provider='openai', usage_file='usage.json')
        path.write_text(json.dumps(data))
        output = root / 'results'
        summary = benchmark.execute(benchmark.load_manifest(path), output)
        self.assertEqual(summary['successes'], 2)
        self.assertEqual(summary['measurement_failures'], 1)
        receipts = [json.loads(path.read_text()) for path in output.glob('*/receipt.json')]
        invalid = next(row for row in receipts if not row['usage_valid'])
        self.assertIsNone(invalid['input_tokens'])
        self.assertTrue(any('repeated provider response' in error for error in invalid['usage_errors']))

    def test_invalid_manifest_conditions_are_rejected(self):
        root, path, original = self.fixture()
        for change in [{'cache_states':['warm']}, {'repeats':False}, {'timeout_seconds':float('nan')},
                       {'arms':{'baseline':{'argv':'shell command'}}}]:
            with self.subTest(change=change):
                data = dict(original, **change)
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    benchmark.load_manifest(path)
        path.write_text('{"version": 1, "version": 1}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            benchmark.load_manifest(path)

    def test_timeout_is_recorded_as_a_failure(self):
        root, path, data = self.fixture('import time; time.sleep(3)')
        data['timeout_seconds'] = 0.05
        path.write_text(json.dumps(data))
        output = root / 'results'
        summary = benchmark.execute(benchmark.load_manifest(path), output)
        self.assertEqual(summary['successes'], 0)
        for receipt in output.glob('*/receipt.json'):
            row = json.loads(receipt.read_text())
            self.assertTrue(row['phases'][0]['timed_out'])
            self.assertNotEqual(row['candidate_exit'], 0)

    def test_changed_grader_is_not_executed(self):
        root, path, data = self.fixture()
        grader = root / 'grade.py'
        marker = root / 'altered-grader-ran'
        grader.write_text('import app; assert app.VALUE == 7\n')
        data['grading_files'] = {'grade.py': hashlib.sha256(grader.read_bytes()).hexdigest()}
        data['tasks'][0]['grader'] = ['{python}', str(grader)]
        replacement = 'from pathlib import Path; Path(' + repr(str(marker)) + ').touch()'
        code = 'from pathlib import Path; Path(' + repr(str(grader)) + ').write_text(' + repr(replacement) + ')'
        for arm in data['arms'].values():
            arm['argv'] = ['{python}', '-c', code]
        path.write_text(json.dumps(data))
        output = root / 'results'
        with self.assertRaisesRegex(ValueError, 'grading files changed'):
            benchmark.execute(benchmark.load_manifest(path), output)
        self.assertFalse(marker.exists())
        row = json.loads(next(output.glob('*/receipt.json')).read_text())
        self.assertEqual(row['grader_exit'], 125)
        self.assertEqual(row['success'], 0)

    def test_existing_output_is_never_overwritten(self):
        root, path, _ = self.fixture()
        output = root / 'results'
        output.mkdir()
        (output / 'existing').write_text('preserve')
        with self.assertRaises(FileExistsError):
            benchmark.execute(benchmark.load_manifest(path), output)
        self.assertEqual((output / 'existing').read_text(), 'preserve')

    def test_fingerprint_has_unambiguous_file_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / 'first', Path(temporary) / 'second'
            first.mkdir()
            second.mkdir()
            (first / 'a').write_bytes(b'X\0b\0Y')
            (second / 'a').write_bytes(b'X')
            (second / 'b').write_bytes(b'Y')
            self.assertNotEqual(benchmark.fingerprint(first), benchmark.fingerprint(second))
            (first / 'a').write_bytes(b'X')
            (second / 'b').unlink()
            self.assertEqual(benchmark.fingerprint(first), benchmark.fingerprint(second))
            (first / 'empty').mkdir()
            self.assertNotEqual(benchmark.fingerprint(first), benchmark.fingerprint(second))

    def test_credential_files_and_symlinks_are_not_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / '.env').write_text('private')
            with self.assertRaisesRegex(ValueError, 'credential'):
                benchmark.fingerprint(root)
            (root / '.env').unlink()
            if os.name == 'posix':
                (root / 'linked').symlink_to('/definitely-not-a-real-source-file')
                with self.assertRaisesRegex(ValueError, 'regular files'):
                    benchmark.fingerprint(root)


if __name__ == '__main__':
    unittest.main()
