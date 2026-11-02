"""Зубы Э8. Последовательный запуск, восстановление исходных байтов в finally."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / '.calc2-astra-local/mutations-e8'
CASES = [
    ('coordinate-layout-loop', 'calc2/static/calc2/60-overlays.js',
     '_labelPos.clear();labelsBeforeFit.forEach((v,k)=>_labelPos.set(k,v));',
     '/* broken: keep intermediate label positions */',
     'после правки формулы доступна отмена', 'astra_label_settle.mjs'),
    ('tax-without-b', 'calc2/static/calc2/51-islm.js',
     'const A=c.a-c.b*c.T+c.I0+c.G+c.Xn,h=1-c.b;',
     'const A=c.a-c.T+c.I0+c.G+c.Xn,h=1-c.b;',
     '14.56 база Y513 r13', 'astra_islm_probe.mjs'),
    ('cb-not-horizontal', 'calc2/static/calc2/51-islm.js',
     'hold=texTag({fn:()=>r.base.P}', 'hold=texTag({fn:Y=>r.base.P+Y}',
     'LM горизонтальная', 'astra_islm_probe.mjs'),
    ('reversed-crowding', 'calc2/static/calc2/51-islm.js',
     'crowdingY:constantMoney.eq?holdEq.Q-constantMoney.eq.Q:null',
     'crowdingY:constantMoney.eq?constantMoney.eq.Q-holdEq.Q:null',
     'фиксированная ставка:ΔY80,вытеснение40', 'astra_islm_probe.mjs'),
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
