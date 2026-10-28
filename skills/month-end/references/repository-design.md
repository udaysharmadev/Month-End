# Repository and release behavior

Month End's distribution unit is a self-contained `month-end/` skill folder.
Keep its entrypoint small and route specialized instructions to references and
optional executable helpers. Runtime use must not depend on developer-only
validation packages, the source checkout or a background service.

## Reviewable local release

The source checkout supplies `scripts/validate_package.py`,
`scripts/release_check.py`, and `scripts/build_release.py`. Run the local checks
and tests before building. The builder validates both a source snapshot and the
standalone skill snapshot, then writes deterministic ZIPs with internal per-file
SHA256 manifests and an external archive-checksum file. It excludes private
outputs, credential filenames and caches, rejects symlinks and selected secret
patterns, and refuses to replace different existing artifacts.

These are bounded package/security regression checks. They are not an external
audit, a complete secret scanner, hosted CI results or proof of model savings.
The source checkout's `docs/release-checklist.md` records the separate gates.

## Publication contract

The user-selected public destination is `udaysharmadev/Month-End` on GitHub.
Publish only the reviewed revision with its actual CI status, license, checksums,
known limitations and available benchmark evidence. Test the real remote install
after publishing; a repository URL is not a working install until its content is
available. Do not make global host changes as an installation convenience.

Keep the README's first screen focused on purpose, one verified installation
path, a real terminal-output example, compatibility and the proof status.
Local byte counts must be labeled terminal bytes. Never describe a prepared
storyboard as a recorded agent demonstration or use a synthetic ledger as live
model evidence.

## Contributions and maintenance

Issue templates cover hidden evidence/regressions, paired benchmark submissions,
and host compatibility. The source checkout includes a security reporting policy
and a truthful launch/article draft. Keep sensitive reproductions private.
Recheck primary documentation before releases, publish negative results, and
retain the versioned mechanism/source registry. MIT applies to original Month End
materials; do not copy restricted third-party source or proprietary prompt text.
