import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / 'skills/month-end/scripts/integrations.py'


class IntegrationTests(unittest.TestCase):
    def call(self, *args, payload=None):
        return subprocess.run([sys.executable, str(CLI), *args], capture_output=True,
                              text=True, input=None if payload is None else json.dumps(payload), timeout=15)

    def test_install_is_project_scoped_idempotent_and_reversible(self):
        for host, prefix in [('claude', '.claude'), ('codex', '.agents'), ('antigravity', '.agents')]:
            with self.subTest(host=host), tempfile.TemporaryDirectory() as td:
                target = Path(td) / prefix / 'skills/month-end'
                for expected in ('installed', 'already-installed'):
                    result = self.call('install', '--host', host, '--project', td)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout)['status'], expected)
                self.assertTrue((target / 'SKILL.md').is_file())
                result = self.call('uninstall', '--host', host, '--project', td)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(target.exists())

    def test_modified_files_and_unknown_directories_are_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(self.call('install', '--host', 'codex', '--project', td).returncode, 0)
            target = Path(td) / '.agents/skills/month-end'
            (target / 'my-notes.md').write_text('keep me')
            result = self.call('uninstall', '--host', 'codex', '--project', td)
            self.assertEqual(result.returncode, 2)
            self.assertTrue((target / 'my-notes.md').exists())
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / '.agents/skills/month-end'
            target.mkdir(parents=True)
            result = self.call('install', '--host', 'codex', '--project', td)
            self.assertEqual(result.returncode, 2)

    def test_installed_copy_can_manage_its_own_project(self):
        for host, prefix in [('claude', '.claude'), ('codex', '.agents'), ('antigravity', '.agents')]:
            with self.subTest(host=host), tempfile.TemporaryDirectory() as td:
                installed = self.call('install', '--host', host, '--project', td)
                self.assertEqual(installed.returncode, 0, installed.stderr)
                target = Path(td) / prefix / 'skills/month-end'
                cli = target / 'scripts/integrations.py'
                commands = [('install', []), ('status', [])]
                if host != 'antigravity':
                    commands.append(('hook-config', ['--checkpoint', 'task-note.md']))
                commands.append(('uninstall', []))
                for action, extra in commands:
                    result = subprocess.run([sys.executable, str(cli), action, '--host', host,
                                             '--project', td, *extra], capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(target.exists())

    def test_install_refuses_symlink_escape(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside:
            (Path(td) / '.agents').symlink_to(outside, target_is_directory=True)
            result = self.call('install', '--host', 'codex', '--project', td)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_hook_config_is_off_by_default_and_does_not_rewrite_settings(self):
        with tempfile.TemporaryDirectory() as td:
            for host in ('codex', 'claude'):
                result = self.call('hook-config', '--host', host, '--project', td,
                                   '--checkpoint', 'task-note.md')
                self.assertEqual(result.returncode, 0, result.stderr)
                config = json.loads(result.stdout)
                handler = config['hooks']['SessionStart'][0]['hooks'][0]
                self.assertNotIn('dangerously', handler['command'])
                self.assertIn('task-note.md', handler['command'])
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_hook_injects_only_explicit_bounded_note_as_untrusted_data(self):
        with tempfile.TemporaryDirectory() as td:
            note = Path(td) / 'task-note.md'
            note.write_text('Goal: preserve exact anchors\nNext: rerun tests\n')
            result = self.call('hook', '--project', td, '--checkpoint', note.name,
                               payload={'hook_event_name': 'SessionStart', 'source': 'resume',
                                        'transcript_path': '/not/read/ever'})
            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
            self.assertIn('Untrusted task checkpoint data', context)
            self.assertIn('preserve exact anchors', context)
            note.write_text('x' * 2049)
            result = self.call('hook', '--project', td, '--checkpoint', note.name,
                               payload={'hook_event_name': 'SessionStart', 'source': 'resume'})
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {})
            self.assertIn('no partial checkpoint', result.stderr)


if __name__ == '__main__':
    unittest.main()
