# Month End release candidate

Month End helps coding agents avoid unnecessary context while preserving exact
source and failure evidence. It combines a small portable skill with optional
local helpers for retrieval, command receipts, task continuity and reproducible
evaluation. Its product promise is a workflow goal, not a measured savings claim.

## Release announcement draft

Month End is available as a local release candidate for compatible coding agents.
It locates relevant files before reading them, refuses unsafe source truncation,
and preserves command exit status while bounding noisy output. Raw evidence can
be saved explicitly. A paired evaluation workflow tracks failed-run spending and
compares cost per accepted solve across matching conditions.

The helpers work offline without API keys or mandatory runtime packages. The
release includes installation instructions, tests, versioned evidence references
and reproducible archives with SHA256 manifests. Live host discovery, actual
provider spending and model-task quality must be assessed using the published
protocol before claiming savings. No fixed percentage or quota-extension claim
is being made.

Publish this draft only after the actual repository destination is selected,
its release checks run, and the remaining gates in
[release-checklist.md](release-checklist.md) are explicitly reported.

## A short article about the measurement decision

### Fewer terminal bytes can still mean a more expensive task

A command can print thousands of repetitive passing lines. Removing many of
those lines is easy to demonstrate. It does not, by itself, establish that an
agent completed the task correctly, used fewer provider tokens, or cost less.

The distinction matters because a missing diagnostic can cause another read,
another test run, or an incorrect patch. Repeated context may also be cached,
so changing its shape can affect the price of later requests. A preprint reports
an example where lower delivered tool-output tokens coincided with higher billed
cost; this is a reason to measure whole tasks, not evidence that every filtering
approach fails. [Token Reduction Is Not Cost Reduction](https://arxiv.org/abs/2607.12161v5).

Month End therefore reports local terminal bytes as local terminal bytes. It
retains exact source lines, exposes incomplete excerpts, includes failed-task
spending, and keeps warm/cold and model conditions separate during evaluation.
Its deterministic local demonstration is recorded by [demo.py](demo.py). That
record is not a live model experiment.

The main result will be actual billed spending divided by independently accepted
solves. Until paired real runs support a claim, publishing a large percentage
would overstate what has been measured. Negative or neutral findings belong in
the release evidence alongside positive ones.

## Sixty second screen recording storyboard

Status: prepared for capture; no screen recording has been fabricated.

| Time | Capture | On-screen label |
| --- | --- | --- |
| 0–8 s | Show the skill folder and its documented project install location | Local release candidate |
| 8–20 s | Locate `validate_payment`, then show its exact excerpt | Targeted source retrieval |
| 20–35 s | Run the deterministic noisy fixture directly, then through `run` | Terminal bytes only; no provider tokens |
| 35–47 s | Run the failing fixture and show preserved exit 9 plus diagnostic | Failure evidence preserved |
| 47–60 s | Show the evaluation command and proof-status statement | Live cost/quality savings not yet established |

Record a real running host invoking the skill if the final video is presented as
an agent demonstration. A plain terminal recording must be labeled accordingly.
