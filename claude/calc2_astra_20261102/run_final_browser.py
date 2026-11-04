"""Final supplementary browser checks, sequential and with explicit exit codes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    label = sys.argv[1]
    if '/' in label or '..' in label:
        raise SystemExit('Label must be a directory name')
    out = ROOT / '.calc2-astra-local/logs' / label
    out.mkdir(exist_ok=False)
    cases = [
        ['calc2/tests/control_numbers.mjs'],
        ['calc2/tests/calc2_math.mjs'],
        ['calc2/tests/canon_checks.mjs'],
        ['calc2/tests/webkit_probe.mjs'],
        ['calc2/tests/astra_new_models_exports.mjs'],
        ['calc2/tests/redesign/state_probe.mjs', '--jobs', '2', '--out', str(out / 'states')],
    ]
    after_pdf = sys.argv[2:] == ['--after-pdf']
    if sys.argv[2:] and not after_pdf:
        raise SystemExit('Неизвестный режим; допустим --after-pdf.')
    if after_pdf:
        cases = [
            ['calc2/tests/control_numbers.mjs'],
            ['calc2/tests/redesign/axis_labels_probe.mjs'],
            ['calc2/tests/redesign/state_probe.mjs', '--jobs', '1',
             '--keys', 'mono-nat,m-transform,m-optimum,m-minmax,m-tangent', '--out', str(out / 'states')],
        ]
    rows = []
    for args in cases:
        log = out / (Path(args[0]).stem + '.log')
        start = time.monotonic()
        with log.open('w') as stream:
            try:
                code = subprocess.call([sys.executable, 'claude/calc2_astra_20261102/run_local.py', 'node', *args], cwd=ROOT, env=dict(os.environ, ENGINES='chromium,webkit') if after_pdf else None, stdout=stream, stderr=subprocess.STDOUT, timeout=3600)
            except subprocess.TimeoutExpired:
                code = 'timeout'
        if args[0].endswith('canon_checks.mjs') and code == 0:
            # Прибор-измеритель возвращает 0 даже с находками. Читаем результат,
            # иначе успешное исполнение было бы принято за соблюдение канона.
            raw = log.read_text().split('###CANON-JSON###')
            findings = json.loads(raw[-1]) if len(raw) == 2 else None
            if findings is None or any(v['n'] for v in findings.values()):
                code = 1
        row = {'test': args, 'code': code, 'seconds': round(time.monotonic() - start, 1)}
        rows.append(row)
        (out / 'summary.json').write_text(json.dumps(rows, indent=2))
        print(json.dumps(row), flush=True)
    return int(any(r['code'] for r in rows))


if __name__ == '__main__':
    sys.exit(main())
