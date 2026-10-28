"""Deterministic reference patcher for runner integration checks, never an AI arm."""
import json
import sys
from pathlib import Path

workspace, task_id = Path(sys.argv[1]), sys.argv[2]
solutions = json.loads((Path(__file__).parent / 'reference_solutions.json').read_text(encoding='utf-8'))
(workspace / 'app.py').write_text(solutions[task_id], encoding='utf-8')
print('Applied a known reference patch for local runner verification: ' + task_id)
