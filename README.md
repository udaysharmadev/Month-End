# Month End

**Your coding agent should finish the task before it finishes your tokens.**

Month End is an Agent Skill for Claude Code, Codex and Antigravity. Locate code
before reading it, keep exact edit anchors, shorten noisy output, and recover
complete diagnostics without rerunning commands.

> **1.0.0:** portable local tools, provider usage imports, paired evaluation and
> reproducible archives. Includes live model findings and a replayable terminal
> demo. Model savings remain unproven; terminal bytes are not billed costs.

Use it for large codebases, noisy test/build output and long task handoffs.
Small one-step tasks can cost more context when a skill is loaded unnecessarily.
The MIT-licensed helpers run locally; no Month End account or service is needed.

## Install locally

Clone the repository, then install a project-scoped copy:

```bash
git clone https://github.com/udaysharmadev/Month-End.git
python3 Month-End/skills/month-end/scripts/integrations.py install \
  --host codex --project /path/to/your/project
```

Use `--host claude` or `--host antigravity` for the other supported layouts.
The installer refuses to overwrite unknown files and supports a reversible
`uninstall` command. [Installation and optional hooks](skills/month-end/references/integrations.md).

For a manual copy, place `skills/month-end/` at `.agents/skills/month-end/`
(Codex/Antigravity) or `.claude/skills/month-end/` (Claude Code). Then ask:
**Use Month End for this coding task and preserve correctness.**

Verify or remove a managed Codex installation using the installed copy:

```bash
python3 /path/to/your/project/.agents/skills/month-end/scripts/integrations.py \
  status --host codex --project /path/to/your/project
python3 /path/to/your/project/.agents/skills/month-end/scripts/integrations.py \
  uninstall --host codex --project /path/to/your/project
```

Removal refuses modified files and user additions. Keep the clone if you used a
manual copy, which has no managed-install receipt. See
[release readiness](docs/market-readiness.md) for current verification and gates.

An actual local command demonstration produces 7,011 raw bytes and a 151-byte
displayed command body, with failure exit 9 preserved.
[Reproduce the demo](docs/demo-record.json). These are terminal bytes, not model tokens.
[Replay the actual command capture](docs/terminal-demo.html) offline, or use its
[asciicast recording](docs/terminal-demo.cast).

## Tools included

| Tool | Purpose |
| --- | --- |
| `monthend.py locate/excerpt/symbol` | Bounded file discovery, exact lines and Python AST definitions |
| `monthend.py run` | Diagnostic profiles, adaptive small-output handling and preserved command exits |
| `monthend.py log-read` | SHA256-verified exact byte recovery from opt-in raw logs |
| `monthend.py audit` | Read-only instruction/configuration size inventory |
| `usage.py` | Offline OpenAI/Anthropic/Gemini export normalization with provenance |
| `benchmark.py` / `compare_runs.py` | Randomized paired repeats, independent grading and task-cluster uncertainty |
| `integrations.py` | Reversible project installation and optional checkpoint-hook configuration |
| `token_count.py` | Optional exact offline text counting with a verified vocabulary |

[CLI guide](skills/month-end/references/cli.md) ·
[Usage imports](skills/month-end/references/usage.md) ·
[Benchmark runner](skills/month-end/references/benchmark.md) ·
[Token counting](skills/month-end/references/token-counting.md).

Optional registry installation uses the real repository:

```bash
npx skills add udaysharmadev/Month-End --skill month-end
```

## How it helps

| Problem | Month End behavior | What it *cannot* promise |
| --- | --- | --- |
| Agent dumps 800 irrelevant lines into context | Locate first, show bounded targeted excerpts | That a shorter search always resolves the task faster |
| CI/test command emits hundreds of passing lines | Preserve exit status, failure keywords, summaries and final lines | That removing 80% of output reduces 80% of provider billing |
| Agent repeats work after context compaction | Keep brief task state: decisions, touched files, tests, next step | That a skill can control a provider's native context manager |
| Tool/schema bloat and cache misses | Explain stable-prefix practices, flag oversized instructions | That a Markdown skill can change hidden host/tool caching |
| Viral savings claims based on command output | Benchmark against actual total task success and billed costs | Any particular percentage without live evidence |

## Use it in a real session

Tell the agent: **Use Month End to keep this task token-efficient but do not compromise correctness.**

Examples below use paths from this repository checkout. After a project install,
replace `skills/month-end/` with `.agents/skills/month-end/` or
`.claude/skills/month-end/` as appropriate. Documented host paths are summarized
in [platform guidance](skills/month-end/references/platforms.md).

For targeted file discovery:

