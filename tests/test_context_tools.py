"""End-to-end advanced retrieval, profiles, and raw-log recovery checks."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'skills' / 'month-end' / 'scripts' / 'monthend.py'


class ContextToolTests(unittest.TestCase):
    def call(self, *arguments, text=True):
        return subprocess.run([sys.executable, str(CLI), *arguments], capture_output=True,
                              text=text, timeout=20)

    def test_ast_symbol_preserves_decorators_and_complete_method(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'source.py'
            source.write_text('class Example:\n    @staticmethod\n    def work(value):\n'
                              '        """doc"""\n        return value + 1\n\n'
                              'def unrelated():\n    return 4\n')
            result = self.call('symbol', str(source), 'Example.work')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('@staticmethod', result.stdout)
            self.assertIn('return value + 1', result.stdout)
            self.assertNotIn('unrelated', result.stdout)
            self.assertIn('exact=true', result.stdout)
            result = self.call('symbol', str(source), 'Example.work', '--max-lines', '1')
            self.assertEqual(result.returncode, 3)
            self.assertNotIn('return value', result.stdout)

    def test_symbol_ambiguity_and_invalid_language_are_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'source.py'
            source.write_text('class A:\n    def same(self): pass\n'
                              'class B:\n    def same(self): pass\n')
            result = self.call('symbol', str(source), 'same')
            self.assertEqual(result.returncode, 2)
            self.assertIn('ambiguous', result.stderr)
            result = self.call('symbol', str(source), 'missing')
            self.assertEqual(result.returncode, 1)
            source = source.with_suffix('.ts')
            source.write_text('function same() {}')
            result = self.call('symbol', str(source), 'same')
            self.assertEqual(result.returncode, 2)
            self.assertIn('LSP', result.stderr)

    def test_index_round_trip_hash_and_selected_line_ranges(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / 'output.log'
            index = Path(td) / 'output.index.json'
            raw = b'first\nERROR: middle\nlast\n'
            result = self.call('run', '--log', str(log), '--log-index', str(index), '--',
                               sys.executable, '-c', 'import sys; sys.stdout.buffer.write(' + repr(raw) + ')')
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(index.read_text())
            self.assertEqual(receipt['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(receipt['raw_bytes'], len(raw))
            for entry in receipt['displayed_ranges']:
                selected = self.call('log-read', str(index), '--log', str(log),
                                     '--line', str(entry['line']), text=False)
                self.assertEqual(selected.returncode, 0, selected.stderr)
                self.assertEqual(selected.stdout, raw[entry['start_byte']:entry['end_byte']])
            log.write_bytes(raw + b'tampered')
            selected = self.call('log-read', str(index), '--log', str(log), '--line', '2')
            self.assertEqual(selected.returncode, 2)
            self.assertIn('integrity', selected.stderr)
            self.assertEqual(selected.stdout, '')

    def test_index_requires_log_and_refuses_overwriting_existing_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / 'ran'
            code = 'from pathlib import Path; Path(' + repr(str(marker)) + ').touch()'
            result = self.call('run', '--log-index', str(root / 'index.json'), '--',
                               sys.executable, '-c', code)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(marker.exists())
            log = root / 'existing.log'
            log.write_bytes(b'keep this evidence')
            result = self.call('run', '--log', str(log), '--', sys.executable, '-c', code)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(log.read_bytes(), b'keep this evidence')
            self.assertFalse(marker.exists())

    def test_binary_log_recovery_needs_explicit_raw_mode_and_budget(self):
        with tempfile.TemporaryDirectory() as td:
            log, index = Path(td) / 'raw.log', Path(td) / 'index.json'
            raw = b'\x00\xff' + b'x' * 200
            result = self.call('run', '--log', str(log), '--log-index', str(index), '--',
                               sys.executable, '-c', 'import sys; sys.stdout.buffer.write(' + repr(raw) + ')')
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.call('log-read', str(index), '--log', str(log), '--end-byte', '202')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            result = self.call('log-read', str(index), '--log', str(log), '--end-byte', '202', '--raw', text=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, raw)
            result = self.call('log-read', str(index), '--log', str(log), '--end-byte', '202', '--max-bytes', '128')
            self.assertEqual(result.returncode, 3)

    def test_adaptive_small_output_remains_complete(self):
        result = self.call('run', '--adaptive', '--', sys.executable, '-c',
                           '[print(str(i)) for i in range(60)]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('0\n1\n2\n', result.stdout)
        self.assertIn('58\n59\n', result.stdout)
        self.assertIn('excerpt=false', result.stdout)
        self.assertIn('filter=passthrough', result.stdout)

    def test_profiles_and_custom_rules_retain_diagnostics(self):
        for profile, diagnostic in [('pytest', 'FAILED test_demo.py::test_case'),
                                    ('vitest', '❯ test/demo.test.ts > fails'),
                                    ('npm', 'npm ERR! lifecycle'),
                                    ('cargo', 'error[E0308]: mismatched types'),
                                    ('go', '--- FAIL: TestCase (0.00s)'),
                                    ('ci', '::error file=app.py,line=1::bad')]:
            with self.subTest(profile=profile):
                code = 'print("before\\n" * 200); print(' + repr(diagnostic) + '); print("noise\\n" * 1000)'
                result = self.call('run', '--profile', profile, '--', sys.executable, '-c', code)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(diagnostic, result.stdout)
                self.assertIn('profile=' + profile, result.stdout)
        with tempfile.TemporaryDirectory() as td:
            rules = Path(td) / 'rules.json'
            rules.write_text(json.dumps({'important': ['^CHECKPOINT-ALERT'], 'summary': ['^TOTAL:']}))
            result = self.call('run', '--profile-config', str(rules), '--', sys.executable,
                               '-c', 'print("before\\n" * 200); print("CHECKPOINT-ALERT: keep"); print("noise\\n" * 1000)')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('CHECKPOINT-ALERT: keep', result.stdout)


if __name__ == '__main__':
    unittest.main()
