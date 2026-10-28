#!/usr/bin/env python3
"""Maintainer checks; PyYAML is optional for users of the installed skill."""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys instead of silently selecting one value."""

    def construct_mapping(self, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ValueError('YAML mapping keys must be strings')
            if key in mapping:
                raise ValueError(f'duplicate YAML key: {key}')
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def check_links(path: Path, boundary: Path) -> None:
    text = re.sub(r'```.*?```', '', path.read_text(encoding='utf-8'), flags=re.DOTALL)
    for raw_link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
        link = raw_link.strip().strip('<>')
        parsed = urlsplit(link)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        target = (path.parent / unquote(parsed.path)).resolve()
        if not target.is_relative_to(boundary.resolve()):
            raise ValueError(f'nonportable local link in {path}: {link}')
        if not target.is_file():
            raise ValueError(f'missing local link in {path}: {link}')


def validate_skill(skill: Path) -> dict:
    skill = Path(skill).resolve()
    manifest = skill / 'SKILL.md'
    text = manifest.read_text(encoding='utf-8')
    match = re.match(r'\A---\n(.*?)\n---\n', text, re.DOTALL)
    if match is None:
        raise ValueError('SKILL.md requires YAML frontmatter')
    # UniqueLoader inherits SafeLoader and only adds duplicate-key rejection.
    loader = UniqueLoader(match.group(1))
    try:
        data = loader.get_single_data()
    finally:
        loader.dispose()
    if not isinstance(data, dict):
        raise ValueError('frontmatter must be a mapping')
    allowed = {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'}
    if set(data) - allowed:
        raise ValueError('unsupported frontmatter fields: ' + ', '.join(sorted(set(data) - allowed)))
    name = data.get('name')
    if not isinstance(name, str) or len(name) > 64 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
        raise ValueError('name must be 1–64 lowercase letters/digits/hyphens without consecutive hyphens')
    if name != skill.name:
        raise ValueError('name must match skill directory')
    for field, limit in [('description', 1024), ('compatibility', 500)]:
        if field == 'description' or field in data:
            value = data.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError(f'{field} must be a nonempty string of at most {limit} characters')
    for field in ('license', 'allowed-tools'):
        if field in data and not isinstance(data[field], str):
            raise ValueError(f'{field} must be a string')
    if 'metadata' in data:
        metadata = data['metadata']
        if not isinstance(metadata, dict) or not all(isinstance(value, str) for value in metadata.values()):
            raise ValueError('metadata must map string keys to string values')
    if not text[match.end():].strip():
        raise ValueError('skill body must not be empty')
    for resource in skill.rglob('*.md'):
        check_links(resource, skill)
    for source in (skill / 'scripts').glob('*.py'):
        ast.parse(source.read_text(encoding='utf-8'), filename=str(source), feature_version=(3, 9))
    return data


def validate_package(root: Path) -> None:
    root = Path(root).resolve()
    skill = root / 'skills' / 'month-end'
    metadata = validate_skill(skill)
    for filename in ('README.md', 'CONTRIBUTING.md', 'LICENSE'):
        path = root / filename
        if not path.is_file():
            raise ValueError(f'missing package resource: {filename}')
        if filename.endswith('.md'):
            check_links(path, root)
    for script in ('monthend.py', 'compare_runs.py'):
        if not (skill / 'scripts' / script).is_file():
            raise ValueError(f'missing helper: {script}')
    tree = ast.parse((skill / 'scripts' / 'monthend.py').read_text(encoding='utf-8'))
    versions = [node.value.value for node in tree.body
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and any(isinstance(target, ast.Name) and target.id == 'VERSION' for target in node.targets)]
    if versions != [metadata.get('metadata', {}).get('version')]:
        raise ValueError('manifest and CLI versions differ')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        validate_package(args.root)
    except (OSError, ValueError, SyntaxError, yaml.YAMLError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    print('PASS: skill schema, portable resource links, Python 3.9 syntax, and matching package versions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
