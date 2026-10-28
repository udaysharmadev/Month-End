#!/usr/bin/env python3
"""Exact local plain-text token counts with an explicit verified vocabulary."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import types
from importlib import metadata
from pathlib import Path
from typing import Any

MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_VOCAB_BYTES = 16 * 1024 * 1024
# Official hashes in openai/tiktoken's openai_public.py, checked 28 Oct 2026.
# The constructors also supply the expected hash; both must agree.
VOCABULARIES = {
    'r50k_base': ('r50k_base.tiktoken', '306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930'),
    'p50k_base': ('p50k_base.tiktoken', '94b5ca7dff4d00767bc256fdd1b27e5b17361d7b8a5f968547f9f23eb70d2069'),
    'p50k_edit': ('p50k_base.tiktoken', '94b5ca7dff4d00767bc256fdd1b27e5b17361d7b8a5f968547f9f23eb70d2069'),
    'cl100k_base': ('cl100k_base.tiktoken', '223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7'),
    'o200k_base': ('o200k_base.tiktoken', '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d'),
    'o200k_harmony': ('o200k_base.tiktoken', '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d'),
}


def _dependencies():
    try:
        import tiktoken
        from tiktoken import model as model_module
        from tiktoken_ext import openai_public
    except ImportError as error:
        raise ValueError('optional tiktoken package is not installed; provision it explicitly before counting') from error
    return tiktoken, model_module, openai_public


def _select_encoding(model, encoding, model_module):
    if model is not None and (not isinstance(model, str) or not model):
        raise ValueError('model must be a nonempty explicit model identifier')
    if encoding is not None and (not isinstance(encoding, str) or not encoding):
        raise ValueError('encoding must be a nonempty explicit encoding name')
    if model is None and encoding is None:
        raise ValueError('provide an explicit --model or --encoding')
    if model is not None:
        if model not in model_module.MODEL_TO_ENCODING:
            raise ValueError(f'unsupported exact model mapping: {model}; arbitrary prefix matching is disabled')
        mapped = model_module.MODEL_TO_ENCODING[model]
        if encoding is not None and mapped != encoding:
            raise ValueError(f'model {model} maps to {mapped}, not {encoding}')
        encoding = mapped
    if encoding not in VOCABULARIES:
        raise ValueError(f'unsupported encoding: {encoding}; supported: ' + ', '.join(sorted(VOCABULARIES)))
    return encoding


def _parse_vocabulary(raw):
    ranks = {}
    used_ranks = set()
    for number, line in enumerate(raw.splitlines(), 1):
        if not line:
            continue
        try:
            token_text, rank_text = line.split()
            token = base64.b64decode(token_text, validate=True)
            if not rank_text.isdigit():
                raise ValueError('rank must be a nonnegative integer')
            rank = int(rank_text)
        except (ValueError, TypeError) as error:
            raise ValueError(f'invalid tokenizer vocabulary line {number}') from error
        if not token or token in ranks or rank in used_ranks:
            raise ValueError(f'empty token, duplicate token or duplicate rank at vocabulary line {number}')
        ranks[token] = rank
        used_ranks.add(rank)
    if not ranks:
        raise ValueError('tokenizer vocabulary is empty')
    if any(bytes([value]) not in ranks for value in range(256)):
        raise ValueError('tokenizer vocabulary must contain all 256 single-byte tokens')
    return ranks


def _local_parameters(encoding, vocabulary, public_module):
    path = Path(vocabulary).expanduser()
    # A local path is mandatory. URLs must never be passed to a provider loader.
    if '://' in str(vocabulary):
        raise ValueError('vocabulary must be an explicit local file, not a URL')
    with path.open('rb') as stream:
        raw = stream.read(MAX_VOCAB_BYTES + 1)
    if len(raw) > MAX_VOCAB_BYTES:
        raise ValueError(f'vocabulary exceeds {MAX_VOCAB_BYTES} bytes')
    filename, expected_hash = VOCABULARIES[encoding]
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_hash:
        raise ValueError(f'vocabulary SHA256 mismatch for {encoding}: expected {expected_hash}, got {digest}')
    ranks = _parse_vocabulary(raw)
    loader_calls = 0

    def local_loader(url, expected_hash=None):
        nonlocal loader_calls
        canonical = 'https://openaipublic.blob.core.windows.net/encodings/' + filename
        if url != canonical or expected_hash != digest:
            raise ValueError('installed tokenizer constructor vocabulary/hash differs from the verified mapping')
        loader_calls += 1
        return ranks

    # Use the installed official constructors for patterns and special-token
    # tables, but provide isolated globals with no network/cache loader or imports.
    # This does not mutate the package's global loader or shared encoder registry.
    namespace: dict[str, Any] = {name: value for name, value in vars(public_module).items() if isinstance(value, str)}
    namespace.update(__builtins__={'range': range}, load_tiktoken_bpe=local_loader)
    constructors = ('o200k_base', encoding) if encoding == 'o200k_harmony' else (encoding,)
    for name in constructors:
        original = getattr(public_module, name, None)
        if not isinstance(original, types.FunctionType):
            raise ValueError(f'installed tokenizer lacks supported constructor: {name}')
        namespace[name] = types.FunctionType(original.__code__, namespace, name, original.__defaults__)
    try:
        parameters = namespace[encoding]()
    except (NameError, KeyError, TypeError, AttributeError) as error:
        raise ValueError('installed tokenizer constructor changed; refusing unsupported offline construction') from error
    if not isinstance(parameters, dict) or loader_calls != 1 or parameters.get('mergeable_ranks') is not ranks or parameters.get('name') != encoding:
        raise ValueError('installed tokenizer constructor did not use exactly the verified local vocabulary')
    return parameters, digest


def count_text(text, vocabulary, *, model=None, encoding=None):
    """Count ordinary UTF-8 text exactly for a verified local encoder, not a request."""
    if not isinstance(text, str):
        raise ValueError('text must be a Unicode string')
    try:
        raw = text.encode('utf-8')
    except UnicodeEncodeError as error:
        raise ValueError('text contains unpaired Unicode surrogates') from error
    if len(raw) > MAX_TEXT_BYTES:
        raise ValueError(f'text exceeds {MAX_TEXT_BYTES} bytes; explicit text counting is bounded')
    tiktoken, model_module, public_module = _dependencies()
    selected = _select_encoding(model, encoding, model_module)
    parameters, digest = _local_parameters(selected, vocabulary, public_module)
    encoder = tiktoken.Encoding(**parameters)
    tokens = encoder.encode_ordinary(text)
    return {
        'text_tokens': len(tokens), 'exact_for_text': True,
        'model': model, 'encoding': selected, 'provider': 'openai',
        'text_bytes': len(raw), 'text_sha256': hashlib.sha256(raw).hexdigest(),
        'vocabulary_sha256': digest, 'tokenizer': 'tiktoken',
        'tokenizer_version': metadata.version('tiktoken'),
        'special_token_policy': 'ordinary text; reserved-looking strings are not control tokens',
        'limitations': [
            'Exact only for this UTF-8 text under the named encoding and tokenizer version.',
            'Not a chat, tool-schema, image/audio, hidden-context or full API request token count.',
            'Not provider usage, cache accounting, billed cost or subscription quota consumption.',
            'Exact model mappings come from the installed package and do not prove API availability.',
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--file', type=Path, help='UTF-8 text file; bytes/newlines are not normalized')
    inputs.add_argument('--text', help='Literal plain text')
    parser.add_argument('--model', help='Exact model key in installed tiktoken; no guessed prefixes')
    parser.add_argument('--encoding', choices=sorted(VOCABULARIES))
    parser.add_argument('--vocabulary', '--vocab', required=True, help='Explicit local official .tiktoken file')
    args = parser.parse_args(argv)
    try:
        text = args.text
        if args.file is not None:
            with args.file.open('rb') as source:
                raw = source.read(MAX_TEXT_BYTES + 1)
            if len(raw) > MAX_TEXT_BYTES:
                raise ValueError(f'text exceeds {MAX_TEXT_BYTES} bytes')
            text = raw.decode('utf-8')
        result = count_text(text, args.vocabulary, model=args.model, encoding=args.encoding)
    except (OSError, ValueError, metadata.PackageNotFoundError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
