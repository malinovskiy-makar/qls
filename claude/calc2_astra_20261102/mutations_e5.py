"""Зубы Э5. Последовательный запуск, восстановление исходных байтов в finally."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / '.calc2-astra-local/mutations-e5'
CASES = [
    ('uniform-first-root', 'calc2/static/calc2/43-discrimination.js',
     '  const efficient=monoBestOutput(Dfn,mc,D,{...options,tr:q=>integrateBroken(Dfn,0,q,kinks)});',
     '  best.Q=best.cands.find(c=>c.Q>1e-8&&c.Q<best.Qhi-1e-8)?.Q||best.Q;\n  const efficient=monoBestOutput(Dfn,mc,D,{...options,tr:q=>integrateBroken(Dfn,0,q,kinks)});',
     'минимум MR=MC отвергнут', 'astra_discrimination_edges.mjs'),
    ('d3-no-fc', 'calc2/static/calc2/43-discrimination.js',
     'profit:tr-vc-cost.fc,cs,dwl:', 'profit:tr-vc,cs,dwl:',
     'FC вычтен в обоих режимах', 'astra_discrimination_probe.mjs'),
    ('d1-no-fc', 'calc2/static/calc2/40-scenes-market.js',
     'integrate(q=>evalCurve(STATE.D,q),0,Qcomp)-evalCurve(tc,Qcomp) : surplus;',
     'integrate(q=>evalCurve(STATE.D,q),0,Qcomp)-evalCurve(tc,Qcomp)+fc : surplus;',
     '6.27 прибыль с FC 1150', 'astra_discrimination_probe.mjs'),
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
