#!/usr/bin/env python3
"""Export allowlisted numeric workflow evidence; never publish private traces."""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

METRICS = ('input_tokens', 'output_tokens', 'reasoning_tokens', 'cache_read_tokens', 'total_tokens')
ARMS = ('baseline', 'month-end')
TOOLS = {'list', 'search', 'read', 'locate', 'excerpt', 'symbol', 'replace', 'test', 'finish', 'invalid'}
HASHES = ('suite_sha256', 'grader_sha256', 'harness_sha256', 'skill_sha256', 'helper_sha256')
OPTIONAL_HASHES = ('transport_sha256', 'sandbox_sha256', 'usage_import_sha256', 'skill_tree_sha256')
SEED = 20261028
DRAWS = 2000


def count(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError('invalid nonnegative integer: ' + label)
    return value


def identifier(value, kind):
    pattern = r'gemini-[A-Za-z0-9._-]{1,100}' if kind == 'model' else r'[a-z0-9][a-z0-9-]{0,79}'
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError('invalid ' + kind + ' identifier')
    return value


def protocol_identity(protocol):
    if not isinstance(protocol, dict):
        raise ValueError('protocol must be an object')
    if protocol.get('cache_state', 'uncontrolled') != 'uncontrolled':
        raise ValueError('this workflow analyzer requires the uncontrolled-cache protocol')
    output: dict[str, Any] = {'kind': 'gemini-tool-workflow', 'cache_state': 'uncontrolled', 'billed_cost_usd': None}
    for field in HASHES + tuple(field for field in OPTIONAL_HASHES if field in protocol):
        value = protocol.get(field)
        if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value):
            raise ValueError('missing or invalid protocol fingerprint: ' + field)
        output[field] = value
    for field in ('source_commit', 'preregistered_commit', 'repo_commit'):
        if field in protocol:
            value = protocol[field]
            if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', value):
                raise ValueError('invalid protocol commit identity')
            output[field] = value
    for field, kind in (('models', 'model'), ('tasks', 'task')):
        values = protocol.get(field)
        if not isinstance(values, list) or not values or len(values) > 10000:
            raise ValueError('protocol requires bounded nonempty model/task lists')
        output[field] = [identifier(value, kind) for value in values]
        if len(set(output[field])) != len(output[field]):
            raise ValueError('duplicate protocol model/task identifiers')
    output['repeats'] = count(protocol.get('repeats'), 'repeats', 1)
    if output['repeats'] > 100:
        raise ValueError('repeat count exceeds analysis bound')
    for field in ('seed', 'max_turns', 'workers'):
        if field in protocol:
            output[field] = count(protocol[field], field)
    for field, pattern in (('python_version', r'[0-9]+\.[0-9]+\.[0-9]+'),
                           ('platform', r'(?:darwin|linux|win32)')):
        if field in protocol:
            if not isinstance(protocol[field], str) or not re.fullmatch(pattern, protocol[field]):
                raise ValueError('invalid protocol software identity')
            output[field] = protocol[field]
    if 'requested_generation_configs' in protocol:
        configs = protocol['requested_generation_configs']
        if not isinstance(configs, dict) or set(configs) != set(output['models']):
            raise ValueError('generation configuration requires every requested model')
        output['requested_generation_configs'] = {}
        for model, config in configs.items():
            if not isinstance(config, dict):
                raise ValueError('generation configuration must be an object')
            clean = {'maxOutputTokens': count(config.get('maxOutputTokens'), 'output token limit', 1)}
            thinking = config.get('thinkingConfig', {})
            if not isinstance(thinking, dict):
                raise ValueError('thinking configuration must be an object')
            if 'thinkingBudget' in thinking:
                clean['thinkingConfig'] = {'thinkingBudget': count(thinking['thinkingBudget'], 'thinking budget')}
            elif 'thinkingLevel' in thinking:
                level = thinking['thinkingLevel']
                if not isinstance(level, str) or level not in {'MINIMAL', 'LOW', 'MEDIUM', 'HIGH'}:
                    raise ValueError('invalid thinking level')
                clean['thinkingConfig'] = {'thinkingLevel': level}
            if config.get('responseMimeType') == 'application/json':
                clean['responseMimeType'] = 'application/json'
            output['requested_generation_configs'][model] = clean
    return output


