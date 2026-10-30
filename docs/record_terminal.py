#!/usr/bin/env python3
"""Capture actual demo command output as asciicast v2 and an offline HTML player."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def capture(root: Path, pause: float = 9.5) -> tuple[list, dict]:
    """Run fixed local commands; pauses provide reading time, not simulated work."""
    header = {'version': 2, 'width': 100, 'height': 30, 'timestamp': int(time.time()),
              'title': 'Month End: actual local terminal command capture',
              'env': {'TERM': 'xterm-256color', 'SHELL': 'command-capture'}}
    events = [header]
    receipt = {'format_version': 1, 'scope': 'actual local subprocess-output recording',
               'capture_method': 'stdout then stderr after each completed child; no interactive TTY',
               'agent_screen_recording': False, 'provider_usage': None, 'billed_cost_usd': None,
               'reading_pause_seconds': pause, 'commands': []}
    started = time.monotonic()

    def emit(value):
        events.append([round(time.monotonic() - started, 6), 'o', value.replace('\n', '\r\n')])

    with tempfile.TemporaryDirectory(prefix='month-end-terminal-demo-') as temporary:
        workspace = Path(temporary)
        (workspace / '.month-end').mkdir()
        shutil.copyfile(root / 'skills/month-end/scripts/monthend.py', workspace / '.month-end/monthend.py')
        (workspace / 'payments.py').write_text('def validate_payment(currency):\n    return currency == "INR"\n')
        (workspace / 'passing.py').write_text('[print("PASS case_%03d" % i) for i in range(500)]\nprint("500 passed")\n')
        (workspace / 'failing.py').write_text('import sys\nprint("ERROR: invalid payment currency")\nsys.exit(9)\n')
        helper = [sys.executable, '.month-end/monthend.py']
        commands = [
            ('python3 .month-end/monthend.py --version', helper + ['--version'], 0),
            ("python3 .month-end/monthend.py locate validate_payment --root .",
             helper + ['locate', 'validate_payment', '--root', '.'], 0),
            ('python3 .month-end/monthend.py excerpt payments.py --pattern validate_payment --context 1',
             helper + ['excerpt', 'payments.py', '--pattern', 'validate_payment', '--context', '1'], 0),
            ('python3 passing.py', [sys.executable, 'passing.py'], 0),
            ('python3 .month-end/monthend.py run --kind tests -- python3 passing.py',
             helper + ['run', '--kind', 'tests', '--', sys.executable, 'passing.py'], 0),
            ('python3 .month-end/monthend.py run --kind tests -- python3 failing.py',
             helper + ['run', '--kind', 'tests', '--', sys.executable, 'failing.py'], 9),
        ]
        for label, argv, expected in commands:
            emit('$ ' + label + '\n')
            result = subprocess.run(argv, cwd=workspace, capture_output=True, timeout=20)
            if result.returncode != expected:
                raise ValueError(f'demo exit mismatch for {label}: {result.returncode}')
            output = (result.stdout + result.stderr).decode('utf-8').replace(str(workspace), '<DEMO_DIR>')
            if not output.endswith('\n'):
                output += '\n'
            emit(output)
            emit(f'[exit={result.returncode}]\n\n')
            receipt['commands'].append({'command': label, 'exit': result.returncode,
                                        'stdout_bytes': len(result.stdout), 'stderr_bytes': len(result.stderr),
                                        'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
                                        'stderr_sha256': hashlib.sha256(result.stderr).hexdigest()})
            if pause:
                time.sleep(pause)
        emit('Terminal-output demonstration complete. No model tokens or billed savings measured.\n')
    receipt['duration_seconds'] = events[-1][0]
    return events, receipt


def player(events: list) -> str:
    payload = json.dumps(events, ensure_ascii=True).replace('<', r'\u003c')
    return '''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Month End — actual terminal recording</title>
<style>
:root{color-scheme:dark light;font:16px system-ui;background:#101827;color:#eff6ff}
body{max-width:1100px;margin:40px auto;padding:0 20px}h1{font-size:28px;margin-bottom:8px}
p{color:#b7c6da;line-height:1.5}section{background:#07101d;border:1px solid #344963;border-radius:12px;overflow:hidden}
nav{display:flex;gap:12px;align-items:center;padding:14px;background:#17263b;flex-wrap:wrap}
button,select{font:inherit;padding:7px 12px;border:1px solid #5f7590;border-radius:6px;background:#233852;color:#fff}
input{flex:1;min-width:160px}pre{padding:20px;margin:0;height:440px;overflow:auto;font:14px/1.45 ui-monospace,monospace;white-space:pre-wrap;color:#c7f9d4}
small{color:#b7c6da}a{color:#88bfff}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #88bfff}
</style>
<h1>Month End terminal demonstration</h1>
<p>Actual command output: locate source, read exact lines, shorten a noisy passing command,
and preserve failure exit 9. Reading pauses are included. This is a local terminal capture;
no agent screen, provider tokens or billed savings are represented.</p>
<section><nav><button id="play" type="button">Play</button><button id="restart" type="button">Restart</button>
<label>Speed <select id="speed"><option value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select></label>
<input id="seek" type="range" min="0" max="1" step="0.01" value="0" aria-label="Recording position">
<output id="clock">0 / 0 s</output></nav><pre id="terminal" tabindex="0" aria-label="Recorded terminal output"></pre></section>
<p><small>Self-contained offline player. The adjacent .cast file uses asciicast v2;
the .receipt.json file records actual exits, byte counts and output hashes.</small></p>
<script>
const recording=PAYLOAD,events=recording.slice(1),end=events.length?events[events.length-1][0]:0;
const play=document.getElementById('play'),seek=document.getElementById('seek'),terminal=document.getElementById('terminal');
const clock=document.getElementById('clock'),speed=document.getElementById('speed');
let position=0,running=false,previous=0;seek.max=end;
function render(){terminal.textContent=events.filter(e=>e[0]<=position).map(e=>e[2]).join('').replace(/\\r/g,'');
 terminal.scrollTop=terminal.scrollHeight;seek.value=position;clock.textContent=position.toFixed(1)+' / '+end.toFixed(1)+' s';}
play.onclick=()=>{if(position>=end)position=0;running=!running;previous=0;play.textContent=running?'Pause':'Play';render();};
document.getElementById('restart').onclick=()=>{position=0;previous=0;render();};
seek.oninput=()=>{position=Number(seek.value);previous=0;render();};
function tick(now){if(running){if(previous)position=Math.min(end,position+(now-previous)/1000*Number(speed.value));
 previous=now;render();if(position>=end){running=false;play.textContent='Play';}}requestAnimationFrame(tick);}
render();requestAnimationFrame(tick);
</script></html>'''.replace('PAYLOAD', payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True, help='New output stem; writes .cast/.html/.receipt.json')
    parser.add_argument('--pause', type=float, default=9.5, help='Actual reading pause after each command, in seconds (0–10)')
    args = parser.parse_args(argv)
    if not 0 <= args.pause <= 10:
        parser.error('--pause must be between zero and ten seconds')
    paths = [args.output.with_suffix(suffix) for suffix in ('.cast', '.html', '.receipt.json')]
    if any(path.exists() for path in paths):
        parser.error('choose a new output stem; existing recordings are never overwritten')
    try:
        events, receipt = capture(args.root.resolve(), args.pause)
        payloads = ['\n'.join(json.dumps(event, ensure_ascii=True) for event in events) + '\n',
                    player(events), json.dumps(receipt, indent=2) + '\n']
        for path, content in zip(paths, payloads):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8') as stream:
                stream.write(content)
        print(f'Recorded {len(receipt["commands"])} commands; exits preserved; {receipt["duration_seconds"]:.1f}s')
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
