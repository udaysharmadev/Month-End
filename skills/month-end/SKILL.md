---
name: month-end
description: Reduce unnecessary context in coding tasks with large repositories, noisy commands, or long sessions. Use targeted source retrieval, bounded diagnostic receipts and deliberate checkpoints. Skip trivial tasks where skill overhead exceeds the benefit; use paired measurements for token or cost claims.
license: MIT
metadata:
  version: "1.0.0"
---
# Month End

Use less unnecessary context while completing the user's task correctly. Apply
only the relevant intervention; loading every reference or running an audit on
each task defeats that goal.

- **Find, then read.** Locate paths/symbols with `rg -l -F` or indexed search,
  then read exact relevant ranges. Widen an inconclusive search. Never edit from
  paraphrased or silently truncated source.
- **Bound noise, preserve evidence.** Prefer native quiet/structured flags. For
  genuinely noisy output, use `scripts/monthend.py run --kind tests --adaptive
  -- <command>`. Preserve exit status, warnings and failure details. A marked
  excerpt is incomplete evidence; inspect more when needed. Choose new
  `--log PATH --log-index PATH` destinations *before* execution for opt-in raw
  bytes and verified recovery. Logs may contain secrets. One huge line defeats
  line-only caps; do not treat `head` as a safe source or diagnostic boundary.
- **Preserve useful state.** At a justified phase/context boundary, checkpoint
  decisions, acceptance criteria, touched paths, unresolved issues and checks.
  Do not compact on a turn-count schedule or churn reusable instructions/tools
  just to save context. A skill cannot configure hidden host caching or quotas.
- **Finish correctly.** Required validation and security findings outrank token
  reduction. After repeated failure without new evidence, diagnose or change
  approach. An optimization that causes rework may cost more overall.

## Optional tools and details

Run helpers from this skill directory. Keep scripts/references on disk until
needed; execute `python3 scripts/monthend.py --help` for CLI options.
Helpers use Python 3.9+ standard library; ripgrep is optional. No network or API
credentials are required.

| Need | Resource |
| --- | --- |
| Locate/excerpt, Python AST symbols, diagnostic profiles, adaptive receipts, SHA256 log recovery or read-only config inventory | [Local tools](references/cli.md) |
| Resume a long task | [Checkpoint template](references/checkpoint.md) |
| Install/uninstall or preview optional project hooks | [Project integration](references/integrations.md) |
| Host paths, native context controls and cache boundaries | [Platforms](references/platforms.md) |
| Source preservation, omissions and privacy | [Safety](references/safety.md) |
| Measure whole-task outcomes, failures and uncertainty | [Evaluation](references/evaluation.md), [benchmark runner](references/benchmark.md) |
| Import explicit provider exports or count local text exactly | [Usage imports](references/usage.md), [token counting](references/token-counting.md) |
| Assess claims or publish a package | [Evidence](references/evidence.md), [repository design](references/repository-design.md) |

Claim a win only from comparable paired task results with preserved correctness
and lower measured billed cost per accepted solve, or explicitly labeled
provider usage when billing is unavailable. Terminal-byte reduction alone is
not evidence of model-token, billed-cost or subscription-quota savings.
