"""Offline tokenizer integrity checks; real-vocabulary tests are opt-in."""
import base64
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills' / 'month-end' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import token_count  # noqa: E402 -- local standalone scripts are imported after adding their directory.

load_tiktoken_bpe = None  # Names resolved only in the isolated fixture constructor.
FIXTURE_HASH = ''


def _fixture_constructor():
    ranks = load_tiktoken_bpe('https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken',
                              expected_hash=FIXTURE_HASH)
    return {'name': 'cl100k_base', 'mergeable_ranks': ranks, 'pat_str': 'fixture', 'special_tokens': {}}


def _changed_constructor():
    return __import__('urllib.request').request.urlopen('https://example.invalid')


class TokenCountIntegrityTests(unittest.TestCase):
    def vocabulary(self):
        raw = b''.join(base64.b64encode(bytes([number])) + b' ' + str(number).encode() + b'\n'
                       for number in range(256))
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'fixture.tiktoken'
        path.write_bytes(raw)
        return path, raw

    def test_small_vocabulary_parser_preserves_exact_bytes_and_ranks(self):
        _, raw = self.vocabulary()
        result = token_count._parse_vocabulary(raw)
        self.assertEqual(len(result), 256)
        for number in range(256):
            self.assertEqual(result[bytes([number])], number)

    def test_invalid_duplicate_and_incomplete_vocabularies_are_rejected(self):
        _, raw = self.vocabulary()
        for bad in (b'', b'not-base64 -1\n', raw + b'AA== 999\n', raw + b'QUJD 1\n',
                    b'AA== 0\n', raw + b'! 999\n'):
            with self.subTest(bad=bad[-20:]), self.assertRaises(ValueError):
                token_count._parse_vocabulary(bad)

    def test_unverified_vocabulary_is_rejected_before_constructor(self):
        path, _ = self.vocabulary()
        public = types.SimpleNamespace(cl100k_base=mock.Mock(side_effect=AssertionError('must not construct')))
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            token_count._local_parameters('cl100k_base', path, public)
        public.cl100k_base.assert_not_called()

    def test_local_constructor_uses_only_verified_bytes_without_mutating_loader(self):
        path, raw = self.vocabulary()
        digest = hashlib.sha256(raw).hexdigest()
        blocked = mock.Mock(side_effect=AssertionError('package loader must not run'))
        public = types.SimpleNamespace(cl100k_base=_fixture_constructor, FIXTURE_HASH=digest,
                                       load_tiktoken_bpe=blocked)
        with mock.patch.dict(token_count.VOCABULARIES, {'cl100k_base': ('cl100k_base.tiktoken', digest)}):
            parameters, actual = token_count._local_parameters('cl100k_base', path, public)
        self.assertEqual(actual, digest)
        self.assertEqual(len(parameters['mergeable_ranks']), 256)
        self.assertIs(public.load_tiktoken_bpe, blocked)
        blocked.assert_not_called()

    def test_changed_constructor_fails_closed_instead_of_importing_network_code(self):
        path, raw = self.vocabulary()
        digest = hashlib.sha256(raw).hexdigest()
        public = types.SimpleNamespace(cl100k_base=_changed_constructor)
        with mock.patch.dict(token_count.VOCABULARIES, {'cl100k_base': ('cl100k_base.tiktoken', digest)}):
            with self.assertRaisesRegex(ValueError, 'constructor changed'):
                token_count._local_parameters('cl100k_base', path, public)

    def test_unknown_model_prefixes_and_mismatched_encodings_are_rejected(self):
        models = types.SimpleNamespace(MODEL_TO_ENCODING={'gpt-4': 'cl100k_base', 'gpt2': 'gpt2'})
        self.assertEqual(token_count._select_encoding('gpt-4', None, models), 'cl100k_base')
        self.assertEqual(token_count._select_encoding(None, 'o200k_base', models), 'o200k_base')
        for model, encoding in [('gpt-4-FAKE', None), ('gpt-4', 'o200k_base'),
                                ('gpt2', None), (None, 'made-up'), (None, None)]:
            with self.subTest(model=model, encoding=encoding), self.assertRaises(ValueError):
                token_count._select_encoding(model, encoding, models)

    def test_urls_are_never_accepted_as_vocabulary_paths(self):
        with self.assertRaisesRegex(ValueError, 'local file'):
            token_count._local_parameters('cl100k_base', 'https://example.invalid/vocab', object())

    def test_missing_optional_dependency_has_no_estimation_fallback(self):
        with mock.patch.dict(sys.modules, {'tiktoken': None}):
            with self.assertRaisesRegex(ValueError, 'not installed'):
                token_count.count_text('hello', '/unused', encoding='cl100k_base')

    def test_oversized_or_surrogate_text_is_rejected_before_tokenizer_import(self):
        with mock.patch.object(token_count, '_dependencies', side_effect=AssertionError('must not import')):
            with self.assertRaisesRegex(ValueError, 'surrogates'):
                token_count.count_text('\ud800', '/unused', encoding='cl100k_base')
            with mock.patch.object(token_count, 'MAX_TEXT_BYTES', 2):
                with self.assertRaisesRegex(ValueError, 'exceeds'):
                    token_count.count_text('abc', '/unused', encoding='cl100k_base')


