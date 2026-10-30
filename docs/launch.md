# Month End

Month End helps coding agents avoid unnecessary context while preserving exact
source and failure evidence. It combines a portable skill with optional local
helpers for retrieval, command receipts, task continuity and reproducible
evaluation. Its product promise is a workflow goal, not a measured savings claim.

## Release announcement

Month End is available from the [public repository](https://github.com/udaysharmadev/Month-End)
and [versioned releases](https://github.com/udaysharmadev/Month-End/releases).
It locates relevant files before reading them, refuses unsafe source truncation,
and preserves command exit status while bounding noisy output. Raw evidence can
be saved explicitly. A paired evaluation workflow tracks failed-run spending and
compares cost per accepted solve across matching conditions.

The helpers work offline without API keys or mandatory runtime packages. The
release includes installation instructions, tests, versioned evidence references
and reproducible archives with SHA256 manifests. Native Codex discovery, a small
subscription coding pilot and a six-target Gemini API pilot are recorded in the
[evidence status](product-status.md). The Gemini experiment found substantial
overhead when full instructions were forced into tiny one-shot tasks. No model
savings or subscription-quota extension is promised.

## Fewer terminal bytes can still mean a more expensive task

A command can print thousands of repetitive passing lines. Removing many of
those lines is easy to demonstrate. It does not establish that an agent
completed the task correctly, used fewer provider tokens, or cost less.

A missing diagnostic can cause another read, another test run, or an incorrect
patch. Repeated context may also be cached, so changing its shape can affect the
price of later requests. A preprint reports lower delivered tool-output tokens
coinciding with higher billed cost; that motivates whole-task measurement.
[Token Reduction Is Not Cost Reduction](https://arxiv.org/abs/2607.12161v5).

Month End reports local terminal bytes as local terminal bytes. It retains exact
source lines, exposes incomplete excerpts, includes failed-task spending and
keeps model and cache conditions distinct during evaluation.

The [Gemini results](gemini-evaluation.md) make that distinction concrete: the
complete model schedule used 3,864 received-response tokens in baseline and
31,215 with the full skill forcibly loaded, including correction attempts.
That is a negative one-shot instruction-overhead result, with uncontrolled
cache conditions and no invoice. The entrypoint was subsequently shortened and
keeps detailed procedures on disk. Smaller instructions still require live
quality and usage evaluation; byte reduction alone does not prove efficacy.

## Recorded terminal demonstration

Open the [offline player](terminal-demo.html), replay the [asciicast v2 capture](terminal-demo.cast),
or inspect its [command receipts](terminal-demo.receipt.json). The recording
contains actual output from six local commands, with reading pauses: helper
version, path-only discovery, exact source excerpt, the verbose passing fixture,
its bounded receipt and a failing child whose exit remains 9.

This is a local command-output capture, not an agent UI recording or a model
benchmark. The original streams are captured after each command completes;
stdout precedes stderr in playback. Output hashes, byte counts and exits are
retained, and the player works without an external service or library.

Reproduce it from the repository root with a new output stem:

```bash
python3 docs/record_terminal.py --output /tmp/month-end-terminal-demo
```

`--pause 0` removes the reading pauses for automated checks. Existing recordings
are never overwritten. The standalone local helpers need no API credentials.
