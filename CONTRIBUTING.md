# Contributing to Month End

Focus on verifiable improvements rather than claims. Every behavioral change should include:

1. A reproducible case: platform version, repository commit, model and task type (without secrets).
2. The relevant raw tool output (redacted) or a synthetic fixture that faithfully reproduces it.
3. A failing test demonstrating why a previous optimization was incorrect or too expensive.
4. An acceptance test that protects task completion, and evidence that exact edit anchors remain intact.
5. If claiming total token or dollar savings: complete paired task-level measurements and cache details, including failed runs.

Do not add automatic global hooks, permissions bypasses, silent config rewrites, nonconsensual telemetry or undocumented provider API claims. Add optional integrations as separate, off-by-default modules.

## Reporting a regression

Provide command, expected output, actual output, exit status, whether `--log` was used, and the minimum sanitized fixture. Never include secret values.

## Local checks

Use Python 3.9+ and a local virtual environment. Install `requirements-dev.txt`,
then run `python scripts/validate_package.py` and
`python -m unittest discover -s tests -v`. The YAML parser is only for maintainer
validation; do not add runtime dependencies to the installed helpers.

For live evaluations include matching `repo_commit,model,cache_state` fields and
use `compare_runs.py --require-metadata`. Keep task grading independent, include
failed attempts in spending, and analyze correlated repeats separately. See the
[evaluation protocol](skills/month-end/references/evaluation.md).
