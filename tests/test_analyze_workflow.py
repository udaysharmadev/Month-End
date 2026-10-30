"""Synthetic-only regression data for the private-to-public workflow exporter."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'analyze_workflow.py'
spec = importlib.util.spec_from_file_location('analyze_workflow', SCRIPT)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
MODEL = 'gemini-test-model'


def response(tokens, received=True, failures=0):
    usage = None if tokens is None else {metric: tokens for metric in analysis.METRICS}
    return {'received': received, 'usage': usage, 'model_version': MODEL,
            'http_failures': [{'http_status': 503, 'message': 'PRIVATE_PROVIDER_ERROR'} for _ in range(failures)]}


def record(task='one', repeat=1, arm='baseline', success=True, responses=None):
    return {'model': MODEL, 'task_id': task, 'repeat': repeat, 'arm': arm,
            'success': success, 'anchor_preserved': True,
            'responses': responses if responses is not None else [response(10)],
            'tools': [{'action': {'tool': 'test', 'mode': 'receipt', 'path': '/PRIVATE/PATH'},
                       'result': {'stdout': 'PRIVATE_MODEL_TOOL_TEXT'}}],
            'wall_seconds': 1.5, 'billed_cost_usd': 'PRIVATE_INVOICE_TEXT'}


def fixture(tasks=('one',), repeats=1):
    protocol = {field: 'a' * 64 for field in analysis.HASHES}
    protocol.update({'models': [MODEL], 'tasks': list(tasks), 'repeats': repeats,
                     'seed': 123, 'max_turns': 12, 'workers': 4,
                     'fixture': '/PRIVATE/HOST/PATH', 'request_id': 'PRIVATE_REQUEST_ID'})
    return {'protocol': protocol,
            'records': [record(task, repeat, arm) for task in tasks for repeat in range(1, repeats + 1)
                        for arm in analysis.ARMS], 'deferred_pairs': [],
            'raw_model_content': 'PRIVATE_RAW_MODEL_TEXT'}


class WorkflowAnalysisTests(unittest.TestCase):
    def test_failed_trial_and_all_received_attempt_usage_remain_in_ratios(self):
        data = fixture(('one', 'two'))
        data['records'][0] = record(success=False, responses=[response(10), response(20)])
        result = analysis.analyze(data)
        baseline = result['by_model'][MODEL]['arms']['baseline']
        comparison = result['by_model'][MODEL]['paired_comparison']['point']
        self.assertEqual(baseline['attempted_trials'], 2)
        self.assertEqual(baseline['accepted_trials'], 1)
        self.assertEqual(baseline['reported_metrics']['total_tokens'], 40)
        self.assertEqual(comparison['baseline_total_tokens_per_accepted_solve'], 40)
        self.assertEqual(comparison['month_end_total_tokens_per_accepted_solve'], 10)
        self.assertEqual(comparison['total_tokens_per_accepted_solve_ratio'], .25)
        self.assertEqual(comparison['success_rate_difference'], .5)

    def test_received_missing_usage_propagates_unknown_instead_of_zero(self):
        data = fixture()
        data['records'][0]['responses'].append(response(None))
        result = analysis.analyze(data)
        baseline = result['by_model'][MODEL]['arms']['baseline']
        self.assertEqual(baseline['received_responses'], 2)
        self.assertEqual(baseline['usage_bearing_responses'], 1)
        self.assertTrue(baseline['unknown_response_usage'])
        self.assertTrue(all(value is None for value in baseline['reported_metrics'].values()))
        self.assertEqual(baseline['known_reported_metric_subtotals']['total_tokens'], 10)
        self.assertEqual(baseline['known_metric_response_counts']['total_tokens'], 1)
        self.assertIsNone(result['by_model'][MODEL]['paired_comparison']['point']
                          ['total_tokens_per_accepted_solve_difference'])

    def test_transient_failure_usage_withholds_complete_ratio_without_erasing_reported_tokens(self):
        data = fixture()
        data['records'][0]['responses'] = [response(25, failures=1)]
        result = analysis.analyze(data)
        baseline = result['by_model'][MODEL]['arms']['baseline']
        self.assertEqual(baseline['reported_metrics']['total_tokens'], 25)
        self.assertEqual(baseline['http_attempts'], 2)
        self.assertEqual(baseline['http_failures'], 1)
        self.assertTrue(baseline['unknown_failure_usage'])
        self.assertFalse(baseline['total_tokens_complete'])
        self.assertIsNone(result['by_model'][MODEL]['paired_comparison']['point']
                          ['baseline_total_tokens_per_accepted_solve'])

    def test_service_no_response_is_in_all_attempted_but_separate_received_subgroup(self):
        data = fixture(('one', 'two'))
        data['records'][0] = record(success=False, responses=[response(None, received=False, failures=3)])
        data['records'][0]['service_failure'] = True
        baseline = analysis.analyze(data)['by_model'][MODEL]['arms']['baseline']
        self.assertEqual(baseline['attempted_trials'], 2)
        self.assertEqual(baseline['success_rate_all_attempted'], .5)
        self.assertEqual(baseline['received_trials'], 1)
        self.assertEqual(baseline['success_rate_received_trials'], 1)
        self.assertEqual(baseline['service_failed_trials'], 1)

    def test_paired_repeats_are_resampled_at_original_task_level(self):
        once = fixture(('one', 'two', 'three'))
        for row in once['records']:
            row['success'] = row['arm'] == 'baseline' or row['task_id'] != 'one'
        repeated = fixture(('one', 'two', 'three'), repeats=3)
        for row in repeated['records']:
            row['success'] = row['arm'] == 'baseline' or row['task_id'] != 'one'
        first = analysis.analyze(once)['by_model'][MODEL]['paired_comparison']
        many = analysis.analyze(repeated)['by_model'][MODEL]['paired_comparison']
        self.assertEqual(many['original_task_clusters'], 3)
        self.assertEqual(many['paired_trials'], 9)
        self.assertEqual(many['bootstrap_draws'], 2000)
        self.assertEqual(many['success_rate_difference_ci95'], first['success_rate_difference_ci95'])
        self.assertEqual(many['total_tokens_per_accepted_solve_difference_ci95'],
                         first['total_tokens_per_accepted_solve_difference_ci95'])
        self.assertGreater(many['undefined_token_ratio_draws'], 0)
        self.assertIsNone(many['total_tokens_per_accepted_solve_difference_ci95'])

    def test_sanitized_output_uses_only_allowlisted_fields_and_numeric_tool_choices(self):
        data = fixture()
        data['records'][0]['responses'][0].update({'request_id': 'PRIVATE_REQUEST_ID',
                                                  'usage_error': 'PRIVATE_PROVIDER_ERROR'})
        public = analysis.analyze(data)
        rendered = json.dumps(public)
        self.assertNotIn('PRIVATE', rendered)
        self.assertNotIn('/PATH', rendered)
        self.assertEqual(public['overall']['test_mode_counts'], {'receipt': 2})
        self.assertEqual(public['overall']['tool_choice_counts'], {'test': 2})
        self.assertIsNone(public['billed_cost_usd'])
        self.assertEqual(public['cache_state'], 'uncontrolled')

    def test_duplicate_and_missing_pairs_are_rejected(self):
        for change in ('duplicate', 'one-arm', 'both-arms'):
            data = fixture(('one', 'two'))
            if change == 'duplicate':
                data['records'].append(copy.deepcopy(data['records'][0]))
            elif change == 'one-arm':
                data['records'].pop()
            else:
                del data['records'][-2:]
            with self.subTest(change=change), self.assertRaises(ValueError):
                analysis.analyze(data)

    def test_declared_deferred_pairs_report_incomplete_study_without_cherry_picking(self):
        data = fixture(('one', 'two'), repeats=2)
        data['records'] = [row for row in data['records'] if not (row['task_id'] == 'two' and row['repeat'] == 2)]
        data['deferred_pairs'] = [{'model': MODEL, 'task_id': 'two', 'repeat': 2,
                                  'reason': 'PRIVATE_PROVIDER_ERROR'}]
        result = analysis.analyze(data)
        self.assertFalse(result['study_complete'])
        self.assertEqual(result['planned_pairs'], 4)
        self.assertEqual(result['attempted_pairs'], 3)
        self.assertEqual(result['deferred_pairs'], 1)
        self.assertEqual(result['overall']['attempted_trials'], 6)
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_legacy_received_inference_and_missing_cache_remain_explicit(self):
        data = fixture()
        del data['records'][0]['responses'][0]['received']
        data['records'][0]['responses'][0]['usage']['cache_read_tokens'] = None
        result = analysis.analyze(data)
        baseline = result['by_model'][MODEL]['arms']['baseline']
        self.assertEqual(baseline['received_responses'], 1)
        self.assertIsNone(baseline['reported_metrics']['cache_read_tokens'])
        self.assertTrue(baseline['total_tokens_complete'])

    def test_cli_refuses_to_overwrite_public_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'private.json'
            output = Path(temporary) / 'public.json'
            source.write_text(json.dumps(fixture()))
            common = [sys.executable, str(SCRIPT), str(source), '--output', str(output)]
            first = subprocess.run(common, capture_output=True, text=True)
            before = output.read_bytes()
            second = subprocess.run(common, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0)
            self.assertEqual(second.returncode, 1)
            self.assertEqual(output.read_bytes(), before)
            self.assertNotIn('PRIVATE', output.read_text())


if __name__ == '__main__':
    unittest.main()