```bash
python3 skills/month-end/scripts/monthend.py locate 'processPayment' --root .
python3 skills/month-end/scripts/monthend.py excerpt src/payments.ts --pattern 'processPayment' --context 6
```

For a noisy test command:

```bash
python3 skills/month-end/scripts/monthend.py run --kind tests -- python3 -m unittest discover -s tests -q
```

If a command fails, Month End preserves its exit status and prints diagnostic excerpts. For recoverable complete output, choose new local paths:

```bash
python3 skills/month-end/scripts/monthend.py run --kind tests \
  --log ./debug-test.log --log-index ./debug-test.index.json -- npm test
```

**Caution:** raw logs can include credentials and customer data. They are written only when you explicitly request `--log`.

`run` bounds its retained output even for a single huge line. Oversized, binary or
invalid UTF-8 lines are omitted whole with an explicit notice; `--log` retains the
original bytes. Diagnostics take priority over passing summaries. The receipt's
`displayed_bytes` counts the emitted command body, including an added final
newline, and excludes the receipt and notices. `--max-bytes` caps that body.
If a log destination cannot be opened, the wrapped command is not started.
Normal exit codes are preserved; on POSIX, signal termination is also preserved.
`--log` applies only to that invocation; use `log-read` to recover indexed evidence
without rerunning it. Existing log/index files are never overwritten.

`excerpt` accepts valid UTF-8 text and refuses partial source when its line or
byte budget is exceeded. Line numbers and display prefixes are added; CRLF and
CR line endings are displayed as LF. Other source characters remain unchanged.
`locate` puts paths on stdout and search receipts on stderr. Without ripgrep,
its bounded fallback skips hidden paths, symlinks, NUL-containing files and files
above `--max-scan-bytes`; it does not interpret `.gitignore` rules.

For a read-only skill/config audit:

```bash
python3 skills/month-end/scripts/monthend.py audit --root .
```

## What makes it different?

