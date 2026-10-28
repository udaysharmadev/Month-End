# Offline usage imports

Use `scripts/usage.py` to normalize saved provider responses into a small JSON
receipt. It reads only the files explicitly provided, makes no network requests,
requires no credentials, and writes nothing by default. Provider responses can
contain private prompts or outputs; the receipt emits counts and provenance,
not those contents.

```bash
python3 scripts/usage.py /path/to/responses.jsonl --provider openai
python3 scripts/usage.py /path/to/messages.json --provider anthropic
python3 scripts/usage.py /path/to/generations.json --provider gemini
```

For Python callers, `load_usage(path, provider, *, billing_path=None)` returns a
dictionary containing `input_tokens`, `output_tokens`, cache counts,
`reasoning_tokens`, `tool_input_tokens`, `uncached_input_tokens`, `total_tokens`,
`model`, `calls`, `cost_usd`, warnings and provenance. Unknown or partially
reported metrics are `null`, not zero. A model is returned only when every
imported call names the same model. The source SHA-256 identifies the bytes
read; it does not authenticate their origin or prove export completeness.
Provenance also includes known response IDs and canonical fingerprints for
ID-less records so a benchmark runner can detect replay across separate files.

## Supported response shapes

- **OpenAI:** full Responses objects, full Chat Completions objects, terminal
  Responses events carrying a response object, and final usage-bearing Chat
  Completions chunks with empty choices. Provisional events and chunks without
  usage are excluded. Input/output are provider totals; cache and reasoning
  counts are subsets and are not added again.
  [Responses usage](https://developers.openai.com/api/reference/cli/resources/responses/methods/retrieve),
  [Chat Completions usage](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
- **Anthropic:** full Messages responses, or sequential JSONL message streams
  from `message_start` through `message_stop`. Stream output counts are
  cumulative, so only the latest reported total is used. Normalized input is
  uncached input plus cache-read plus cache-creation tokens; if a component is
  missing, the total remains unknown and the reported components stay available.
  Overlapping or unterminated streams are errors.
  [Input/cache accounting](https://platform.claude.com/docs/en/build-with-claude/prompt-caching),
  [stream usage](https://platform.claude.com/docs/en/build-with-claude/streaming).
- **Gemini:** generateContent responses with `usageMetadata` (or explicit SDK
  snake-case fields), and Interactions objects with top-level `usage`.
  Interaction step usage is not added to the parent total. Prompt counts include
  cached content. Generated-response/candidate counts, thoughts and tool-prompt
  counts remain separate; the importer does not silently combine them into an
  OpenAI-shaped total. A completed Interaction event is accepted only if it
  carries the full response including usage; otherwise export the retrieved
  Interaction object. No cache-write count is invented.
  [generateContent usage](https://ai.google.dev/api/generate-content#UsageMetadata),
  [Interactions usage](https://ai.google.dev/api/interactions-api).

These mappings were checked against the linked primary documentation on
28 October 2026. Token scopes differ across providers; compare like-for-like
models and formats rather than pooling these secondary metrics blindly.
Native usage responses do not establish actual billed dollars.

## Actual billed-dollar attachments

Supply an aggregate billing record only after allocating actual billed spending
to exactly the calls in the usage file, including failed attempts. The importer
checks its shape and records its provenance; it cannot reconcile an invoice or
verify the allocation. Estimated list-price costs and subscription quota
percentages do not belong in this attachment.

```json
{
  "currency": "USD",
  "cost_usd": 0.25,
  "source": "provider invoice export",
  "reference": "invoice identifier and allocation record"
}
```

```bash
python3 scripts/usage.py responses.json --provider openai --billing billed.json
```

The output marks these dollars as user-attached and not independently verified.
Missing cost remains `null`; there is no byte-to-token, token-to-dollar or
currency conversion. Raw `cost_usd` or `total_cost_usd` fields inside native
responses are not automatically trusted as invoiced cost.

An explicit combined export uses this project-owned envelope:

```json
{
  "format": "month-end-usage-v1",
  "provider": "openai",
  "responses": [],
  "billing": {
    "currency": "USD",
    "cost_usd": 0.25,
    "source": "provider invoice export",
    "reference": "invoice identifier and allocation record"
  }
}
```

Populate `responses` with complete provider response objects. The empty array
above is a schema illustration and is rejected as a measurement. `billing` is
optional; do not also provide `--billing` when it is present in the envelope.

## Import integrity

Inputs may be one response object, an array of responses/events, or JSONL with
one object per line. Exports are bounded to 64 MiB; split larger files on complete
call boundaries. Duplicate JSON keys, duplicate final response IDs, malformed
records, impossible subset counts, negative/fractional/bool token counts and
non-finite numbers are errors. When IDs are absent, exact-content duplicates are
rejected and a warning explains that stronger deduplication was impossible.

Usage-bearing snapshots of the same call must not be submitted as separate
calls. Export one final record per call; repeated Gemini streaming snapshots are
rejected when they share a response ID. A saved export can omit calls without
the importer detecting that omission, so independent task grading, trace
retention and billing reconciliation remain necessary.
