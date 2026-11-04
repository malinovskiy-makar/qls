"""Зубы Э6. Последовательный запуск, восстановление исходных байтов в finally."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / '.calc2-astra-local/mutations-e6'
CASES = [
    ('rounded-allocation', 'calc2/static/calc2/45-plants.js',
     'function plantsCandidate(f,g,u,v){',
     'function plantsCandidate(f,g,u,v){ v=Math.round(v/.3)*.3;',
     '4.18г раздел7/5', 'astra_plants_probe.mjs'),
    ('wrong-axis', 'calc2/static/calc2/45-plants.js',
     "drawAxes('Q',mc?'MC':'TC')", "drawAxes('Q',mc?'MC':'P')",
     'ось TC', 'astra_plants_probe.mjs'),
    ('no-capacity', 'calc2/static/calc2/45-plants.js',
     'const raw=[{...p.poly,lo:0,hi:p.K,alloc:[[1,0]]}',
     'const raw=[{...p.poly,lo:0,hi:Infinity,alloc:[[1,0]]}',
     'независимый Python Q12', 'astra_plants_probe.mjs'),
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
