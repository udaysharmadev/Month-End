"""Verify frozen behavioral oracles before any model sees a workflow task."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'benchmarks' / 'workflow'
spec = importlib.util.spec_from_file_location('workflow_grader', DIRECTORY / 'grader.py')
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)


class WorkflowSuiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = json.loads((DIRECTORY / 'suite.json').read_text(encoding='utf-8'))
        cls.references = json.loads((DIRECTORY / 'reference_solutions.json').read_text(encoding='utf-8'))

    def test_all_frozen_reference_solutions_pass_and_every_bug_is_detected(self):
        tasks = self.suite['tasks']
        self.assertEqual(len(tasks), 60)
        self.assertEqual(len({task['id'] for task in tasks}), 60)
        self.assertEqual(sorted(Counter(task['category'] for task in tasks).values()), [10] * 6)
        self.assertEqual(set(self.references), {task['id'] for task in tasks})
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'app.py'
            for task in tasks:
                with self.subTest(task=task['id']):
                    self.assertGreaterEqual(len(task['tests']), 4)
                    source.write_text(self.references[task['id']], encoding='utf-8')
                    full = grader.grade(source, task)
                    self.assertEqual(full['passed'], full['total'], full)
                    smoke = grader.grade(source, task, visible=True)
                    self.assertEqual(smoke['passed'], 2, smoke)
                    source.write_text(task['source'], encoding='utf-8')
                    buggy = grader.grade(source, task)
                    self.assertLess(buggy['passed'], buggy['total'], buggy)

    def test_grader_detects_input_mutation_even_when_result_matches(self):
        task = {'id': 'mutation', 'tests': [{'args': [[1]], 'expected': []}]}
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'app.py'
            source.write_text('def solve(values):\n    values.clear()\n    return []\n')
            result = grader.grade(source, task)
        self.assertEqual(result['passed'], 0)
        self.assertIn('mutated', result['failures'][0]['error'])

    def test_grader_rejects_generators_and_bool_for_integer_results(self):
        for code, expected in [('def solve(): return iter([1])', [1]), ('def solve(): return True', 1)]:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temporary:
                source = Path(temporary) / 'app.py'
                source.write_text(code)
                result = grader.grade(source, {'id': 'type', 'tests': [{'args': [], 'expected': expected}]})
                self.assertEqual(result['passed'], 0)

    def test_cli_smoke_hides_edge_cases_and_failure_exit_is_preserved(self):
        task = next(task for task in self.suite['tasks'] if task['id'] == 'parse-port')
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'app.py'
            source.write_text(task['source'])
            common = [sys.executable, str(DIRECTORY / 'grader.py'), str(source), task['id']]
            smoke = subprocess.run([*common, '--visible'], capture_output=True, text=True)
            full = subprocess.run(common, capture_output=True, text=True)
        self.assertEqual(smoke.returncode, 0)
        self.assertEqual(json.loads(smoke.stdout)['total'], 2)
        self.assertEqual(full.returncode, 1)
        self.assertGreater(json.loads(full.stdout)['total'], 2)

    def test_cli_can_receive_trusted_oracles_without_suite_file_access(self):
        task = next(task for task in self.suite['tasks'] if task['id'] == 'parse-port')
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'app.py'
            source.write_text(self.references[task['id']])
            copied_grader = Path(temporary) / 'grader.py'
            copied_grader.write_bytes((DIRECTORY / 'grader.py').read_bytes())
            command = [sys.executable, str(copied_grader), str(source), task['id'], '--task-stdin']
            result = subprocess.run(command, input=json.dumps(task), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['total'], len(task['tests']))
            mismatched = {**task, 'id': 'mismatched'}
            rejected = subprocess.run(command, input=json.dumps(mismatched), capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn('identity mismatch', rejected.stderr)


if __name__ == '__main__':
    unittest.main()
