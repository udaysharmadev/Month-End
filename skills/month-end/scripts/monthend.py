#!/usr/bin/env python3
"""Month End: conservative, local context hygiene helpers. No external dependencies."""
from __future__ import annotations

import argparse
import ast
import collections
import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

VERSION = '1.0.0'
IGNORES = {'.git', 'node_modules', '.next', 'dist', 'build', 'coverage', '__pycache__', '.venv', 'vendor', '.turbo', 'target'}
CONFIG = {'AGENTS.md', 'CLAUDE.md', 'GEMINI.md', 'SKILL.md'}
IMPORTANT = re.compile(r'(?i)(error|fail(?:ed|ure)?|exception|traceback|panic|warning|warn:|fatal|assertion|\b[1-9]\d* failed\b|security|vulnerab|not found|denied)')
SUMMARY = re.compile(r'(?i)(\d+ passed|\d+ failed|test(?:s)? passed|test(?:s)? failed|built in|build complete|compilation finished|successfully|\bSUCCESS\b|\bFAILURE\b|test suites?:|tests?:|ran \d+ tests|\d+ warnings?)')
ANSI = re.compile(rb'\x1b\[[0-?]*[ -/]*[@-~]')
AGENT_DIRS = {'.agents', '.claude', '.codex', '.gemini'}
PROFILES = {
    'generic': ([], []),
    'pytest': ([r'^FAILED\s', r'^E\s+'], [r'=+.*\d+ (?:passed|failed|skipped)']),
    'vitest': ([r'[❯×]\s.*(?:test|spec|>)', r'^\s*Expected:', r'^\s*Received:'], [r'Test Files', r'Duration']),
    'npm': ([r'npm (?:ERR!|error)', r'ERR_PNPM', r'\bTS\d{4}:'], [r'^>\s', r'packages? (?:audited|added)']),
    'cargo': ([r'^error\[', r'^\s*--> ', r'^test .*FAILED'], [r'test result:', r'^\s*Finished ']),
    'go': ([r'^--- FAIL:', r'^FAIL\s', r'^#\s'], [r'^ok\s', r'^\?\s']),
    'ci': ([r'^::(?:error|warning)', r'^##\[error\]'], [r'^::(?:notice|group)', r'job .*completed']),
}
OutputLine = tuple[int, str, int, int, int]


def safe_root(raw: str) -> Path:
    p = Path(raw).expanduser().resolve()
    if not p.is_dir():
        raise ValueError(f'Not a directory: {p}')
    return p


def cmd_locate(a: argparse.Namespace) -> int:
    root = safe_root(a.root)
    rg = shutil.which('rg')
    names: list[str] = []
    if rg:
        cmd = [rg, '-l', '--null', '--fixed-strings', '--max-count', '1', '--color', 'never', '--max-filesize', str(a.max_scan_bytes)]
        for ignored in sorted(IGNORES):
            cmd.extend(['--glob', f'!**/{ignored}/**'])
        cmd.extend(['-e', a.pattern, '--', '.'])
        # Stop after one extra path instead of buffering the entire match catalog.
        with subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE) as search:
            assert search.stdout is not None
            pending = bytearray()
            try:
                while len(names) <= a.limit:
                    byte = search.stdout.read(1)
                    if not byte:
                        break
                    if byte == b'\x00':
                        names.append(os.fsdecode(bytes(pending)))
                        pending.clear()
                    else:
                        pending.extend(byte)
                        if len(pending) > 65536:
                            raise ValueError('search path exceeds the supported path budget')
                limited = len(names) > a.limit
                if limited:
                    search.terminate()
                code = search.wait()
                if not limited and code not in (0, 1):
                    return code
            finally:
                if search.poll() is None:
                    search.terminate()
                    search.wait()
    else:
        names = []
        for base, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if d not in IGNORES and not d.startswith('.')]
            for filename in files:
                if len(names) >= a.limit + 1:
                    break
                if filename.startswith('.'):
                    continue
                path = Path(base) / filename
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                    with path.open('rb') as source:
                        raw = source.read(a.max_scan_bytes + 1)
                    if len(raw) > a.max_scan_bytes or b'\x00' in raw:
                        continue
                    if a.pattern.encode('utf-8') in raw:
                        names.append(str(path.relative_to(root)))
                except (OSError, UnicodeError):
                    continue
            if len(names) >= a.limit + 1:
                break
    if not a.null and any('\n' in name or '\r' in name for name in names[:a.limit]):
        raise ValueError('a matching path contains a newline; use --null for unambiguous paths')
    for name in names[:a.limit]:
        print(name, end='\x00' if a.null else '\n')
    print(f'[month-end] matches_shown={min(len(names), a.limit)}'
          f' more_results={str(len(names) > a.limit).lower()} search=literal', file=sys.stderr)
    if len(names) > a.limit:
        print('[month-end] Too many matches; narrow pattern or search directory, do not assume completeness.', file=sys.stderr)
    if not rg:
        print('[month-end] Fallback skips hidden paths, symlinks, NUL-containing files and files above --max-scan-bytes; .gitignore rules are not applied.', file=sys.stderr)
    return 0