def numeric_trial(record):
    """Build a fresh object; never copy free-form strings or nested trace values."""
    if not isinstance(record, dict):
        raise ValueError('trial must be an object')
    model = identifier(record.get('model'), 'model')
    task = identifier(record.get('task_id'), 'task')
    arm = record.get('arm')
    if arm not in ARMS:
        raise ValueError('unknown trial arm')
    if type(record.get('success')) is not bool or type(record.get('anchor_preserved')) is not bool:
        raise ValueError('success and anchor fidelity must be booleans')
    responses = record.get('responses')
    tools = record.get('tools')
    if not isinstance(responses, list) or not isinstance(tools, list):
        raise ValueError('trial responses and tools must be lists')
    metrics: dict[str, Any] = dict.fromkeys(METRICS, 0)
    known_subtotals = dict.fromkeys(METRICS, 0)
    known_counts = dict.fromkeys(METRICS, 0)
    received = usage_bearing = failures = attempts = 0
    unknown_response_usage = False
    versions = set()
    statuses: Counter = Counter()
    skill_loaded = False
    for response in responses:
        if not isinstance(response, dict):
            raise ValueError('response receipt must be an object')
        usage = response.get('usage')
        got_response = response.get('received', usage is not None)
        if type(got_response) is not bool:
            raise ValueError('received flag must be boolean')
        if not got_response and usage is not None:
            raise ValueError('usage-bearing response cannot be marked unreceived')
        received += got_response
        http_failures = response.get('http_failures', [])
        if not isinstance(http_failures, list):
            raise ValueError('HTTP failure receipts must be a list')
        failures += len(http_failures)
        attempts += len(http_failures) + got_response
        for failure in http_failures:
            if not isinstance(failure, dict):
                raise ValueError('HTTP failure receipt must be an object')
            status = count(failure.get('http_status'), 'HTTP status')
            if status > 599:
                raise ValueError('invalid HTTP status')
            statuses[str(status)] += 1
        version = response.get('model_version')
        if version is not None:
            versions.add(identifier(version, 'model'))
        if usage is None or response.get('usage_error'):
            if got_response:
                unknown_response_usage = True
                metrics = dict.fromkeys(METRICS)
            continue
        if not isinstance(usage, dict):
            raise ValueError('usage must be an object or null')
        usage_bearing += 1
        for metric in METRICS:
            value = usage.get(metric)
            if value is None:
                metrics[metric] = None
            else:
                value = count(value, metric)
                known_subtotals[metric] += value
                known_counts[metric] += 1
                if metrics[metric] is not None:
                    metrics[metric] += value
    if not received:
        metrics = dict.fromkeys(METRICS)
    choices: Counter = Counter()
    test_modes: Counter = Counter()
    for tool in tools:
        if not isinstance(tool, dict) or not isinstance(tool.get('action', {}), dict):
            raise ValueError('tool receipt and action must be objects')
        action = tool.get('action', {})
        name = action.get('tool')
        path = action.get('path')
        skill_loaded |= name == 'read' and isinstance(path, str) and path.endswith('month-end/SKILL.md')
        choices[name if isinstance(name, str) and name in TOOLS else 'other'] += 1
        if name == 'test':
            mode = action.get('mode', 'full')
            test_modes[mode if isinstance(mode, str) and mode in {'full', 'quiet', 'receipt'} else 'other'] += 1
    wall = record.get('wall_seconds')
    if wall is not None and (type(wall) not in {int, float} or not math.isfinite(wall) or wall < 0):
        raise ValueError('invalid trial wall time')
    if record['success'] and not received:
        raise ValueError('accepted trial has no received model response')
    return {'requested_model': model, 'task_id': task, 'repeat': count(record.get('repeat'), 'repeat', 1),
            'arm': arm, 'accepted': int(record['success']), 'anchor_preserved': int(record['anchor_preserved']),
            'service_failed': int(bool(record.get('service_failure'))), 'received_trial': int(received > 0),
            'received_responses': received, 'usage_bearing_responses': usage_bearing,
            'response_slots': len(responses), 'http_attempts': attempts, 'http_failures': failures,
            'http_status_counts': dict(sorted(statuses.items())),
            'unknown_failure_usage': failures > 0,
            'unknown_response_usage': unknown_response_usage,
            'total_tokens_complete': received > 0 and metrics['total_tokens'] is not None and failures == 0,
            'reported_metrics': metrics,
            'known_reported_metric_subtotals': {metric: known_subtotals[metric] if known_counts[metric] else None
                                               for metric in METRICS},
            'known_metric_response_counts': known_counts, 'returned_models': sorted(versions),
            'tool_choice_counts': dict(sorted(choices.items())), 'test_mode_counts': dict(sorted(test_modes.items())),
            'skill_loaded': int(skill_loaded), 'wall_seconds': wall}


