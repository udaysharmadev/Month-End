#!/usr/bin/env python3
"""Explicit Gemini patch-generation pilot. No keys saved; no automatic API calls."""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import getpass
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/'
DEFAULT_MODELS = ('gemini-3.8-flash', 'gemini-3.5-flash-lite', 'gemini-3.1-pro-preview', 'gemini-2.5-flash')
MAX_RESPONSE_BYTES = 8_000_000
ALLOWED_IMPORTS = {'csv', 'io', 'decimal', 'collections', 'datetime', 'heapq', 'json',
                   're', 'unicodedata', 'posixpath', 'pathlib', 'copy', 'math', 'functools', 'itertools', 'typing'}
FORBIDDEN_NAMES = {'eval', 'exec', 'compile', 'open', '__import__', 'getattr', 'setattr',
                   'delattr', 'globals', 'locals', 'vars', 'input', 'breakpoint', 'help',
                   'read_text', 'read_bytes', 'write_text', 'write_bytes', 'FileIO', 'file_digest'}
METRICS = ('input_tokens', 'output_tokens', 'reasoning_tokens', 'cache_read_tokens', 'total_tokens')
PRINT_LOCK = threading.Lock()


def progress(message):
    with PRINT_LOCK:
        print(message, flush=True)


class APIError(Exception):
    def __init__(self, status, message, retry_after=None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, key, *, sleeper=time.sleep, opener=None):
        if not key.strip():
            raise ValueError('Gemini key is empty')
        self._key = key.strip()
        self._sleep = sleeper
        self._open = opener or urllib.request.build_opener(NoRedirect()).open

    def sanitize(self, value):
        return json.loads(json.dumps(value, ensure_ascii=False).replace(self._key, '[REDACTED]'))

    def request(self, endpoint, payload=None):
        if not re.fullmatch(r'models(?:\?pageSize=1000(?:&pageToken=[A-Za-z0-9_.%~-]+)?)?|models/[A-Za-z0-9._-]+:generateContent', endpoint):
            raise ValueError('unsupported Gemini endpoint')
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(BASE_URL + endpoint, data=data,
                                         headers={'x-goog-api-key': self._key, 'Content-Type': 'application/json'})
        try:
            with self._open(request, timeout=90) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            try:
                raw = error.read(65536).decode('utf-8', errors='replace').replace(self._key, '[REDACTED]')
            finally:
                error.close()
            try:
                details = json.loads(raw).get('error', {})
                message = details.get('message', 'Gemini API rejected request')
            except (ValueError, AttributeError):
                details = {}
                message = 'Gemini API rejected request'
            header = error.headers.get('Retry-After', '')
            retry_after = float(header) if re.fullmatch(r'\d+(?:\.\d+)?', header) else None
            for detail in details.get('details', []):
                if isinstance(detail, dict) and str(detail.get('@type', '')).endswith('RetryInfo'):
                    delay = detail.get('retryDelay', '')
                    if isinstance(delay, str) and re.fullmatch(r'\d+(?:\.\d+)?s', delay):
                        retry_after = max(retry_after or 0, float(delay[:-1]))
            raise APIError(error.code, str(message)[:800], retry_after) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise APIError(0, type(error).__name__ + ': transport failure; response usage may be unknown') from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise APIError(0, 'Gemini response exceeded the bounded response size; usage unknown')
        result = self.sanitize(json.loads(raw))
        if not isinstance(result, dict):
            raise ValueError('Gemini response is not a JSON object')
        return result

    def with_retry(self, endpoint, payload=None, *, attempts=3, cooldown=10):
        failures: list[dict[str, Any]] = []
        for attempt in range(attempts):
            started = time.monotonic()
            try:
                result = self.request(endpoint, payload)
                return result, failures
            except APIError as error:
                record = {'http_status': error.status, 'message': str(error),
                          'attempt': attempt + 1, 'wall_seconds': time.monotonic() - started,
                          'usage': None}
                failures.append(record)
                transient = error.status in {0, 408, 429, 500, 502, 503, 504}
                if not transient or attempt + 1 == attempts or (error.retry_after or 0) > 60:
                    return None, failures
                delay = min(60, max(cooldown * 2 ** attempt, error.retry_after or 0))
                record['retry_delay_seconds'] = delay
                progress(f'  transient HTTP {error.status}; retry {attempt + 2}/{attempts} after {delay:g}s')
                self._sleep(delay)
        raise RuntimeError('unreachable retry state')

    def models(self):
        output = []
        token = None
        for _ in range(20):
            endpoint = 'models?pageSize=1000'
            if token:
                endpoint += '&pageToken=' + urllib.parse.quote(token, safe='')
            response, failures = self.with_retry(endpoint)
            if response is None:
                raise ValueError('Gemini model discovery failed: ' + json.dumps(failures))
            output.extend(response.get('models', []))
            token = response.get('nextPageToken')
            if not token:
                return output
        raise ValueError('model pagination exceeded twenty pages')


