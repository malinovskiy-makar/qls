"""Зубы Э13. Последовательный запуск, восстановление исходных байтов в finally."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / '.calc2-astra-local/mutations-e13'
CASES = [
    ('ignore-country-B', 'calc2/static/calc2/55-big-trade.js',
     'const prepared={A:bigTradePrepare(input.A),B:bigTradePrepare(input.B)};', "const prepared={A:bigTradePrepare(input.A),B:bigTradePrepare({...input.B,policy:{},ban:'free'})};",
     'вмешательства обеих стран', 'astra_big_trade_probe.mjs'),
    ('world-without-budget', 'calc2/static/calc2/55-big-trade.js',
     'worldSW:A.sw+B.sw+A.rent+B.rent', 'worldSW:A.sw+B.sw+A.rent+B.rent-A.budget-B.budget',
     'благосостояние75', 'astra_big_trade_probe.mjs'),
]


def run(name, test):
    result = subprocess.run(
        [sys.executable, 'claude/calc2_astra_20261102/run_local.py',
         'node', 'calc2/tests/'+test],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
        env={**os.environ, 'ENGINES': 'chromium', 'WIDTHS': '1280'})
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