**1. Success first.** If a token-saver causes another tool call, re-read, broken edit or failed test, its local reduction might be a net loss. See research by Weinberger & Hozez (2026, preprint): [Token Reduction Is Not Cost Reduction](https://arxiv.org/abs/2607.12161).

**2. Conservative, reversible outputs.** A small command wrapper, no arbitrary LLM rewriting of code/stack traces. Exact code excerpts reject unsafe truncation rather than pretending truncated source is complete.

**3. Cache-aware boundaries.** Prompt caching is real but differs by provider and model. Changing standing instructions/effort mid-task can eliminate cached-prefix savings. Month End offers guidance rather than an undocumented cache hack.

**4. Progressive disclosure.** One short `SKILL.md`; detailed references and scripts stay on disk until needed. That avoids constantly spending token budget to explain how to save it.

**5. Local-first.** No API keys, data collection, automatic hooks, global config edits or background services. Python 3.9+ standard library; `rg` optional.

## Measurements: be precise

| Metric | Meaning | Main claim? |
| --- | --- | --- |
| `raw_bytes` vs `displayed_bytes` | Local output filtering on one command | No |
| Provider `input_tokens` / `output_tokens` | Task-level consumption in that platform | Secondary |
| Provider `cached_tokens` / `cache_write_tokens` | Required for fair billing where exposed | Secondary |
| **Actual dollars / correct task** | The dollar cost of all attempts divided by accepted solves | **Primary** |
| Success / correctness regression | Whether the optimization harms outcomes | **Hard gate** |

A demonstration dataset is in `examples/benchmark_runs.csv` (synthetic; do not cite as real results):

```bash
python3 skills/month-end/scripts/compare_runs.py examples/benchmark_runs.csv
```

For live evaluation, freeze task/model/repo/test conditions, compare paired arms, count failures in cost, retain raw anonymized traces and publish confidence intervals. See [evaluation protocol](skills/month-end/references/evaluation.md).

The reader rejects incomplete pairs and malformed rows rather than silently
excluding them. Missing billed cost stays `UNAVAILABLE`; failures contribute to
total spending. A task that passes baseline and fails with Month End produces an
explicit quality-gate warning, even if raw cost decreases.

For live ledgers, include `repo_commit,model,cache_state` and use
`compare_runs.py --require-metadata runs.csv`. Each pair must share the full Git
commit hash, model identifier, and `cold`/`warm` cache condition. Different model
and cache combinations are reported separately. Legacy files are labeled when
these conditions cannot be checked.

The report now bootstraps the **difference in billed USD per success**, counting
failed-run spending. It withholds the interval if billing is missing, there are
fewer than three independent pairs, or zero-success resamples make it undefined.
Labels and submitted billing still need independent verification.

When a long task needs a handoff or context boundary, use the
[checkpoint template](skills/month-end/references/checkpoint.md) to preserve its
goal, acceptance criteria, evidence, changed files, checks and next action.

## Architecture

```text
month-end/
├── README.md
├── LICENSE
├── skills/
│   └── month-end/
│       ├── SKILL.md                 # low-overhead, agent-facing rules
│       ├── scripts/
│       │   ├── monthend.py          # local locate/excerpt/run/audit
│       │   └── compare_runs.py      # success-aware paired metrics
│       └── references/
│           ├── platforms.md         # Claude / Codex / Antigravity
│           ├── evidence.md          # links, strength, limitations
│           ├── evaluation.md        # full-task evaluation
│           ├── checkpoint.md        # optional task continuity note
│           ├── safety.md            # preservation and privacy
│           └── repository-design.md
├── tests/
├── examples/
└── docs/
```

## Comparison with existing tools

- **RTK** ([rtk-ai/rtk](https://github.com/rtk-ai/rtk)): dedicated command output proxy, richer command adapters than Month End's tiny optional wrapper. Month End focuses on conservative workflow behavior and independently measured full-task economics.
- **Token Saver** ([otnc skill](https://www.skills.sh/otnc/skills_ai-agent-saving-tech/token-saver)): concise agent-neutral instructions plus platform-specific packs. Month End's differentiation is preservation of exact edit anchors and a built-in success-cost audit.
- **Context engineering collection** ([muratcankoylan](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering)): broad architecture and context management curriculum. Month End is a narrow runtime workflow.
- **LLMLingua / LLMLingua-2**: learned text compression research; Month End does **not** compress exact code or logs with a model because loss risk and cache economics require special evidence.

## Tested here

- Local regression tests for exact excerpts, hidden configuration discovery,
  bounded capture of a 5 MB line, raw-log recovery, diagnostics in a 20,000-line
  log, normal/signal exit preservation, no-shell argument handling, strict paired
  metrics, cost-per-success uncertainty and clean project installation layouts.
- Copied helpers execute under isolated Python with no repository or third-party
  runtime packages. These checks do not exercise discovery in running agent hosts.
- Codex native project discovery was verified. A small subscription-only coding
  pilot is reported separately from the local fixtures; task billing remains
  unavailable. No sixty-task independent live evaluation or billed savings is claimed.

[Recorded checks and scope](docs/product-status.md) ·
[Live subscription pilot](docs/verification/live-codex-summary.json) ·
[Local suite summary](docs/verification/local-suite-summary.json) ·
[Gemini multi-model results](docs/gemini-evaluation.md) ·
[Unexecuted tool-workflow evaluation protocol](docs/workflow-evaluation.md).

The Gemini API pilot found increased token use when the entire skill was forced
into tiny one-shot tasks. Use its activation boundaries; this release does not
claim demonstrated model-token or billed savings.

Run local verification with Python 3.9+:

```bash
python3 -m unittest discover -s tests -v
```

For all maintainer checks, use an isolated environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/validate_package.py
.venv/bin/python -m unittest discover -s tests -v
```

On Windows, use `.venv\Scripts\python.exe` for the virtual-environment commands.
PyYAML is a developer-only dependency for manifest checks; the installed helpers
remain standard-library-only. YAML-dependent tests explicitly skip if it is
absent. CI is configured for Python 3.9, 3.12 and 3.14 on Linux, plus Python 3.12
on macOS, plus a real-vocabulary tokenizer job. All five jobs passed in
[hosted CI](https://github.com/udaysharmadev/Month-End/actions/runs/40735467870).
Installation from the public Git clone and `skills add --list` discovery were
also exercised successfully.

## Research and limitations

Sources are grouped by evidence quality in [evidence.md](skills/month-end/references/evidence.md). Official docs establish what the platforms do; academic and preprint work supplies hypotheses and counterexamples; Reddit/X/Quora comments are not validation. Quora access was not available in this research run; unofficial leaked prompt dumps were deliberately excluded as unreliable and version-dependent.

The supplied PRD remains local and is excluded from public source/releases. The
evidence register records reviewed source identities, dates and explicit
limitations; primary references are rechecked at release time.

## Contributing

Please submit reproducible bug reports and **paired benchmarks including negative results**. Never post tokens, raw production secrets, private user data or credentials. Changes to optimization behavior should have tests for failure evidence, exit codes and patch anchors. See [CONTRIBUTING.md](CONTRIBUTING.md).

MIT license. This repository is independent of Anthropic, OpenAI, Google and Vercel.
