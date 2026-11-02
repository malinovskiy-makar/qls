"""Шесть реальных дефектов Э2: зелёный → ожидаемый красный → зелёный.

Запускать без параллельных браузерных проверок. Байты восстанавливаются в finally.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / '.calc2-astra-local/mutations-e2'
CASES = [
    ('subsidy-ps', '42-scenes-mono.js',
     'const psM = Pt * Qt - vcM - budget;', 'const psM = Pt * Qt - vcM;',
     'субсидия: PS=22500'),
    ('rounded-sw', '20-plane.js',
     'acc + (isFinite(v) ? v : NaN)', 'acc + (isFinite(v) ? roundShown(v) : NaN)',
     'SW считается из точных слагаемых'),
    ('no-shrink', '52-modes.js',
     'if (fit) setRanges(w.qmax, w.pmax);', 'if (fit) growRanges(w.qmax, w.pmax);',
     'новая малая формула сжимает окно'),
    ('intermediate-input', '82-input.js',
     'if (!err && commit) { inp._formulaCommitted', 'if (!err) { inp._formulaCommitted',
     'ошибка возвращает MSC к записи до правки'),
    ('unconditional-cs', '40-scenes-market.js',
     "html += `<div class=\"stat\"><span>$SW$ в оптимуме</span><b>${fmt(e.swOpt)}</b></div>`;",
     "html += `<div class=\"stat\"><span>$CS$ в оптимуме</span><b>1</b></div>`;",
     'без Пигу у оптимума нет условных CS'),
    ('nan-mrs', '10-math-core.js',
     'Math.abs(pa) <= zero ? NaN : Math.sign(pa) * Infinity', 'NaN',
     'MRS: бесконечность'),
]


def run(name):
    cmd = [sys.executable, 'claude/calc2_astra_20261102/run_local.py',
           'node', 'calc2/tests/astra_edges_probe.mjs']
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
    (REPORT / (name + '.log')).write_text(r.stdout + r.stderr)
    return r


def main():
    if str(ROOT) != '/private/tmp/calc2-astra-local-20261102/calc2-astra-work':
        raise SystemExit('Only isolated checkout')
    REPORT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, file, old, new, expected in CASES:
        target = ROOT / 'calc2/static/calc2' / file
        original = target.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        (REPORT / (name + '.original')).write_bytes(original)
        if run(name + '-before').returncode:
            raise RuntimeError(name + ': исходная проверка красная')
        source = original.decode()
        if source.count(old) != 1:
            raise RuntimeError(name + ': неоднозначное место мутации')
        try:
            target.write_text(source.replace(old, new, 1))
            r = run(name + '-broken')
            if r.returncode != 1 or not any(l.startswith('FAIL ') and expected in l for l in r.stdout.splitlines()):
                raise RuntimeError(name + ': нужный дефект не пойман')
        finally:
            target.write_bytes(original)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest or run(name + '-after').returncode:
            raise RuntimeError(name + ': восстановление не подтверждено')
        rows.append({'mutation':name, 'caught':True, 'restored':True, 'sha256':digest})
        (REPORT / 'results.json').write_text(json.dumps(rows, indent=2))
        print(name + ': green → expected red → green; bytes restored', flush=True)


if __name__ == '__main__':
    main()
