# Frozen synthetic workflow tasks

This suite contains sixty distinct small Python `solve` contracts in six
categories: parsing, collections, finance, dates, security validation and text.
The 321 expected outcomes were written before model execution. Every task has
at least four cases, a concrete buggy starting source and a separately stored
reference implementation.

Decimal task inputs use ordinary notation with at most forty integer and forty
fractional digits; compound periods are at most one hundred. Reference decimal
calculations use an explicit high-precision local context rather than inheriting
the process's default precision. Date edge cases include the final supported
Gregorian date, 9999-12-31. These bounds are declared before model execution.

The tasks are synthetic and public. They are not sixty production repositories,
are not external independent reproduction, and cannot exclude training-data or
public-fixture contamination. Reference-solution success only validates the
fixtures and grader; model trials are recorded separately.

## Grading

```bash
python3 benchmarks/workflow/grader.py /path/to/app.py parse-port --visible
python3 benchmarks/workflow/grader.py /path/to/app.py parse-port
python3 -m unittest discover -s tests -p test_workflow_suite.py -v
```

`--visible` runs the first two smoke cases only. Full grading runs every case,
including the remaining edge cases withheld from the model's tool filesystem.
The model task prompt must contain the full contract, including errors; passing
a smoke test never substitutes for full acceptance. Public fixture files remain
available to humans for reproduction.

The grader imports candidate source, calls `solve(*args, **kwargs)` against fixed
JSON values, checks expected exceptions and concrete JSON output types, and
rejects input mutation even when the return value matches. It returns a brief
JSON result and a nonzero exit on failure. It does not evaluate model-provided
test strings or let a candidate replace the oracle. It is **not a sandbox**:
run its CLI in a bounded isolated subprocess with the candidate security guard,
minimal environment, and operating-system restrictions used by the harness.

The API tool filesystem must exclude this directory, the task JSON's `tests`
field, the reference solutions, private receipts and host credentials. A model
may see only its prompt, its workspace and the two-case smoke feedback.

Before live execution, commit/freeze the suite, grader and skill versions. Keep
that identity with each trial, preserve both arms' usage and failures, and report
provider availability separately from accuracy. Do not tune a task or oracle
based on model results without recording a new suite version.
