#!/usr/bin/env python3
"""Shared bounded developer subprocesses; generated code requires OS isolation.

AST checks are defense in depth, never a substitute for the macOS sandbox.
Portable trusted-fixture checks may use the runner without require_isolation.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAX_TOOL_BYTES = 48_000


def bounded_subprocess(argv, workspace, timeout=15, *, read_paths=(), require_isolation=False):
    workspace = Path(workspace).resolve()
    if require_isolation and (sys.platform != 'darwin' or not shutil.which('sandbox-exec')):
        raise ValueError('generated-code execution requires the macOS sandbox')
    environment = {'PATH': os.defpath, 'HOME': str(workspace), 'TMPDIR': str(workspace),
                   'PYTHONHASHSEED': '0'}
    if sys.platform == 'darwin' and shutil.which('sandbox-exec'):
        read_roots = {str(workspace), str(Path(sys.base_prefix).resolve()), str(Path(sys.prefix).resolve()),
                      '/System', '/usr', '/Library', '/dev'}
        allowed_reads = ''.join('(subpath ' + json.dumps(path) + ')' for path in sorted(read_roots))
        exact_files = {str(path.resolve()) for path in (*read_paths, Path('/private/etc/localtime'))}
        # Homebrew's C decimal extension links a separately installed mpdecimal
        # library. Denying it silently selects the slower Python fallback and
        # changes high-precision grading behavior. Admit only trusted runtime
        # dependency files, not all package-manager configuration/data.
        import _decimal
        extension = getattr(_decimal, '__file__', None)
        if extension:
            dependency_check = subprocess.run(['/usr/bin/otool', '-L', extension],
                                              env={'PATH': os.defpath}, capture_output=True,
                                              text=True, timeout=5, check=True)
            for line in dependency_check.stdout.splitlines()[1:]:
                dependency = line.strip().split(' (', 1)[0]
                if Path(dependency).is_absolute():
                    exact_files.update({dependency, str(Path(dependency).resolve())})
        # macOS runtime startup reads ancestor directory entries. Literal
        # directory access admits their names, not arbitrary descendant files.
        ancestors = {str(parent) for path in read_roots | exact_files for parent in Path(path).parents}
        allowed_reads += ''.join('(literal ' + json.dumps(path) + ')'
                                 for path in sorted(exact_files | ancestors))
        profile = ('(version 1)(allow default)(deny network*)'
                   '(deny file-write* (require-not (subpath ' + json.dumps(str(workspace)) + ')))'
                   '(deny file-read-data (require-not (require-any ' + allowed_reads + ')))')
        argv = ['sandbox-exec', '-p', profile, *argv]
    output: dict[str, Any] = {}
    with subprocess.Popen(argv, cwd=workspace, env=environment, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, start_new_session=os.name == 'posix') as process:
        def collect(name, stream):
            retained = bytearray()
            count = 0
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                count += len(chunk)
                retained.extend(chunk)
                if len(retained) > MAX_TOOL_BYTES:
                    del retained[:-MAX_TOOL_BYTES]
            prefix = '[output exceeds tool budget; showing tail; use narrower or quiet mode]\n' if count > MAX_TOOL_BYTES else ''
            rendered = prefix + retained.decode('utf-8', errors='replace')
            for private, public in ((str(workspace), '<WORKSPACE>'), (str(ROOT), '<PROJECT>'),
                                    (sys.executable, '<PYTHON>'), (sys.base_prefix, '<PYTHON_RUNTIME>')):
                rendered = rendered.replace(private, public)
            output[name] = rendered

        readers = [threading.Thread(target=collect, args=(name, stream), daemon=True)
                   for name, stream in (('stdout', process.stdout), ('stderr', process.stderr))]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            if os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                process.kill()
            process.wait()
            for reader in readers:
                reader.join(timeout=5)
        if timed_out:
            output['stderr'] = output.get('stderr', '') + '\nbounded tool timed out'
        return {'exit': 124 if timed_out else process.returncode, **output}


def require_sandbox():
    """Fail before credentials or API calls if candidate isolation cannot run."""
    if sys.platform != 'darwin' or not shutil.which('sandbox-exec'):
        raise ValueError('live candidate execution requires the macOS sandbox; plan/analysis are portable')
    with tempfile.TemporaryDirectory(prefix='month-end-sandbox-check-') as temporary:
        workspace = Path(temporary).resolve() / 'workspace'
        workspace.mkdir()
        outside = workspace.parent / 'outside.txt'
        outside.write_text('synthetic isolation sentinel', encoding='utf-8')
        code = ('from pathlib import Path\nimport socket\n'
                'def denied(operation):\n'
                '    try:\n        operation()\n'
                '    except PermissionError:\n        return\n'
                '    raise SystemExit("sandbox allowed a forbidden operation")\n'
                'def bind_socket():\n'
                '    with socket.socket() as sock:\n        sock.bind(("127.0.0.1", 0))\n'
                'path = Path(' + repr(str(outside)) + ')\n'
                'denied(path.read_text)\n'
                'denied(lambda: path.write_text("unexpected mutation"))\n'
                'denied(bind_socket)\n'
                'print("isolation-ready")\n')
        result = bounded_subprocess([sys.executable, '-I', '-c', code], workspace)
        if result['exit'] != 0 or result.get('stdout', '').strip() != 'isolation-ready':
            raise ValueError('macOS sandbox preflight failed; candidate execution is unavailable in this environment')