def read_source(file: str, max_file_bytes: int) -> tuple[Path, str, list[str]]:
    path = Path(file).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f'Not a file: {path}')
    with path.open('rb') as source:
        raw = source.read(max_file_bytes + 1)
    if len(raw) > max_file_bytes:
        raise ValueError(f'File exceeds {max_file_bytes} bytes: narrow by another search tool or increase explicit bound.')
    if b'\x00' in raw:
        raise ValueError('Refusing to render binary or NUL-containing file.')
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as error:
        raise ValueError('Exact excerpts require valid UTF-8; no replacement characters or partial code returned.') from error
    # Only actual source newlines count; str.splitlines also splits inside strings
    # containing Unicode separators, vertical tabs and form feeds.
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if lines[-1] == '':
        lines.pop()
    return path, text, lines


def render_source(lines: list[str], selected, max_lines: int, max_bytes: int) -> int:
    indices = sorted(set(selected))
    if len(indices) > max_lines:
        print(f'[month-end] would require {len(indices)} lines; narrow pattern/context or increase --max-lines. No partial code returned.', file=sys.stderr)
        return 3
    result = ''.join(f'{index + 1:>6} | {lines[index]}\n' for index in indices)
    size = len(result.encode('utf-8'))
    if size > max_bytes:
        print(f'[month-end] exact excerpt requires {size} bytes, limit is {max_bytes}; narrow or increase explicit budget. No truncated code returned.', file=sys.stderr)
        return 3
    print(result, end='')
    return 0


def cmd_excerpt(a: argparse.Namespace) -> int:
    path, _, lines = read_source(a.file, a.max_file_bytes)
    needle = re.compile(a.pattern if a.regex else re.escape(a.pattern), 0 if a.case_sensitive else re.IGNORECASE)
    indices = [i for i, line in enumerate(lines) if needle.search(line)]
    if not indices:
        print('[month-end] pattern not found; widen search. No code excerpt was assumed.')
        return 1
    selected: set[int] = set()
    for i in indices[:a.max_matches]:
        selected.update(range(max(0, i - a.context), min(len(lines), i + a.context + 1)))
    result = render_source(lines, selected, a.max_lines, a.max_bytes)
    if result:
        return result
    print(f'[month-end] source={path} matched_lines={len(indices)} shown_matches={min(len(indices), a.max_matches)} exact=true')
    return 0


def cmd_symbol(a: argparse.Namespace) -> int:
    path, text, lines = read_source(a.file, a.max_file_bytes)
    if path.suffix not in {'.py', '.pyi'}:
        raise ValueError('Built-in AST retrieval supports Python; use your host LSP for this language, then excerpt exact lines.')
    try:
        tree = ast.parse(text.removeprefix('\ufeff'), filename=str(path))
    except SyntaxError as error:
        raise ValueError(f'Python AST parse failed at line {error.lineno}: {error.msg}') from error
    definitions = []

    def visit(node, prefix=''):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = prefix + node.name
            definitions.append((name, node))
            prefix = name + '.'
        for child in ast.iter_child_nodes(node):
            visit(child, prefix)

    visit(tree)
    matches = [(name, node) for name, node in definitions
               if name == a.name or ('.' not in a.name and name.rsplit('.', 1)[-1] == a.name)]
    if not matches:
        print('[month-end] symbol not found; widen search.', file=sys.stderr)
        return 1
    if len(matches) != 1:
        raise ValueError('ambiguous symbol; use a qualified name: ' + ', '.join(name for name, _ in matches[:20]))
    name, node = matches[0]
    start = min([node.lineno] + [item.lineno for item in node.decorator_list]) - 1
    end = node.end_lineno
    if end is None:
        raise ValueError('AST did not supply an exact end line; use host LSP plus excerpt')
    selected = range(max(0, start - a.context), min(len(lines), end + a.context))
    result = render_source(lines, selected, a.max_lines, a.max_bytes)
    if not result:
        print(f'[month-end] source={path} symbol={name} language=python exact=true')
    return result


