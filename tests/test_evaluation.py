"""Checks for matched experimental conditions and the primary cost outcome."""
import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills' / 'month-end' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import compare_runs


class EvaluationTests(unittest.TestCase):
    def ledger(self, rows, fields=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'runs.csv'
        fields = fields or ['task_id', 'arm', 'success', 'cost_usd',
                            'repo_commit', 'model', 'cache_state']
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def pair(self, task='task-1', **changes):
        baseline = dict(task_id=task, arm='baseline', success=1, cost_usd=2,
                        repo_commit='a' * 40, model='frozen-model', cache_state='cold')
        optimized = dict(baseline, arm='month-end', cost_usd=1)
        optimized.update(changes)
        return [baseline, optimized]

    def test_strict_metadata_accepts_matching_conditions(self):
        path = self.ledger(self.pair())
        rows, incomplete = compare_runs.load(path, require_metadata=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1]['model'], 'frozen-model')
        self.assertFalse(incomplete)

    def test_rejects_mismatched_conditions(self):
        for field, value in [('repo_commit', 'b' * 40), ('model', 'different-model'),
                             ('cache_state', 'warm')]:
            with self.subTest(field=field):
                path = self.ledger(self.pair(**{field: value}))
                with self.assertRaisesRegex(ValueError, field):
                    compare_runs.load(path)

    def test_partial_blank_or_unknown_metadata_is_rejected(self):
        for changes in ({'model': ''}, {'repo_commit': 'main'}, {'cache_state': 'unknown'}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    compare_runs.load(self.ledger(self.pair(**changes)))
        partial = [{key: value for key, value in row.items() if key != 'model'}
                   for row in self.pair()]
        with self.assertRaisesRegex(ValueError, 'metadata'):
            compare_runs.load(self.ledger(partial, ['task_id', 'arm', 'success', 'cost_usd',
                                                  'repo_commit', 'cache_state']))

    def test_legacy_ledger_is_labeled_and_strict_mode_rejects_it(self):
        path = self.ledger([dict(task_id='t', arm=arm, success=1)
                            for arm in ('baseline', 'month-end')],
                           ['task_id', 'arm', 'success'])
        result = subprocess.run([sys.executable, str(SCRIPTS / 'compare_runs.py'), str(path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('metadata=UNAVAILABLE', result.stdout)
        result = subprocess.run([sys.executable, str(SCRIPTS / 'compare_runs.py'),
                                 '--require-metadata', str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('metadata', result.stderr)

    def test_different_cache_conditions_are_reported_separately(self):
        rows = self.pair('cold-task')
        rows += [dict(row, cache_state='warm') for row in self.pair('warm-task')]
        path = self.ledger(rows)
        result = subprocess.run([sys.executable, str(SCRIPTS / 'compare_runs.py'),
                                 '--require-metadata', str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('STRATUM model=frozen-model cache_state=cold pairs=1', result.stdout)
        self.assertIn('STRATUM model=frozen-model cache_state=warm pairs=1', result.stdout)
        self.assertNotIn('baseline: tasks=2', result.stdout)

    def test_primary_delta_includes_spending_on_failed_attempts(self):
        records = self.pair('a') + self.pair('b', success=0) + self.pair('c')
        rows, _ = compare_runs.load(self.ledger(records))
        estimate, interval, undefined = compare_runs.cost_per_success_delta(rows, iterations=200)
        # baseline: 6 / 3 = 2; optimized: 3 / 2 = 1.5.
        self.assertAlmostEqual(estimate, -0.5)
        self.assertIsNone(interval)  # Some resamples contain only failed optimized tasks.
        self.assertGreater(undefined, 0)

    def test_primary_bootstrap_is_seeded_and_keeps_pairs_together(self):
        records = []
        for task, cost in [('a', 2), ('b', 10), ('c', 50)]:
            pair = self.pair(task)
            pair[0]['cost_usd'] = cost
            pair[1]['cost_usd'] = cost - 1
            records.extend(pair)
        rows, _ = compare_runs.load(self.ledger(records))
        first = compare_runs.cost_per_success_delta(rows, seed=77, iterations=200)
        second = compare_runs.cost_per_success_delta(rows, seed=77, iterations=200)
        self.assertEqual(first, second)
        self.assertAlmostEqual(first[0], -1.0)
        self.assertAlmostEqual(first[1][0], -1.0)
        self.assertAlmostEqual(first[1][1], -1.0)
        self.assertEqual(first[2], 0)

    def test_lower_raw_spending_can_still_increase_cost_per_success(self):
        example = SCRIPTS.parents[2] / 'examples' / 'benchmark_runs.csv'
        rows, _ = compare_runs.load(example)
        estimate, _, _ = compare_runs.cost_per_success_delta(rows, iterations=200)
        self.assertAlmostEqual(estimate, 1.17 / 2 - 1.42 / 3)
        self.assertGreater(estimate, 0)

    def test_missing_billing_zero_success_and_small_samples_are_explicit(self):
        path = self.ledger(self.pair(cost_usd=''))
        rows, _ = compare_runs.load(path)
        self.assertIsNone(compare_runs.cost_per_success_delta(rows))
        rows, _ = compare_runs.load(self.ledger(self.pair()))
        self.assertEqual(compare_runs.cost_per_success_delta(rows), (-1.0, None, 0))
        rows[0][2]['success'] = False
        self.assertEqual(compare_runs.cost_per_success_delta(rows), (None, None, 0))

    def test_invalid_bootstrap_count_is_a_cli_error(self):
        path = self.ledger(self.pair())
        result = subprocess.run([sys.executable, str(SCRIPTS / 'compare_runs.py'),
                                 '--bootstrap-samples', '0', str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('at least 100', result.stderr)

    def test_repeats_remain_in_original_task_clusters(self):
        records = []
        for repeat in (1, 2, 3):
            records.extend(dict(row, repeat=repeat) for row in self.pair())
        fields = ['task_id', 'arm', 'success', 'cost_usd', 'repo_commit', 'model', 'cache_state', 'repeat']
        rows, _ = compare_runs.load(self.ledger(records, fields))
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(compare_runs.task_clusters(rows)), 1)
        self.assertEqual(compare_runs.cost_per_success_delta(rows), (-1.0, None, 0))
        self.assertEqual(compare_runs.delta_ci(rows, 'cost_usd'), (-1.0, None))

    def test_plain_snapshot_fingerprint_is_not_fabricated_as_git_revision(self):
        records = [dict(row, repo_commit='', source_sha256='b' * 64) for row in self.pair()]
        fields = ['task_id', 'arm', 'success', 'cost_usd', 'repo_commit', 'model', 'cache_state', 'source_sha256']
        rows, _ = compare_runs.load(self.ledger(records, fields), require_metadata=True)
        self.assertEqual(rows[0][1]['repo_commit'], '')
        self.assertEqual(rows[0][1]['source_sha256'], 'b' * 64)
        records[1]['source_sha256'] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'source_sha256'):
            compare_runs.load(self.ledger(records, fields))

    def test_repeated_task_cannot_change_its_source_revision(self):
        records = [dict(row, repeat=1) for row in self.pair()]
        records += [dict(row, repeat=2, repo_commit='b' * 40) for row in self.pair()]
        fields = ['task_id', 'arm', 'success', 'cost_usd', 'repo_commit', 'model', 'cache_state', 'repeat']
        with self.assertRaisesRegex(ValueError, 'between repeats'):
            compare_runs.load(self.ledger(records, fields))

    def test_optional_harness_conditions_must_match_within_pairs(self):
        fields = ['task_id', 'arm', 'success', 'cost_usd', 'repo_commit', 'model', 'cache_state', 'effort']
        records = [dict(row, effort='high') for row in self.pair()]
        records[1]['effort'] = 'low'
        with self.assertRaisesRegex(ValueError, 'effort'):
            compare_runs.load(self.ledger(records, fields))


if __name__ == '__main__':
    unittest.main()
