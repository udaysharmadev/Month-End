#!/usr/bin/env python3
"""Explicit bounded subscription-only Codex quality pilot, never a billing benchmark."""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from candidate_sandbox import bounded_subprocess, require_sandbox

ROOT = Path(__file__).resolve().parents[1]


def usage_events(raw):
    totals = {'input_tokens': 0, 'cached_input_tokens': 0, 'output_tokens': 0}
    completed = 0
    errors = []
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') in {'error', 'turn.failed'}:
            errors.append(str(event.get('message', event.get('error', 'turn failed')))[:500])
        if event.get('type') == 'turn.completed':
            usage = event.get('usage')
            if not isinstance(usage, dict):
                continue
            for key in totals:
                value = usage.get(key)
                if type(value) is not int or value < 0:
                    raise ValueError('invalid native CLI usage metric: ' + key)
                totals[key] += value
            completed += 1
    return {'usage': totals if completed else None, 'completed_turns': completed, 'errors': errors}


def run_pilot(output, repeats=1, timeout=150, seed=2026):
    require_sandbox()
    executable = shutil.which('codex')
    if executable is None:
        raise ValueError('Codex is not installed')
    environment = dict(os.environ)
    for key in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'AZURE_OPENAI_API_KEY', 'CODEX_API_KEY'):
        environment.pop(key, None)
    authentication = subprocess.run([executable, 'login', 'status'], capture_output=True,
                                    text=True, env=environment, timeout=15)
    if authentication.returncode or 'Logged in using ChatGPT' not in authentication.stderr + authentication.stdout:
        raise ValueError('ChatGPT subscription authentication is required; no API-key fallback is allowed')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    suite = json.loads((ROOT / 'benchmarks/local/suite.json').read_text())
    tasks = [task for task in suite['tasks'] if task['id'] in {'quoted-csv', 'retry-budget', 'nested-redaction'}]
    pairs = [(task, repeat) for task in tasks for repeat in range(1, repeats + 1)]
    generator = random.Random(seed)
    generator.shuffle(pairs)
    records = []
    stop = False
    for task, repeat in pairs:
        arms = ['baseline', 'month-end']
        generator.shuffle(arms)
        for arm in arms:
            label = task['id'] + '-' + str(repeat) + '-' + arm
            with tempfile.TemporaryDirectory(prefix='month-end-live-') as temporary:
                workspace = Path(temporary)
                shutil.copytree(ROOT / 'benchmarks/local' / task['source_dir'], workspace, dirs_exist_ok=True)
                if arm == 'month-end':
                    skill = workspace / '.agents/skills/month-end'
                    shutil.copytree(ROOT / 'skills/month-end', skill,
                                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                prompt = ('Implement the requested behavior in app.py. Use only Python standard library. '
                          'Do not access outside this task workspace or make network requests. '
                          'Do not start subagents. Finish the code edit. Task: ' + task['prompt'])
                if arm == 'month-end':
                    prompt = 'Use $month-end for this coding task. ' + prompt
                argv = [executable, 'exec', '--ignore-user-config', '--ephemeral', '--json',
                        '--skip-git-repo-check', '--sandbox', 'workspace-write',
                        '-c', 'forced_login_method="chatgpt"', '-C', str(workspace), prompt]
                timed_out = False
                try:
                    candidate = subprocess.run(argv, capture_output=True, text=True, env=environment,
                                               timeout=timeout)
                    stdout, stderr, code = candidate.stdout, candidate.stderr, candidate.returncode
                except subprocess.TimeoutExpired as error:
                    stdout = (error.stdout or b'').decode('utf-8', errors='replace') if isinstance(error.stdout, bytes) else error.stdout or ''
                    stderr = 'native CLI exceeded the per-invocation timeout'
                    code, timed_out = 124, True
                parsed = usage_events(stdout)
                grader = ROOT / 'benchmarks/local/grade.py'
                grade = bounded_subprocess([sys.executable, '-I', str(grader), str(workspace), task['id']],
                                           workspace, read_paths=(grader,), require_isolation=True)
                (output / (label + '.jsonl')).write_text(stdout, encoding='utf-8')
                (output / (label + '.stderr.txt')).write_text(stderr, encoding='utf-8')
                shutil.copyfile(workspace / 'app.py', output / (label + '.app.py'))
                record = {'task_id': task['id'], 'repeat': repeat, 'arm': arm,
                          'candidate_exit': code, 'grader_exit': grade['exit'],
                          'success': code == 0 and grade['exit'] == 0, 'timed_out': timed_out,
                          'skill_path_observed_in_trace': arm == 'month-end' and ('SKILL.md' in stdout and 'month-end' in stdout),
                          'grade': grade['stdout'].strip(), **parsed}
                records.append(record)
                print(label + ': ' + ('PASS' if record['success'] else 'FAIL'), flush=True)
                if parsed['errors'] and not parsed['completed_turns']:
                    stop = True
                    break
        if stop:
            break
    result = {'format_version': 1, 'kind': 'live-subscription-quality-pilot', 'host': 'codex',
              'auth': 'chatgpt-subscription', 'seed': seed, 'planned_invocations': len(pairs) * 2,
              'executed_invocations': len(records), 'repeats': repeats, 'records': records,
              'billed_cost_usd': None, 'cache_condition': 'uncontrolled',
              'limitations': ['Not a registered sixty-task evaluation', 'Native CLI input/output/cache usage is not billing',
                              'Underlying model request count is not exposed by this pilot',
                              'Cold/warm provider caches are not controlled', 'No savings conclusion is justified']}
    (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Explicitly authorize subscription invocations')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--repeats', type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args(argv)
    if not args.execute:
        print(f'PLAN: {args.repeats * 6} native subscription invocations; no commands started')
        return 0
    if not args.output:
        parser.error('--execute requires a new explicit --output directory')
    try:
        result = run_pilot(args.output, repeats=args.repeats)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        return 1
    print(json.dumps({'executed': result['executed_invocations'],
                      'passed': sum(record['success'] for record in result['records']),
                      'billed_cost_usd': None}))
    return 0 if len(result['records']) == result['planned_invocations'] and all(record['success'] for record in result['records']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
