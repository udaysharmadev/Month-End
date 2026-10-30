# Market readiness — 30 October 2026

Release scope: Month End 1.0.0 as the existing MIT-licensed, offline Agent Skill
and optional Python CLI toolkit. Market readiness means installable artifacts,
working advertised behavior, reproducible verification and accurate public
claims. It does not mean a guarantee of defect-free software or demonstrated
model savings.

## Acceptance contract

- Preserve the existing implementation and uncommitted workflow/recording work.
- Review installation, retrieval, command execution, evidence recovery, usage
  imports, evaluation, packaging and launch documentation end to end.
- Fix reproduced correctness or security defects with focused regression checks.
- Pass the complete local suite, provisioned offline tokenizer checks, package
  validation, lint, configured typing and medium/high security checks.
- Build source and standalone-skill archives twice; compare bytes, verify hashes
  and exercise installation and removal from extracted release content.
- Keep historical pilots, local mechanism tests and unexecuted protocols distinct.
- During preparation, make no paid API calls, public pushes, tags or release
  publication. The user subsequently approved publishing the free open-source
  v1.0.0 release; the publication plan follows below.

## Implementation plan

| Step | Files | Change | Risk and recovery |
| --- | --- | --- | --- |
| 1 | Runtime helpers and related tests | Audit advertised behavior; preserve SIGKILL termination in the wrapper | Focused subprocess tests; retain normal exits and catchable signal behavior |
| 2 | scripts/candidate_sandbox.py, live_gemini.py, live_workflow.py, live_codex.py, analyze_workflow.py, build_release.py and related tests | Share bounded candidate isolation, reject unsafe import aliases, preflight before model use, reconcile analysis identity, reject archive path aliases | Synthetic reproductions before changes; unsupported isolation fails closed |
| 3 | README, changelog, release notes, product status, this record | Clarify supported release scope, installation and remaining evidence gates | Cross-check claims with observed results and existing receipts |
| 4 | dist/market-1.0.0 | Build fresh immutable archives and checksums after verification | Existing artifacts stay intact; use separate temporary build for reproducibility |

Decision: use the existing standard-library tools and test suite. No new runtime
dependencies, hosted service, account system or payment system is required for
the existing skill/CLI product.

## Initial observations

- Existing source changes target 1.0.0; old local archives target 1.0.0-rc.1.
- Baseline lint and configured typing passed; Bandit medium/high checks passed.
- The restricted session cannot start a nested macOS sandbox. The same fifteen
  offline workflow tests passed outside that session sandbox, including denied
  reads outside the candidate workspace. Isolation was not disabled.
- Review reproduced a wrapper crash when its child terminates with SIGKILL:
  Python cannot register a signal handler for SIGKILL. The parent must propagate
  that signal without attempting to reset its handler.
- Installed integration commands reject their own managed path; ordinary usage
  imports in the benchmark also create unmanaged bytecode caches. Receipt checks
  must still preserve user additions after these lifecycle fixes.
- The older developer evaluator accepts private/import aliases and captures
  output without a retention bound. Source inspection is only a heuristic; all
  generated-code execution must use the shared OS sandbox and bounded capture.
- The workflow producer writes a full Python build string, while the analysis
  consumer accepts only a numeric version. Verify that produced summaries can
  actually pass through the public analysis command.

Decision: consolidate the existing sandbox code into one developer-only module;
keep runtime helpers dependency-free. No generated model code or paid experiment
is needed to reproduce or fix these defects.

## End-to-end audit result

| Surface | Result and coverage |
| --- | --- |
| Discovery and source retrieval | Exact UTF-8 excerpts, Python symbols, bounded search, ambiguous symbols, binary/huge-line refusal and source nonexecution are covered by regressions |
| Command receipts and evidence | Normal exits, SIGTERM/SIGKILL, diagnostic priority, explicit raw logs, SHA256 recovery and forged/mutated evidence are checked |
| Managed installation | Fresh, idempotent and installed-copy management; all three host layouts; user-file preservation and symlink scope checks |
| Usage and comparisons | Offline provider semantics, missing billing, retries/replays, failed spending, complete pairs and task-cluster uncertainty |
| Local task runner | 144/144 deterministic mechanism trials passed; this is not live model or savings evidence |
| Workflow fixtures | All sixty reference repairs pass their fixed cases and all sixty buggy starting sources are rejected; live model study remains unexecuted |
| Generated-code evaluation | Shared bounded capture, minimal environment, timeouts, OS isolation, preflight before model use, rejected private/wildcard imports and producer-to-analysis compatibility |
| Optional tokenizer | All provisioned offline vocabulary checks passed; vocabulary stays local and hash-verified |
| Native discovery | Fresh Codex project installation discovered and enabled, zero model calls; [sanitized receipt](verification/market-codex-discovery.json) |
| Distribution | Source and standalone skill archives, licenses, per-file manifests, checksums, clean extracted installs and reproducibility checks |
| Launch material | Installation/removal guidance, replayable actual command recording, issue forms, security policy, release notes and explicit evidence limits |

