# Product scope and evidence

Version 1.0.0-rc.1 implements the portable Month End skill and its optional local
tools. Package functionality and empirical model savings are tracked separately.

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| F01 skill format | YAML manifest, portable resources, matching version | Automated validator; native Codex discovery |
| F02 progressive retrieval | Streaming bounded path search, exact excerpts | Path-only and budget regression tests |
| F03 source fidelity | Strict UTF-8, complete lines and Python AST definitions | Invalid text, huge lines, decorators and conditional definitions |
| F04 command receipts | Bounded capture, profiles, summaries and adaptive mode | Passing/noisy/ANSI/custom-profile fixtures |
| F05 failure fidelity | Preserved exits/signals, omission markers and recovery | Middle-error, binary, huge-line and signal tests |
| F06 cache guidance | Provider-specific documented boundaries | Dated source register |
| F07 safe local behavior | No shell interpolation, no telemetry, scoped opt-ins | Runtime review, static checks and adversarial tests |
| F08 config audit | Byte-size inventory with hidden agent folders | Content privacy and excluded-tree fixtures |
| F09 paired evaluation | Strict pairs, metadata, missing costs and failed spending | Exact arithmetic fixtures and clustered-repeat tests |
| F10 distribution | README, project installer, deterministic archives and CI | Clean installed-copy tests, ZIP manifests and hashes |
| P1 symbols | Python AST; other languages delegate to native LSP | Complete source and unsupported-language tests |
| P1 diagnostic adapters | pytest, Vitest, npm, Cargo, Go, CI and custom rules | Profile and omission-marker tests |
| P1 checkpoint | Optional template and bounded selected-note hook | No transcript/environment reads; lifecycle fixtures |
| P1 usage import | OpenAI, Anthropic and Gemini JSON/JSONL exports | Provider-shaped semantic, replay and billing fixtures |
| P1 raw index | Explicit full raw log, SHA256 and byte-range index | Tampering, mutation and binary round-trip tests |
| P1 benchmark runner | Frozen source, randomized pair order, repeats, independent graders | Twelve distinct local tasks; 144 graded trials |
| P2 hooks | Optional documented Codex/Claude checkpoint adapter | Inert by default, configuration preview, nonblocking errors |
| P2 adaptive choice | Auto profiles and complete small-output pass-through | Short, threshold-boundary and noisy-command tests |
| P2 token counts | Optional offline tiktoken plus explicit verified vocabulary | Official cl100k vocabulary tests; no download loaders |
| P2 research maintenance | Versioned mechanism/source registry and 90-day checks | Source identity/revision review and stale-record tests |

The source PRD, retained locally and excluded from public releases, proposes a
sixty-task live study and independent reproduction.
The included twelve-task suite uses deterministic reference patches to verify
the runner; its 144 trials are not 144 independent AI tasks. The small native
subscription pilot is exploratory and does not establish general effectiveness.
No task-level invoice is available from subscription use, so billed-cost savings
remain unavailable. Research papers were reviewed, not independently reproduced.

Project installation and copied helpers are tested for all documented layouts;
live native discovery is verified for Codex. Claude Code is currently configured
with API-key authentication, so its generation tests were excluded under the
user's no-paid-API constraint. Antigravity's native model catalog was reachable;
that alone is not a completed coding evaluation.

No percentage-saving claim, sixty-task live study, external security audit or
fabricated screen recording is included. The release contains a reproducible
terminal-byte demo and an honest recording storyboard instead.

Hosted verification: [all five CI jobs passed](https://github.com/udaysharmadev/Month-End/actions/runs/40735467870),
covering Linux Python 3.9/3.12/3.14, macOS Python 3.12 and optional exact-tokenizer
fixtures. A fresh clone of the actual public repository installed and invoked
the skill successfully; the published skills installer discovered one skill
named `month-end`. Original attachments and private pilot traces are excluded
from the repository and release archives.

Additional live evidence: the [Gemini multi-model pilot](gemini-evaluation.md)
tested six endpoint targets with delayed bounded retries. Three produced coding
responses; other targets were blocked by access, quota or service availability.
The pilot found substantial overhead when full instructions were forced into
tiny one-shot tasks. This does not demonstrate token or billed savings.
