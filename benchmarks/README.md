# Benchmark fixtures and results

`local/suite.json` registers twelve distinct coding tasks with frozen source
fingerprints, three repeats, both baseline/Month End arms and cold/warm setup
branches. `local/grade.py` grades behavior independently of the deterministic
reference patcher. These are local runner checks, not live AI-agent evidence.

```bash
python3 skills/month-end/scripts/benchmark.py benchmarks/local/suite.json
python3 skills/month-end/scripts/benchmark.py benchmarks/local/suite.json --execute --output benchmarks/results/new-run
python3 skills/month-end/scripts/compare_runs.py --require-metadata benchmarks/results/new-run/runs.csv
```

Do not describe a reference patcher as an agent or cite its wall time/output as
model savings. Its ledger intentionally has no model tokens or billed dollars.
The runner supports external subscription/API harnesses only through explicitly
supplied argv and supported usage exports. It never chooses paid calls or reads
credentials. Read the [runner contract](../skills/month-end/references/benchmark.md)
before constructing a live manifest or sharing raw artifacts.

The separate [workflow suite](workflow/README.md) registers sixty distinct
synthetic repair tasks and 321 cases for the explicit multi-turn Gemini study.
Its smoke cases and final acceptance cases are separated in the model's tool
filesystem. The live workflow study has not been run; see its
[planned protocol](../docs/workflow-evaluation.md).
