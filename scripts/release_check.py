#!/usr/bin/env python3
"""Read-only release checks; optionally run the complete local test suite."""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from build_release import source_files
from validate_package import check_links, validate_package


def check_source_register(root: Path, as_of: date) -> dict:
    registry = json.loads((root / 'docs' / 'source-register.json').read_text(encoding='utf-8'))
    interval = registry.get('review_interval_days')
    if registry.get('format_version') != 1 or not isinstance(interval, int) or not 1 <= interval <= 366:
        raise ValueError('invalid source-register format or review interval')
    statuses = {'verified', 'abstract_reviewed', 'identity_reviewed', 'anecdote_reviewed', 'unavailable'}
    seen = set()
    for record in registry.get('sources', []):
        key = record.get('id')
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError('duplicate or missing source ID')
        seen.add(key)
        if record.get('status') not in statuses or not str(record.get('url', '')).startswith('https://'):
            raise ValueError(f'invalid source status or URL: {key}')
        if not record.get('review_scope') or not record.get('title'):
            raise ValueError(f'missing source identity or review scope: {key}')
        checked = date.fromisoformat(record['checked_on'])
        age = (as_of - checked).days
        if age < 0 or age > interval:
            raise ValueError(f'source review is future-dated or stale: {key} (checked {checked})')
    if not seen:
        raise ValueError('empty source register')
    for mechanism in registry.get('mechanisms', []):
        if not set(mechanism.get('source_ids', [])).issubset(seen):
            raise ValueError('mechanism refers to an unknown source ID')
    return registry


def check_release(root: Path, run_tests: bool = False, as_of: date | None = None) -> dict:
    root = Path(root).resolve()
    validate_package(root)
    files = source_files(root)
    check_source_register(root, as_of or datetime.now(timezone.utc).date())
    for name in files:
        if name.endswith('.md'):
            check_links(root / name, root)
    runtime = root / 'skills' / 'month-end' / 'scripts'
    # Check imports without importing or executing the files under review.
    prohibited = {'requests', 'httpx', 'urllib.request', 'socket', 'boto3', 'keyring'}
    for path in sorted(runtime.glob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path), feature_version=(3, 9))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            if any(module in prohibited or module.split('.')[0] in prohibited for module in modules):
                raise ValueError(f'network/credential import needs separate explicit review: {path.name}')
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {'run', 'Popen', 'call', 'check_call', 'check_output'}:
                    for keyword in node.keywords:
                        if keyword.arg == 'shell' and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is False):
                            raise ValueError(f'nonliteral shell=False subprocess policy: {path.name}:{node.lineno}')
    if run_tests:
        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=root, shell=False)
        if result.returncode:
            raise ValueError(f'local tests failed with exit {result.returncode}')
    return {'files_reviewed': len(files), 'runtime_files_reviewed': len(list(runtime.glob('*.py'))),
            'tests_run': run_tests, 'security_scope': 'static heuristics; not an external security audit'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--tests', action='store_true', help='Also run all local unittest checks')
    parser.add_argument('--as-of', type=date.fromisoformat, help='Explicit date for source-review freshness; default UTC date')
    arguments = parser.parse_args(argv)
    try:
        result = check_release(arguments.root, arguments.tests, arguments.as_of)
    except (OSError, ValueError, SyntaxError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    print(f'PASS: package/resources/security heuristics across {result["files_reviewed"]} release files; '
          f'tests_run={str(result["tests_run"]).lower()}')
    print('Static checks are bounded heuristics, not proof of no vulnerabilities or valid live savings.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
