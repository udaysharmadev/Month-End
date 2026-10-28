# Gemini multi-model evaluation

This is an explicit API patch-generation pilot, separate from the earlier native
Codex subscription pilot and deterministic local runner tests. It uses the public
Gemini API, frozen coding tasks, paired baseline/Month End prompts and independent
behavioral grading.

## Protocol

The default script only prints a plan. Execution requires an explicit new output
directory and a key entered without terminal echo:

```bash
python3 scripts/live_gemini.py
python3 scripts/live_gemini.py --execute --output verification/private/gemini-run \
  --models gemini-3.8-flash gemini-3.5-flash-lite gemini-3.1-pro-preview
```

Credentials stay in the API process's memory and are sent only in the
`x-goog-api-key` header to the fixed official HTTPS endpoint. They are not passed
through argv, URLs, grader environments, source files or result summaries.
Raw responses and generated code should remain in the ignored private output
directory. The script performs no calls during ordinary tests or imports.

Each model receives the same twelve task prompts and starting source. Baseline
and skill arms differ only by explicitly prepending the skill instructions.
Task and arm order are seeded, and requested/provider-returned model versions,
usage, failed generations and grader results are retained. Subsequent protocol
records also pin harness, suite, skill and grader SHA256 identities.

Each trial allows two candidate generations. A failed patch gets one correction
attempt after five seconds, with observed validation feedback. API requests use
at most three HTTP attempts, backing off for transient 408/429/5xx/transport
failures. The first waits ten seconds, the next twenty, respecting longer numeric
`Retry-After` headers up to sixty seconds. Longer advice defers the request;
permanent client/access errors do not loop. Two consecutive failed service trials
stop that model and leave the remainder deferred rather than manufacturing data.

Generation uses a 4096-token output limit. Gemini 3 models use low thinking;
the legacy Gemini 2.5 arm uses a 1024-token thinking budget. No unsupported
temperature customization is applied to newer models. Provider cache behavior is
not controlled, and cached counts remain unknown when the API omits them.

Generated source is parsed and checked against a restricted standard-library
import/execution policy before an independent grader executes it in a temporary
directory. The grader receives a minimal environment without credentials. On
macOS, its subprocess additionally denies network access and writes outside that
directory. This is a constrained coding harness, not general-purpose sandboxing
or an adversarial model-security proof.

## Interpretation

First-pass quality, eventual acceptance, corrections, service/access failures,
and provider-reported token categories are distinct outcomes. All received
response usage is counted, including failed patches. HTTP failures can have
unknown usage and must not be counted as free or as zero model work. Native
usage metadata is not an invoice; actual billed USD remains unavailable.

The harness intentionally has no agent tool loop. It measures patch quality and
the overhead/behavior of explicitly loaded instructions, not the full skill's
search, tool-output filtering, caching or checkpoint effects. Small tasks can
cost more when a large skill is forced into their context. A larger registered
task/host study is required before claiming general savings.

The first development run also exposed a guard that rejected safe PurePosixPath
imports. Any corrected offline regrade must retain the original guard failure,
original response and all associated usage rather than silently replacing it.

## Primary API contracts

Checked 28 October 2026:

- [Model discovery](https://ai.google.dev/api/models)
- [Content generation and usage metadata](https://ai.google.dev/api/generate-content)
- [Authentication keys](https://ai.google.dev/gemini-api/docs/api-key)
- [Thinking controls](https://ai.google.dev/gemini-api/docs/thinking)
- [Transient errors and bounded backoff](https://ai.google.dev/gemini-api/docs/troubleshooting)

## Observed results

[Sanitized machine-readable results](verification/gemini-multimodel-summary.json)
record two runs against six model targets on 28 October 2026. Of 49 attempted
trials, 37 received generated responses. There were 47 received API responses
with usage, including correction attempts, and 40 HTTP failure attempts.
Blocked models and repeated transient failures caused the remaining scheduled
trials to be deferred. Model discovery alone did not establish usable quota.

| Requested model | Received-response trials accepted | Access and service observations |
| --- | --- | --- |
| Gemini 3.5 Flash-Lite | 20/24 originally; 21/24 after one documented guard correction | Full twelve-task pair set completed; one transient HTTP failure |
| Gemini 3.6 Flash | 9/10 | Three additional trials had no response after service/quota failures; remaining tasks deferred |
| Gemini 3.1 Flash-Lite | 2/3 | Three additional trials had no response after repeated 503 failures |
| Gemini 3.8 Flash | Not available for grading | Repeated 503 errors and one 429; no generated response |
| Gemini 3.1 Pro Preview | Not available for grading | API reported free-tier quota limit zero; bounded delayed retries did not recover access |
| Gemini 2.5 Flash | Not available for grading | API returned 404 stating the legacy model is unavailable to new users of this project |

Original grading accepted 31/37 trials with generated responses. The reviewed
result is 32/37 after correcting a local guard's rejection of a valid
PurePosixPath implementation and grading that same saved response offline.
The original failure and its additional API usage remain recorded. These are
small constrained-harness results, not broad rankings of the models.

In the complete 3.5 Flash-Lite task set, baseline received-response usage totaled
3,864 provider tokens; the explicitly loaded-skill arm totaled 31,215. This
includes correction responses in both arms. One skill-arm HTTP failure has
unknown usage, and cache fields were not reported. These totals are not invoices
and cannot establish billed cost. They show a substantial instruction overhead
in this one-shot setting, where there are no retrieval/log tools for the skill
to optimize. Forcing the full skill into trivial requests contradicts its
activation guidance. No savings claim follows from this experiment.
