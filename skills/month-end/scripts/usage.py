#!/usr/bin/env python3
"""Offline provider-usage import. No keys, network access, or price inference."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

MAX_EXPORT_BYTES = 64 * 1024 * 1024
COUNTS = ('input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens',
          'reasoning_tokens', 'uncached_input_tokens', 'tool_input_tokens', 'total_tokens')
TERMINAL = {'completed', 'failed', 'incomplete', 'cancelled', 'requires_action'}


def _tags(record):
    for field in ('type', 'object', 'status', 'event_type'):
        if field in record and not isinstance(record[field], str):
            raise ValueError(f'{field} must be a string')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f'non-finite JSON number: {value}')


def _decode(text):
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)


def _read(path):
    path = Path(path).expanduser().resolve()
    with path.open('rb') as source:
        raw = source.read(MAX_EXPORT_BYTES + 1)
    if len(raw) > MAX_EXPORT_BYTES:
        raise ValueError(f'export exceeds {MAX_EXPORT_BYTES} bytes; split it into complete calls')
    return path, raw, raw.decode('utf-8-sig')


def _count(mapping, field):
    value = mapping.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f'{field} must be a nonnegative integer or null')
    return value


def _mapping(value, label, optional=False):
    if value is None and optional:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object')
    return value


def _alias(mapping, camel, snake):
    if camel in mapping and snake in mapping:
        raise ValueError(f'ambiguous fields: both {camel} and {snake}')
    return camel if camel in mapping else snake


def _normalize(response, provider):
    _tags(response)
    result: dict[str, Any] = dict.fromkeys(COUNTS)
    result.update(model=None, identity=None, format=None)
    model = response.get('model')
    if provider == 'openai':
        kind = response.get('object')
        if kind not in {'response', 'chat.completion', 'chat.completion.chunk'}:
            return None
        if kind == 'response' and response.get('status', 'completed') not in TERMINAL:
            return None
        if response.get('usage') is None:
            return None
        data = _mapping(response['usage'], 'usage')
        if kind == 'response':
            prompt, output, detail = 'input_tokens', 'output_tokens', 'input_tokens_details'
            reasoning_detail = 'output_tokens_details'
        else:
            prompt, output, detail = 'prompt_tokens', 'completion_tokens', 'prompt_tokens_details'
            reasoning_detail = 'completion_tokens_details'
            if kind == 'chat.completion.chunk' and response.get('choices'):
                raise ValueError('usage-bearing chat stream chunk must be the final empty-choices usage chunk')
        details = _mapping(data.get(detail), detail, optional=True)
        reasoning = _mapping(data.get(reasoning_detail), reasoning_detail, optional=True)
        result.update(input_tokens=_count(data, prompt), output_tokens=_count(data, output),
                      cache_read_tokens=_count(details, 'cached_tokens'),
                      cache_write_tokens=_count(details, 'cache_write_tokens'),
                      reasoning_tokens=_count(reasoning, 'reasoning_tokens'),
                      total_tokens=_count(data, 'total_tokens'))
        result['format'] = 'openai.responses' if kind == 'response' else 'openai.chat-completions'
        result['input_semantics'] = 'provider total input; includes cached/cache-write subsets'
        result['output_semantics'] = 'provider total output; includes reasoning subset'
    elif provider == 'anthropic':
        if response.get('type') != 'message' or response.get('usage') is None:
            return None
        data = _mapping(response['usage'], 'usage')
        fresh = _count(data, 'input_tokens')
        read = _count(data, 'cache_read_input_tokens')
        write = _count(data, 'cache_creation_input_tokens')
        result.update(input_tokens=sum((fresh, read, write)) if None not in (fresh, read, write) else None,
                      uncached_input_tokens=fresh, output_tokens=_count(data, 'output_tokens'),
                      cache_read_tokens=read, cache_write_tokens=write)
        result['format'] = 'anthropic.messages'
        result['input_semantics'] = 'uncached input + cache reads + cache writes; unknown if any component is absent'
        result['output_semantics'] = 'provider output token count; do not add a separate thinking estimate'
    elif provider == 'gemini':
        if 'usageMetadata' in response or 'usage_metadata' in response:
            key = _alias(response, 'usageMetadata', 'usage_metadata')
            data = _mapping(response[key], key)
            fields = {
                'input_tokens': ('promptTokenCount', 'prompt_token_count'),
                'output_tokens': ('candidatesTokenCount', 'candidates_token_count'),
                'cache_read_tokens': ('cachedContentTokenCount', 'cached_content_token_count'),
                'reasoning_tokens': ('thoughtsTokenCount', 'thoughts_token_count'),
                'tool_input_tokens': ('toolUsePromptTokenCount', 'tool_use_prompt_token_count'),
                'total_tokens': ('totalTokenCount', 'total_token_count'),
            }
            for normalized, aliases in fields.items():
                result[normalized] = _count(data, _alias(data, *aliases))
            model = response.get(_alias(response, 'modelVersion', 'model_version'))
            result['identity'] = response.get(_alias(response, 'responseId', 'response_id'))
            result['format'] = 'gemini.generate-content'
        elif response.get('object') == 'interaction':
            if response.get('status', 'completed') not in TERMINAL or response.get('usage') is None:
                return None
            data = _mapping(response['usage'], 'usage')
            interaction_fields = dict(input_tokens='total_input_tokens', output_tokens='total_output_tokens',
                          cache_read_tokens='total_cached_tokens', reasoning_tokens='total_thought_tokens',
                          tool_input_tokens='total_tool_use_tokens', total_tokens='total_tokens')
            for normalized, field in interaction_fields.items():
                result[normalized] = _count(data, field)
            result['format'] = 'gemini.interactions'
        else:
            return None
        result['input_semantics'] = 'provider prompt/context token count; includes cached subset; tool prompts separate'
        result['output_semantics'] = 'provider generated-response/candidate tokens; excludes thoughts reported separately'
    else:
        raise ValueError('provider must be openai, anthropic or gemini')
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError('model identifier must be a nonempty string when present')
    result['model'] = model
    if result['identity'] is None:
        result['identity'] = response.get('id')
    identity = result['identity']
    if identity is not None and (not isinstance(identity, str) or not identity):
        raise ValueError('response identifier must be a nonempty string when present')
    if result['input_tokens'] is None and result['output_tokens'] is None and result['uncached_input_tokens'] is None:
        raise ValueError('recognized usage record has no input or output token count')
    if provider != 'anthropic' and result['input_tokens'] is not None and result['cache_read_tokens'] is not None:
        if result['cache_read_tokens'] > result['input_tokens']:
            raise ValueError('cached token subset exceeds reported input tokens')
    if provider == 'openai':
        if result['output_tokens'] is not None and result['reasoning_tokens'] is not None:
            if result['reasoning_tokens'] > result['output_tokens']:
                raise ValueError('reasoning token subset exceeds reported output tokens')
        if result['input_tokens'] is not None and result['cache_write_tokens'] is not None:
            if result['cache_write_tokens'] > result['input_tokens']:
                raise ValueError('cache-write token subset exceeds reported input tokens')
        if None not in (result['input_tokens'], result['cache_read_tokens'], result['cache_write_tokens']):
            fresh = result['input_tokens'] - result['cache_read_tokens'] - result['cache_write_tokens']
            if fresh < 0:
                raise ValueError('cache-read and cache-write subsets exceed reported input tokens')
            result['uncached_input_tokens'] = fresh
        if None not in (result['input_tokens'], result['output_tokens'], result['total_tokens']):
            if result['input_tokens'] + result['output_tokens'] != result['total_tokens']:
                raise ValueError('OpenAI total_tokens disagrees with input_tokens + output_tokens')
    return result


def _billing(record):
    record = _mapping(record, 'billing')
    for field in ('source', 'reference'):
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ValueError(f'billing.{field} requires a nonempty provenance string')
    if record.get('currency') != 'USD':
        raise ValueError('billing.currency must be USD; no currency conversion is performed')
    cost = record.get('cost_usd')
    try:
        valid = not isinstance(cost, bool) and isinstance(cost, (int, float)) and math.isfinite(cost) and cost >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError('billing.cost_usd must be finite nonnegative actual dollars')
    return dict(cost_usd=cost, source=record['source'], reference=record['reference'],
                currency='USD', independently_verified=False)


def load_usage(path, provider, *, billing_path=None):
    """Import complete exported calls. Absent metrics never become zero or prices."""
    if provider not in {'openai', 'anthropic', 'gemini'}:
        raise ValueError('provider must be openai, anthropic or gemini')
    source, raw, text = _read(path)
    if not text.strip():
        raise ValueError('empty usage export')
    try:
        parsed = _decode(text)
    except json.JSONDecodeError as original:
        parsed = []
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                parsed.append(_decode(line))
            except (ValueError, json.JSONDecodeError) as error:
                raise ValueError(f'invalid JSONL at line {number}: {error}') from original
    attached = None
    if isinstance(parsed, dict) and parsed.get('format') == 'month-end-usage-v1':
        if parsed.get('provider') != provider:
            raise ValueError('envelope provider differs from selected provider')
        attached = parsed.get('billing')
        parsed = parsed.get('responses')
        if not isinstance(parsed, list):
            raise ValueError('usage envelope responses must be an array of provider responses')
    records = parsed if isinstance(parsed, list) else [parsed]
    normalized = []
    seen = set()
    ignored = 0
    no_identity = 0
    response_ids = []
    record_fingerprints = []
    stream = None
    stream_output_seen = False
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('every usage export record must be an object')
        _tags(record)
        event = record.get('type', '')
        if provider == 'anthropic' and event in {'message_start', 'message_delta', 'message_stop'}:
            if event == 'message_start':
                if stream is not None:
                    raise ValueError('overlapping Anthropic streams cannot be disambiguated')
                message = _mapping(record.get('message'), 'message_start.message')
                stream = dict(message, type='message', usage=dict(_mapping(message.get('usage'), 'message.usage')))
                for field in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'):
                    _count(stream['usage'], field)
                stream_output_seen = False
                continue
            if stream is None:
                raise ValueError(f'{event} without an active message_start')
            if event == 'message_delta':
                delta = _mapping(record.get('usage'), 'message_delta.usage', optional=True)
                for field in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'):
                    _count(delta, field)
                previous = stream['usage'].get('output_tokens')
                following = delta.get('output_tokens')
                if previous is not None and following is not None and following < previous:
                    raise ValueError('cumulative Anthropic output token count decreased')
                stream['usage'].update(delta)
                stream_output_seen |= 'output_tokens' in delta
                continue
            if not stream_output_seen:
                stream['usage']['output_tokens'] = None
            record, stream = stream, None
        elif provider == 'openai' and isinstance(event, str) and event.startswith('response.'):
            if event not in {'response.completed', 'response.failed', 'response.incomplete', 'response.cancelled'}:
                ignored += 1
                continue
            record = _mapping(record.get('response'), 'response event payload')
        elif provider == 'gemini' and 'event_type' in record:
            if record['event_type'] != 'interaction.completed':
                ignored += 1
                continue
            record = _mapping(record.get('interaction'), 'interaction event payload')
        item = _normalize(record, provider)
        if item is None:
            ignored += 1
            continue
        identity = item['identity']
        if identity is None:
            no_identity += 1
            fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
            record_fingerprints.append(fingerprint)
            identity = 'content-sha256:' + fingerprint
        else:
            response_ids.append(identity)
        key = item['format'], identity
        if key in seen:
            raise ValueError(f'duplicate usage response: {identity}; export one final usage record per call')
        seen.add(key)
        normalized.append(item)
    if stream is not None:
        raise ValueError('unterminated Anthropic stream; final message_stop is required')
    if not normalized:
        raise ValueError(f'no supported {provider} usage records found')
    totals = {metric: sum(row[metric] for row in normalized)
              if all(row[metric] is not None for row in normalized) else None for metric in COUNTS}
    models = {row['model'] for row in normalized}
    warnings = []
    if len(models) > 1:
        warnings.append('multiple models or missing model identifiers; aggregate model is unknown')
    elif None in models:
        warnings.append('model identifier is unavailable in the export')
    if ignored:
        warnings.append(f'{ignored} unrelated or provisional event(s) ignored; export completeness is not verified')
    if no_identity:
        warnings.append(f'{no_identity} response(s) lack provider IDs; only exact-content duplicate checks were possible')
    missing = [metric for metric in COUNTS if totals[metric] is None]
    if missing:
        warnings.append('absent or partial metrics remain unknown: ' + ', '.join(missing))
    billing_provenance = None
    if billing_path is not None:
        if attached is not None:
            raise ValueError('billing supplied both in envelope and separate attachment')
        billing_source, billing_raw, billing_text = _read(billing_path)
        attached = _decode(billing_text)
        billing_provenance = dict(source_path=str(billing_source), source_sha256=hashlib.sha256(billing_raw).hexdigest())
    billed = _billing(attached) if attached is not None else None
    if billed:
        warnings.append('billed dollars are supplied by the user attachment and are not independently reconciled')
    else:
        warnings.append('native token usage is not a billed-dollar record; cost_usd is unknown')
    totals.update(provider=provider, model=next(iter(models)) if len(models) == 1 else None,
                  calls=len(normalized), ignored_records=ignored, cost_usd=billed['cost_usd'] if billed else None,
                  formats=sorted({row['format'] for row in normalized}), warnings=warnings,
                  input_semantics='; '.join(sorted({row['input_semantics'] for row in normalized})),
                  output_semantics='; '.join(sorted({row['output_semantics'] for row in normalized})),
                  provenance=dict(source_path=str(source), source_sha256=hashlib.sha256(raw).hexdigest(),
                                  format_version=1, billing=billed, billing_attachment=billing_provenance,
                                  response_ids=response_ids, record_fingerprints=record_fingerprints,
                                  completeness_verified=False))
    return totals


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('--provider', required=True, choices=['openai', 'anthropic', 'gemini'])
    parser.add_argument('--billing', type=Path, help='Explicit aggregate USD invoice attachment with source/reference')
    args = parser.parse_args(argv)
    try:
        result = load_usage(args.export, args.provider, billing_path=args.billing)
    except (OSError, ValueError, RecursionError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
