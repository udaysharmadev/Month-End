#!/usr/bin/env python3
"""Plan or explicitly run frozen paired tasks. Local fixtures are not AI evidence."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

METRICS = ('cost_usd', 'input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens',
           'reasoning_tokens', 'uncached_input_tokens', 'tool_input_tokens', 'total_tokens', 'calls')
IGNORES = {'.git', '.venv', '__pycache__', 'node_modules'}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError('nonfinite JSON constant: ' + value)


def fingerprint(directory):
    """Hash names and bytes of regular snapshot files, refusing symlink escapes."""
    directory = Path(directory).resolve()
    digest = hashlib.sha256()
    digest.update(b'month-end-source-sha256-v1\0')
    for base, dirs, files in os.walk(directory, followlinks=False):
        relative = Path(base).relative_to(directory).as_posix().encode('utf-8')
        digest.update(b'D' + len(relative).to_bytes(8, 'big') + relative)
        dirs[:] = sorted(name for name in dirs if name not in IGNORES)
        if any((Path(base) / name).is_symlink() for name in dirs):
            raise ValueError('source snapshots must not contain directory symlinks')
        for name in sorted(files):
            path = Path(base) / name
            if path.is_symlink() or not path.is_file():
                raise ValueError('source snapshots must contain regular files only')
            if name == '.env' or name.startswith('.env.'):
                raise ValueError('source snapshots must exclude credential .env files')
            name_bytes = path.relative_to(directory).as_posix().encode('utf-8')
            size = path.stat().st_size
            digest.update(b'F' + len(name_bytes).to_bytes(8, 'big') + name_bytes + size.to_bytes(8, 'big'))
            read_bytes = 0
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(65536), b''):
                    digest.update(chunk)
                    read_bytes += len(chunk)
            if read_bytes != size:
                raise ValueError('source file size changed while fingerprinting')
    return digest.hexdigest()


def command(value, label):
    if not isinstance(value, list) or not value or any(not isinstance(arg, str) or '\0' in arg for arg in value):
        raise ValueError(f'{label} must be a nonempty argv string list without NUL bytes')
    if not value[0]:
        raise ValueError(f'{label} executable is empty')
    return value


def load_manifest(path):
    path = Path(path).resolve()
    if path.stat().st_size > 2_000_000:
        raise ValueError('manifest exceeds 2 MB')
    manifest = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object, parse_constant=invalid_constant)
    if not isinstance(manifest, dict) or manifest.get('version') != 1 or isinstance(manifest.get('version'), bool):
        raise ValueError('manifest version must be 1')
    if manifest.get('data_kind') not in {'local-mechanism', 'model-evaluation'}:
        raise ValueError('data_kind must explicitly identify local-mechanism or model-evaluation')
    if not isinstance(manifest.get('model'), str) or not manifest['model'].strip():
        raise ValueError('model must be an explicit identifier (use local-fixture for local-only runs)')
    for field, default in [('repeats', 3), ('max_attempts', 1)]:
        value = manifest.get(field, default)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f'{field} must be a positive integer')
        manifest[field] = value
    states = manifest.get('cache_states', ['cold'])
    if not isinstance(states, list) or not states or any(not isinstance(s, str) or s not in {'cold', 'warm'} for s in states) or len(states) != len(set(states)):
        raise ValueError('cache_states must contain unique cold/warm labels')
    manifest['cache_states'] = states
    timeout = manifest.get('timeout_seconds', 300)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 86400:
        raise ValueError('timeout_seconds must be positive and at most 86400')
    manifest['timeout_seconds'] = timeout
    conditions = manifest.get('conditions', {})
    if not isinstance(conditions, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in conditions.items()):
        raise ValueError('conditions must map string labels to string values')
    manifest['conditions'] = conditions
    grading = manifest.get('grading_files', {})
    if not isinstance(grading, dict):
        raise ValueError('grading_files must map relative file paths to SHA-256 fingerprints')
    for name, expected in grading.items():
        if not isinstance(name, str) or not isinstance(expected, str):
            raise ValueError('grading_files must map string paths to fingerprints')
        file = (path.parent / name).resolve()
        if not file.is_relative_to(path.parent) or not file.is_file() or not re.fullmatch(r'[a-f0-9]{64}', expected):
            raise ValueError('grading_files must stay inside the manifest folder and use full fingerprints')
        if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise ValueError('grading file fingerprint mismatch: ' + name)
    arms = manifest.get('arms')
    if not isinstance(arms, dict) or set(arms) != {'baseline', 'month-end'}:
        raise ValueError('arms must contain baseline and month-end')
    for name, arm in arms.items():
        if not isinstance(arm, dict):
            raise ValueError('each arm must be an object')
        command(arm.get('argv'), f'{name}.argv')
        if 'warm' in states:
            command(arm.get('warmup_argv'), f'{name}.warmup_argv for warm condition')
        if arm.get('provider') not in {None, 'openai', 'anthropic', 'gemini'}:
            raise ValueError('unsupported usage provider')
        if arm.get('provider') and not isinstance(arm.get('usage_file'), str):
            raise ValueError('a usage provider requires a relative usage_file')
        if arm.get('usage_file') and not arm.get('provider'):
            raise ValueError('usage_file requires an explicit provider')
        if arm.get('usage_file'):
            usage_path = Path(arm['usage_file'])
            if usage_path.is_absolute() or '..' in usage_path.parts:
                raise ValueError('usage_file must stay within the trial workspace')
    tasks = manifest.get('tasks')
    if not isinstance(tasks, list) or not tasks:
        raise ValueError('tasks must be a nonempty list')
    identifiers = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError('each task must be an object')
        task_id = task.get('id', '')
        if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}', task_id) or task_id in identifiers:
            raise ValueError('task IDs must be unique safe path components of at most 101 characters')
        identifiers.add(task_id)
        for field in ('prompt', 'category', 'source_dir', 'source_sha256'):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise ValueError(f'task {task_id} requires {field}')
        source = (path.parent / task['source_dir']).resolve()
        if not source.is_dir() or not source.is_relative_to(path.parent):
            raise ValueError('source_dir must be a directory inside the manifest folder')
        if not re.fullmatch(r'[a-f0-9]{64}', task['source_sha256']) or fingerprint(source) != task['source_sha256']:
            raise ValueError(f'source snapshot fingerprint mismatch for {task_id}')
        if task.get('repo_commit') and not re.fullmatch(r'[a-fA-F0-9]{40}|[a-fA-F0-9]{64}', task['repo_commit']):
            raise ValueError('repo_commit must be a full Git commit hash when supplied')
        command(task.get('grader'), f'{task_id}.grader')
        task['_source'] = str(source)
    manifest['_path'] = str(path)
    manifest['_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest


def schedule(manifest, seed=2026):
    pairs = [(task['id'], repeat, state) for task in manifest['tasks']
             for repeat in range(1, manifest['repeats'] + 1) for state in manifest['cache_states']]
    rand = random.Random(seed)
    rand.shuffle(pairs)
    trials: list[dict[str, Any]] = []
    for task, repeat, state in pairs:
        arms = ['baseline', 'month-end']
        rand.shuffle(arms)
        trials.extend(dict(task_id=task, repeat=repeat, cache_state=state, arm=arm) for arm in arms)
    return trials


def expand(argv, values):
    expanded = []
    for argument in argv:
        for name, value in values.items():
            argument = argument.replace('{' + name + '}', str(value))
        expanded.append(argument)
    return expanded


def run_command(argv, workspace, log, timeout):
    started = time.monotonic()
    timed_out = False
    try:
        with Path(log).open('xb') as stream:
            with subprocess.Popen(argv, cwd=workspace, stdout=stream, stderr=subprocess.STDOUT,
                                  shell=False, start_new_session=(os.name == 'posix')) as process:
                try:
                    exit_code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    if os.name == 'posix':
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    exit_code = process.wait()
                except BaseException:
                    if os.name == 'posix':
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait()
                    raise
        error = None
    except OSError as exception:
        exit_code, error = 127, str(exception)
    return dict(exit_code=exit_code, timed_out=timed_out, wall_seconds=time.monotonic() - started,
                log=Path(log).name, error=error)


def collect_usage(arm, workspace, destination):
    if not arm.get('provider'):
        return None, None
    source = workspace / arm['usage_file']
    if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(workspace.resolve()):
        return None, 'configured usage file is missing or escapes the workspace'
    try:
        from usage import load_usage
        totals = load_usage(source, arm['provider'])
        shutil.copyfile(source, destination)
        totals['provenance'] = dict(totals.get('provenance', {}), source_path=destination.name,
                                    storage='relative-to-trial-receipt')
        return totals, None
    except (OSError, ValueError, ImportError) as error:
        return None, str(error)


def grading_intact(manifest):
    for name, expected in manifest.get('grading_files', {}).items():
        path = Path(manifest['_path']).parent / name
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            return False
    return True


def execute(manifest, output, seed=2026):
    output = Path(output).resolve()
    if any(output.is_relative_to(Path(task['_source'])) for task in manifest['tasks']):
        raise ValueError('output must not be inside a source snapshot')
    output.mkdir(parents=True, exist_ok=False)
    tasks = {task['id']: task for task in manifest['tasks']}
    trials = schedule(manifest, seed)
    shutil.copyfile(manifest['_path'], output / 'manifest.json')
    (output / 'plan.json').write_text(json.dumps(dict(seed=seed, manifest_sha256=manifest['_sha256'],
        data_kind=manifest['data_kind'], trials=trials), indent=2) + '\n', encoding='utf-8')
    rows = []
    seen_ids: set[str] = set()
    seen_exports: set[str] = set()
    seen_records: set[str] = set()
    for number, trial in enumerate(trials, 1):
        trial_started = time.monotonic()
        task, arm = tasks[trial['task_id']], manifest['arms'][trial['arm']]
        trial_output = output / f'{number:04d}-{task["id"]}-{trial["cache_state"]}-r{trial["repeat"]}-{trial["arm"]}'
        trial_output.mkdir()
        if fingerprint(task['_source']) != task['source_sha256']:
            raise ValueError('source changed after planning; stopped before the next command')
        if not grading_intact(manifest):
            raise ValueError('grading files changed; stopped before the next command')
        usage_records, phases, usage_errors = [], [], []
        with tempfile.TemporaryDirectory(prefix='month-end-benchmark-') as temporary:
            workspace = Path(temporary) / 'workspace'
            shutil.copytree(task['_source'], workspace, symlinks=True, ignore=shutil.ignore_patterns(*IGNORES))
            if fingerprint(workspace) != task['source_sha256']:
                raise ValueError('isolated copy does not match frozen source')
            prompt = Path(temporary) / 'task.md'
            prompt.write_text(task['prompt'] + '\n', encoding='utf-8')
            values = dict(trial, task_id=task['id'], workspace=workspace, python=sys.executable,
                          suite=Path(manifest['_path']).parent, prompt_file=prompt)
            usage_file = workspace / arm.get('usage_file', '.month-end-usage.json')
            values['usage_file'] = usage_file
            candidate, grader = None, None
            if trial['cache_state'] == 'warm':
                if arm.get('provider') and usage_file.exists():
                    usage_file.unlink()
                phase = run_command(expand(arm['warmup_argv'], values), workspace,
                                    trial_output / 'warmup.log', manifest['timeout_seconds'])
                phase['phase'] = 'warmup'
                phases.append(phase)
                usage, error = collect_usage(arm, workspace, trial_output / 'warmup-usage.json')
                usage_records.append(usage)
                if error:
                    usage_errors.append(error)
            warmup_ok = not phases or phases[-1]['exit_code'] == 0
            attempts = 0
            if warmup_ok:
                for attempts in range(1, manifest['max_attempts'] + 1):
                    if arm.get('provider') and usage_file.exists():
                        usage_file.unlink()
                    candidate = run_command(expand(arm['argv'], values), workspace,
                                            trial_output / f'candidate-{attempts}.log', manifest['timeout_seconds'])
                    candidate['phase'] = 'candidate'
                    phases.append(candidate)
                    usage, error = collect_usage(arm, workspace, trial_output / f'usage-{attempts}.json')
                    usage_records.append(usage)
                    if error:
                        usage_errors.append(error)
                    if grading_intact(manifest):
                        grader = run_command(expand(task['grader'], values), workspace,
                                             trial_output / f'grader-{attempts}.log', manifest['timeout_seconds'])
                    else:
                        grader = dict(exit_code=125, timed_out=False, wall_seconds=0,
                                      error='grading files changed; altered grader was not executed', log=None)
                    grader['phase'] = 'grader'
                    if not grading_intact(manifest):
                        grader['exit_code'] = 125
                        grader['error'] = 'grading files changed during execution; grade rejected'
                    phases.append(grader)
                    if candidate['exit_code'] == 0 and grader['exit_code'] == 0:
                        break
            success = bool(candidate and grader and candidate['exit_code'] == grader['exit_code'] == 0)
            totals = {}
            for metric in METRICS:
                values_for_metric = [record.get(metric) if record else None for record in usage_records]
                known_values = [value for value in values_for_metric if value is not None]
                totals[metric] = sum(known_values) if values_for_metric and len(known_values) == len(values_for_metric) else None
            observed_totals = dict(totals)
            observed_models = {record.get('model') for record in usage_records if record and record.get('model')}
            if observed_models and observed_models != {manifest['model']}:
                usage_errors.append('observed usage model differs from the frozen manifest model')
            for record in usage_records:
                if not record:
                    continue
                provenance = record.get('provenance', {})
                identities = set(provenance.get('response_ids', []))
                fingerprints = set(provenance.get('record_fingerprints', []))
                digest = provenance.get('source_sha256')
                if identities.intersection(seen_ids) or fingerprints.intersection(seen_records) or (isinstance(digest, str) and digest in seen_exports):
                    usage_errors.append('repeated provider response/export across phases; spending cannot be counted twice')
                seen_ids.update(identities)
                if isinstance(digest, str):
                    seen_exports.add(digest)
                seen_records.update(fingerprints)
                if any('multiple models' in warning for warning in record.get('warnings', [])):
                    usage_errors.append('usage export mixes or partially omits model identities')
            if usage_errors:
                totals = dict.fromkeys(METRICS)
            row = dict(trial, category=task['category'], success=int(success), model=manifest['model'],
                       repo_commit=task.get('repo_commit', ''), source_sha256=task['source_sha256'],
                       data_kind=manifest['data_kind'], attempts=attempts, turns='',
                       candidate_exit=candidate['exit_code'] if candidate else '',
                       grader_exit=grader['exit_code'] if grader else '',
                       wall_seconds=time.monotonic() - trial_started,
                       command_wall_seconds=sum(phase['wall_seconds'] for phase in phases),
                       usage_valid=int(not usage_errors),
                       usage_available=int(bool(arm.get('provider') and usage_records and all(usage_records))), **totals)
            row.update({field: manifest['conditions'].get(field, '') for field in ('effort', 'harness', 'toolset', 'grading')})
            row['provider'] = arm.get('provider', '')
            receipt = dict(row, phases=phases, usage_errors=usage_errors, observed_usage_totals=observed_totals,
                           usage_provenance=[record.get('provenance') for record in usage_records if record],
                           usage_warnings=[warning for record in usage_records if record for warning in record.get('warnings', [])])
            (trial_output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
            rows.append(row)
        # Flush the ledger after every completed trial, including failures.
        with (output / 'runs.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    summary = dict(data_kind=manifest['data_kind'], trials=len(rows), successes=sum(row['success'] for row in rows),
                   measurement_failures=sum(not row['usage_valid'] for row in rows),
                   note='Local fixture runs are mechanism checks, not AI quality, cache-hit or savings evidence.')
    groups: dict[str, dict[str, int]] = {}
    pairs: dict[tuple[str, int, str], dict[str, dict[str, Any]]] = {}
    for row in rows:
        label = f'{row["category"]}/{row["cache_state"]}/{row["arm"]}'
        group = groups.setdefault(label, dict(trials=0, successes=0, candidate_failures=0, grader_failures=0))
        group['trials'] += 1
        group['successes'] += row['success']
        group['candidate_failures'] += row['candidate_exit'] != 0
        group['grader_failures'] += row['grader_exit'] != 0
        pairs.setdefault((row['task_id'], row['repeat'], row['cache_state']), {})[row['arm']] = row
    summary['category_cache_arm'] = groups
    summary['quality_regressions'] = [dict(task_id=key[0], repeat=key[1], cache_state=key[2],
                                         category=pair['baseline']['category'])
                                      for key, pair in pairs.items()
                                      if pair['baseline']['success'] and not pair['month-end']['success']]
    summary['quality_improvements'] = [dict(task_id=key[0], repeat=key[1], cache_state=key[2],
                                          category=pair['baseline']['category'])
                                       for key, pair in pairs.items()
                                       if not pair['baseline']['success'] and pair['month-end']['success']]
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--execute', action='store_true', help='Explicitly run the manifest commands; default only plans')
    parser.add_argument('--output', type=Path, help='Required new results directory for execution')
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        if args.execute:
            if args.output is None:
                parser.error('--execute requires --output pointing to a new directory')
            summary = execute(manifest, args.output, args.seed)
            print(json.dumps({key: summary[key] for key in ('data_kind', 'trials', 'successes', 'measurement_failures')}, indent=2))
            print('Detailed receipts, regression attribution and the frozen manifest are in ' + str(args.output))
            return 0 if summary['successes'] == summary['trials'] and not summary['measurement_failures'] else 1
        print(json.dumps(dict(mode='plan-only', data_kind=manifest['data_kind'], seed=args.seed,
                              manifest_sha256=manifest['_sha256'], trials=schedule(manifest, args.seed)), indent=2))
        return 0
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    # Sibling imports must not add unmanaged cache files to an installed skill.
    sys.dont_write_bytecode = True
    raise SystemExit(main())
