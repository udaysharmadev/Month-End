#!/usr/bin/env python3
"""Compare paired baseline and Month End tasks. Never fabricate billed costs."""
from __future__ import annotations

import argparse
import csv
import math
import random
import re
import statistics
from pathlib import Path
from typing import Any

NUMS = ('cost_usd', 'input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens', 'turns', 'wall_seconds',
        'reasoning_tokens', 'uncached_input_tokens', 'tool_input_tokens', 'total_tokens', 'calls')
COUNTS = set(NUMS) - {'cost_usd', 'wall_seconds'}
METADATA = {'repo_commit', 'model', 'cache_state'}
CONDITIONS = ('provider', 'effort', 'harness', 'toolset', 'grading')


def to_float(raw):
    if raw is None or str(raw).strip() == '':
        return None
    val = float(raw)
    if not math.isfinite(val) or val < 0:
        raise ValueError('negative or non-finite numeric metric')
    return val


def load(path, require_metadata=False):
    groups: dict[tuple[str, int, str | None], dict[str, dict[str, Any]]] = {}
    with Path(path).open(newline='', encoding='utf-8') as f:
        rows = csv.DictReader(f, strict=True)
        fields = rows.fieldnames or []
        if len(fields) != len(set(fields)):
            raise ValueError('duplicate CSV column names')
        if not {'task_id', 'arm', 'success'}.issubset(fields):
            raise ValueError('required fields: task_id,arm,success')
        present = METADATA.intersection(fields)
        if (present or require_metadata) and present != METADATA:
            raise ValueError('metadata requires all of repo_commit,model,cache_state')
        for row in rows:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'CSV row {rows.line_num} does not match the header column count')
            key = row['task_id'].strip()
            repeat_raw = row.get('repeat', '1').strip()
            if not repeat_raw.isdecimal() or int(repeat_raw) < 1:
                raise ValueError('repeat must be a positive integer')
            repeat = int(repeat_raw)
            arm = row['arm'].strip().lower()
            if not key or arm not in {'baseline', 'month-end'}:
                raise ValueError('invalid task_id/arm; allowed arms baseline and month-end')
            if row['success'].strip().lower() not in {'0', '1', 'true', 'false'}:
                raise ValueError('success must be 0/1/true/false')
            state: dict[str, Any] = {'success': row['success'].strip().lower() in {'1', 'true'},
                     'task_id': key, 'repeat': repeat,
                     'source_sha256': row.get('source_sha256', '').strip() or None}
            state.update({field: row.get(field, '').strip() or None for field in CONDITIONS})
            for field in METADATA:
                state[field] = row[field].strip() if present else None
            if present:
                if not state['model']:
                    raise ValueError(f'empty model metadata for task {key}')
                state['repo_commit'] = state['repo_commit'].lower()
                snapshot = state['source_sha256']
                if snapshot is not None and not re.fullmatch(r'[a-f0-9]{64}', snapshot):
                    raise ValueError('source_sha256 must be a full lowercase SHA-256 fingerprint')
                if not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', state['repo_commit']) and not (not state['repo_commit'] and snapshot):
                    raise ValueError('repo_commit metadata must be a full 40- or 64-character Git commit hash')
                state['cache_state'] = state['cache_state'].lower()
                if state['cache_state'] not in {'cold', 'warm'}:
                    raise ValueError('cache_state metadata must be cold or warm; analyze unknown conditions separately')
            for metric in NUMS:
                state[metric] = to_float(row.get(metric))
                if metric in COUNTS and state[metric] is not None and not state[metric].is_integer():
                    raise ValueError(f'{metric} must be a whole-number count')
            pair_key = (key, repeat, state['cache_state'])
            groups.setdefault(pair_key, {})
            if arm in groups[pair_key]:
                raise ValueError(f'duplicate arm {arm} for task {key}: supply one pair per task')
            groups[pair_key][arm] = state
    complete = [(k[0] if 'repeat' not in fields else f'{k[0]}[repeat={k[1]},cache={k[2]}]', a['baseline'], a['month-end'])
                for k,a in groups.items() if len(a) == 2]
    incomplete = [k for k,a in groups.items() if len(a) != 2]
    if incomplete:
        raise ValueError('incomplete task/repeat/cache_state pairs: ' + ', '.join(str(key) for key in sorted(incomplete)))
    if not complete:
        raise ValueError('no paired tasks found')
    for task, baseline, optimized in complete:
        for field in METADATA | {'source_sha256'} | set(CONDITIONS):
            if baseline[field] != optimized[field]:
                raise ValueError(f'mismatched {field} metadata for task {task}')
    frozen: dict[str, tuple[Any, ...]] = {}
    for _, baseline, _ in complete:
        task = baseline['task_id']
        identity = (baseline['model'], baseline['repo_commit'], baseline['source_sha256'],
                    *(baseline[field] for field in CONDITIONS))
        if task in frozen and frozen[task] != identity:
            raise ValueError(f'task model/source metadata changes between repeats: {task}')
        frozen[task] = identity
    return sorted(complete), incomplete


