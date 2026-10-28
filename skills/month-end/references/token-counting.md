# Exact local text counts

Use `scripts/token_count.py` only when an exact count for a particular plain-text
string will help the task. It is an optional tool, not an always-on tokenizer or
a source of provider billing. Ordinary helper commands do not import tiktoken.

The counter requires both an explicitly installed `tiktoken` package and an
explicit local vocabulary file. It never calls `get_encoding`,
`encoding_for_model`, the package cache loader, a downloader, or a provider API.
It verifies the vocabulary's SHA-256 against the official pinned hash before
constructing a local encoder. Patterns and special-token tables come from the
installed official constructor in isolated globals containing only constants,
`range`, and the verified local loader; package globals and caches are unchanged.
An unsupported constructor change fails closed.

## Count a file or literal text

From the installed skill directory:

```bash
python3 scripts/token_count.py --file /path/to/source.txt \
  --model gpt-4 --vocabulary /path/to/cl100k_base.tiktoken
python3 scripts/token_count.py --text 'hello world' \
  --encoding cl100k_base --vocabulary /path/to/cl100k_base.tiktoken
```

Text files must be valid UTF-8. Their bytes, BOM characters and line endings are
not normalized. Input text is capped at 8 MiB and vocabularies at 16 MiB. Reserved
token-looking strings are encoded as ordinary text, not interpreted as protocol
controls. The JSON receipt reports text tokens, model (or `null` for an explicit
encoding), encoding, tokenizer version, text and vocabulary hashes, byte count,
special-token policy and limitations. It does not print the text or token IDs.

Only exact model names in the installed package's `MODEL_TO_ENCODING` table are
accepted. Guessed model prefixes, fine-tune identifiers and unsupported future
names are rejected. For example, `gpt-4-FAKE` will not silently inherit an
encoding. Supplying both `--model` and `--encoding` requires an exact mapping
match. The mapping describes that installed tokenizer release; it does not
establish that a model is currently offered by an API.

Supported encoding families are `r50k_base`, `p50k_base`, `p50k_edit`,
`cl100k_base`, `o200k_base`, and `o200k_harmony` when their official constructors
are present. `p50k_edit` shares the p50k vocabulary; Harmony shares o200k's BPE
vocabulary but uses its own installed special-token table. GPT-2's two-file
format and other provider tokenizers are not silently substituted.

## Explicit maintainer provisioning

Provisioning is a separate, user-requested setup operation with network access.
The counting command never does this automatically. Use a local virtual
environment; the optional dependency is not required to install or run the core
skill helpers.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install 'tiktoken==0.14.0'
mkdir -p /path/to/tokenizer-data
curl --fail --location \
  'https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken' \
  --output /path/to/tokenizer-data/cl100k_base.tiktoken
```

The expected cl100k SHA-256 is
`223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`.
The tool independently verifies it on every count. Store vocabulary artifacts
outside the installed skill so normal installation stays small. Provision only
the encodings actually required; do not load an unverified third-party file.

To exercise real-vocabulary tests from the repository:

```bash
MONTH_END_TEST_CL100K_VOCAB=/path/to/tokenizer-data/cl100k_base.tiktoken \
  .venv/bin/python -m unittest discover -s tests -p test_token_count.py -v
```

Tests without this optional setup still verify parser integrity, mapping
refusals, hash failures, no-loader construction, missing dependencies and bounded
input. Real-vocabulary tests explicitly skip rather than inventing a count.

## Scope and sources

The result is exact for the supplied text under the named encoding and package
version. It excludes message boundaries, roles, tool schemas, hidden prompts,
images/audio, cache treatment, and model-specific request processing. It is not
an exact chat/request count, actual usage, billed cost, or subscription quota.
Use recorded provider usage for those measurements; never use bytes divided by
four as an exact token count.

Primary sources checked 28 October 2026:

- [OpenAI token-counting limitations](https://developers.openai.com/api/docs/guides/token-counting).
- [Official encoding constructors and vocabulary hashes](https://github.com/openai/tiktoken/blob/main/tiktoken_ext/openai_public.py).
- [Exact model mapping table and permissive-prefix warning](https://github.com/openai/tiktoken/blob/main/tiktoken/model.py).
- [Direct Encoding construction and ordinary text encoding](https://github.com/openai/tiktoken/blob/main/tiktoken/core.py).

Recheck the installed package and official hashes before adding an encoding or
updating the pinned dependency. A future mapping or hash change requires a
reviewed update; there is no network fallback.
