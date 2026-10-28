# Paired task benchmark runner

`scripts/benchmark.py` orchestrates explicit candidate commands and independent
grading. It does not supply an AI agent, access credentials, call provider APIs,
or turn local command-output reduction into a savings claim. It uses Python
3.9+ and the standard library. The optional usage importer is packaged beside it.

## Plan before execution

```bash
python3 scripts/benchmark.py /path/to/suite.json --seed 2026
```

The default validates the manifest and source fingerprints, then prints a seeded
schedule. It starts no commands and writes no results. Pair order is randomized,
and each pair's baseline/Month End order is randomized while its task, repeat,
and cache condition remain matched.

Execution is explicit and requires a new output directory:

```bash
python3 scripts/benchmark.py /path/to/suite.json --execute --output /path/to/new-results --seed 2026
python3 scripts/compare_runs.py --require-metadata /path/to/new-results/runs.csv
```

Existing output is never overwritten. Each candidate, warmup, and grader is an
argv list with `shell=False` and inherited permissions/environment. A temporary
source copy is created independently for every arm, repeat and cache condition.
Retries within one trial share that trial's workspace. This is workspace
isolation, not an operating-system security sandbox; use normal tool permissions.

## Manifest

```json
{
  "version": 1,
  "data_kind": "model-evaluation",
  "model": "exact-model-version",
  "conditions": {"effort": "high", "harness": "pinned-host-version", "toolset": "pinned-tools", "grading": "pinned-acceptance-version"},
  "repeats": 3,
  "max_attempts": 1,
  "cache_states": ["cold"],
  "timeout_seconds": 300,
  "grading_files": {"grade.py": "SHA256_OF_GRADER_FILE"},
  "arms": {
    "baseline": {"argv": ["/path/to/candidate-wrapper", "{workspace}", "{prompt_file}", "{usage_file}"], "provider": "openai", "usage_file": "usage.json"},
    "month-end": {"argv": ["/path/to/skill-candidate-wrapper", "{workspace}", "{prompt_file}", "{usage_file}"], "provider": "openai", "usage_file": "usage.json"}
  },
  "tasks": [
    {
      "id": "frozen-task-001",
      "category": "debugging",
      "prompt": "The exact coding task and acceptance conditions.",
      "source_dir": "sources/frozen-task-001",
      "source_sha256": "SHA256_OF_FROZEN_SOURCE",
      "repo_commit": "OPTIONAL_ACTUAL_FULL_GIT_COMMIT",
      "grader": ["{python}", "{suite}/grade.py", "{workspace}", "{task_id}"]
    }
  ]
}
```

Replace the explanatory fingerprint placeholders with real digests. Omit
`repo_commit` for plain folder snapshots; it is never filled with a fake Git
revision. Sources must be inside the manifest directory and have a matching
content fingerprint. Directory/file symlinks and `.env` credential files are
rejected. Git, virtual-environment, dependency and Python-cache directories are
excluded from snapshots. Use an explicitly prepared task fixture rather than
pointing the runner at a home directory or a production checkout.

Compute the source fingerprint with the packaged function:

```python
from benchmark import fingerprint
print(fingerprint("/path/to/suite/sources/frozen-task-001"))
```

The versioned hash includes typed, length-delimited relative directory/file
names, empty directories, file lengths and original bytes in deterministic
order. Source changes after planning stop the next
command. `grading_files` pins external grader files; changed graders are rejected
before execution, and later trials stop. Grader code embedded directly in an
argv string is already pinned by the retained manifest hash. Graders should
remain outside candidate copies so the task does not expose holdout tests.

Supported placeholders are `{python}`, `{suite}`, `{workspace}`, `{prompt_file}`,
`{usage_file}`, `{task_id}`, `{arm}`, `{repeat}` and `{cache_state}`. Replacement
occurs inside individual arguments and never invokes a shell. Commands are
supplied by the benchmark author; the runner does not guess host CLI flags.

