"""Зубы Э9. Последовательный запуск, восстановление исходных байтов в finally."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / '.calc2-astra-local/mutations-e9'
CASES = [
    ('no-lr-sras-shift', 'calc2/static/calc2/53-adas.js',
     'const delta=lr.P-srasAfter.pAtY(Ystar);', 'const delta=0;',
     'сдвинутая SRAS проходит через LR', 'astra_adas_probe.mjs'),
    ('changing-sr-wage', 'calc2/static/calc2/53-adas.js',
     'const sr=shock?adasIntersection(adAfter,srasAfter):base',
     "if(laborEngine&&shock?.kind==='ad')srasAfter=laborEngine.curve(laborEngine.base.nominalW*2);const sr=shock?adasIntersection(adAfter,srasAfter):base",
     '14.54 SR Y96 P6 ΔY32', 'astra_adas_probe.mjs'),
    ('percent-from-new-price', 'calc2/static/calc2/53-adas.js',
     '100*(e.P-base.P)/base.P', '100*(e.P-base.P)/e.P',
     '14.52 проценты от исходной точки', 'astra_adas_probe.mjs'),
]


def run(name, test):
    result = subprocess.run(
        [sys.executable, 'claude/calc2_astra_20261102/run_local.py',
         'node', 'calc2/tests/'+test],
        cwd=ROOT, capture_output=True, text=True, timeout=120)
    (REPORT / (name + '.log')).write_text(result.stdout + result.stderr)
    return result


def main():
    if str(ROOT) != '/private/tmp/calc2-astra-local-20261102/calc2-astra-work':
        raise SystemExit('Only isolated checkout')
    REPORT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, file, old, new, expected, test in CASES:
        target = ROOT / file
        original = target.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        (REPORT / (name + '.original')).write_bytes(original)
        if run(name + '-before',test).returncode:
            raise RuntimeError(name + ': исходная проверка красная')
        source = original.decode()
        if source.count(old) != 1:
            raise RuntimeError(name + ': неоднозначное место мутации')
        try:
            target.write_text(source.replace(old, new, 1))
            result = run(name + '-broken',test)
            caught = any(line.startswith('FAIL ') and expected in line
                         for line in result.stdout.splitlines())
            if result.returncode != 1 or not caught:
                raise RuntimeError(name + ': нужный дефект не пойман')
        finally:
            target.write_bytes(original)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest or run(name + '-after',test).returncode:
            raise RuntimeError(name + ': восстановление не подтверждено')
        rows.append({'mutation': name, 'caught': True, 'restored': True, 'sha256': digest})
        (REPORT / 'results.json').write_text(json.dumps(rows, indent=2))
        print(name + ': green → expected red → green; bytes restored', flush=True)


if __name__ == '__main__':
    main()
