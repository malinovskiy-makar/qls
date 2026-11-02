"""Зубы Э10. Последовательный запуск, восстановление исходных байтов в finally."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / '.calc2-astra-local/mutations-e10'
CASES = [
    ('mc-rule-instead-of-global', 'calc2/static/calc2/46-firm-supply.js',
     'const cs=m.candidates.map(b=>firmCandidateAt(m,b,P)).filter(Boolean)',
     "const cs=m.candidates.filter(b=>b.kind==='curve'||b.Q===0).map(b=>firmCandidateAt(m,b,P)).filter(Boolean)",
     '7.2б вогнутые TC:cap8,shutdown8', 'astra_supply_probe.mjs'),
    ('ignore-capacity', 'calc2/static/calc2/46-firm-supply.js',
     'const tax=firmTax(c.tax),original=firmPolynomialPieces(sp.rhs,c.mode,K);',
     'K=Infinity;const tax=firmTax(c.tax),original=firmPolynomialPieces(sp.rhs,c.mode,K);',
     '7.2в K10:0/5/10', 'astra_supply_probe.mjs'),
    ('quasi-as-sunk', 'calc2/static/calc2/46-firm-supply.js',
     "const avoidable=c.period==='lr'||c.kind==='quasi',zeroCost=avoidable?0:fc+tax.lump;\n    let autoCap=null;",
     "const avoidable=c.period==='lr',zeroCost=avoidable?0:fc+tax.lump;\n    let autoCap=null;",
     '7.2г quasi shutdown40,0/20/30', 'astra_supply_probe.mjs'),
    ('revenue-as-unit', 'calc2/static/calc2/46-firm-supply.js',
     'const tax=firmTax(c.tax),original=firmPolynomialPieces(sp.rhs,c.mode,K);',
     "const tax=firmTax(c.tax);if(tax.type==='revenue'){tax.alpha=1;tax.unit=(tax.kind==='subsidy'?-1:1)*tax.rate;}const original=firmPolynomialPieces(sp.rhs,c.mode,K);",
     '7.3 revenue/tax', 'astra_supply_probe.mjs'),
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
