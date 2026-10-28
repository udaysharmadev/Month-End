# Release checklist

This is an execution checklist, not evidence that unchecked external steps ran.

## Local candidate

- Install `requirements-dev.txt` into a local virtual environment.
- Run `python scripts/release_check.py --tests` and retain the observed output.
- Run the benchmark plan and local mechanism suite described in the benchmark
  reference; keep deterministic fixture results separate from model results.
- Run `python docs/demo.py --output docs/demo-record.json` to capture actual
  terminal-byte receipts. A changed record needs a new explicit output path.
- Build with `python scripts/build_release.py --output dist`.
- Verify both ZIPs' internal `RELEASE_MANIFEST.json` entries and the external
  versioned `SHA256SUMS` file. The builder performs internal verification itself.
- Extract the standalone skill into a clean project and exercise its advertised
  helpers. Confirm that it has no dependency on repository-relative resources.
- Keep the original supplied DOCX unchanged locally and exclude it from public
  source/releases. Its prototype status is historical context, not the current test count.

## Host and evidence gates

- Confirm discovery and explicit invocation inside each claimed running host.
- Freeze task revisions, model versions, effort, tools, graders and cache strata.
- Run the registered paired model evaluation within an approved cost limit.
- Include failures and all retries in spending, and retain provider field semantics.
- Independently grade the resulting artifacts and analyze repeated trials at
  the task cluster level. Report missing billing as unavailable.
- Review source identities and provider documentation using the dated
  [verification record](source-verification.md). Recheck changing sources before
  each release, or within 90 days, whichever comes first.
- Claim savings only when the actual quality and cost evidence supports it.

## Publication

- Confirm the owner/repository, visibility, release tag and authorization.
- Push the reviewed candidate and observe hosted CI on that exact revision.
- Publish archives/checksums, release notes, license, known limitations and
  benchmark evidence. An absent live benchmark is a limitation, not a green gate.
- Test the real published installation URL before placing it in the first-screen
  README. Never replace the destination with a fabricated owner/repository.
- Capture and inspect the actual video before publishing the storyboard's claims.
- Open a contribution path using the issue templates and security policy.
