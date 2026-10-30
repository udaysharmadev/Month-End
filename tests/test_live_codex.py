import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/live_codex.py'
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location('live_codex', SCRIPT)
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class LivePilotTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('sandbox-exec'),
                         'macOS sandbox canonical workspace check')
    def test_native_pilot_temporary_workspace_allows_its_own_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            result = live.bounded_subprocess([sys.executable, '-I', '-c',
                      'from pathlib import Path; Path("inside.txt").write_text("synthetic"); print("ok")'],
                      workspace, require_isolation=True)
            self.assertEqual(result['exit'], 0, result)
            self.assertEqual((workspace / 'inside.txt').read_text(), 'synthetic')

    def test_unsupported_grading_is_rejected_before_native_invocations(self):
        with mock.patch.object(live, 'require_sandbox', side_effect=ValueError('sandbox unavailable')), \
                mock.patch.object(live.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'sandbox unavailable'):
                live.run_pilot('/not-created')
            run.assert_not_called()

    def test_native_usage_is_reported_without_billing(self):
        event = {'type': 'turn.completed', 'usage': {'input_tokens': 100, 'cached_input_tokens': 40, 'output_tokens': 12}}
        result = live.usage_events(json.dumps(event))
        self.assertEqual(result['usage']['cached_input_tokens'], 40)
        self.assertEqual(result['completed_turns'], 1)

    def test_invalid_usage_is_rejected_and_errors_preserved(self):
        with self.assertRaises(ValueError):
            live.usage_events('{"type":"turn.completed","usage":{"input_tokens":-1}}')
        self.assertEqual(live.usage_events('{"type":"error","message":"quota"}')['errors'], ['quota'])

    def test_default_is_a_plan_without_model_calls(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('no commands started', result.stdout)


if __name__ == '__main__':
    unittest.main()