def summarize(rows, arm):
    vals = [r[1 if arm == 'baseline' else 2] for r in rows]
    successes = sum(v['success'] for v in vals)
    costs = [v['cost_usd'] for v in vals]
    print(f'{arm}: tasks={len(vals)} success={successes} ({100*successes/len(vals):.1f}%)')
    if all(x is not None for x in costs):
        print(f'  billed_total_usd=${sum(costs):.4f} billed_usd_per_success={"$"+format(sum(costs)/successes, ".4f") if successes else "undefined (0 successes)"}')
    else:
        print('  billed_usd_per_success=UNAVAILABLE (missing provider-billed dollars; no simulated cost)')
    for metric in NUMS[1:]:
        avail = [v[metric] for v in vals if v[metric] is not None]
        if len(avail) == len(vals):
            print(f'  {metric}: total={sum(avail):.0f} mean={statistics.mean(avail):.1f}')


def task_clusters(rows):
    clusters: dict[str, list[Any]] = {}
    for row in rows:
        clusters.setdefault(row[1].get('task_id', row[0]), []).append(row)
    return list(clusters.values())


def resample_clusters(clusters, rand):
    return [row for cluster in rand.choices(clusters, k=len(clusters)) for row in cluster]


def delta_ci(rows, field, seed=2026, iterations=1500):
    pairs = [(b[field], m[field]) for _, b, m in rows]
    if any(x is None or y is None for x,y in pairs):
        return None
    diffs = [y-x for x,y in pairs]
    clusters = task_clusters(rows)
    if len(clusters) < 3:
        return statistics.mean(diffs), None
    rand = random.Random(seed)
    stats = sorted(statistics.mean(m[field] - b[field] for _, b, m in resample_clusters(clusters, rand)) for _ in range(iterations))
    return statistics.mean(diffs), (stats[int(.025 * iterations)], stats[int(.975 * iterations)])


def cost_per_success_delta(rows, seed=2026, iterations=1500):
    """Difference of spending/success ratios; preserve each task's paired arms."""
    if any(b['cost_usd'] is None or m['cost_usd'] is None for _, b, m in rows):
        return None

    def difference(sample):
        baseline_successes = sum(b['success'] for _, b, _ in sample)
        optimized_successes = sum(m['success'] for _, _, m in sample)
        if not baseline_successes or not optimized_successes:
            return None
        baseline_cost = sum(b['cost_usd'] for _, b, _ in sample)
        optimized_cost = sum(m['cost_usd'] for _, _, m in sample)
        return optimized_cost / optimized_successes - baseline_cost / baseline_successes

    estimate = difference(rows)
    clusters = task_clusters(rows)
    if estimate is None or len(clusters) < 3:
        return estimate, None, 0
    rand = random.Random(seed)
    samples = [difference(resample_clusters(clusters, rand)) for _ in range(iterations)]
    undefined = sum(value is None for value in samples)
    # Dropping undefined ratios would condition on successful resamples and bias
    # the interval. Report the failure count and withhold that interval instead.
    if undefined:
        return estimate, None, undefined
    ordered = sorted(samples)
    return estimate, (ordered[int(.025 * iterations)], ordered[int(.975 * iterations)]), 0