def extract_code(response):
    candidates = response.get('candidates', [])
    if not candidates:
        raise ValueError('no candidate returned')
    candidate = candidates[0]
    if candidate.get('finishReason') != 'STOP':
        raise ValueError('candidate not complete: ' + str(candidate.get('finishReason')))
    code = ''.join(part.get('text', '') for part in candidate.get('content', {}).get('parts', [])
                   if part.get('thought') is not True).strip()
    if code.startswith('```'):
        match = re.fullmatch(r'```(?:python|py)?\s*\n(.*?)\n```', code, re.DOTALL)
        if not match:
            raise ValueError('candidate includes incomplete or mixed markdown')
        code = match.group(1)
    if not code or len(code.encode('utf-8')) > 100_000:
        raise ValueError('candidate source empty or exceeds 100 KB')
    tree = ast.parse(code)
    if not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'solve' for node in tree.body):
        raise ValueError('candidate has no solve function')
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split('.')[0] not in ALLOWED_IMPORTS for alias in node.names):
                raise ValueError('candidate imports outside the grading allowlist')
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or '').split('.')[0] not in ALLOWED_IMPORTS:
                raise ValueError('candidate imports outside the grading allowlist')
        elif isinstance(node, ast.Name) and (node.id in FORBIDDEN_NAMES or node.id.startswith('__')):
            raise ValueError('candidate uses a forbidden execution/introspection name')
        elif isinstance(node, ast.Attribute) and (node.attr in FORBIDDEN_NAMES or node.attr.startswith('__') or node.attr in {'os', 'sys', 'subprocess'}):
            raise ValueError('candidate uses a forbidden execution/introspection attribute')
    return code + '\n'


def grade_code(code, task_id, grader):
    with tempfile.TemporaryDirectory(prefix='month-end-gemini-grade-') as temporary:
        workspace = Path(temporary).resolve()
        (workspace / 'app.py').write_text(code, encoding='utf-8')
        argv = [sys.executable, '-I', str(grader), str(workspace), task_id]
        environment = {'PATH': os.defpath, 'HOME': str(workspace), 'TMPDIR': str(workspace), 'PYTHONHASHSEED': '0'}
        if sys.platform == 'darwin' and shutil.which('sandbox-exec'):
            profile = ('(version 1)(allow default)(deny network*)'
                       '(deny file-write* (require-not (subpath ' + json.dumps(str(workspace)) + ')))')
            argv = ['sandbox-exec', '-p', profile, *argv]
        try:
            result = subprocess.run(argv, cwd=workspace, env=environment, capture_output=True,
                                    text=True, timeout=15)
            return {'exit': result.returncode, 'stdout': result.stdout[-8000:], 'stderr': result.stderr[-8000:]}
        except subprocess.TimeoutExpired:
            return {'exit': 124, 'stdout': '', 'stderr': 'independent grade timed out'}


def generation_config(model):
    thinking = {'thinkingBudget': 1024} if model.startswith('gemini-2.5') else {'thinkingLevel': 'LOW'}
    return {'maxOutputTokens': 4096, 'thinkingConfig': thinking}


def prompt_for(task, source, arm, skill_text):
    common = ('Implement solve in app.py using Python standard library. Return only the complete Python source; '
              'no commentary. The code must not access files, environment variables, network or processes.\n'
              'TASK:\n' + task['prompt'] + '\nCURRENT app.py:\n' + source)
    if arm == 'month-end':
        common = 'Apply the following Month End skill where relevant to this constrained patch-generation task:\n' + skill_text + '\n\n' + common
    return common