def diagnostic_rules(a: argparse.Namespace, argv: list[str]):
    profile = a.profile
    if profile == 'auto':
        command = Path(argv[0]).name.lower().removesuffix('.exe')
        if command.startswith('pytest') or ('-m' in argv and 'pytest' in argv):
            profile = 'pytest'
        elif 'vitest' in argv or command == 'vitest':
            profile = 'vitest'
        elif command in {'npm', 'pnpm', 'yarn', 'bun'}:
            profile = 'npm'
        elif command == 'cargo':
            profile = 'cargo'
        elif command == 'go' and 'test' in argv:
            profile = 'go'
        else:
            profile = 'generic'
    important, summary = PROFILES[profile]
    important, summary = list(important), list(summary)
    if a.profile_config:
        with Path(a.profile_config).expanduser().open('rb') as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            raise ValueError('profile config exceeds 64 KiB')
        config = json.loads(raw)
        if not isinstance(config, dict) or set(config) - {'important', 'summary'}:
            raise ValueError('profile config fields are important and summary regex lists')
        for key, target in [('important', important), ('summary', summary)]:
            values = config.get(key, [])
            if not isinstance(values, list) or len(values) > 20 or any(not isinstance(value, str) or len(value) > 512 for value in values):
                raise ValueError(f'{key} must contain at most 20 regex strings of at most 512 characters')
            target.extend(values)
    return profile, [IMPORTANT] + [re.compile(rule, re.I) for rule in important], [SUMMARY] + [re.compile(rule, re.I) for rule in summary]