def report(rows, seed, iterations):
    print(f'independent_tasks={len(task_clusters(rows))} paired_trials={len(rows)} resampling=original-task-clusters')
    summarize(rows, 'baseline')
    summarize(rows, 'month-end')
    lost = sum(b['success'] and not m['success'] for _, b, m in rows)
    if lost:
        print(f'QUALITY GATE: NOT MET ({lost} task(s) passed baseline but failed with Month End); do not claim an efficiency win.')
    primary = cost_per_success_delta(rows, seed, iterations)
    if primary is None:
        print('primary_delta(billed_usd_per_success)=UNAVAILABLE (missing billed dollars)')
    else:
        estimate, interval, undefined = primary
        if estimate is None:
            print('primary_delta(billed_usd_per_success)=UNDEFINED (an arm has 0 successes)')
        else:
            print(f'primary_delta(billed_usd_per_success)={estimate:+.4f} [month-end minus baseline]')
            if interval is not None:
                print(f'  bootstrap95CI=[{interval[0]:+.4f},{interval[1]:+.4f}] seed={seed} resamples={iterations}')
            elif undefined:
                print(f'  bootstrap95CI=UNAVAILABLE ({undefined}/{iterations} resamples have 0 successes in an arm)')
            else:
                print('  bootstrap95CI=UNAVAILABLE (n<3 independent task clusters)')
    for field in ('cost_usd', 'input_tokens', 'output_tokens', 'turns', 'wall_seconds'):
        result = delta_ci(rows, field, seed, iterations)
        if result:
            mean, ci = result
            suffix = f' bootstrap95CI=[{ci[0]:+.4f},{ci[1]:+.4f}]' if ci is not None else ' (n<3; no CI)'
            print(f'paired_mean_delta({field})={mean:+.4f} [month-end minus baseline]{suffix}')


def main(argv=None):
    p = argparse.ArgumentParser(description='Paired, success-aware token-efficiency audit from actual run data.')
    p.add_argument('csv_file')
    p.add_argument('--require-metadata', action='store_true', help='Require matching repo_commit, model and cold/warm cache_state for each pair')
    p.add_argument('--seed', type=int, default=2026, help='Paired bootstrap seed')
    p.add_argument('--bootstrap-samples', type=int, default=1500, help='At least 100 resamples (default: 1500)')
    a = p.parse_args(argv)
    if a.bootstrap_samples < 100:
        p.error('--bootstrap-samples must be at least 100')
    try:
        rows, incomplete = load(a.csv_file, require_metadata=a.require_metadata)
    except (ValueError, OSError, csv.Error) as e:
        p.error(str(e))
    print(f'MONTH END PAIRED EVALUATION | complete_pairs={len(rows)} excluded_incomplete={len(incomplete)}')
    if rows[0][1]['model'] is None:
        print('metadata=UNAVAILABLE (model/revision/cache comparability was not checked; use --require-metadata for live evaluation)')
        report(rows, a.seed, a.bootstrap_samples)
    else:
        print('metadata=MATCHED (self-reported model/revision/cache conditions; actual provider behavior is not verified)')
        strata: dict[tuple[str, ...], list[Any]] = {}
        for row in rows:
            key = (row[1]['model'], row[1]['cache_state'], *(row[1][field] or '' for field in CONDITIONS))
            strata.setdefault(key, []).append(row)
        for condition, pairs in sorted(strata.items()):
            model, cache_state = condition[:2]
            print(f'STRATUM model={model} cache_state={cache_state} pairs={len(pairs)}')
            labels = [f'{field}={value}' for field, value in zip(CONDITIONS, condition[2:]) if value]
            if labels:
                print('conditions: ' + ' '.join(labels))
            report(pairs, a.seed, a.bootstrap_samples)
    print('WARNING: confidence intervals are exploratory, original-task cluster bootstrap; repeats stay together. Independent task grading and comparable model/cache conditions required.')
    print('No claim of net savings is valid without equal success/quality safeguards and actual billing where available.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