REAL_VOCAB = os.environ.get('MONTH_END_TEST_CL100K_VOCAB')
HAS_TOKENIZER = importlib.util.find_spec('tiktoken') is not None


@unittest.skipUnless(HAS_TOKENIZER and REAL_VOCAB, 'Provision tiktoken and MONTH_END_TEST_CL100K_VOCAB for real encoding checks')
class RealTokenCountTests(unittest.TestCase):
    def test_real_encoding_is_exact_for_text_and_never_calls_a_downloading_loader(self):
        import tiktoken.load
        from tiktoken_ext import openai_public
        original_loader = openai_public.load_tiktoken_bpe
        with mock.patch.object(tiktoken.load, 'read_file', side_effect=AssertionError('network loader called')), \
                mock.patch.object(tiktoken.load, 'read_file_cached', side_effect=AssertionError('cache loader called')), \
                mock.patch.object(openai_public, 'load_tiktoken_bpe', side_effect=AssertionError('package loader called')):
            result = token_count.count_text('hello world', REAL_VOCAB, model='gpt-4')
        self.assertIs(openai_public.load_tiktoken_bpe, original_loader)
        self.assertEqual(result['text_tokens'], 2)
        self.assertEqual(result['encoding'], 'cl100k_base')
        self.assertTrue(result['exact_for_text'])
        self.assertEqual(result['vocabulary_sha256'], token_count.VOCABULARIES['cl100k_base'][1])
        self.assertTrue(result['tokenizer_version'])

    def test_real_unicode_and_literal_special_marker_round_trip_scope(self):
        import tiktoken
        from tiktoken_ext import openai_public
        parameters, _ = token_count._local_parameters('cl100k_base', REAL_VOCAB, openai_public)
        encoder = tiktoken.Encoding(**parameters)
        text = 'नमस्ते 👋\r\n<|endoftext|>'
        result = token_count.count_text(text, REAL_VOCAB, encoding='cl100k_base')
        encoded = encoder.encode_ordinary(text)
        self.assertEqual(result['text_tokens'], len(encoded))
        self.assertEqual(encoder.decode(encoded), text)
        self.assertEqual(result['text_bytes'], len(text.encode()))
        self.assertGreater(token_count.count_text('<|endoftext|>', REAL_VOCAB,
                                                encoding='cl100k_base')['text_tokens'], 1)

    def test_cli_reports_scope_and_does_not_write_files(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'text ü.txt'
            source.write_bytes(b'hello world')
            before = set(Path(directory).iterdir())
            result = subprocess.run([sys.executable, str(SCRIPTS / 'token_count.py'), '--file', str(source),
                                     '--model', 'gpt-4', '--vocabulary', REAL_VOCAB], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt['text_tokens'], 2)
            self.assertIn('Not provider usage', ' '.join(receipt['limitations']))
            self.assertEqual(set(Path(directory).iterdir()), before)


if __name__ == '__main__':
    unittest.main()