## Cache, attempts and grades

`cache_states` contains unique `cold` and/or `warm` labels. A warm condition
requires an explicit `warmup_argv` in each arm. The runner cannot flush or prove
a provider cache, and temporary workspace paths may affect reusable prefixes.
These are experimental setup labels; retain provider cache usage to validate them.
Optional `conditions` labels record effort, harness, toolset and grading versions.
The evaluator rejects pair/repeat mismatches in these fields when present and
reports different conditions separately. Labels are self-reported; they do not
verify a host's effective configuration.

Warmup spending and every candidate attempt are included when usage exports are
available. The default is one attempt. Increasing `max_attempts` explicitly
authorizes retries when a command or its grade fails. A warmup failure stops
that trial's candidate. A zero candidate exit alone is insufficient: success
requires both the candidate and independent grader to exit zero. Timeouts are
failures, retain their receipts, and terminate the process group on POSIX.
Windows timeout cleanup can terminate the immediate process but is not a
guarantee that arbitrary grandchildren terminate.

For subscription hosts or APIs, write a candidate wrapper that invokes the
chosen host and exports supported provider usage to the configured relative
`usage_file`. It may instead leave usage unconfigured when the host exposes no
reliable export; the report then preserves unknown tokens and dollars. No
private session directories or environment-variable values are scanned.

`provider` selects `openai`, `anthropic`, or `gemini` for [usage import](usage.md).
The usage file is reset between attempts; each phase must emit its own complete
export. Replayed response IDs or identical ID-less records across phases/trials
invalidate measurement rather than counting the same usage twice. Missing or
invalid phase data does not become zero. Native token usage is
not billing: actual dollars remain unavailable unless an explicit billing
attachment is supplied to the importer. Attachments are user-supplied evidence,
not independently reconciled invoices. Retain provider-specific token semantics.

## Results and uncertainty

The output contains the frozen `manifest.json`, `plan.json`, `runs.csv`,
`summary.json`, and one directory per trial with raw phase logs, supported usage
exports and `receipt.json`. Logs and exported content may be sensitive; review
and redact before sharing. Receipts include command/grade exits, timing,
attempts, source identity, usage warnings/provenance, and unknown billing.
`summary.json` attributes failures to category/cache/arm and lists paired quality
regressions and improvements. A nonzero runner exit signals failures or invalid
measurement; it does not erase failed spending from the ledger.

The evaluator pairs `task_id,repeat,cache_state`. A plain source snapshot can use
`source_sha256` with an empty `repo_commit`; both arms must match. Repeated
trials must retain the same original task ID and source/model identity.
Confidence intervals resample original-task clusters, carrying all repeats
together within each model/cache stratum. Three repeats of one task remain one
independent task, not three independent samples. Missing billing, fewer than
three independent tasks, or undefined zero-success resamples withhold the
primary interval. See [evaluation](evaluation.md) for remaining causal limits.

## Included local suite

The repository's `benchmarks/local/suite.json` contains twelve distinct local
coding problems covering structured parsing, decimal arithmetic, interval and
dependency algorithms, unhashable data, path traversal, retry behavior, streaming,
strict diagnostics, time zones, Unicode and nested secret redaction. It includes
independent behavioral graders with more than sixty acceptance assertions.

Both arms deliberately use a known reference patcher. This exercises orchestration,
grading, source isolation, repetitions, cache-setup branches and artifact handling;
it does not test an AI model or establish Month End savings. The suite is twelve
tasks, not sixty independent model tasks. A representative sixty-task live
evaluation still requires genuinely different registered tasks, host access and
independent grading rather than duplicating these fixtures.

From the repository root:

```bash
python3 skills/month-end/scripts/benchmark.py benchmarks/local/suite.json
python3 skills/month-end/scripts/benchmark.py benchmarks/local/suite.json --execute --output benchmarks/results/new-local-run
```
