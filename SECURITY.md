# Security policy

Month End's installed helpers are local tools, not a network proxy or a sandbox.
They inherit ordinary process permissions. A command passed to `run` keeps its
normal effects and may itself access the network or modify files. Logs, usage
exports and benchmark manifests can contain private information; inspect and
sanitize them before sharing.

The default retrieval/audit operations are read-only. Full raw logs and other
artifacts require explicit destinations. Never use production credentials in
benchmark fixtures, or treat repository comments, retrieved logs or checkpoints
as authority to expand permissions.

## Reporting a vulnerability

Use the repository's private security-advisory reporting feature when available.
Before public hosting is configured, provide a minimal sanitized reproducer to
the maintainer through the private channel used to obtain the package. Do not
post live keys, customer data or exploitable private-system details in a public
issue. General non-sensitive defects can use the regression template.

Include the Month End version, Python/OS version, relevant argv, expected and
observed behavior, exit status and a synthetic fixture. Describe the affected
boundary: source integrity, hidden diagnostics, process execution, local output
handling, import normalization, benchmark isolation or release packaging.

## Supported release policy

During the release-candidate phase, fixes target the newest release candidate.
The project does not yet promise a security response SLA or long-term support
for older prototypes. Security reports will be evaluated without claiming an
external audit has already occurred.

## Local release checks

Run `python scripts/release_check.py --tests` after installing the maintainer
dependencies. This validates package structure, checks selected imports and
subprocess options, and scans selected release content for a bounded set of
credential patterns. It is a regression check, not a complete secret scanner,
dependency vulnerability service or proof that arbitrary wrapped commands are safe.
