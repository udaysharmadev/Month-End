"""Provider-response fixtures; these are schema examples, not live usage claims."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills' / 'month-end' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import usage  # noqa: E402 -- local standalone scripts are imported after adding their directory.


class UsageTests(unittest.TestCase):
    def export(self, payload, jsonl=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / ('usage.jsonl' if jsonl else 'usage.json')
        text = '\n'.join(json.dumps(item) for item in payload) if jsonl else json.dumps(payload)
        path.write_text(text, encoding='utf-8')
        return path

    def response(self, identity='resp-1', **metrics):
        counts = dict(input_tokens=100, output_tokens=30,
                      input_tokens_details=dict(cached_tokens=40, cache_write_tokens=10),
                      output_tokens_details=dict(reasoning_tokens=12), total_tokens=130)
        counts.update(metrics)
        return dict(id=identity, object='response', model='frozen-model', status='completed', usage=counts)

    def test_openai_responses_keeps_cache_and_reasoning_subsets(self):
        result = usage.load_usage(self.export(self.response()), 'openai')
        self.assertEqual(result['input_tokens'], 100)
        self.assertEqual(result['output_tokens'], 30)
        self.assertEqual(result['cache_read_tokens'], 40)
        self.assertEqual(result['cache_write_tokens'], 10)
        self.assertEqual(result['reasoning_tokens'], 12)
        self.assertIsNone(result['cost_usd'])
        self.assertEqual(result['calls'], 1)
        self.assertIn('includes reasoning', result['output_semantics'])

    def test_chat_completions_and_final_stream_event(self):
        completion = dict(id='chat-1', object='chat.completion', model='frozen-model',
                          usage=dict(prompt_tokens=80, completion_tokens=20,
                                     prompt_tokens_details=dict(cached_tokens=50),
                                     completion_tokens_details=dict(reasoning_tokens=5)))
        event = dict(type='response.completed', response=self.response())
        result = usage.load_usage(self.export([completion, event]), 'openai')
        self.assertEqual(result['input_tokens'], 180)
        self.assertEqual(result['output_tokens'], 50)
        self.assertEqual(result['cache_read_tokens'], 90)
        self.assertIsNone(result['cache_write_tokens'])
        self.assertEqual(result['calls'], 2)

    def test_progress_events_are_not_double_counted(self):
        progress = dict(type='response.in_progress', response=self.response())
        result = usage.load_usage(self.export([progress, dict(type='response.completed',
                                                             response=self.response())], jsonl=True), 'openai')
        self.assertEqual(result['calls'], 1)
        self.assertEqual(result['input_tokens'], 100)
        self.assertEqual(result['ignored_records'], 1)

    def test_failed_terminal_calls_remain_in_usage_totals(self):
        failed = self.response('resp-failed', input_tokens=20, output_tokens=0,
                               input_tokens_details=dict(cached_tokens=0, cache_write_tokens=0),
                               output_tokens_details=dict(reasoning_tokens=0), total_tokens=20)
        failed['status'] = 'failed'
        result = usage.load_usage(self.export([self.response(),
                                              dict(type='response.failed', response=failed)]), 'openai')
        self.assertEqual(result['calls'], 2)
        self.assertEqual(result['input_tokens'], 120)
        self.assertEqual(result['output_tokens'], 30)

    def test_duplicate_response_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            usage.load_usage(self.export([self.response(), self.response()]), 'openai')

    def test_provenance_supports_replay_checks_across_export_files(self):
        identified = usage.load_usage(self.export(self.response()), 'openai')
        self.assertEqual(identified['provenance']['response_ids'], ['resp-1'])
        self.assertEqual(identified['provenance']['record_fingerprints'], [])
        anonymous = self.response()
        anonymous.pop('id')
        first = usage.load_usage(self.export(anonymous), 'openai')
        second = usage.load_usage(self.export([anonymous], jsonl=True), 'openai')
        self.assertEqual(first['provenance']['response_ids'], [])
        self.assertEqual(first['provenance']['record_fingerprints'], second['provenance']['record_fingerprints'])

    def test_mixed_or_missing_models_are_not_arbitrarily_selected(self):
        second = self.response('resp-2')
        second['model'] = 'other-model'
        result = usage.load_usage(self.export([self.response(), second]), 'openai')
        self.assertIsNone(result['model'])
        self.assertIn('multiple models', ' '.join(result['warnings']))
        second.pop('model')
        result = usage.load_usage(self.export([self.response(), second]), 'openai')
        self.assertIsNone(result['model'])

    def test_anthropic_input_is_uncached_plus_read_plus_write(self):
        message = dict(id='msg-1', type='message', model='claude-frozen',
                       usage=dict(input_tokens=10, output_tokens=4,
                                  cache_read_input_tokens=100, cache_creation_input_tokens=20))
        result = usage.load_usage(self.export(message), 'anthropic')
        self.assertEqual(result['input_tokens'], 130)
        self.assertEqual(result['uncached_input_tokens'], 10)
        self.assertEqual(result['cache_read_tokens'], 100)
        self.assertEqual(result['cache_write_tokens'], 20)
        message['usage'].pop('cache_creation_input_tokens')
        result = usage.load_usage(self.export(message), 'anthropic')
        self.assertIsNone(result['input_tokens'])
        self.assertIsNone(result['cache_write_tokens'])

    def test_anthropic_stream_uses_final_cumulative_output_once(self):
        events = [
            dict(type='message_start', message=dict(id='msg-1', model='claude-frozen',
                 usage=dict(input_tokens=10, output_tokens=1, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0))),
            dict(type='content_block_delta', delta=dict(text='untrusted text')),
            dict(type='message_delta', usage=dict(output_tokens=7)),
            dict(type='message_delta', usage=dict(output_tokens=9)),
            dict(type='message_stop'),
        ]
        result = usage.load_usage(self.export(events, jsonl=True), 'anthropic')
        self.assertEqual(result['output_tokens'], 9)
        self.assertEqual(result['input_tokens'], 10)
        self.assertEqual(result['calls'], 1)
        with self.assertRaisesRegex(ValueError, 'unterminated'):
            usage.load_usage(self.export(events[:-1], jsonl=True), 'anthropic')

    def test_gemini_generate_content_preserves_separate_thoughts(self):
        response = dict(responseId='gem-1', modelVersion='gemini-frozen', usageMetadata=dict(
            promptTokenCount=100, candidatesTokenCount=20, cachedContentTokenCount=60,
            thoughtsTokenCount=10, toolUsePromptTokenCount=5, totalTokenCount=135))
        result = usage.load_usage(self.export(response), 'gemini')
        self.assertEqual(result['input_tokens'], 100)
        self.assertEqual(result['output_tokens'], 20)
        self.assertEqual(result['reasoning_tokens'], 10)
        self.assertEqual(result['tool_input_tokens'], 5)
        self.assertEqual(result['cache_read_tokens'], 60)
        self.assertIsNone(result['cache_write_tokens'])
        self.assertIn('excludes thoughts', result['output_semantics'])

    def test_gemini_interactions_uses_top_level_usage_not_steps(self):
        response = dict(id='inter-1', object='interaction', status='completed', model='gemini-frozen',
                        usage=dict(total_input_tokens=100, total_output_tokens=20,
                                   total_cached_tokens=60, total_thought_tokens=10,
                                   total_tool_use_tokens=5, total_tokens=135),
                        steps=[dict(step_usage=dict(total_input_tokens=100))])
        result = usage.load_usage(self.export(response), 'gemini')
        self.assertEqual(result['input_tokens'], 100)
        self.assertEqual(result['output_tokens'], 20)
        self.assertEqual(result['calls'], 1)
        self.assertEqual(result['reasoning_tokens'], 10)

    def test_missing_and_partial_metrics_stay_unknown(self):
        first = self.response(input_tokens_details=None)
        second = self.response('resp-2')
        result = usage.load_usage(self.export([first, second]), 'openai')
        self.assertIsNone(result['cache_read_tokens'])
        self.assertIsNone(result['cache_write_tokens'])
        self.assertEqual(result['input_tokens'], 200)

    def test_numeric_tokens_must_be_nonnegative_integers_not_bools(self):
        for invalid in (-1, True, 1.5, '4', float('nan'), float('inf')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                usage.load_usage(self.export(self.response(input_tokens=invalid)), 'openai')

    def test_unrelated_only_or_wrong_provider_records_are_errors(self):
        with self.assertRaisesRegex(ValueError, 'no supported'):
            usage.load_usage(self.export([dict(type='user', content='private')]), 'openai')
        with self.assertRaisesRegex(ValueError, 'no supported'):
            usage.load_usage(self.export(self.response()), 'anthropic')

    def test_duplicate_json_keys_and_malformed_jsonl_are_rejected(self):
        path = self.export(self.response())
        path.write_text('{"id":"one","id":"two"}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            usage.load_usage(path, 'openai')
        path = self.export([], jsonl=True)
        path.write_text('{}\nnot-json\n')
        with self.assertRaisesRegex(ValueError, 'line 2'):
            usage.load_usage(path, 'openai')

    def test_raw_cost_fields_are_not_assumed_billed_dollars(self):
        response = self.response()
        response['cost_usd'] = 0.2
        response['total_cost_usd'] = 0.3
        result = usage.load_usage(self.export(response), 'openai')
        self.assertIsNone(result['cost_usd'])

    def test_cli_is_offline_read_only_and_prints_provenance(self):
        path = self.export(self.response())
        before = set(path.parent.iterdir())
        result = subprocess.run([sys.executable, '-I', str(SCRIPTS / 'usage.py'),
                                 str(path), '--provider', 'openai'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        normalized = json.loads(result.stdout)
        self.assertEqual(normalized['calls'], 1)
        self.assertIsNone(normalized['cost_usd'])
        self.assertEqual(len(normalized['provenance']['source_sha256']), 64)
        self.assertEqual(set(path.parent.iterdir()), before)

    def test_explicit_invoice_envelope_and_sidecar_keep_provenance(self):
        billing = dict(currency='USD', cost_usd=0.25, source='provider invoice export', reference='invoice/example-1')
        envelope = dict(format='month-end-usage-v1', provider='openai',
                        responses=[self.response()], billing=billing)
        result = usage.load_usage(self.export(envelope), 'openai')
        self.assertEqual(result['cost_usd'], 0.25)
        self.assertFalse(result['provenance']['billing']['independently_verified'])
        self.assertEqual(result['provenance']['billing']['reference'], 'invoice/example-1')
        result = usage.load_usage(self.export(self.response()), 'openai', billing_path=self.export(billing))
        self.assertEqual(result['cost_usd'], 0.25)
        self.assertEqual(len(result['provenance']['billing_attachment']['source_sha256']), 64)
        with self.assertRaisesRegex(ValueError, 'both'):
            usage.load_usage(self.export(envelope), 'openai', billing_path=self.export(billing))

    def test_billing_cannot_be_estimated_from_non_usd_or_missing_provenance(self):
        valid = dict(currency='USD', cost_usd=0.25, source='provider invoice', reference='invoice/example')
        for changes in (dict(currency='EUR'), dict(source=''), dict(reference=''),
                        dict(cost_usd=-1), dict(cost_usd=True), dict(cost_usd=float('inf'))):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                usage.load_usage(self.export(self.response()), 'openai', billing_path=self.export(dict(valid, **changes)))

    def test_cache_subsets_and_totals_cannot_exceed_the_reported_scope(self):
        for metrics in (dict(input_tokens_details=dict(cached_tokens=120)),
                        dict(input_tokens_details=dict(cached_tokens=60, cache_write_tokens=50)),
                        dict(total_tokens=999),
                        dict(output_tokens_details=dict(reasoning_tokens=99))):
            with self.subTest(metrics=metrics), self.assertRaises(ValueError):
                usage.load_usage(self.export(self.response(**metrics)), 'openai')

    def test_malformed_event_discriminators_fail_cleanly(self):
        for field in ('type', 'object', 'status', 'event_type'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                usage.load_usage(self.export(dict(self.response(), **{field: {}})), 'openai')

    def test_sdk_gemini_fields_are_explicitly_supported(self):
        response = dict(response_id='g-1', model_version='gemini-frozen', usage_metadata=dict(
            prompt_token_count=8, candidates_token_count=4, cached_content_token_count=2,
            thoughts_token_count=3, tool_use_prompt_token_count=0, total_token_count=15))
        result = usage.load_usage(self.export(response), 'gemini')
        self.assertEqual(result['output_tokens'], 4)
        self.assertEqual(result['reasoning_tokens'], 3)
        response['usageMetadata'] = {}
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            usage.load_usage(self.export(response), 'gemini')

    def test_cumulative_anthropic_stream_counts_cannot_decrease(self):
        events = [dict(type='message_start', message=dict(id='m', model='claude-frozen',
                                                        usage=dict(input_tokens=3, output_tokens=1))),
                  dict(type='message_delta', usage=dict(output_tokens=10)),
                  dict(type='message_delta', usage=dict(output_tokens=2)),
                  dict(type='message_stop')]
        with self.assertRaisesRegex(ValueError, 'decreased'):
            usage.load_usage(self.export(events, jsonl=True), 'anthropic')

    def test_export_byte_bound_is_explicit(self):
        path = self.export(self.response())
        original = usage.MAX_EXPORT_BYTES
        try:
            usage.MAX_EXPORT_BYTES = 8
            with self.assertRaisesRegex(ValueError, 'exceeds 8 bytes'):
                usage.load_usage(path, 'openai')
        finally:
            usage.MAX_EXPORT_BYTES = original


if __name__ == '__main__':
    unittest.main()
