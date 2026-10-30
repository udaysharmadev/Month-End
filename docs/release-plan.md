# Release implementation plan

Historical release-candidate preparation record. The current stable completion
pass and live API evidence are tracked in [product-status.md](product-status.md)
and [workflow-evaluation.md](workflow-evaluation.md); statements below describe
what ran during the original preparation workstream.

Scope: build reviewable local release artifacts, verify the research register,
and prepare truthful launch materials. External publication, real billing
experiments and a screen recording remain separate evidence-producing actions.

| Step | Files | Change | Risk |
| --- | --- | --- | --- |
| 1 | scripts/build_release.py, tests/test_release.py | Reproducible source and skill ZIPs with hashes and private-file exclusions | Moderate; archive content selection |
| 2 | scripts/release_check.py, SECURITY.md | Repeatable static/package checks and disclosure process | Low; local read-only checks |
| 3 | docs/source-verification.md, references/evidence.md | Verify sources and qualify unavailable or unreplicated claims | Low; read-only public research |
| 4 | docs/demo.py, docs/demo-record.json, docs/launch.md, docs/release-checklist.md | Record a deterministic terminal-output demonstration and prepare release assets | Low; no live savings claim |
| 5 | .github/ISSUE_TEMPLATE | Usable regression, benchmark and compatibility reports | Low |

Decision: use the existing package validator and Python standard-library archive,
hashing and subprocess tools. Reject symlinks and suspicious packaged content;
never copy a workspace wholesale into a release archive. If validation fails,
fix the source before rebuilding. Retain the original PRD unchanged.

## Observed results

- Release tooling and demo checks: `Ran 11 tests` / `OK`.
- Current workspace smoke build produced and verified the source and standalone
  skill archives for `1.0.0-rc.1` in an isolated temporary output directory.
  Final distributable archives must be rebuilt after integration is complete.
- Current release/package/security heuristics pass for the selected source tree.
  These are bounded local checks, not an external security audit.
- The recorded local terminal demonstration uses the actual release-candidate
  helper: 7,011 raw command bytes, 151 displayed command-body bytes, 270 bytes
  for the complete wrapper stdout, and preserved failure exit 9. Provider tokens
  and billed dollars are explicitly unavailable.
- All original S01–S31 source identities were reviewed with their evidence tiers
  and limitations. The unavailable S01 article is replaced by current official
  guidance; no experimental results were independently reproduced.
- The original DOCX matches the supplied ZIP byte-for-byte; SHA256 is
  `b5743e6b96e80dab2cd2872dcc48ab035d576d1f642416ace6f86c438e081b2d`.
- Public destination selection is handled by the primary task. No publication,
  paid provider call, hosted-CI claim or fabricated agent recording occurred in
  this release-preparation work.

VERDICT: PASS
