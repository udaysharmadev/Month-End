# Local tools

Run helpers by their installed absolute path or from this skill directory. They
do not require repository files, credentials or a background service.

## Retrieve exact source

```bash
python3 scripts/monthend.py locate processPayment --root /path/to/project
python3 scripts/monthend.py excerpt /path/to/project/app.py --pattern processPayment --context 4
python3 scripts/monthend.py symbol /path/to/project/app.py PaymentService.process
```

Search emits paths only on stdout and receipts on stderr. `--limit` bounds the
match catalog; `--max-scan-bytes` bounds each searched file. Use `--null` for
NUL-delimited filenames, including names containing newlines. The fallback
skips hidden files, NUL-containing files and symlinks; it does not parse gitignore.

`symbol` uses Python's AST without importing or executing repository code. It
returns complete class/function/method definitions, including decorators and
conditional definitions. Qualify ambiguous method names as `Class.method`.
Other languages use the host's LSP, followed by exact excerpts; no heavy parser
is bundled. `--max-file-bytes`, `--max-lines` and `--max-bytes` refuse oversized
results whole. Text must be UTF-8. Presentation adds line numbers and normalizes
line endings to LF while preserving source characters.

## Diagnostic profiles and adaptive output

```bash
python3 scripts/monthend.py run --kind tests --profile pytest --adaptive -- python3 -m pytest -q
python3 scripts/monthend.py run --profile cargo -- cargo test
```

Profiles: `auto`, `generic`, `pytest`, `vitest`, `npm`, `cargo`, `go`, `ci`.
Automatic selection recognizes known executable/argv combinations; an unknown
command uses generic diagnostics. `--profile-config PATH` adds explicit JSON
`important` and `summary` regex lists (20 patterns per list, 512 characters each).
Treat custom regex files as trusted configuration; pathological expressions
can be expensive. Invalid rules fail before the command starts.

`--adaptive` preserves complete small output below `--min-savings-bytes` (default
1024), within `--max-bytes`. Larger output uses bounded diagnostics and summaries.
The byte cap covers the command body; receipts and omission notices are additional.
Failures preserve exit status and still require complete evidence when excerpts
omit relevant context. Filters never silently chop a source/diagnostic line.

## Opt-in lossless log and byte index

```bash
python3 scripts/monthend.py run --kind tests --log /tmp/test-run.log \
  --log-index /tmp/test-run.index.json -- python3 -m unittest discover -s tests -v
python3 scripts/monthend.py log-read /tmp/test-run.index.json \
  --log /tmp/test-run.log --line 12
python3 scripts/monthend.py log-read /tmp/test-run.index.json \
  --log /tmp/test-run.log --start-byte 0 --end-byte 200
```

Both files require new explicit destinations and never overwrite existing
evidence. Logs may contain sensitive command output. No argv/environment secrets
are copied into the index; it records the raw SHA256, total bytes, exit and
retained line byte ranges. The complete raw range remains recoverable, including
omitted binary/oversized lines. The index is not a cryptographic signature.

`log-read` requires an explicit raw-log path, verifies the entire hash, and emits
only bounded bytes captured in that same verification pass. Line mappings are
checked against original newline boundaries. `--raw` explicitly allows binary
or partial-UTF8 recovery; default text output refuses those ranges. Nothing is
rerun to recover evidence. Keep both raw file and its index when archiving a run.

## Configuration inventory

```bash
python3 scripts/monthend.py audit --root /path/to/project
```

Audit reports supported instruction/config filenames and byte sizes, including
hidden agent folders. It never prints contents and excludes vendor/build trees.
Bytes are not provider token counts or subscription usage.