def cmd_run(a: argparse.Namespace) -> int:
    argv = list(a.command)
    if argv and argv[0] == '--':
        argv = argv[1:]
    if not argv:
        raise ValueError('Provide command after --, e.g. run --kind tests -- python3 -m unittest -q')
    if a.log_index and not a.log:
        raise ValueError('--log-index requires an explicit --log path')
    if a.log_index and Path(a.log_index).expanduser().resolve() == Path(a.log).expanduser().resolve():
        raise ValueError('raw log and index must use different paths')
    profile, important_rules, summary_rules = diagnostic_rules(a, argv)
    digest = hashlib.sha256()
    raw_total = 0
    lines_total = 0
    top = []
    last: collections.deque[OutputLine] = collections.deque(maxlen=30)
    key_lines: list[list[OutputLine]] = [[], []]  # Separate budgets protect errors from passing summaries.
    key_bytes = [0, 0]
    oversized = 0
    nontext = 0
    important_seen = False
    discarding = False
    scan_tail = b''
    line_start = 0
    ranges = []
    small = []
    small_limit = min(a.min_savings_bytes, a.max_bytes)
    with contextlib.ExitStack() as resources:
        # Validate the explicit log destination before a command can have effects.
        log_handle = resources.enter_context(Path(a.log).expanduser().open('xb')) if a.log else None
        index_handle = resources.enter_context(Path(a.log_index).expanduser().open('x', encoding='utf-8')) if a.log_index else None
        try:
            # Never use shell=True; preserve argv and the inherited environment.
            proc = resources.enter_context(subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT))
        except OSError as error:
            if index_handle is not None:
                json.dump({'format_version': 1, 'command_started': False, 'exit': 127,
                           'sha256': digest.hexdigest(), 'raw_bytes': 0, 'displayed_ranges': []}, index_handle)
            print(f'[month-end] Failed to start command: {error}', file=sys.stderr)
            return 127
        assert proc.stdout is not None
        try:
            while True:
                # A line can be gigabytes long. Drain it in bounded pieces, saving
                # every raw byte only to the explicit log and omitting the whole line.
                raw_line = proc.stdout.readline(a.max_bytes + 1)
                if not raw_line:
                    break
                raw_total += len(raw_line)
                if log_handle is not None:
                    log_handle.write(raw_line)
                    if index_handle is not None:
                        digest.update(raw_line)
                probe = scan_tail + raw_line
                important_seen |= any(rule.search(ANSI.sub(b'', probe).decode('utf-8', errors='replace')) for rule in important_rules)
                scan_tail = probe[-128:]
                if discarding or len(raw_line) > a.max_bytes:
                    discarding = not raw_line.endswith(b'\n')
                    if not discarding:
                        lines_total += 1
                        oversized += 1
                        scan_tail = b''
                        line_start = raw_total
                    continue
                scan_tail = b''
                lines_total += 1
                try:
                    line = raw_line.decode('utf-8')
                except UnicodeDecodeError:
                    nontext += 1
                    line_start = raw_total
                    continue
                if '\x00' in line:
                    nontext += 1
                    line_start = raw_total
                    continue
                clean = ANSI.sub(b'', raw_line).decode('utf-8')
                priority = 0 if any(rule.search(clean) for rule in important_rules) else 1 if any(rule.search(clean) for rule in summary_rules) else 2
                item = (lines_total, line, priority, line_start, raw_total)
                line_start = raw_total
                if a.adaptive and raw_total <= small_limit:
                    small.append(item)
                else:
                    small.clear()
                if lines_total <= 3:
                    top.append(item)
                last.append(item)
                if priority < 2 and key_bytes[priority] + len(raw_line) <= a.max_bytes:
                    key_lines[priority].append(item)
                    key_bytes[priority] += len(raw_line)
            if discarding:
                lines_total += 1
                oversized += 1
            ret = proc.wait()
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        tail = list(last)
        if ret == 0 and a.kind != 'generic':
            tail = tail[-8:]
        passthrough = a.adaptive and raw_total <= small_limit and not oversized and not nontext
        candidates = {item[0]: item for item in (small if passthrough else top + key_lines[0] + key_lines[1] + tail)}
        final = {}
        shown_bytes = 0
        # Retain diagnostics before ordinary output, then emit in source order.
        for index, line, _priority, start, end in sorted(candidates.values(), key=lambda item: (item[2], -item[0] if item[2] == 2 else item[0])):
            displayed = line if line.endswith('\n') else line + '\n'
            size = len(displayed.encode('utf-8'))
            if size > a.max_bytes - shown_bytes:
                oversized += 1
                continue
            final[index] = displayed
            shown_bytes += size
            ranges.append({'line': index, 'start_byte': start, 'end_byte': end})
        if index_handle is not None:
            assert log_handle is not None
            log_handle.flush()
            json.dump({'format_version': 1, 'month_end_version': VERSION,
                       'log_path': str(Path(a.log).expanduser().resolve()), 'command_started': True,
                       'exit': ret, 'profile': profile, 'raw_bytes': raw_total,
                       'sha256': digest.hexdigest(), 'raw_range': [0, raw_total],
                       'displayed_ranges': sorted(ranges, key=lambda item: item['line'])}, index_handle, indent=2)
            index_handle.write('\n')
    abridged = len(final) < lines_total
    passthrough = passthrough and not abridged
    for index in sorted(final):
        print(final[index], end='')
    print(f'[month-end] exit={ret} kind={a.kind} raw_bytes={raw_total} displayed_bytes={shown_bytes} lines={lines_total} excerpt={str(abridged).lower()} profile={profile} filter={"passthrough" if passthrough else "bounded"}')
    if oversized:
        print(f'[month-end] {oversized} candidate line(s) could not fit the byte budget and were OMITTED; inspect the full output before editing from them.')
    if nontext:
        print(f'[month-end] {nontext} binary or invalid UTF-8 line(s) were OMITTED; inspect raw output with an appropriate viewer.')
    if ret != 0:
        print('[month-end] Command FAILED. Diagnostics above are an excerpt, NOT a substitute for complete error analysis.')
        if not a.log:
            print('[month-end] For full evidence rerun with --log PATH or execute command unwrapped.')
    elif important_seen:
        print('[month-end] Warning/error-like text was present despite exit=0; inspect complete output if actionable.')
    if a.log:
        print('[month-end] Full raw output was written locally to user-provided path.')
    return ret


