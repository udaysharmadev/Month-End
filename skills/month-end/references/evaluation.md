# Evaluation: reject vanity metrics

## Primary outcome
Paired **billed USD per accepted successful task** = total billed USD across runs divided by runs passing independently defined acceptance tests. Include failed runs and retries in the numerator.

## Secondary outcomes
- Acceptance-test success, regressions, patch correctness, human review.
- Input, output, cache-write and cache-read tokens separately (provider definitions vary).
- Total model calls, tool calls, failed retries, compactions, wall-clock time, latency.
- Tool output bytes displayed versus raw (local proxy metric only; not actual model tokens).

## Experiment design
1. Freeze a repository commit, task statement, acceptance tests, model/version/effort, permissions, available tools, budget and run conditions.
2. Choose representative tasks *before* looking at results: tiny edit, moderate bug, repo exploration, noisy tests, long-run multi-file migration and security-sensitive task.
3. Randomize control versus Month End order; isolate worktrees/cache when feasible; repeat runs. Warm/cold caching states should be separate strata, not accidentally confounded.
4. Capture actual provider usage or invoices where possible. In subscription-hosted agents, cost is often not exposed: call it provider usage rather than billed cost.
5. Grade success with tests independent of the agent; evaluate failed/incomplete runs, not only survivors.
6. Compare paired costs and success-adjusted costs, with confidence intervals across tasks; inspect failure cases, and roll back damaging interventions.
7. Publish reproducible task IDs, pinned versions, raw anonymized metrics, analysis scripts and limitations. Avoid cherry-picked terminal-output examples.

CSV columns used by `scripts/compare_runs.py`: `task_id,arm,success,cost_usd,input_tokens,output_tokens,cache_read_tokens,cache_write_tokens,turns,wall_seconds`. `arm` values are `baseline` and `month-end`. Each pair is one row per arm per task_id; `cost_usd` may be empty if billing unavailable. The script will NOT infer dollar cost from raw tokens.

Incomplete pairs, duplicate arms/columns, and rows with the wrong number of
fields are errors. Metrics must be finite and nonnegative; token and turn counts
must be whole numbers. Combine all failed attempts and retries for an arm into
that task's row, including their spending. Missing billing remains unavailable.
Observed baseline-success/Month-End-failure pairs trigger a quality-gate warning;
the reader does not independently grade tasks or verify submitted billing.

## Matched conditions

For live data, add `repo_commit,model,cache_state` and run:

```bash
python3 scripts/compare_runs.py --require-metadata /path/to/runs.csv
```

Include all three fields or none. Each row needs a nonempty model identifier, a
full 40- or 64-character Git commit hash, and `cold` or `warm` cache state. A plain
folder snapshot may instead supply `source_sha256` and leave `repo_commit` empty.
Paired
arms must match all three. Cache state describes the experimental setup, not a
guaranteed cache hit. Unknown cache conditions need a separate investigation.
The reader checks these self-reported labels; it cannot verify actual model
versions, repository contents, invoices, effort settings or harness identity.

Different model/cache combinations produce separate reports, avoiding pooled
warm/cold comparisons. Repository revision can differ between tasks, but must
match within each task pair. Keep effort, tools, permissions and independent
grading frozen as described above. Legacy ledgers remain readable with an
explicit `metadata=UNAVAILABLE` notice and fail `--require-metadata`.

## Uncertainty for the primary outcome

The primary delta is Month End billed USD per success minus baseline billed USD
per success. Positive values mean higher cost per success. It uses every task's
spending, including failed tasks, before dividing by each arm's accepted solves.

The percentile bootstrap resamples original task clusters within each model/cache
stratum, keeping all paired repeats for a task together and recomputing both
spending/success ratios on each sample.
Use `--seed` (default 2026) and `--bootstrap-samples` (default 1500, minimum 100)
for repeatability. With fewer than three independent tasks, missing billing, or an arm
with no accepted solves, no interval is reported. If any resample has zero
successes in an arm, the interval is withheld and the count is displayed rather
than dropping those undefined samples. These intervals remain exploratory.

Repeated trials of the same task are correlated; do not relabel them as new
independent tasks to increase the bootstrap sample size. Keep the original
`task_id` and a positive `repeat` column; the evaluator pairs task/repeat/cache
and resamples original task clusters. Optional provider, effort, harness,
toolset and grading labels must agree within pairs/repeats and produce separate
reports for different conditions. The [runner](benchmark.md) freezes source
and grader identities and records failed attempts and measurement problems.
Secondary mean-cost/token intervals are diagnostics, not the primary gate.

## Pre-registered minimum gates (proposal, not achieved benchmarks)
- No material reduction in correctness, security findings or required checks; zero concealed nonzero exits.
- A statistically supportable lower cost per success, not just fewer terminal lines. Pre-register task coverage, quality criteria and the required effect size before collecting results; report the observed outcome even if zero or negative.
- If success-adjusted cost worsens or anchoring errors occur, disable that optimization in the default mode.

Source: https://developers.openai.com/blog/eval-skills
Source: https://arxiv.org/abs/2607.12161 (preprint)
Source: https://arxiv.org/abs/2610.22732 (preprint)