def aggregate(rows):
    metrics = {}
    known_subtotals = {}
    known_counts = {}
    for metric in METRICS:
        values = [row['reported_metrics'][metric] for row in rows]
        metrics[metric] = sum(values) if values and all(value is not None for value in values) else None
        known = [row['known_reported_metric_subtotals'][metric] for row in rows
                 if row['known_reported_metric_subtotals'][metric] is not None]
        known_subtotals[metric] = sum(known) if known else None
        known_counts[metric] = sum(row['known_metric_response_counts'][metric] for row in rows)
    wall = [row['wall_seconds'] for row in rows]
    choices: Counter = Counter()
    modes: Counter = Counter()
    statuses: Counter = Counter()
    for row in rows:
        choices.update(row['tool_choice_counts'])
        modes.update(row['test_mode_counts'])
        statuses.update(row['http_status_counts'])
    received_trials = sum(row['received_trial'] for row in rows)
    accepted = sum(row['accepted'] for row in rows)
    return {'attempted_trials': len(rows), 'accepted_trials': accepted,
            'success_rate_all_attempted': accepted / len(rows) if rows else None,
            'received_trials': received_trials,
            'accepted_received_trials': sum(row['accepted'] for row in rows if row['received_trial']),
            'success_rate_received_trials': accepted / received_trials if received_trials else None,
            'service_failed_trials': sum(row['service_failed'] for row in rows),
            'received_responses': sum(row['received_responses'] for row in rows),
            'usage_bearing_responses': sum(row['usage_bearing_responses'] for row in rows),
            'http_attempts': sum(row['http_attempts'] for row in rows),
            'http_failures': sum(row['http_failures'] for row in rows),
            'unknown_failure_usage': any(row['unknown_failure_usage'] for row in rows),
            'unknown_response_usage': any(row['unknown_response_usage'] for row in rows),
            'total_tokens_complete': bool(rows) and all(row['total_tokens_complete'] for row in rows),
            'anchor_failures': sum(1 - row['anchor_preserved'] for row in rows),
            'skill_loaded_trials': sum(row['skill_loaded'] for row in rows),
            'reported_metrics': metrics, 'known_reported_metric_subtotals': known_subtotals,
            'known_metric_response_counts': known_counts,
            'wall_seconds': sum(wall) if wall and all(v is not None for v in wall) else None,
            'returned_models': sorted({model for row in rows for model in row['returned_models']}),
            'tool_choice_counts': dict(sorted(choices.items())), 'test_mode_counts': dict(sorted(modes.items())),
            'http_status_counts': dict(sorted(statuses.items()))}


def statistics(pairs):
    baseline = [pair[0] for pair in pairs]
    month_end = [pair[1] for pair in pairs]
    b_success = sum(row['accepted'] for row in baseline)
    m_success = sum(row['accepted'] for row in month_end)
    quality_delta = (m_success - b_success) / len(pairs) if pairs else None
    complete = bool(pairs) and all(row['total_tokens_complete'] for row in baseline + month_end)
    b_ratio = m_ratio = delta = ratio = None
    if complete and b_success and m_success:
        b_ratio = sum(row['reported_metrics']['total_tokens'] for row in baseline) / b_success
        m_ratio = sum(row['reported_metrics']['total_tokens'] for row in month_end) / m_success
        delta = m_ratio - b_ratio
        ratio = m_ratio / b_ratio if b_ratio else None
    return {'success_rate_difference': quality_delta,
            'baseline_total_tokens_per_accepted_solve': b_ratio,
            'month_end_total_tokens_per_accepted_solve': m_ratio,
            'total_tokens_per_accepted_solve_difference': delta,
            'total_tokens_per_accepted_solve_ratio': ratio}


def clustered_comparison(pairs, draws=DRAWS, seed=SEED):
    clusters: dict[str, list[Any]] = defaultdict(list)
    for pair in pairs:
        clusters[pair[0]['task_id']].append(pair)
    point = statistics(pairs)
    result = {'paired_trials': len(pairs), 'original_task_clusters': len(clusters),
              'resampling_unit': 'original-task-with-all-paired-repeats', 'seed': seed,
              'bootstrap_draws': draws, 'point': point,
              'success_rate_difference_ci95': None,
              'total_tokens_per_accepted_solve_difference_ci95': None,
              'undefined_token_ratio_draws': 0,
              'baseline_pass_month_end_fail_pairs': sum(b['accepted'] and not m['accepted'] for b, m in pairs)}
    if len(clusters) < 3:
        result['interval_status'] = 'fewer_than_three_original_task_clusters'
        return result
    rng = random.Random(seed)
    values = list(clusters.values())
    success_samples = []
    token_samples = []
    token_available = point['total_tokens_per_accepted_solve_difference'] is not None
    for _ in range(draws):
        sample = [pair for cluster in rng.choices(values, k=len(values)) for pair in cluster]
        stat = statistics(sample)
        success_samples.append(stat['success_rate_difference'])
        if token_available:
            value = stat['total_tokens_per_accepted_solve_difference']
            if value is None:
                result['undefined_token_ratio_draws'] += 1
            else:
                token_samples.append(value)
    def interval(samples):
        ordered = sorted(samples)
        return [ordered[int(.025 * draws)], ordered[min(draws - 1, int(.975 * draws))]]
    result['success_rate_difference_ci95'] = interval(success_samples)
    if token_available and not result['undefined_token_ratio_draws']:
        result['total_tokens_per_accepted_solve_difference_ci95'] = interval(token_samples)
    result['interval_status'] = ('unknown_or_undefined_token_totals' if not token_available
                                 else 'undefined_token_resamples' if result['undefined_token_ratio_draws'] else 'available')
    return result


