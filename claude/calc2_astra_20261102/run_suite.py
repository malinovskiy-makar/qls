"""Последовательная регрессия с отдельными логами и честными кодами завершения."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
SUITES = {
    'e3-numberrepair': [
        'calc2/tests/astra_numbers_probe.mjs',
        'calc2/tests/control_numbers.mjs',
        'calc2/tests/redesign/parity_quick.mjs',
        'calc2/tests/answer_interv_probe.mjs',
        'calc2/tests/math_answer_probe.mjs',
        'calc2/tests/astra_numbers_view.mjs',
        'calc2/tests/tex/ci_quick.mjs',
    ],
    'e3-final': [
        'calc2/tests/astra_numbers_probe.mjs',
        'calc2/tests/control_numbers.mjs',
        'calc2/tests/redesign/parity_quick.mjs',
        'calc2/tests/calc2_math.mjs',
        'calc2/tests/astra_edges_probe.mjs',
        'calc2/tests/redesign/axis_labels_probe.mjs',
        'calc2/tests/answer_interv_probe.mjs',
        'calc2/tests/math_answer_probe.mjs',
        'calc2/tests/astra_view_probe.mjs',
        'calc2/tests/tex/ci_quick.mjs',
    ],
    'e3-first': [
        'calc2/tests/astra_numbers_probe.mjs',
        'calc2/tests/control_numbers.mjs',
        'calc2/tests/redesign/parity_quick.mjs',
        'calc2/tests/redesign/answer_probe.mjs',
        'calc2/tests/math_answer_probe.mjs',
        'calc2/tests/tex/ci_quick.mjs',
    ],
    'e2-final': [
        'calc2/tests/astra_edges_probe.mjs',
        'calc2/tests/redesign/axis_labels_probe.mjs',
        'calc2/tests/tex/ci_quick.mjs',
    ],
    'e2': [
        'calc2/tests/astra_edges_probe.mjs',
        'calc2/tests/control_numbers.mjs',
        'calc2/tests/redesign/parity_quick.mjs',
        'calc2/tests/redesign/answer_probe.mjs',
        'calc2/tests/tex/ci_quick.mjs',
        'calc2/tests/calc2_math.mjs',
        'calc2/tests/astra_view_probe.mjs',
    ],
    'e1': [
        'calc2/tests/astra_view_probe.mjs',
        'calc2/tests/control_numbers.mjs',
        'calc2/tests/redesign/parity_quick.mjs',
        'calc2/tests/redesign/answer_probe.mjs',
        'calc2/tests/tex/ci_quick.mjs',
        'calc2/tests/calc2_math.mjs',
        'calc2/tests/redesign/axis_labels_probe.mjs',
    ],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('suite', choices=SUITES)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    if '/' in args.label or '..' in args.label:
        raise SystemExit('Метка — имя каталога без пути.')
    out = ROOT / '.calc2-astra-local/logs' / args.label
    out.mkdir(parents=True, exist_ok=False)
    summary = []
    for test in SUITES[args.suite]:
        name = Path(test).stem
        start = time.monotonic()
        with (out / (name + '.log')).open('w') as log:
            try:
                result = subprocess.run(
                    [sys.executable, 'claude/calc2_astra_20261102/run_local.py', 'node', test],
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=600)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 'timeout'
        row = {'test':test, 'exit_code':code, 'seconds':round(time.monotonic()-start,1)}
        summary.append(row)
        (out / 'summary.json').write_text(json.dumps(summary,indent=2))
        print(json.dumps(row), flush=True)
    return int(any(row['exit_code'] != 0 for row in summary))


if __name__ == '__main__':
    sys.exit(main())
