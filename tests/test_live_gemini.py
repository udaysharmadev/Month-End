"""Offline tests for the explicit Gemini API pilot; no credentials or network."""
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/live_gemini.py'
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location('live_gemini', SCRIPT)
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class LiveGeminiTests(unittest.TestCase):
    def test_default_makes_no_calls(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('no API calls', result.stdout)

    def test_execution_requires_isolation_before_credentials(self):
        with mock.patch.object(live, 'require_sandbox', side_effect=ValueError('sandbox unavailable')), \
                mock.patch.object(live.getpass, 'getpass') as credentials, \
                mock.patch.object(live, 'Client') as client:
            with self.assertRaises(SystemExit) as stopped:
                live.main(['--execute', '--output', '/not-created'])
            self.assertEqual(stopped.exception.code, 2)
            credentials.assert_not_called()
            client.assert_not_called()

    def test_unsafe_import_aliases_and_annotation_evaluators_are_rejected(self):
        for imported, expression in [
            ('from io import FileIO as Reader', 'Reader(value).read()'),
            ('from io import open_code as Reader', 'Reader(value).read()'),
            ('from collections import __builtins__ as B', 'B["open"](value).read()'),
            ('from pathlib import *', 'Path(value).exists()'),
            ('from typing import get_type_hints as hints', 'hints(value)'),
            ('import re._compiler as private', 'private.compile(value)'),
        ]:
            with self.subTest(imported=imported), self.assertRaises(ValueError):
                live.extract_code(self.response(imported + '\ndef solve(value): return ' + expression))

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('sandbox-exec'),
                         'generated code requires macOS isolation')
    def test_actual_candidate_grade_uses_read_isolation_and_bounded_output(self):
        grader = SCRIPT.parent.parent / 'benchmarks/local/grade.py'
        code = 'import csv,io\ndef solve(text): return list(csv.reader(io.StringIO(text)))\n'
        result = live.grade_code(code, 'quoted-csv', grader)
        self.assertEqual(result['exit'], 0, result)
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary) / 'synthetic.txt'
            outside.write_text('PRIVATE_SYNTHETIC_SENTINEL')
            # Bypass the AST heuristic deliberately to check the OS boundary itself.
            code = 'def solve(text): return open(' + repr(str(outside)) + ').read()\n'
            result = live.grade_code(code, 'quoted-csv', grader)
            self.assertNotEqual(result['exit'], 0)
            self.assertIn('PermissionError', result['stderr'])
            self.assertNotIn('PRIVATE_SYNTHETIC_SENTINEL', json.dumps(result))

    def test_candidate_grade_refuses_an_unsupported_platform(self):
        with mock.patch('candidate_sandbox.sys.platform', 'linux'):
            with self.assertRaisesRegex(ValueError, 'requires the macOS sandbox'):
                live.grade_code('def solve(value): return value\n', 'unused', SCRIPT)

    def test_secret_only_in_header_not_url_or_body(self):
        captured = []
        def opener(request, timeout):
            captured.append(request)
            return io.BytesIO(b'{"models":[]}')
        client = live.Client('synthetic-auth-value', opener=opener)
        client.models()
        self.assertNotIn('synthetic-auth-value', captured[0].full_url)
        self.assertIsNone(captured[0].data)
        self.assertEqual(captured[0].get_header('X-goog-api-key'), 'synthetic-auth-value')

    def test_transient_retries_wait_and_preserve_all_failure_receipts(self):
        waits = []
        client = live.Client('test-only-secret', sleeper=waits.append)
        with mock.patch.object(client, 'request', side_effect=[live.APIError(429, 'quota', 15),
                                                             live.APIError(503, 'busy'), {'ok': True}]):
            response, failures = client.with_retry('models', cooldown=10)
        self.assertEqual(response, {'ok': True})
        self.assertEqual(waits, [15, 20])
        self.assertEqual(len(failures), 2)
        self.assertTrue(all(record['usage'] is None for record in failures))

    def test_permanent_errors_and_long_retry_after_do_not_loop(self):
        for error in (live.APIError(400, 'invalid'), live.APIError(403, 'access'),
                      live.APIError(429, 'wait later', 120)):
            with self.subTest(status=error.status):
                client = live.Client('test-only-secret', sleeper=mock.Mock())
                with mock.patch.object(client, 'request', side_effect=error) as request:
                    response, failures = client.with_retry('models')
                self.assertIsNone(response)
                self.assertEqual(len(failures), 1)
                request.assert_called_once()
                client._sleep.assert_not_called()

    def test_http_messages_cannot_echo_key(self):
        key = 'synthetic-sensitive-value'
        body = json.dumps({'error': {'message': 'Invalid key ' + key}}).encode()
        def opener(*args, **kwargs):
            raise urllib.error.HTTPError('https://example.invalid', 403, 'Forbidden', {}, io.BytesIO(body))
        client = live.Client(key, opener=opener)
        response, failures = client.with_retry('models')
        self.assertIsNone(response)
        self.assertNotIn(key, json.dumps(failures))
        self.assertIn('[REDACTED]', failures[0]['message'])

    def test_google_retry_info_is_honored_without_retrying_early(self):
        body = json.dumps({'error': {'message': 'busy', 'details': [
            {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '45s'}]}}).encode()
        def opener(*args, **kwargs):
            raise urllib.error.HTTPError('https://example.invalid', 429, 'Busy', {}, io.BytesIO(body))
        client = live.Client('test-only-secret', opener=opener)
        with self.assertRaises(live.APIError) as caught:
            client.request('models')
        self.assertEqual(caught.exception.retry_after, 45)

    def response(self, source, finish='STOP'):
        return {'candidates': [{'finishReason': finish, 'content': {'parts': [{'text': source}]}}]}

    def test_extracts_complete_source_but_rejects_unsafe_and_truncated_programs(self):
        source = 'def solve(value):\n    return value + 1\n'
        self.assertEqual(live.extract_code(self.response(source)), source)
        self.assertEqual(live.extract_code(self.response('```python\n' + source + '```')), source)
        for response in (self.response(source, 'MAX_TOKENS'), self.response('import os\ndef solve(): pass'),
                         self.response('def solve(): return open("/tmp/x").read()'),
                         self.response('def solve(): return (1).__class__'), self.response('pass')):
            with self.subTest(response=response), self.assertRaises(ValueError):
                live.extract_code(response)

    def test_prompt_pair_changes_only_skill_instructions(self):
        task = {'prompt': 'Return the input unchanged'}
        baseline = live.prompt_for(task, 'def solve(): pass', 'baseline', 'skill rules')
        optimized = live.prompt_for(task, 'def solve(): pass', 'month-end', 'skill rules')
        self.assertTrue(optimized.endswith(baseline))
        self.assertNotIn('skill rules', baseline)

    def test_pure_path_and_copy_imports_are_permitted_but_file_reads_are_not(self):
        source = 'from pathlib import PurePosixPath\nfrom copy import deepcopy\ndef solve(x):\n    return str(PurePosixPath(x))\n'
        self.assertEqual(live.extract_code(self.response(source)), source)
        with self.assertRaises(ValueError):
            live.extract_code(self.response('from pathlib import Path\ndef solve(x): return Path(x).read_text()'))

    def test_no_response_usage_is_unknown_not_zero(self):
        records = [{'model': 'm', 'arm': 'baseline', 'success': False,
                    'generations': [{'usage': None, 'http_failures': [{'http_status': 403}]}]}]
        metrics = live.aggregate(records)['m']['baseline']['metrics']
        self.assertTrue(all(value is None for value in metrics.values()))

    def test_failed_generation_usage_is_included_and_unknown_cache_remains_unknown(self):
        def usage(n, cache=None):
            return {'input_tokens': n, 'output_tokens': n, 'reasoning_tokens': n,
                    'cache_read_tokens': cache, 'total_tokens': n * 3}
        records = [{'model': 'm', 'arm': 'month-end', 'success': True,
                    'generations': [{'success': False, 'usage': usage(5), 'http_failures': []},
                                    {'success': True, 'usage': usage(7), 'http_failures': [{'http_status': 429}]}]}]
        arm = live.aggregate(records)['m']['month-end']
        self.assertEqual(arm['first_pass_successes'], 0)
        self.assertEqual(arm['accepted_successes'], 1)
        self.assertEqual(arm['metrics']['input_tokens'], 12)
        self.assertIsNone(arm['metrics']['cache_read_tokens'])
        self.assertTrue(arm['unknown_failure_usage'])

    def test_generation_limits_are_model_specific_and_explicit(self):
        self.assertEqual(live.generation_config('gemini-3.8-flash')['thinkingConfig'], {'thinkingLevel': 'LOW'})
        self.assertEqual(live.generation_config('gemini-2.5-flash')['thinkingConfig'], {'thinkingBudget': 1024})

    def test_foreign_endpoints_cannot_receive_the_credential(self):
        opener = mock.Mock()
        client = live.Client('test-only-secret', opener=opener)
        for endpoint in ('https://other.example/models', '../models', 'models/x:generateContent?key=anything'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                client.request(endpoint)
        opener.assert_not_called()

    def test_redirects_are_rejected_instead_of_forwarding_authentication(self):
        client = live.Client('test-only-secret')
        handler = next(handler for handler in client._open.__self__.handlers
                       if isinstance(handler, live.NoRedirect))
        self.assertIsNone(handler.redirect_request(None, None, 302, 'Found', {}, 'https://other.example'))

    def test_public_package_rejects_gemini_credentials(self):
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            from build_release import source_files
        except ImportError:
            self.skipTest('maintainer YAML dependency is unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'docs').mkdir()
            for prefix, count in (('AQ.', 45), ('AIza', 35)):
                (root / 'docs' / 'unsafe.md').write_text(prefix + 'x' * count)
                with self.assertRaisesRegex(ValueError, 'credential'):
                    source_files(root)


if __name__ == '__main__':
    unittest.main()