def aggregate(records):
    models: dict[str, dict[str, dict[str, Any]]] = {}
    for record in records:
        arm = models.setdefault(record['model'], {}).setdefault(record['arm'],
               {'tasks': 0, 'first_pass_successes': 0, 'accepted_successes': 0, 'api_responses': 0,
                'generated_trials': 0, 'no_response_trials': 0, 'grader_failures': 0,
                'source_guard_rejections': 0, 'incomplete_responses': 0,
                'http_failures': 0, 'metrics': {name: 0 for name in METRICS}, 'unknown_failure_usage': False})
        arm['tasks'] += 1
        arm['accepted_successes'] += record['success']
        arm['first_pass_successes'] += bool(record['generations'] and record['generations'][0].get('success'))
        generated = any(generation.get('usage') is not None for generation in record['generations'])
        arm['generated_trials'] += generated
        arm['no_response_trials'] += not generated
        for generation in record['generations']:
            arm['http_failures'] += len(generation.get('http_failures', []))
            arm['unknown_failure_usage'] |= bool(generation.get('http_failures'))
            arm['unknown_failure_usage'] |= bool(generation.get('usage_error'))
            arm['grader_failures'] += generation.get('grade', {}).get('exit', 0) != 0
            error = generation.get('error', '')
            arm['source_guard_rejections'] += 'grading allowlist' in error or 'forbidden execution' in error
            arm['incomplete_responses'] += 'candidate not complete' in error
            if generation.get('usage') is None:
                continue
            arm['api_responses'] += 1
            for metric in METRICS:
                value = generation['usage'].get(metric)
                if value is None:
                    arm['metrics'][metric] = None
                elif arm['metrics'][metric] is not None:
                    arm['metrics'][metric] += value
    for arms in models.values():
        for arm in arms.values():
            if not arm['api_responses']:
                arm['metrics'] = {name: None for name in METRICS}
    return models