def cmd_log_read(a: argparse.Namespace) -> int:
    with Path(a.index).expanduser().open('rb') as source:
        raw_index = source.read(4_000_001)
    if len(raw_index) > 4_000_000:
        raise ValueError('log index exceeds 4 MB')
    index = json.loads(raw_index)
    if not isinstance(index, dict) or index.get('format_version') != 1 or index.get('command_started') is not True:
        raise ValueError('unsupported or incomplete log index')
    expected_size, expected_hash = index.get('raw_bytes'), index.get('sha256')
    if type(expected_size) is not int or expected_size < 0 or not isinstance(expected_hash, str) or not re.fullmatch('[a-f0-9]{64}', expected_hash):
        raise ValueError('invalid integrity metadata')
    start, end = a.start_byte, a.end_byte
    if a.line is not None:
        if start != 0 or end is not None:
            raise ValueError('--line cannot be combined with byte range arguments')
        entries = index.get('displayed_ranges')
        if not isinstance(entries, list):
            raise ValueError('invalid displayed_ranges index')
        matches = [entry for entry in entries if isinstance(entry, dict) and entry.get('line') == a.line]
        if len(matches) != 1:
            raise ValueError('line is not present in the retained range index; use an explicit byte range')
        start, end = matches[0].get('start_byte'), matches[0].get('end_byte')
    if end is None:
        end = expected_size
    if type(start) is not int or type(end) is not int or not 0 <= start <= end <= expected_size:
        raise ValueError('invalid byte range')
    if end - start > a.max_bytes:
        print('[month-end] exact raw range exceeds --max-bytes; narrow it or increase the budget. No partial log returned.', file=sys.stderr)
        return 3
    digest, size = hashlib.sha256(), 0
    selected = bytearray()
    preceding_newlines = 0
    preceding_byte = None
    with Path(a.log).expanduser().open('rb') as source:
        for chunk in iter(lambda: source.read(65536), b''):
            digest.update(chunk)
            before = max(0, min(len(chunk), start - size))
            preceding_newlines += chunk[:before].count(b'\n')
            if before:
                preceding_byte = chunk[before - 1]
            left, right = max(0, start - size), min(len(chunk), end - size)
            if left < right:
                selected.extend(chunk[left:right])
            size += len(chunk)
        if size != expected_size or digest.hexdigest() != expected_hash:
            raise ValueError('log integrity check failed; file size or SHA256 differs from index')
    # Emit only bytes captured during the hash pass; rereading mutable evidence
    # after verification could silently substitute a different byte sequence.
    raw = bytes(selected)
    if a.line is not None and (preceding_newlines + 1 != a.line or
                              (start > 0 and preceding_byte != 10) or not raw or
                              b'\n' in raw[:-1] or (end < size and not raw.endswith(b'\n'))):
        raise ValueError('line mapping differs from verified raw-log boundaries')
    if not a.raw:
        if b'\x00' in raw:
            raise ValueError('binary range; use --raw for explicit byte recovery')
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError as error:
            raise ValueError('range is not valid UTF-8; choose complete character boundaries or use --raw') from error
        sys.stdout.write(text)
    else:
        sys.stdout.buffer.write(raw)
    print(f'[month-end] integrity=verified start_byte={start} end_byte={end} exact=true', file=sys.stderr)
    return 0