def analyze(summary):
    if not isinstance(summary, dict):
        raise ValueError('summary must be an object')
    protocol = protocol_identity(summary.get('protocol'))
    records = summary.get('records')
    deferred = summary.get('deferred_pairs', [])
    if not isinstance(records, list) or not isinstance(deferred, list):
        raise ValueError('records and deferred_pairs must be lists')
    planned = {(model, task, repeat) for model in protocol['models'] for task in protocol['tasks']
               for repeat in range(1, protocol['repeats'] + 1)}
    pairs: dict[tuple, dict[str, dict]] = {}
    rows = []
    for record in records:
        row = numeric_trial(record)
        key = (row['requested_model'], row['task_id'], row['repeat'])
        if key not in planned:
            raise ValueError('trial is outside the registered model/task/repeat plan')
        arms = pairs.setdefault(key, {})
        if row['arm'] in arms:
            raise ValueError('duplicate model/task/repeat arm')
        arms[row['arm']] = row
        rows.append(row)
    if any(set(arms) != set(ARMS) for arms in pairs.values()):
        raise ValueError('missing paired arm; do not discard incomplete pairs')
    deferred_keys = set()
    for item in deferred:
        if not isinstance(item, dict):
            raise ValueError('deferred pair must be an object')
        key = (identifier(item.get('model'), 'model'), identifier(item.get('task_id'), 'task'),
               count(item.get('repeat'), 'repeat', 1))
        if key not in planned or key in pairs or key in deferred_keys:
            raise ValueError('duplicate, attempted or unregistered deferred pair')
        deferred_keys.add(key)
    if set(pairs) | deferred_keys != planned:
        raise ValueError('unaccounted planned pairs must be explicitly deferred')
    by_model = {}
    for model in protocol['models']:
        model_rows = [row for row in rows if row['requested_model'] == model]
        complete_pairs = [(arms['baseline'], arms['month-end']) for key, arms in sorted(pairs.items()) if key[0] == model]
        by_model[model] = {'planned_pairs': len(protocol['tasks']) * protocol['repeats'],
                           'attempted_pairs': len(complete_pairs),
                           'deferred_pairs': sum(key[0] == model for key in deferred_keys),
                           'arms': {arm: aggregate([row for row in model_rows if row['arm'] == arm]) for arm in ARMS},
                           'paired_comparison': clustered_comparison(complete_pairs)}
    return {'format_version': 1, 'kind': 'sanitized-gemini-tool-workflow-analysis',
            'protocol': protocol, 'billed_cost_usd': None, 'cache_state': 'uncontrolled',
            'planned_pairs': len(planned), 'attempted_pairs': len(pairs),
            'deferred_pairs': len(deferred_keys), 'study_complete': not deferred_keys,
            'overall': aggregate(rows), 'by_model': by_model,
            'trials': sorted(rows, key=lambda row: (row['requested_model'], row['task_id'], row['repeat'], row['arm'])),
            'deferred_pair_ids': [{'requested_model': model, 'task_id': task, 'repeat': repeat}
                                  for model, task, repeat in sorted(deferred_keys)],
            'limitations': ['Provider-reported tokens are not billing; actual billed USD unavailable',
                            'Provider cache conditions uncontrolled; missing categories remain null',
                            'Failed trials and received failed-attempt usage are included',
                            'HTTP failure usage is unknown, so complete token ratios are withheld when needed',
                            'Service failures remain in all-attempted success; received-trial subgroup is separate',
                            'Intervals resample original task clusters, preserving paired arms and repeats',
                            'Synthetic public tasks and a custom tool harness, not independent native-host reproduction']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Private summary.json; raw content is never copied')
    parser.add_argument('--output', type=Path, required=True, help='Explicit new sanitized JSON file')
    args = parser.parse_args(argv)
    try:
        result = analyze(json.loads(args.input.read_text(encoding='utf-8')))
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write('\n')
        print('PASS: sanitized numeric workflow analysis written; private traces omitted')
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print('FAIL: ' + (str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
