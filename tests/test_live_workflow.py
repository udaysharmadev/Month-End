"""Offline invariants for the explicit bounded API workflow; no network."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('live_workflow', SCRIPTS / 'live_workflow.py')
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)
TASK = {'id': 'add-one', 'category': 'arithmetic', 'prompt': 'Add one.',
        'source': 'def solve(value):\n    return value\n'}


class WorkflowTests(unittest.TestCase):
    def test_default_is_plan_only(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'live_workflow.py')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('360', result.stdout)
        self.assertIn('no API calls', result.stdout)

    def test_unusable_sandbox_is_rejected_before_credentials_or_calls(self):
        with mock.patch.object(workflow, 'require_sandbox', side_effect=ValueError('sandbox preflight failed')), \
                mock.patch.object(workflow.getpass, 'getpass') as credentials, \
                mock.patch.object(workflow, 'Client') as client:
            with self.assertRaises(SystemExit) as stopped:
                workflow.main(['--execute', '--output', '/not-created'])
            self.assertEqual(stopped.exception.code, 2)
            credentials.assert_not_called()
            client.assert_not_called()

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('sandbox-exec'),
                         'macOS sandbox operational preflight')
    def test_sandbox_preflight_runs_and_enforces_read_isolation(self):
        workflow.require_sandbox()

    def test_workspace_excludes_grades_references_and_private_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = workflow.Workspace(temporary, TASK, {'SKILL.md': 'small skill'})
            listing = workspace.action({'tool': 'list'})['paths']
            self.assertFalse(any('grader' in name or 'suite.json' in name or 'reference_solutions' in name for name in listing))
            for path in ('../outside', '/etc/passwd', 'src/../harness_noise.py'):
                with self.assertRaises(ValueError):
                    workspace.action({'tool': 'read', 'path': path})
            target = workspace.path(workspace.target)
            target.unlink()
            target.symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):
                workspace.path(workspace.target)

    def test_exact_anchor_edit_rejects_ambiguity_and_protects_other_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = workflow.Workspace(temporary, TASK, {})
            for path, old, new in ((workspace.target, 'missing', 'x'),
                                   ('src/archive/component_0.py', 'return value', 'return 0'),
                                   (workspace.target, '# historical fixture 000', '# changed fixture 000')):
                with self.assertRaises(ValueError):
                    workspace.action({'tool': 'replace', 'path': path, 'old': old, 'new': new})
            workspace.action({'tool': 'replace', 'path': workspace.target, 'old': 'return value', 'new': 'return value + 1'})
            self.assertTrue(workspace.path(workspace.target).read_text().startswith(workspace.prefix))
            self.assertIn('return value + 1', workspace.path(workspace.target).read_text())
            with self.assertRaises(ValueError):
                workspace.action({'tool': 'replace', 'path': workspace.target, 'old': 'return value + 1',
                                  'new': 'return open("/etc/passwd").read()'})

    def test_import_aliases_cannot_bypass_execution_and_file_guards(self):
        for imported in ('from io import FileIO as Reader',
                         'from io import open_code as Reader',
                         'from posixpath import os as system',
                         'from pathlib import _os as system',
                         'from pathlib import Path as Pure',
                         'import re._compiler as private'):
            with self.subTest(imported=imported), self.assertRaises(ValueError):
                workflow.validate_source(imported + '\ndef solve(value):\n    return value\n')
        workflow.validate_source('from pathlib import PurePosixPath as Pure\n'
                                 'def solve(value):\n    return str(Pure(value))\n')
        for source in ('import pathlib\ndef solve(value): return str(pathlib.Path(value))',
                       'import pathlib\ndef solve(value): return pathlib._os.getcwd()',
                       'import io\ndef solve(value): return io.open_code(value).read()'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                workflow.validate_source(source)

    def test_unicode_separators_remain_inside_exact_source_lines(self):
        task = {**TASK, 'source': 'def solve(value):\n    return "a\u2028b\u0085c"\n'}
        with tempfile.TemporaryDirectory() as temporary:
            workspace = workflow.Workspace(temporary, task, {})
            result = workspace.action({'tool': 'read', 'path': workspace.target, 'start': 242, 'end': 242})
            self.assertEqual(result['output'], '242:     return "a\u2028b\u0085c"')
            search = workspace.action({'tool': 'search', 'text': 'b\u0085c'})
            self.assertEqual(search['output'], workspace.target + ':242:    return "a\u2028b\u0085c"')

    def test_locate_paths_are_usable_and_source_reads_are_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = workflow.Workspace(temporary, TASK, {})
            found = workspace.action({'tool': 'locate', 'text': 'def solve'})
            self.assertEqual(found['exit'], 0)
            self.assertIn(workspace.target, found['stdout'].splitlines())
            selected = workspace.action({'tool': 'read', 'path': workspace.target, 'start': 241, 'end': 242})
            self.assertEqual(selected['output'], '241: def solve(value):\n242:     return value')

    def test_tool_subprocess_receives_minimal_environment(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict('os.environ', {'FAKE_API_KEY': 'secret-value'}):
            result = workflow.bounded_subprocess([sys.executable, '-c',
                        'import os; print(os.environ.get("FAKE_API_KEY", "absent"))'], Path(temporary))
            self.assertEqual(result['exit'], 0)
            self.assertEqual(result['stdout'].strip(), 'absent')

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('sandbox-exec'),
                         'macOS sandbox read isolation check')
    def test_os_sandbox_denies_reads_outside_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary) / 'outside-private.txt'
            outside.write_text('PRIVATE_SENTINEL_DO_NOT_EXPOSE')
            workspace = Path(temporary) / 'workspace'
            workspace.mkdir()
            code = 'from pathlib import Path; print(Path(' + repr(str(outside)) + ').read_text())'
            result = workflow.bounded_subprocess([sys.executable, '-c', code], workspace)
            self.assertNotEqual(result['exit'], 0)
            self.assertNotIn('PRIVATE_SENTINEL_DO_NOT_EXPOSE', result['stdout'])
            self.assertNotIn('PRIVATE_SENTINEL_DO_NOT_EXPOSE', result['stderr'])

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('sandbox-exec'),
                         'candidate grading requires macOS isolation')
    def test_scripted_tool_workflow_finishes_with_full_independent_grade(self):
        task = json.loads(workflow.SUITE.read_text())['tasks'][0]
        solution = json.loads((workflow.SUITE.parent / 'reference_solutions.json').read_text())[task['id']]
        target = 'src/' + task['id'].replace('-', '_') + '.py'
        actions = [{'tool': 'list'}, {'tool': 'locate', 'text': 'def solve'},
                   {'tool': 'symbol', 'path': target, 'name': 'solve'},
                   {'tool': 'replace', 'path': target, 'old': task['source'], 'new': solution},
                   {'tool': 'test', 'mode': 'quiet'}, {'tool': 'finish'}]
        client = mock.Mock()
        client.sanitize.side_effect = lambda value: value
        client.with_retry.side_effect = [({'modelVersion': 'gemini-test',
            'usageMetadata': {'promptTokenCount': 1, 'candidatesTokenCount': 2, 'totalTokenCount': 3},
            'candidates': [{'finishReason': 'STOP', 'content': {'role': 'model',
                           'parts': [{'text': json.dumps(action)}]}}]}, []) for action in actions]
        with tempfile.TemporaryDirectory() as temporary:
            result = workflow.trial(client, 'gemini-test', task, 'month-end', 1,
                                    Path(temporary), {'SKILL.md': 'small skill'})
        self.assertTrue(result['success'])
        self.assertEqual(result['grade']['exit'], 0)
        self.assertEqual(result['tools'][-2]['result']['visible_cases']['exit'], 0)
        self.assertEqual(len(result['responses']), len(actions))
        self.assertTrue(all(receipt['received'] for receipt in result['responses']))
        serialized = json.dumps(result)
        self.assertNotIn(str(workflow.ROOT), serialized)
        self.assertNotIn('/private/var/folders/', serialized)
        group = workflow.summarize([result])['gemini-test/month-end']
        self.assertEqual(group['metrics']['total_tokens'], len(actions) * 3)

    def test_produced_summary_can_be_consumed_by_public_analysis(self):
        import analyze_workflow

        def offline_trial(client, model, task, arm, repeat, output, skill_files):
            return {'model': model, 'task_id': task['id'], 'arm': arm, 'repeat': repeat,
                    'success': False, 'anchor_preserved': True, 'tools': [], 'responses': [],
                    'service_failure': True, 'wall_seconds': 0}

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'run'
            client = mock.Mock()
            client.sanitize.side_effect = lambda value: value
            with mock.patch.object(workflow, 'require_sandbox'), \
                    mock.patch.object(workflow.getpass, 'getpass', return_value='synthetic-only'), \
                    mock.patch.object(workflow, 'Client', return_value=client), \
                    mock.patch.object(workflow.subprocess, 'run',
                                      return_value=subprocess.CompletedProcess(['git'], 1, stdout='', stderr='no git')), \
                    mock.patch.object(workflow, 'trial', side_effect=offline_trial):
                self.assertEqual(workflow.main(['--execute', '--output', str(output), '--task-limit', '1',
                                               '--repeats', '1', '--workers', '1', '--models', 'gemini-test']), 0)
            summary = json.loads((output / 'summary.json').read_text())
            result = analyze_workflow.analyze(summary)
            self.assertEqual(result['attempted_pairs'], 1)
            self.assertTrue(result['study_complete'])
            self.assertEqual(result['overall']['accepted_trials'], 0)
            self.assertNotIn('repo_commit', result['protocol'])

    def test_received_response_with_missing_usage_is_counted_but_total_unknown(self):
        metric = dict(input_tokens=10, output_tokens=2, reasoning_tokens=None,
                      cache_read_tokens=None, total_tokens=12)
        records = [{'model': 'm', 'arm': 'baseline', 'success': False, 'tools': [],
                    'anchor_preserved': True, 'responses': [
                        {'received': True, 'usage': metric, 'http_failures': []},
                        {'received': True, 'usage': None, 'usage_error': 'missing metadata', 'http_failures': []}]}]
        group = workflow.summarize(records)['m/baseline']
        self.assertEqual(group['received_responses'], 2)
        self.assertEqual(group['usage_bearing_responses'], 1)
        self.assertTrue(all(value is None for value in group['metrics'].values()))
        self.assertTrue(group['unknown_failure_usage'])

    def test_high_precision_decimal_uses_required_runtime_dependency(self):
        code = ('from decimal import Decimal, localcontext\n'
                'with localcontext() as context:\n'
                '    context.prec=10000\n'
                '    print((Decimal(1)/3*100).quantize(Decimal(".01")))\n')
        with tempfile.TemporaryDirectory() as temporary:
            result = workflow.bounded_subprocess([sys.executable, '-c', code], Path(temporary))
        self.assertEqual(result['exit'], 0, result)
        self.assertEqual(result['stdout'].strip(), '33.33')

    def test_nonzero_and_timeout_are_never_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = workflow.bounded_subprocess([sys.executable, '-c', 'raise SystemExit(7)'], Path(temporary))
            self.assertEqual(result['exit'], 7)
            timed = workflow.bounded_subprocess([sys.executable, '-c', 'import time; time.sleep(10)'],
                                                Path(temporary), timeout=0.05)
            self.assertEqual(timed['exit'], 124)

    def test_oversized_tool_output_retention_is_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = workflow.bounded_subprocess([sys.executable, '-c', 'print("x" * 2000000)'], Path(temporary))
        self.assertEqual(result['exit'], 0)
        self.assertIn('showing tail', result['stdout'])
        self.assertLess(len(result['stdout'].encode()), workflow.MAX_TOOL_BYTES + 200)

    def test_actions_require_complete_json_objects(self):
        def response(text, finish='STOP'):
            return {'candidates': [{'finishReason': finish, 'content': {'parts': [{'text': text}]}}]}
        self.assertEqual(workflow.parse_action(response('{"tool":"finish"}')), {'tool': 'finish'})
        for candidate in (response('[]'), response('not JSON'), response('{}'), response('{', 'MAX_TOKENS')):
            with self.assertRaises(ValueError):
                workflow.parse_action(candidate)

    def test_failed_response_usage_is_retained_and_missing_cache_unknown(self):
        metric = dict(input_tokens=10, output_tokens=2, reasoning_tokens=None, cache_read_tokens=None, total_tokens=12)
        records = [{'task_id': 'x', 'model': 'm', 'arm': 'baseline', 'success': False,
                    'tools': [], 'anchor_preserved': True,
                    'responses': [{'usage': metric, 'http_failures': [{'http_status': 429}]},
                                  {'usage': metric, 'http_failures': []}]}]
        group = workflow.summarize(records)['m/baseline']
        self.assertEqual(group['metrics']['total_tokens'], 24)
        self.assertIsNone(group['metrics']['cache_read_tokens'])
        self.assertEqual(group['accepted'], 0)
        self.assertTrue(group['unknown_failure_usage'])
        json.dumps(group)


if __name__ == '__main__':
    unittest.main()
