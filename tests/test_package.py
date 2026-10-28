"""Installed helper smoke checks and maintainer-only manifest validation."""
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'month-end'
sys.path.insert(0, str(ROOT / 'scripts'))
if importlib.util.find_spec('yaml') is not None:
    import validate_package
else:
    validate_package = None


class InstalledSkillTests(unittest.TestCase):
    def test_helpers_work_from_clean_host_layouts_without_repository(self):
        for host, directory in [('claude', '.claude/skills'), ('codex', '.agents/skills'),
                                ('antigravity', '.agents/skills')]:
            with self.subTest(host=host), tempfile.TemporaryDirectory() as td:
                project = Path(td) / 'project with spaces ü'
                project.mkdir()
                installed = project / directory / 'month-end'
                shutil.copytree(SKILL, installed, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                source = project / 'app.py'
                source.write_text('ANCHOR = "preserved"\n', encoding='utf-8')

                def call(script, *arguments, installed=installed, project=project):
                    return subprocess.run([sys.executable, '-I', str(installed / 'scripts' / script),
                                           *arguments], cwd=project, capture_output=True, text=True, timeout=15)

                for arguments in [('--help',), ('locate', 'ANCHOR'),
                                  ('excerpt', 'app.py', '--pattern', 'ANCHOR'), ('audit',),
                                  ('run', '--kind', 'tests', '--', sys.executable, '-I',
                                   '-c', 'print("2 passed")')]:
                    result = call('monthend.py', *arguments)
                    self.assertEqual(result.returncode, 0, result.stderr)
                ledger = project / 'runs.csv'
                ledger.write_text('task_id,arm,success\nt,baseline,1\nt,month-end,1\n', encoding='utf-8')
                result = call('compare_runs.py', str(ledger))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('UNAVAILABLE', result.stdout)
                self.assertTrue((installed / 'references' / 'checkpoint.md').is_file())


@unittest.skipIf(validate_package is None, 'Install requirements-dev.txt for YAML validation')
class PackageValidationTests(unittest.TestCase):
    def copy_skill(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        target = Path(temporary.name) / 'month-end'
        shutil.copytree(SKILL, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        return target

    def test_repository_package_is_valid(self):
        validate_package.validate_package(ROOT)

    def test_invalid_frontmatter_is_rejected(self):
        cases = [
            'name: wrong-name\ndescription: scoped task',
            'name: month-end\ndescription: ""',
            'name: month-end\ndescription: scoped task\nmetadata:\n  version: 1',
            'name: month-end\ndescription: scoped task\nname: month-end',
            'name: month-end\ndescription: scoped task\ncompatibility: ' + 'x' * 501,
            'name: month-end\ndescription: scoped task\nunknown-field: value',
        ]
        for header in cases:
            with self.subTest(header=header):
                skill = self.copy_skill()
                (skill / 'SKILL.md').write_text('---\n' + header + '\n---\nInstructions.\n')
                with self.assertRaises(ValueError):
                    validate_package.validate_skill(skill)

    def test_missing_and_external_local_resources_are_rejected(self):
        for link in ('references/missing.md', '../outside.md'):
            with self.subTest(link=link):
                skill = self.copy_skill()
                (skill.parent / 'outside.md').write_text('outside')
                manifest = skill / 'SKILL.md'
                manifest.write_text(manifest.read_text() + '\n[resource](' + link + ')\n')
                with self.assertRaisesRegex(ValueError, 'local link'):
                    validate_package.validate_skill(skill)

    def test_syntax_errors_in_bundled_helpers_are_rejected(self):
        skill = self.copy_skill()
        (skill / 'scripts' / 'broken.py').write_text('def missing_colon()\n    pass\n')
        with self.assertRaises(SyntaxError):
            validate_package.validate_skill(skill)

    def test_cli_version_mismatch_is_rejected(self):
        skill = self.copy_skill()
        root = skill.parent / 'repository'
        root.mkdir()
        for name in ('README.md', 'CONTRIBUTING.md', 'LICENSE'):
            (root / name).write_text('Fixture package\n')
        installed = root / 'skills' / 'month-end'
        shutil.copytree(skill, installed)
        validate_package.validate_package(root)
        script = installed / 'scripts' / 'monthend.py'
        text = script.read_text()
        import re
        script.write_text(re.sub(r"VERSION = '[^']+'", "VERSION = 'different'", text, count=1))
        with self.assertRaisesRegex(ValueError, 'versions differ'):
            validate_package.validate_package(root)

    def test_yaml_cannot_instantiate_python_objects(self):
        skill = self.copy_skill()
        manifest = skill / 'SKILL.md'
        manifest.write_text('---\nname: month-end\ndescription: safe\n'
                            'metadata: !!python/object/apply:builtins.print ["must not execute"]\n'
                            '---\nInstructions.\n')
        with self.assertRaises(validate_package.yaml.YAMLError):
            validate_package.validate_skill(skill)


if __name__ == '__main__':
    unittest.main()
