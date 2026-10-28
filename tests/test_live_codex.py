import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/live_codex.py'
spec = importlib.util.spec_from_file_location('live_codex', SCRIPT)
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class LivePilotTests(unittest.TestCase):
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
