"""Reproducible artifacts, content exclusion and bounded static checks."""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
if importlib.util.find_spec('yaml'):
    import build_release
    import release_check
else:
    build_release = release_check = None


@unittest.skipIf(build_release is None, 'Install requirements-dev.txt for release validation')
class ReleaseTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / 'source'
        root.mkdir()
        for name in ('README.md', 'LICENSE', 'CONTRIBUTING.md', 'SECURITY.md'):
            (root / name).write_text('Fixture package\n', encoding='utf-8')
        skill = root / 'skills' / 'month-end'
        (skill / 'scripts').mkdir(parents=True)
        (skill / 'SKILL.md').write_text('---\nname: month-end\ndescription: Scoped fixture task\n'
                                      'metadata:\n  version: "1.0.0-rc.1"\n---\nInstructions.\n')
        (skill / 'scripts' / 'monthend.py').write_text('VERSION = "1.0.0-rc.1"\n')
        (skill / 'scripts' / 'compare_runs.py').write_text('"""Fixture evaluator."""\n')
        (root / 'docs').mkdir()
        (root / 'docs' / 'source-register.json').write_text(json.dumps({
            'format_version': 1, 'review_interval_days': 90,
            'sources': [{'id': 'S1', 'title': 'Fixture source', 'url': 'https://example.org/spec',
                         'status': 'verified', 'review_scope': 'test fixture only', 'checked_on': '2026-10-28'}],
            'mechanisms': [{'id': 'fixture', 'source_ids': ['S1']}],
        }))
        return root

    def test_build_is_deterministic_and_manifest_covers_every_byte(self):
        root = self.fixture()
        first = build_release.build_release(root, root.parent / 'first')
        second = build_release.build_release(root, root.parent / 'second')
        self.assertEqual([path.name for path in first], [path.name for path in second])
        for left, right in zip(first, second):
            self.assertEqual(left.read_bytes(), right.read_bytes())
            if left.suffix == '.zip':
                manifest = build_release.verify_archive(left)
                self.assertEqual(manifest['version'], '1.0.0-rc.1')
                self.assertIn('LICENSE', manifest['files'])
        checksums = next(path for path in first if path.name.endswith('SHA256SUMS')).read_text()
        for archive in [path for path in first if path.suffix == '.zip']:
            self.assertIn(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name, checksums)

    def test_private_outputs_and_environment_files_are_excluded(self):
        root = self.fixture()
        for relative in ['.env', '.aws/credentials', 'WORK_LOG.md', '.venv/package.py',
                         'docs/.env.local', 'docs/private.log', 'tests/__pycache__/cache.pyc',
                         'benchmarks/results/raw.jsonl', 'skills/month-end/credentials.json']:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('PRIVATE_SENTINEL', encoding='utf-8')
        artifacts = build_release.build_release(root, root / 'dist')
        for archive in [path for path in artifacts if path.suffix == '.zip']:
            with zipfile.ZipFile(archive) as package:
                self.assertFalse(any(b'PRIVATE_SENTINEL' in package.read(name) for name in package.namelist()))

    def test_secret_patterns_and_symlinks_are_rejected(self):
        for case in ('key', 'token', 'symlink'):
            with self.subTest(case=case):
                root = self.fixture()
                path = root / 'docs' / 'unsafe.txt'
                path.parent.mkdir(exist_ok=True)
                if case == 'symlink':
                    path.symlink_to(root / 'README.md')
                elif case == 'key':
                    path.write_text('-----BEGIN ' + 'PRIVATE KEY-----\nexample')
                else:
                    path.write_text('ghp_' + 'A' * 40)
                with self.assertRaises(ValueError):
                    build_release.build_release(root, root / 'dist')

    def test_existing_artifacts_are_reused_only_if_identical(self):
        root = self.fixture()
        artifacts = build_release.build_release(root, root / 'dist')
        self.assertEqual(build_release.build_release(root, root / 'dist'), artifacts)
        archive = next(path for path in artifacts if path.suffix == '.zip')
        archive.write_bytes(b'valuable existing artifact')
        with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
            build_release.build_release(root, root / 'dist')
        self.assertEqual(archive.read_bytes(), b'valuable existing artifact')

    def test_source_output_directory_is_rejected(self):
        root = self.fixture()
        with self.assertRaisesRegex(ValueError, 'outside packaged'):
            build_release.build_release(root, root / 'docs' / 'releases')

    def test_excluded_workspace_resource_cannot_leave_a_broken_release_link(self):
        root = self.fixture()
        (root / 'docs' / 'private.log').write_text('private evidence')
        (root / 'README.md').write_text('[Evidence](docs/private.log)\n')
        with self.assertRaisesRegex(ValueError, 'missing local link'):
            build_release.build_release(root, root / 'dist')

    def test_tampered_zip_and_traversal_are_rejected(self):
        root = self.fixture()
        output = root.parent / 'bad.zip'
        output.write_bytes(build_release.archive_bytes({'LICENSE': b'original'}, '1.0.0-rc.1', 'skill'))
        with zipfile.ZipFile(output) as archive:
            contents = {name: archive.read(name) for name in archive.namelist()}
        with zipfile.ZipFile(output, 'w') as archive:
            for name, content in contents.items():
                archive.writestr(name, b'tampered' if name.endswith('/LICENSE') else content)
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            build_release.verify_archive(output)
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('month-end/../outside', 'bad')
            archive.writestr('month-end/RELEASE_MANIFEST.json', json.dumps({'files': {}}))
        with self.assertRaisesRegex(ValueError, 'unsafe archive path'):
            build_release.verify_archive(output)

    def test_runtime_network_and_shell_regressions_are_flagged(self):
        for code in ('import socket\n', 'import subprocess\nsubprocess.run(["tool"], shell=True)\n'):
            with self.subTest(code=code):
                root = self.fixture()
                (root / 'skills' / 'month-end' / 'scripts' / 'unsafe.py').write_text(code)
                with self.assertRaises(ValueError):
                    release_check.check_release(root, as_of=date(2026, 10, 28))

    def test_noncanonical_archive_paths_cannot_alias_extracted_files(self):
        root = self.fixture()
        archive = root.parent / 'aliased.zip'
        for alias in ('./LICENSE', 'nested//file', 'nested/./file', 'LICENSE/'):
            with self.subTest(alias=alias):
                archive.write_bytes(build_release.archive_bytes(
                    {'LICENSE': b'original', alias: b'changed'}, '1.0.0', 'skill'))
                with self.assertRaisesRegex(ValueError, 'unsafe archive path'):
                    build_release.verify_archive(archive)

    def test_stale_research_and_unknown_mechanism_sources_are_rejected(self):
        root = self.fixture()
        release_check.check_source_register(root, date(2026, 10, 28))
        with self.assertRaisesRegex(ValueError, 'stale'):
            release_check.check_source_register(root, date(2027, 1, 27))
        register = root / 'docs' / 'source-register.json'
        data = json.loads(register.read_text())
        data['mechanisms'][0]['source_ids'] = ['unknown']
        register.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'unknown source'):
            release_check.check_source_register(root, date(2026, 10, 28))

    def test_archive_member_limit_is_checked_before_decompression(self):
        root = self.fixture()
        archive = root.parent / 'large.zip'
        archive.write_bytes(build_release.archive_bytes({'payload': b'x' * 5000}, '1.0.0-rc.1', 'skill'))
        with mock.patch.object(build_release, 'MAX_FILE_BYTES', 1000):
            with self.assertRaisesRegex(ValueError, 'size limit'):
                build_release.verify_archive(archive)


class DemoTests(unittest.TestCase):
    def test_demo_records_actual_terminal_bytes_and_failure_status(self):
        sys.path.insert(0, str(ROOT / 'docs'))
        import demo
        result = demo.record_demo(ROOT)
        self.assertEqual(result['passing_exit'], 0)
        self.assertEqual(result['failing_exit'], 9)
        self.assertLess(result['displayed_command_body_bytes'], result['raw_command_bytes'])
        self.assertGreater(result['entire_wrapper_stdout_bytes'], result['displayed_command_body_bytes'])
        self.assertIn('invalid payment currency', result['failing_stdout'])
        self.assertIsNone(result['provider_usage'])
        self.assertIsNone(result['billed_cost_usd'])


if __name__ == '__main__':
    unittest.main()
