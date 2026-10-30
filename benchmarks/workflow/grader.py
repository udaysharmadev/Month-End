#!/usr/bin/env python3
"""Independent prewritten JSON-call oracles for the synthetic workflow suite.

Run candidate code in an isolated subprocess; this module is not a sandbox.
The visible mode runs only the first two smoke cases. Full grading runs all
cases, including held-back edge cases. Public fixtures permit reproduction and
are not claimed to be contamination-resistant independent production tasks.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

SUITE = Path(__file__).with_name('suite.json')
EXCEPTIONS = {'ValueError': ValueError, 'TypeError': TypeError, 'KeyError': KeyError}


def same_json(actual, expected):
    """Require concrete JSON types; bool is not an integer or a lazy iterator."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(same_json(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(same_json(actual[key], value) for key, value in expected.items())
    return actual == expected


def grade(source: Path, task: dict, visible: bool = False) -> dict:
    tests = task['tests'][:2] if visible else task['tests']
    result = {'task_id': task['id'], 'passed': 0, 'total': len(tests),
              'mode': 'visible-smoke' if visible else 'full-independent', 'failures': []}
    previous_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location('workflow_candidate', source)
        if spec is None or spec.loader is None:
            raise ValueError('candidate is not an importable Python source')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        solve = module.solve
    except Exception as error:
        result['failures'].append({'phase': 'load', 'error': type(error).__name__})
        return result
    finally:
        sys.dont_write_bytecode = previous_bytecode
    for index, case in enumerate(tests, 1):
        args = copy.deepcopy(case['args'])
        kwargs = copy.deepcopy(case.get('kwargs', {}))
        failure = None
        try:
            actual = solve(*args, **kwargs)
            if 'raises' in case:
                failure = 'Expected ' + case['raises'] + ', but function returned'
            elif not same_json(actual, case['expected']):
                failure = 'Returned value or concrete JSON type differs from expected'
        except Exception as error:
            if 'raises' not in case or not isinstance(error, EXCEPTIONS[case['raises']]):
                failure = 'Unexpected ' + type(error).__name__
        if not same_json(args, case['args']) or not same_json(kwargs, case.get('kwargs', {})):
            failure = 'Input argument was mutated'
        if failure is None:
            result['passed'] += 1
        else:
            result['failures'].append({'case': index, 'error': failure})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('task_id')
    parser.add_argument('--visible', action='store_true', help='Only the first two public smoke cases')
    parser.add_argument('--task-stdin', action='store_true', help='Read the trusted fixed task oracle from stdin')
    args = parser.parse_args(argv)
    if args.task_stdin:
        raw = sys.stdin.read(1_000_001)
        try:
            if len(raw) > 1_000_000:
                raise ValueError('trusted task exceeds input budget')
            task = json.loads(raw)
            if not isinstance(task, dict) or task.get('id') != args.task_id:
                raise ValueError('trusted task identity mismatch')
            tests = task.get('tests')
            if not isinstance(tests, list) or not tests:
                raise ValueError('trusted task requires fixed test cases')
            for case in tests:
                if (not isinstance(case, dict) or not isinstance(case.get('args'), list)
                        or not isinstance(case.get('kwargs', {}), dict)
                        or ('raises' in case) == ('expected' in case)
                        or ('raises' in case and case['raises'] not in EXCEPTIONS)):
                    raise ValueError('invalid trusted test case')
        except ValueError as error:
            parser.error(str(error))
    else:
        tasks = json.loads(SUITE.read_text(encoding='utf-8'))['tasks']
        task = next((task for task in tasks if task['id'] == args.task_id), None)
    if task is None:
        parser.error('unknown task ID')
    result = grade(args.source, task, args.visible)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['passed'] == result['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
