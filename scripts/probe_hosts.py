#!/usr/bin/env python3
"""Check Codex skill discovery through its local app-server, with zero model calls."""
from __future__ import annotations

import argparse
import json
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


def probe_codex(project: Path, timeout: float = 20.0) -> dict:
    executable = shutil.which('codex')
    if executable is None:
        raise ValueError('Codex CLI is not installed')
    project = project.expanduser().resolve()
    if not project.is_dir():
        raise ValueError('project does not exist')
    with subprocess.Popen([executable, '-c', 'analytics.enabled=false', 'app-server', '--stdio'],
                          cwd=project, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL) as process:
        messages: queue.Queue = queue.Queue(maxsize=128)
        assert process.stdin is not None and process.stdout is not None

        def consume():
            assert process.stdout is not None
            while True:
                raw = process.stdout.readline(1_000_001)
                if not raw:
                    messages.put({'local_error': 'app-server closed its output'})
                    return
                if len(raw) > 1_000_000:
                    messages.put({'local_error': 'app-server response exceeded the byte bound'})
                    return
                try:
                    messages.put(json.loads(raw))
                except ValueError:
                    messages.put({'local_error': 'app-server returned invalid JSON'})
                    return

        reader = threading.Thread(target=consume, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout

        def send(method, params=None, identifier=None):
            message = {'method': method}
            if params is not None:
                message['params'] = params
            if identifier is not None:
                message['id'] = identifier
            assert process.stdin is not None
            process.stdin.write((json.dumps(message) + '\n').encode())
            process.stdin.flush()

        def receive(identifier):
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('local app-server discovery timed out')
                try:
                    message = messages.get(timeout=remaining)
                except queue.Empty as error:
                    raise ValueError('local app-server discovery timed out') from error
                if not isinstance(message, dict):
                    raise ValueError('invalid app-server message')
                if 'local_error' in message:
                    raise ValueError(message['local_error'])
                if message.get('id') != identifier:
                    continue
                if 'error' in message:
                    raise ValueError('app-server rejected ' + str(message['error']))
                return message.get('result')

        try:
            send('initialize', {'clientInfo': {'name': 'month-end-discovery-check', 'version': '1.0.0'},
                                'capabilities': {'experimentalApi': True}}, 1)
            receive(1)
            send('initialized')
            send('skills/list', {'cwds': [str(project)], 'forceReload': True}, 2)
            result = receive(2)
            if not isinstance(result, dict) or not isinstance(result.get('data'), list):
                raise ValueError('app-server returned an invalid skills list')
            matches = []
            for entry in result['data']:
                for skill in entry.get('skills', []):
                    if skill.get('name') != 'month-end':
                        continue
                    path = Path(skill['path']).resolve()
                    if path.is_relative_to(project):
                        matches.append({'name': skill['name'], 'enabled': skill['enabled'],
                                        'scope': skill['scope'], 'path': path.relative_to(project).as_posix()})
            if len(matches) != 1 or matches[0].get('enabled') is not True:
                raise ValueError('the project Month End skill was not uniquely discovered and enabled')
            return {'host': 'codex', 'status': 'pass', 'check': 'local-skill-discovery',
                    'model_calls': 0, 'skill': matches[0]}
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, help='Explicit new result file; default stdout only')
    args = parser.parse_args(argv)
    try:
        result = probe_codex(args.project)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x', encoding='utf-8') as stream:
                json.dump(result, stream, indent=2)
                stream.write('\n')
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
