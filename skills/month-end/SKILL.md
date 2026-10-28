---
name: month-end
description: Apply context-saving workflows with targeted code retrieval, bounded command receipts, and paired cost evaluation. Use for coding tasks involving large repositories, noisy commands, long sessions, context limits, or explicit token/cost optimization. Skip trivial exchanges where loading the skill would outweigh its benefit.
license: MIT
compatibility: Python 3.9+ for optional local CLI; ripgrep optional for fast file search. No network or API credentials required.
metadata:
  version: "1.0.0-rc.1"
---
# Month End

Spend fewer tokens **per correctly completed task**, not merely fewer characters per command.

## Operating contract

1. Correctness, security, explicit user instructions and project rules outrank optimization. Never hide a failure, skip necessary validation, truncate code required for an edit, or claim savings without comparable measurements.
2. **Locate before read.** Start with filenames, symbols, precise `rg -l` queries or indexed search; open only relevant files and bounded ranges. If the search is inconclusive, widen it. Never replace exact source text with a paraphrase when editing.
3. **Control noisy output.** Use tool-native quiet/structured flags first. For noisy commands, `scripts/monthend.py run --kind tests --adaptive -- <command>` preserves small output and prioritizes diagnostics on larger output. Profiles cover pytest, Vitest/npm, Cargo, Go and CI. Inspect complete evidence when needed. Specify new `--log PATH --log-index PATH` destinations before execution to retain raw bytes and a verified retrieval index; this applies only to that invocation. See [local tools](references/cli.md).
4. **Keep prefix stable.** Avoid modifying global instructions, skill files, model/effort settings, MCP tool schemas or reusable prompt prefixes mid-task without cause. Never claim the skill can directly control provider caching in a host agent.
5. **Use checkpoints deliberately.** For unrelated new tasks, prefer a clean session with the relevant work summary. For an ongoing complex task, preserve decisions, acceptance criteria, touched paths, unresolved issues and verification; compact at a natural phase boundary only when context pressure justifies the lost-cache/write overhead. Do not automatically compact every N turns. Use the [checkpoint template](references/checkpoint.md) when continuity needs a task note.
6. **Stop unproductive loops.** If the same failing approach repeats twice without new evidence, diagnose the root cause or change approach. Do not omit necessary test retries for flaky behavior.
7. **Verify efficiently.** Use smallest relevant tests during investigation, then all checks required by the task before completion. Avoid redundant repeated full suites, never omit a mandatory final gate.
8. **Keep answers proportional.** Report changed files, behavior, tests and genuine blockers; give detail when requested. Never suppress risk findings to save tokens.

## Choose the next action

| Situation | Default | Escalation |
| --- | --- | --- |
| Unknown file location | `rg -l -F 'symbol'` then bounded `excerpt` | Wider search if no match |
| Target file known | Exact line range / symbol lookup | Whole file only if needed |
| Verbose passing tests | Native `-q` / quiet mode, or `run --kind tests` | Full log for warnings or flakiness |
| Failing tests | Preserve exit code, error details and test IDs | Re-run targeted failing test with full log |
| Many available tools | Use available tool search / defer controls | Don't mutate tool schemas merely to save context |
| Long active task | Preserve a compact working-state note | Native compaction if justified and supported |
| New unrelated task | New session with scoped instructions | Carry only necessary known context |
| Need proof of savings | Paired baseline-vs-skill runs | Revert optimization if cost per success worsens |

## Optional local CLI

From this skill directory (scripts are not loaded into model context unless needed):

```bash
python3 scripts/monthend.py --help
python3 scripts/monthend.py locate 'token_counter' --root .
python3 scripts/monthend.py excerpt src/app.py --pattern 'token_counter' --context 6
python3 scripts/monthend.py run --kind tests -- python3 -m pytest -q
python3 scripts/monthend.py audit --root .
python3 scripts/monthend.py symbol src/app.py Service.process
python3 scripts/compare_runs.py /path/to/benchmark_runs.csv
```

Do not pipe arbitrary commands to `head` as proof of safety. One huge line can defeat line caps; use byte budgets, exact-source refusal when necessary and explicit truncation notices.

## Platform notes

- **Claude Code:** Use `/context` to inspect standing overhead, `/clear` for unrelated tasks, and native `/compact` when sensible. The host manages caching and automatic compaction. See [platform details](references/platforms.md).
- **Codex:** Use project `.agents/skills/month-end/` and the host's native skill/context controls. A skill does not directly configure API caching or hidden tool catalogs.
- **Antigravity:** Use project `.agents/skills/month-end/`. Global locations and context controls differ by surface; consult platform details before changing settings.
- **API/harness owners:** Consider native prompt caching, deferred tools, context editing and verified compaction *outside* the skill. Do not pretend an instruction file turns on these APIs.

## Success criterion

A change counts as a token-efficiency win **only** when paired task runs achieve comparable acceptance-test success and a lower *measured billed cost per success* (or, where billing is inaccessible, clearly labeled provider-reported usage), with no unacceptable safety/quality regressions. Output-line reduction is a diagnostic, not the main result. Use [evaluation protocol](references/evaluation.md) and [evidence & limitations](references/evidence.md).

## Load further details only when relevant

- [Platforms](references/platforms.md): verified knobs and host limitations.
- [Evidence](references/evidence.md): peer-reviewed studies, current preprints, official documentation and community claims.
- [Evaluation](references/evaluation.md): controlled experiments, billing and confidence intervals.
- [Safety](references/safety.md): suppression boundaries, privacy, retrieval anchors and failure modes.
- [Repository design](references/repository-design.md): README, installability, CI, honest claims and publishing.
- [Local tools](references/cli.md): AST retrieval, command profiles, adaptive output and verified log recovery.
- [Usage imports](references/usage.md): normalize explicit provider exports and preserve billing unknowns.
- [Benchmark runner](references/benchmark.md): frozen tasks, randomized repeats, independent grading and clustered analysis.
- [Project integration](references/integrations.md): reversible scoped installation and optional checkpoint hooks.
- [Exact text tokens](references/token-counting.md): optional offline tokenizer with verified explicit vocabularies.
