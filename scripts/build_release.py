#!/usr/bin/env python3
"""Build deterministic local source and standalone-skill release archives."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

from validate_package import check_links, validate_package, validate_skill

ROOT_FILES = {'README.md', 'LICENSE', 'CHANGELOG.md', 'CONTRIBUTING.md', 'SECURITY.md',
              'requirements-dev.txt', 'requirements-tokenizer.txt', 'pyproject.toml', '.gitignore'}
ROOT_DIRS = {'.github', 'skills', 'scripts', 'tests', 'docs', 'examples', 'benchmarks'}
EXCLUDED_DIRS = {'.git', '.venv', 'venv', '__pycache__', 'dist', 'build', 'node_modules',
                 '.pytest_cache', '.mypy_cache', '.ruff_cache', 'coverage', 'results',
                 'logs', '.aws', '.codex', '.agents', '.claude', '.cache'}
EXCLUDED_NAMES = {'.DS_Store', 'credentials.json', 'credentials', 'id_rsa', 'id_ed25519',
                  'secrets.json', 'token.json', 'tokens.json', 'authorized_keys'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.log', '.pem', '.key', '.p12', '.pfx', '.docx'}
MAX_FILE_BYTES = 20_000_000
MAX_TOTAL_BYTES = 100_000_000
MANIFEST = 'RELEASE_MANIFEST.json'
PRIVATE_KEY = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----')
SERVICE_TOKEN = re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{32,})\b')


def excluded(path: Path) -> bool:
    return (any(part in EXCLUDED_DIRS for part in path.parts)
            or any(path.parts[index:index + 2] == ('verification', 'private') for index in range(len(path.parts) - 1))
            or path.name in EXCLUDED_NAMES or path.name.startswith('.env')
            or path.suffix.lower() in EXCLUDED_SUFFIXES)


def source_files(root: Path) -> dict[str, bytes]:
    """Use explicit release roots; never traverse user configuration or outputs."""
    root = Path(root).resolve()
    files = {}
    total = 0
    for entry in sorted(root.iterdir()):
        if entry.name not in ROOT_FILES | ROOT_DIRS:
            continue
        paths = [entry, *sorted(entry.rglob('*'))] if entry.is_dir() and not entry.is_symlink() else [entry]
        for path in paths:
            relative = path.relative_to(root)
            if excluded(relative):
                continue
            if path.is_symlink():
                raise ValueError(f'release source contains a symlink: {relative}')
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError(f'release source is not a regular file: {relative}')
            with path.open('rb') as stream:
                content = stream.read(MAX_FILE_BYTES + 1)
            if len(content) > MAX_FILE_BYTES:
                raise ValueError(f'release file exceeds {MAX_FILE_BYTES} bytes: {relative}')
            if PRIVATE_KEY.search(content) or SERVICE_TOKEN.search(content):
                raise ValueError(f'possible private key or service credential in release file: {relative}')
            total += len(content)
            if total > MAX_TOTAL_BYTES:
                raise ValueError(f'release content exceeds {MAX_TOTAL_BYTES} bytes')
            files[relative.as_posix()] = content
    return files


def archive_bytes(files: dict[str, bytes], version: str, kind: str) -> bytes:
    manifest = {
        'format_version': 1, 'name': 'month-end', 'version': version, 'kind': kind,
        'files': {name: {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
                  for name, content in sorted(files.items())},
    }
    entries = dict(files)
    entries[MANIFEST] = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode('utf-8')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo('month-end/' + name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content, compresslevel=9)
    return output.getvalue()


def validate_snapshot(files: dict[str, bytes], kind: str) -> None:
    """Validate the distributable content, not dependencies left in the workspace."""
    with tempfile.TemporaryDirectory(prefix='month-end-release-') as temporary:
        root = Path(temporary) / 'month-end'
        root.mkdir()
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if kind == 'source':
            validate_package(root)
        else:
            validate_skill(root)
        for name in files:
            if name.endswith('.md'):
                check_links(root / name, root)


def verify_archive(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('duplicate archive paths')
        if len(names) > 20_000 or sum(info.file_size for info in archive.infolist()) > MAX_TOTAL_BYTES + MAX_FILE_BYTES:
            raise ValueError('archive exceeds verification size limits')
        if 'month-end/' + MANIFEST not in names:
            raise ValueError('archive has no release manifest')
        for name in names:
            parts = Path(name).parts
            info = archive.getinfo(name)
            mode = stat.S_IFMT(info.external_attr >> 16)
            if info.file_size > MAX_FILE_BYTES:
                raise ValueError('archive member exceeds verification size limit')
            if (not name.startswith('month-end/') or Path(name).is_absolute() or '..' in parts
                    or '\\' in name or any(ord(character) < 32 for character in name)
                    or mode not in {0, stat.S_IFREG}):
                raise ValueError('unsafe archive path')
        manifest = json.loads(archive.read('month-end/' + MANIFEST))
        expected = {'month-end/' + name for name in manifest['files']}
        if set(names) != expected | {'month-end/' + MANIFEST}:
            raise ValueError('archive content differs from manifest')
        for name, receipt in manifest['files'].items():
            content = archive.read('month-end/' + name)
            if len(content) != receipt['bytes'] or hashlib.sha256(content).hexdigest() != receipt['sha256']:
                raise ValueError(f'archive hash mismatch: {name}')
        return manifest


def build_release(root: Path, output_dir: Path) -> list[Path]:
    root = Path(root).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.is_relative_to(root):
        output_parts = output_dir.relative_to(root).parts
        if output_parts and output_parts[0] in ROOT_DIRS and not any(part in EXCLUDED_DIRS for part in output_parts):
            raise ValueError('release output must be outside packaged source directories (use dist/)')
    validate_package(root)
    metadata = validate_skill(root / 'skills' / 'month-end')
    version = metadata.get('metadata', {}).get('version', '')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version):
        raise ValueError('release version must be a semantic version, optionally prerelease')
    files = source_files(root)
    skill_prefix = 'skills/month-end/'
    skill = {name[len(skill_prefix):]: content for name, content in files.items() if name.startswith(skill_prefix)}
    skill['LICENSE'] = files['LICENSE']
    validate_snapshot(files, 'source')
    validate_snapshot(skill, 'skill')
    artifacts = {
        f'month-end-{version}-source.zip': archive_bytes(files, version, 'source'),
        f'month-end-{version}-skill.zip': archive_bytes(skill, version, 'skill'),
    }
    checksum_name = f'month-end-{version}-SHA256SUMS'
    artifacts[checksum_name] = ''.join(f'{hashlib.sha256(content).hexdigest()}  {name}\n'
                                        for name, content in sorted(artifacts.items())).encode('ascii')
    output_dir.mkdir(parents=True, exist_ok=True)
    # A rebuild may reuse identical files, but must not replace different artifacts.
    for name, content in artifacts.items():
        path = output_dir / name
        if path.is_symlink():
            raise ValueError(f'refusing to overwrite a different existing artifact: {path}')
        if path.exists():
            with path.open('rb') as stream:
                if stream.read(len(content) + 1) != content:
                    raise ValueError(f'refusing to overwrite a different existing artifact: {path}')
    for name, content in artifacts.items():
        path = output_dir / name
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(content)
        if name.endswith('.zip'):
            verify_archive(path)
    return [output_dir / name for name in sorted(artifacts)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, default=Path('dist'))
    arguments = parser.parse_args(argv)
    try:
        artifacts = build_release(arguments.root, arguments.output)
    except (OSError, ValueError, SyntaxError, zipfile.BadZipFile) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    for path in artifacts:
        print(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