def run_model(client, model, tasks, output, skill_text, *, repeats=1, seed=2026):
    sys.path.insert(0, str(ROOT / 'skills/month-end/scripts'))
    from usage import load_usage
    model_output = output / model
    model_output.mkdir()
    planned = [(task, repeat) for task in tasks for repeat in range(1, repeats + 1)]
    generator = random.Random(seed)
    generator.shuffle(planned)
    records = []
    consecutive_service_failures = 0
    for task, repeat in planned:
        arms = ['baseline', 'month-end']
        generator.shuffle(arms)
        source = (ROOT / 'benchmarks/local' / task['source_dir'] / 'app.py').read_text()
        for arm in arms:
            label = f'{task["id"]}-{repeat}-{arm}'
            record: dict[str, Any] = {'model': model, 'task_id': task['id'], 'repeat': repeat,
                                     'arm': arm, 'success': False, 'generations': []}
            prompt = prompt_for(task, source, arm, skill_text)
            for generation in range(2):
                payload = {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                           'generationConfig': generation_config(model)}
                started = time.monotonic()
                response, failures = client.with_retry('models/' + model + ':generateContent', payload)
                item: dict[str, Any] = {'number': generation + 1, 'http_failures': failures,
                                        'wall_seconds': time.monotonic() - started, 'usage': None,
                                        'request_sha256': hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}
                record['generations'].append(item)
                if response is None:
                    item['error'] = 'API request failed after bounded retry policy'
                    consecutive_service_failures += 1
                    break
                consecutive_service_failures = 0
                receipt = model_output / f'{label}-response-{generation + 1}.json'
                receipt.write_text(json.dumps(client.sanitize(response), indent=2) + '\n')
                try:
                    normalized = load_usage(receipt, 'gemini')
                    item['usage'] = {name: normalized.get(name) for name in METRICS}
                    item['model_version'] = normalized.get('model')
                    item['response_ids'] = normalized['provenance']['response_ids']
                except ValueError as error:
                    item['usage_error'] = str(error)
                try:
                    code = extract_code(response)
                    (model_output / f'{label}-candidate-{generation + 1}.py').write_text(code)
                    grade = grade_code(code, task['id'], ROOT / 'benchmarks/local/grade.py')
                    item['grade'] = grade
                    item['success'] = grade['exit'] == 0
                    if item['success']:
                        record['success'] = True
                        break
                    feedback = grade['stderr'][-2000:]
                except (ValueError, SyntaxError) as error:
                    feedback = str(error)
                    item['error'] = feedback
                if generation == 0:
                    progress(f'{model} {label}: retrying failed patch after 5s')
                    client._sleep(5)
                    prompt += '\nYour previous patch failed independent validation. Correct it. Diagnostic:\n' + feedback
            records.append(record)
            (model_output / 'records.json').write_text(json.dumps(client.sanitize(records), indent=2) + '\n')
            progress(f'{model} {label}: {"PASS" if record["success"] else "FAIL"}')
            if consecutive_service_failures >= 2:
                progress(f'{model}: stopping after repeated service/access failures; remaining trials deferred')
                return records
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--models', nargs='+', default=list(DEFAULT_MODELS))
    parser.add_argument('--task-limit', type=int, default=12)
    parser.add_argument('--repeats', type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args(argv)
    if not 1 <= args.task_limit <= 12 or len(args.models) > 6 or len(set(args.models)) != len(args.models):
        parser.error('select 1–12 tasks and at most six unique explicit models')
    if any(not re.fullmatch(r'gemini-[A-Za-z0-9._-]+', model) for model in args.models):
        parser.error('invalid Gemini model identifier')
    if not args.execute:
        print(f'PLAN: {len(args.models)} models × {args.task_limit} tasks × {args.repeats} repeats × 2 arms; no API calls')
        return 0
    if not args.output:
        parser.error('--execute requires an explicit new --output directory')
    key = getpass.getpass('Gemini key (hidden): ')
    client = Client(key)
    del key
    try:
        models = client.models()
        available = {model['name'].removeprefix('models/') for model in models
                     if 'generateContent' in model.get('supportedGenerationMethods', [])}
        if set(args.models) - available:
            raise ValueError('unavailable generateContent models: ' + ', '.join(sorted(set(args.models) - available)))
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=False)
        suite = json.loads((ROOT / 'benchmarks/local/suite.json').read_text())
        tasks = suite['tasks'][:args.task_limit]
        skill_text = (ROOT / 'skills/month-end/SKILL.md').read_text()
        protocol = {'kind': 'gemini-constrained-patch-generation', 'models': args.models,
                    'tasks': [task['id'] for task in tasks], 'repeats': args.repeats,
                    'seed': 2026, 'max_candidate_generations_per_trial': 2,
                    'max_http_attempts_per_generation': 3,
                    'skill_sha256': hashlib.sha256(skill_text.encode()).hexdigest(),
                    'grader_sha256': hashlib.sha256((ROOT / 'benchmarks/local/grade.py').read_bytes()).hexdigest(),
                    'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'suite_sha256': hashlib.sha256((ROOT / 'benchmarks/local/suite.json').read_bytes()).hexdigest(),
                    'cache_state': 'uncontrolled', 'billing_usd': None,
                    'limits': 'No API tools/agent loop; measures patch quality and instruction overhead, not tool-output savings'}
        (output / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n')
        records = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(run_model, client, model, tasks, output, skill_text,
                                       repeats=args.repeats): model for model in args.models}
            for future in concurrent.futures.as_completed(futures):
                records.extend(future.result())
        summary = {'protocol': protocol, 'trials_completed': len(records),
                   'successes': sum(record['success'] for record in records),
                   'by_model': aggregate(records), 'records': records,
                   'limitations': ['No tool-using host loop', 'Small public synthetic task suite; not independent external reproduction',
                                   'Provider cache conditions uncontrolled', 'Reported usage is not an invoice; billed dollars unavailable',
                                   'All failed generations are retained; transport failures can have unknown usage',
                                   'Instructions are explicitly loaded even on small tasks; this can increase token use']}
        (output / 'summary.json').write_text(json.dumps(client.sanitize(summary), indent=2) + '\n')
        progress(f'FINISHED: {summary["successes"]}/{summary["trials_completed"]} accepted patches')
        return 0 if all(record['success'] for record in records) else 1
    except (OSError, ValueError, APIError) as error:
        print('FAIL: ' + str(error).replace(client._key, '[REDACTED]'), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