def cmd_audit(a: argparse.Namespace) -> int:
    root = safe_root(a.root)
    files = []
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in IGNORES and (not d.startswith('.') or d in AGENT_DIRS)]
        depth = len(Path(base).relative_to(root).parts)
        if depth > a.depth:
            dirs[:] = []
            continue
        for name in names:
            if name in CONFIG or name in {'settings.json', '.cursorrules'}:
                p = Path(base) / name
                try:
                    if not p.is_symlink() and p.is_file():
                        files.append((p.stat().st_size, str(p.relative_to(root))))
                except OSError:
                    pass
    print(f'Month End configuration size audit: {root}')
    for nbytes, name in sorted(files, reverse=True):
        flag = ' LARGE' if nbytes > a.warn_bytes else ''
        print(f'{nbytes:>8} B  {name}{flag}')
    print(f'[month-end] files={len(files)} total_config_bytes={sum(x[0] for x in files)}'
          ' metric=bytes_not_provider_tokens')
    print('[month-end] Audit is read-only. Long instruction files may be necessary; inspect before altering.')
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Month End: conservative local tools for lean coding-agent context. No telemetry, no network.')
    p.add_argument('--version', action='version', version=f'month-end {VERSION}')
    sub = p.add_subparsers(dest='sub', required=True)
    a = sub.add_parser('locate', help='Find matching file paths (literal search); do not stream whole files.')
    a.add_argument('pattern')
    a.add_argument('--root', default='.')
    a.add_argument('--limit', type=int, default=20)
    a.add_argument('--max-scan-bytes', type=int, default=2_000_000, help='Maximum bytes per searched file')
    a.add_argument('--null', action='store_true', help='NUL-delimited paths, including names containing newlines')
    a.set_defaults(fn=cmd_locate)
    a = sub.add_parser('excerpt', help='Render exact, bounded source lines around matches, refusing unsafe truncation.')
    a.add_argument('file')
    a.add_argument('--pattern', required=True)
    a.add_argument('--context', type=int, default=4)
    a.add_argument('--max-matches', type=int, default=4)
    a.add_argument('--max-lines', type=int, default=90)
    a.add_argument('--max-bytes', type=int, default=12000)
    a.add_argument('--max-file-bytes', type=int, default=5_000_000)
    a.add_argument('--regex', action='store_true')
    a.add_argument('--case-sensitive', action='store_true')
    a.set_defaults(fn=cmd_excerpt)
    a = sub.add_parser('symbol', help='Retrieve a complete Python AST definition with exact source and budgets.')
    a.add_argument('file')
    a.add_argument('name', help='Qualified name, e.g. PaymentService.process')
    a.add_argument('--context', type=int, default=0)
    a.add_argument('--max-lines', type=int, default=150)
    a.add_argument('--max-bytes', type=int, default=16000)
    a.add_argument('--max-file-bytes', type=int, default=5_000_000)
    a.set_defaults(fn=cmd_symbol)
    a = sub.add_parser('run', help='Wrap a known noisy command, preserving its exit code and relevant diagnostics.')
    a.add_argument('--kind', choices=['tests', 'build', 'lint', 'generic'], default='generic')
    a.add_argument('--max-bytes', type=int, default=12000)
    a.add_argument('--log', help='Explicit local path to persist full raw output; may contain secrets')
    a.add_argument('--log-index', help='Explicit JSON index path; requires --log; neither destination is overwritten')
    a.add_argument('--profile', choices=['auto', *PROFILES], default='auto')
    a.add_argument('--profile-config', help='Explicit JSON file with additional important/summary regex lists')
    a.add_argument('--adaptive', action='store_true', help='Preserve small complete output; filter only above the threshold')
    a.add_argument('--min-savings-bytes', type=int, default=1024)
    a.add_argument('command', nargs=argparse.REMAINDER)
    a.set_defaults(fn=cmd_run)
    a = sub.add_parser('log-read', help='Verify a raw log hash and recover an exact bounded range without rerunning its command.')
    a.add_argument('index')
    a.add_argument('--log', required=True, help='Explicit raw log path; paths in the index are never opened automatically')
    a.add_argument('--line', type=int, help='Recover a retained line by its original line number')
    a.add_argument('--start-byte', type=int, default=0)
    a.add_argument('--end-byte', type=int)
    a.add_argument('--max-bytes', type=int, default=12000)
    a.add_argument('--raw', action='store_true', help='Explicitly allow binary/partial-UTF8 bytes on stdout')
    a.set_defaults(fn=cmd_log_read)
    a = sub.add_parser('audit', help='Read-only configuration-size inventory; NOT a token or billing estimate.')
    a.add_argument('--root', default='.')
    a.add_argument('--depth', type=int, default=5)
    a.add_argument('--warn-bytes', type=int, default=12000)
    a.set_defaults(fn=cmd_audit)
    return p


def main(argv: list[str] | None = None) -> int:
    p = parser()
    a = p.parse_args(argv)
    for name in ['limit', 'context', 'max_matches', 'max_lines', 'max_bytes', 'max_scan_bytes', 'max_file_bytes', 'depth', 'warn_bytes', 'min_savings_bytes', 'start_byte', 'end_byte', 'line']:
        if hasattr(a, name) and getattr(a, name) is not None and getattr(a, name) < 0:
            p.error(f'{name} must be nonnegative')
    if hasattr(a, 'max_bytes') and a.max_bytes < 128:
        p.error('max_bytes must be >= 128')
    if hasattr(a, 'max_matches') and a.max_matches == 0:
        p.error('max_matches must be positive')
    if hasattr(a, 'max_scan_bytes') and a.max_scan_bytes == 0:
        p.error('max_scan_bytes must be positive')
    try:
        return a.fn(a)
    except (ValueError, OSError, re.error) as ex:
        print(f'[month-end] {ex}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    result = main()
    if result < 0 and os.name == 'posix':
        sys.stdout.flush()
        sys.stderr.flush()
        # SIGKILL cannot have a handler; it can still be propagated to this process.
        if -result != signal.SIGKILL:
            signal.signal(-result, signal.SIG_DFL)
        os.kill(os.getpid(), -result)
    raise SystemExit(result)
