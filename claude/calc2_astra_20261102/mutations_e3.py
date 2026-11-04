"""Зубы Э3. Последовательный запуск, восстановление исходных байтов в finally."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / '.calc2-astra-local/mutations-e3'
CASES = [
    ('coefficient-rounded', 'calc2/static/calc2/10-math-core.js',
     'const n = v => CalcNumber.expression(v);',
     'const n = v => CalcNumber.expression(Math.round(v * 100) / 100);',
     'коэффициент 0.625 сохранён'),
    ('fraction-rounded', 'calc2/static/calc2/12-numbers.js',
     "if(f)r={kind:'fraction',text:fraction(...f),tex:fraction(...f,true)};",
     "if(f)r={kind:'decimal',text:decimal(v,2,true),tex:decimal(v,2,true)};",
     'запись 100/3'),
    ('radical-rounded', 'calc2/static/calc2/12-numbers.js',
     "if(rad)r={kind:'radical',text:radical(rad),tex:radical(rad,true)};",
     "if(rad)r={kind:'approx',text:decimal(v,3,true),tex:decimal(v,3,true)};",
     'запись 5√2'),
    ('self-rejects-fraction', 'calc2/static/calc2/96-self.js',
     'function selfParse(t) {',
     "function selfParse(t) { if (String(t).includes('/')) return null;",
     'Сначала сам 100/3'),
    ('reader-rejects-approx', 'calc2/tests/parse_shown.mjs',
     "if(s.startsWith('≈'))s=s.slice(1);else s=s.split('≈')[0];",
     "if(s.startsWith('≈'))return NaN;else s=s.split('≈')[0];",
     'parseShown ≈ 2,154'),
]


def run(name):
    result = subprocess.run(
        [sys.executable, 'claude/calc2_astra_20261102/run_local.py',
         'node', 'calc2/tests/astra_numbers_probe.mjs'],
        cwd=ROOT, capture_output=True, text=True, timeout=120)
    (REPORT / (name + '.log')).write_text(result.stdout + result.stderr)
    return result


def main():
    if str(ROOT) != '/private/tmp/calc2-astra-local-20261102/calc2-astra-work':
        raise SystemExit('Only isolated checkout')
    REPORT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, file, old, new, expected in CASES:
        target = ROOT / file
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
            result = run(name + '-broken')
            caught = any(line.startswith('FAIL ') and expected in line
                         for line in result.stdout.splitlines())
            if result.returncode != 1 or not caught:
                raise RuntimeError(name + ': нужный дефект не пойман')
        finally:
            target.write_bytes(original)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest or run(name + '-after').returncode:
            raise RuntimeError(name + ': восстановление не подтверждено')
        rows.append({'mutation': name, 'caught': True, 'restored': True, 'sha256': digest})
        (REPORT / 'results.json').write_text(json.dumps(rows, indent=2))
        print(name + ': green → expected red → green; bytes restored', flush=True)


if __name__ == '__main__':
    main()
