"""Independent adversarial checks for retrieval, evidence, and managed installs."""
import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'month-end' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import integrations
import monthend


class IndependentSecurityTests(unittest.TestCase):
    def cli(self, *arguments):
        return subprocess.run([sys.executable, str(SCRIPTS / 'monthend.py'), *arguments],
                              capture_output=True, text=True, timeout=10)

    def index(self, path, raw, ranges):
        path.write_text(json.dumps({'format_version': 1, 'command_started': True,
                                    'raw_bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                                    'displayed_ranges': ranges}), encoding='utf-8')

    def test_uninstall_preserves_user_data_under_cache_or_git_names(self):
        for relative in ('__pycache__/my-research.md', '.git/my-research.md'):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                integrations.install(project, 'codex')
                note = project / '.agents/skills/month-end' / relative
                note.parent.mkdir(parents=True, exist_ok=True)
                note.write_text('valuable user work', encoding='utf-8')
                try:
                    integrations.uninstall(project, 'codex')
                except ValueError:
                    pass
                self.assertTrue(note.is_file(), 'managed uninstall deleted unrecognized user data')
                self.assertEqual(note.read_text(), 'valuable user work')

    def test_installer_does_not_commit_outside_project_after_parent_symlink_swap(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            project, external = Path(temporary), Path(outside)
            real_temporary_directory = integrations.tempfile.TemporaryDirectory

            def swap_before_staging(*arguments, **keywords):
                parent = Path(keywords['dir'])
                parent.rename(project / 'detached-skills')
                parent.symlink_to(external, target_is_directory=True)
                return real_temporary_directory(*arguments, **keywords)

            with mock.patch.object(integrations.tempfile, 'TemporaryDirectory', side_effect=swap_before_staging):
                try:
                    integrations.install(project, 'codex')
                except (OSError, ValueError):
                    pass
            self.assertFalse((external / 'month-end').exists(),
                             'installation escaped the selected project after symlink scope changed')

    def test_line_lookup_rejects_a_tampered_line_to_byte_mapping(self):
        with tempfile.TemporaryDirectory() as temporary:
            log, index = Path(temporary) / 'raw.log', Path(temporary) / 'index.json'
            raw = b'line one\nline two\n'
            log.write_bytes(raw)
            self.index(index, raw, [{'line': 2, 'start_byte': 0, 'end_byte': 9}])
            result = self.cli('log-read', str(index), '--log', str(log), '--line', '2')
            self.assertNotEqual(result.returncode, 0,
                                'a correct whole-log hash does not authenticate a false line mapping')
            self.assertEqual(result.stdout, '')

    def test_log_recovery_never_labels_post_hash_mutation_as_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            log, index = Path(temporary) / 'raw.log', Path(temporary) / 'index.json'
            raw = b'ORIGINAL\n'
            log.write_bytes(raw)
            self.index(index, raw, [{'line': 1, 'start_byte': 0, 'end_byte': len(raw)}])
            original_sha256 = monthend.hashlib.sha256

            class MutatingDigest:
                def __init__(self):
                    self.digest = original_sha256()

                def update(self, chunk):
                    self.digest.update(chunk)

                def hexdigest(self):
                    result = self.digest.hexdigest()
                    log.write_bytes(b'MUTATION\n')
                    return result

            output, diagnostics = io.StringIO(), io.StringIO()
            with mock.patch.object(monthend.hashlib, 'sha256', MutatingDigest), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(diagnostics):
                result = monthend.main(['log-read', str(index), '--log', str(log), '--line', '1'])
            self.assertNotIn('MUTATION', output.getvalue(),
                             'reader re-read mutable evidence after verifying a different byte sequence')
            if result == 0:
                self.assertEqual(output.getvalue(), raw.decode('utf-8'))
                self.assertIn('integrity=verified', diagnostics.getvalue())

    def test_symbol_retrieval_finds_definitions_inside_control_flow(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'conditional.py'
            source.write_text('if True:\n    def conditional(value):\n        return value + 1\n', encoding='utf-8')
            result = self.cli('symbol', str(source), 'conditional')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('def conditional(value):', result.stdout)
            self.assertIn('return value + 1', result.stdout)
            self.assertIn('exact=true', result.stdout)

    def test_adaptive_receipt_does_not_call_an_omitted_body_passthrough(self):
        result = self.cli('run', '--adaptive', '--max-bytes', '128', '--min-savings-bytes', '128',
                          '--', sys.executable, '-c', 'import sys; sys.stdout.write("x" * 128)')
        self.assertEqual(result.returncode, 0, result.stderr)
        if 'excerpt=true' in result.stdout:
            self.assertNotIn('filter=passthrough', result.stdout,
                             'adaptive receipt claims passthrough even though its only line was omitted')

    def test_profile_errors_are_rejected_before_any_command_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker, config = root / 'ran', root / 'rules.json'
            code = 'from pathlib import Path; Path(' + repr(str(marker)) + ').touch()'
            for rules in ({'important': ['(']}, {'important': 'not-a-list'}, ['not-a-map']):
                with self.subTest(rules=rules):
                    config.write_text(json.dumps(rules), encoding='utf-8')
                    result = self.cli('run', '--profile-config', str(config), '--', sys.executable, '-c', code)
                    self.assertEqual(result.returncode, 2)
                    self.assertFalse(marker.exists())

    def test_omitted_custom_warning_still_has_a_visible_indicator(self):
        with tempfile.TemporaryDirectory() as temporary:
            rules = Path(temporary) / 'rules.json'
            rules.write_text(json.dumps({'important': ['^CHECKPOINT-ALERT']}), encoding='utf-8')
            result = self.cli('run', '--profile-config', str(rules), '--max-bytes', '128', '--',
                              sys.executable, '-c', 'print("CHECKPOINT-ALERT " + "x" * 10000)')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('OMITTED', result.stdout)
            self.assertIn('Warning/error-like text was present', result.stdout)

    def test_hook_path_escape_and_malformed_payload_do_not_mutate_settings(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            project = Path(temporary)
            settings = project / '.claude/settings.json'
            settings.parent.mkdir()
            content = '{"permissions": {"deny": ["Bash(rm *)"]}}\n'
            settings.write_text(content, encoding='utf-8')
            selected = Path(outside) / 'note.md'
            selected.write_text('untrusted note', encoding='utf-8')
            (project / 'note.md').symlink_to(selected)
            payload = {'hook_event_name': 'SessionStart', 'source': 'resume'}
            with self.assertRaises(ValueError):
                integrations.run_hook(project, 'note.md', payload)
            self.assertEqual(integrations.run_hook(project, 'note.md', ['SessionStart']), {})
            result = subprocess.run([sys.executable, str(SCRIPTS / 'integrations.py'), 'hook',
                                     '--project', str(project), '--checkpoint', 'note.md'],
                                    input='{malformed', capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {})
            self.assertEqual(settings.read_text(), content)

    def test_ast_retrieval_does_not_execute_repository_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, marker = root / 'module.py', root / 'executed'
            source.write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').touch()\n'
                              'def selected():\n    return "anchor"\n', encoding='utf-8')
            result = self.cli('symbol', str(source), 'selected')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('return "anchor"', result.stdout)
            self.assertFalse(marker.exists())


@unittest.skipUnless(importlib.util.find_spec('yaml'), 'Release checks need maintainer dependency')
class PrivateArtifactSelectionTests(unittest.TestCase):
    def test_nested_project_caches_and_verification_private_files_are_excluded(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import build_release
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ('docs/.cache/session.json', 'docs/verification/private/account.json',
                             'benchmarks/local/.cache/session.json', 'docs/Month_End_Research_and_PRD.docx'):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('private verification sentinel', encoding='utf-8')
            selected = build_release.source_files(root)
            self.assertEqual(selected, {}, 'private cached verification artifacts entered the release snapshot')


if __name__ == '__main__':
    unittest.main()
