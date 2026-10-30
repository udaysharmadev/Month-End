# Tool-workflow evaluation protocol

Status on 30 October 2026: the harness, sixty synthetic tasks and offline
regression checks are implemented. This protocol has not been executed as a
live model study; no completed registration or workflow-result dataset is
included in this release. The earlier single-response pilot is a separate
completed experiment.

The proposed study compares skill activation in a multi-turn tool harness.
Before any live trial, freeze task fixtures, reference implementations,
acceptance oracles and all protocol fingerprints. Retain failures and unknown
usage in the eventual results.

## Planned protocol

- Sixty distinct synthetic Python repair tasks across parsing, collections,
  finance, dates, security validation and text algorithms; 321 prewritten cases.
- Three repeats per task, paired baseline and Month End arms, seeded task order
  and independently seeded arm order. Primary target: Gemini 3.5 Flash-Lite,
  selected because it completed the earlier pilot's full schedule.
- Both arms have exactly the same bounded list, literal search, exact read,
  AST symbol, anchor replacement and test tools. Both can choose native quiet
  output or Month End receipts. Only the skill activation instruction differs.
  The skill files are present in both workspaces so tool availability is equal.
- Each synthetic workspace contains a target module, eight unrelated modules,
  240 historical comment lines per module and 240 actual unittest sanity cases.
  These are deliberately noisy stress fixtures, not production repositories.
- The test tool shows two predefined smoke cases; final grading includes the
  remaining cases, never exposed to the model's tool filesystem. Concrete JSON
  return types, error contracts, input mutation and unrelated-source integrity
  are checked. Reference solutions are excluded from that filesystem.
- Maximum twelve model responses per trial. Each HTTP request permits at most
  three attempts with delayed bounded retry. Two consecutive service-failed
  trials stop that model's queued work. No credential or billing changes occur.
- Credentials stay in the API parent process and the fixed official HTTPS
  authentication header. Generated code runs in separate, timed subprocesses
  with minimal environments, bounded retained output and macOS read/write/network
  restrictions. This developer harness requires macOS sandbox support for live
  execution; the installed skill remains portable and offline.

At execution, the harness writes suite, grader, harness, sandbox, skill and
helper SHA256 values and the Git revision to protocol.json before model calls.
Archive that registration before the first trial. Requested and returned model
versions, responses, tool actions, failures and usage should remain private;
publish only reviewed aggregate data and numeric per-trial rows.

The harness checks that the macOS sandbox can execute and deny outside reads,
outside writes and local network binding before requesting a credential. Both
live evaluators share bounded subprocess capture and fail closed when candidate
isolation is unavailable. Their AST source checks are additional heuristics,
not a Python security sandbox. Ordinary plan/analysis commands remain portable.

## Analysis and interpretation

Report acceptance across all attempted trials, service availability separately,
paired success regressions and total provider usage across all attempts. Analyze
repeats at the original-task cluster level rather than treating them as distinct
tasks. Missing cache or invoice fields remain unknown; HTTP failures are not
assumed free. Any confidence interval describes this frozen synthetic suite.

The harness resends conversation history and leaves provider caching uncontrolled.
It cannot create independent cold/warm strata or establish invoice cost. This is
a custom Gemini harness, not native Claude Code, Codex or Antigravity execution.
Public synthetic cases cannot establish broad generalization or exclude fixture
contamination. No external independent reproduction is claimed.

Ordinary checks and script imports make no API calls:

```bash
python3 scripts/live_workflow.py
python3 scripts/live_workflow.py --execute --output verification/private/workflow-run \
  --models gemini-3.5-flash-lite --repeats 3
```

Execution makes paid API requests and prompts for a key; it is never part of
ordinary installation, tests or release checks. After an explicitly authorized
run, export numeric evidence with:

```bash
python3 scripts/analyze_workflow.py verification/private/workflow-run/summary.json \
  --output /tmp/month-end-workflow-analysis.json
```

The smaller [single-response experiment](gemini-evaluation.md) remains published,
including its increased token usage. A later study does not erase that result.

API JSON action transport follows the provider's
[structured output contract](https://ai.google.dev/gemini-api/docs/structured-output).
Thinking settings follow the
[official generation guidance](https://ai.google.dev/gemini-api/docs/thinking).
