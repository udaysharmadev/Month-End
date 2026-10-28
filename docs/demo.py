#!/usr/bin/env python3
"""Record an actual local terminal-output demo; no model or billing simulation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def record_demo(root: Path) -> dict:
    helper = Path(root).resolve() / 'skills' / 'month-end' / 'scripts' / 'monthend.py'
    passing_code = '[print("PASS case_%03d" % i) for i in range(500)]; print("500 passed")'
    failing_code = 'import sys; print("ERROR: invalid payment currency"); sys.exit(9)'
    with tempfile.TemporaryDirectory(prefix='month-end-demo-') as temporary:
        project = Path(temporary).resolve()
        (project / 'payments.py').write_text('def validate_payment(currency):\n    return currency == "INR"\n', encoding='utf-8')

        def execute(arguments):
            return subprocess.run(arguments, cwd=project, shell=False, capture_output=True, timeout=20)

        raw = execute([sys.executable, '-c', passing_code])
        passing = execute([sys.executable, str(helper), 'run', '--kind', 'tests', '--', sys.executable, '-c', passing_code])
        failed = execute([sys.executable, str(helper), 'run', '--kind', 'tests', '--', sys.executable, '-c', failing_code])
        locate = execute([sys.executable, str(helper), 'locate', 'validate_payment', '--root', '.'])
        excerpt = execute([sys.executable, str(helper), 'excerpt', 'payments.py', '--pattern', 'validate_payment', '--context', '1'])
        version = execute([sys.executable, str(helper), '--version'])
        if raw.returncode or passing.returncode or locate.returncode or excerpt.returncode or failed.returncode != 9:
            raise ValueError('demo command or preserved failure exit did not match the fixture')
        receipt = re.search(rb'raw_bytes=(\d+) displayed_bytes=(\d+)', passing.stdout)
        if receipt is None or int(receipt[1]) != len(raw.stdout):
            raise ValueError('demo receipt does not match directly captured raw bytes')

        def rendered(content):
            return content.decode('utf-8').replace(str(project), '<DEMO_DIR>')

        return {
            'format_version': 1,
            'helper_version': rendered(version.stdout).strip(),
            'scope': 'deterministic local terminal-output demonstration; not a model benchmark',
            'input': '500 passing fixture lines and one real failing child command',
            'raw_command_bytes': len(raw.stdout),
            'displayed_command_body_bytes': int(receipt[2]),
            'entire_wrapper_stdout_bytes': len(passing.stdout),
            'passing_exit': passing.returncode,
            'failing_exit': failed.returncode,
            'locate_stdout': rendered(locate.stdout),
            'excerpt_stdout': rendered(excerpt.stdout),
            'passing_stdout': rendered(passing.stdout),
            'failing_stdout': rendered(failed.stdout),
            'provider_usage': None,
            'billed_cost_usd': None,
            'limitations': ['No model called', 'No provider tokens measured', 'No task-success or billed-savings claim'],
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, help='Explicit destination for a JSON record; otherwise stdout')
    arguments = parser.parse_args(argv)
    try:
        content = json.dumps(record_demo(arguments.root), indent=2, sort_keys=True) + '\n'
        if arguments.output:
            if arguments.output.exists() and arguments.output.read_text(encoding='utf-8') != content:
                raise ValueError('destination differs; choose a new explicit demo-record path')
            if not arguments.output.exists():
                with arguments.output.open('x', encoding='utf-8') as stream:
                    stream.write(content)
            print(f'Recorded terminal-byte demo: {arguments.output}')
        else:
            print(content, end='')
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