Observed local gate on macOS / Python 3.14.6:

```text
Ran 193 tests
OK
All checks passed!
Success: no issues found in 15 source files
PASS: skill schema, portable resource links, Python 3.9 syntax, and matching package versions
```

Bandit medium/high checks and `git diff --check` exited zero. The full test run
used the existing local cl100k vocabulary; no tests were skipped. The release
checker also passed package/resources/security heuristics. These are bounded
engineering checks, not an external security audit. Review reproduced and fixed
the macOS `/var` versus `/private/var` workspace policy mismatch before packaging.
An initial source-ZIP test also caught a producer/analyzer mismatch when Git
metadata is absent; the producer now omits an unavailable commit identity while
retaining content hashes, with a Git-less regression check.

Reproduce maintainer checks with the documented virtual environment:

```bash
python -m ruff check skills/month-end/scripts scripts tests
python -m mypy
python -m bandit -q -r skills/month-end/scripts scripts -ll
python scripts/release_check.py --tests
python scripts/build_release.py --output dist/market-1.0.0
```

Exact tokenizer tests additionally require `MONTH_END_TEST_CL100K_VOCAB` pointing
to the provisioned official vocabulary; absent optional tokenizer prerequisites
are explicitly skipped. macOS isolation tests require permission to start
`sandbox-exec`; a nested restricted session may reject that operation. Linux
continues to run portable checks, while live candidate evaluation refuses to
run without the required OS isolation.

## Release decision and external gates

The local toolkit is prepared for release as a context-management utility with
the measured limitations above. Do not market it as proven to reduce provider
tokens, billed dollars or subscription quota.

At the preparation checkpoint on 30 October 2026, read-only GitHub checks
confirmed the public destination is
[udaysharmadev/Month-End](https://github.com/udaysharmadev/Month-End). The latest
published version at that checkpoint was
[v1.0.0-rc.1](https://github.com/udaysharmadev/Month-End/releases/tag/v1.0.0-rc.1).
The latest successful hosted test run at that checkpoint covered
[dc1a0e8](https://github.com/udaysharmadev/Month-End/actions/runs/40740843052),
which predates these local changes.

Before calling 1.0.0 publicly released, publish the reviewed source, observe all
hosted jobs on that exact revision, tag the version, and verify downloaded
release assets and the actual published installation. The release workflow
already distinguishes stable from prerelease tags. Preparation performed no
push, commit, tag or external publication and preserved the pre-existing work.

## Authorized publication plan

The user approved the free, open-source skill and CLI scope and explicitly
requested publication of v1.0.0 after reviewing the preparation results.

| Step | Action | Verification and recovery |
| --- | --- | --- |
| 1 | Commit the reviewed public release roots, excluding private traces, attachments and local outputs | Re-run package/security checks and inspect the staged file inventory; preserve the existing prerelease |
| 2 | Push the candidate to the existing public main branch | Confirm the remote revision; observe every hosted CI job on that exact commit; fix failures before tagging |
| 3 | Tag v1.0.0 and let the release workflow publish source, skill and checksum assets | Confirm stable release metadata and successful release job; do not overwrite an existing tag or release |
| 4 | Download published assets and exercise the published installation | Match local deterministic hashes, verify internal manifests and checksums, and install/invoke/remove a clean copy |

Decision: the user's publication approval authorizes the public commit, push,
stable tag and release assets. No paid model experiments or expanded savings
claims are included. Current publication evidence is available from the
[release page](https://github.com/udaysharmadev/Month-End/releases/tag/v1.0.0)
and its linked revision and workflow runs; this preparation record does not
predict their outcome.

Native Claude/Antigravity coding behavior, a completed sixty-task live study,
independent reproduction and actual billed savings remain unverified. They are
required before expanding compatibility or efficacy claims beyond the evidence,
not findings that can be replaced with synthetic fixture success.

VERDICT: PASS for local functionality and recorded engineering gates. Public
1.0.0 publication and efficacy claims remain separate external gates.
