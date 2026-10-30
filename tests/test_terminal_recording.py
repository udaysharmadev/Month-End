"""Actual local recording evidence and offline player integrity."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('record_terminal', ROOT / 'docs/record_terminal.py')
recording = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recording)


class TerminalRecordingTests(unittest.TestCase):
    def test_capture_runs_real_commands_and_retains_failure(self):
        events, receipt = recording.capture(ROOT, pause=0)
        self.assertEqual(events[0]['version'], 2)
        self.assertEqual([command['exit'] for command in receipt['commands']], [0, 0, 0, 0, 0, 9])
        output = ''.join(event[2] for event in events[1:])
        self.assertIn('def validate_payment(currency):', output)
        self.assertIn('raw_bytes=7011 displayed_bytes=151', output)
        self.assertIn('ERROR: invalid payment currency', output)
        self.assertIn('[exit=9]', output)
        self.assertNotIn(str(ROOT), output)
        self.assertNotIn('/var/folders/', output)
        self.assertIsNone(receipt['provider_usage'])
        self.assertFalse(receipt['agent_screen_recording'])
        self.assertEqual(sorted(event[0] for event in events[1:]), [event[0] for event in events[1:]])

    def test_player_embeds_exact_events_without_script_injection(self):
        events = [{'version': 2}, [1.0, 'o', '</script><p>\r\n']]
        html = recording.player(events)
        embedded = html.split('const recording=', 1)[1].split(',events=', 1)[0]
        self.assertEqual(json.loads(embedded), events)
        self.assertNotIn('</script><p>', html)
        self.assertNotIn('src="http', html)

    def test_existing_recording_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            stem = Path(temporary) / 'demo'
            target = stem.with_suffix('.cast')
            target.write_text('valuable existing recording')
            with self.assertRaises(SystemExit):
                recording.main(['--output', str(stem), '--pause', '0'])
            self.assertEqual(target.read_text(), 'valuable existing recording')


if __name__ == '__main__':
    unittest.main()
