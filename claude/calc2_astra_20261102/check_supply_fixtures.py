"""Независимо пересчитать 60 эталонов прямым Python-перебором шага .001.

Не вызывает JavaScript, не импортирует код калькулятора и не меняет эталоны.
"""
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
ROWS = ROOT / 'calc2/tests/fixtures/astra_supply_grid.json'
PATTERN = r'([0-9.]+)\*Q\^3\+\((-?[0-9.]+)\)\*Q\^2\+([0-9.]+)\*Q\+([0-9.]+)'


def main():
    rows = json.loads(ROWS.read_text())
    for index, row in enumerate(rows):
        c = row['config']
        match = re.fullmatch(PATTERN, c['expr'])
        if not match:
            raise ValueError(c['expr'])
        a, b, d, fc = map(float, match.groups())
        cap = c['K']
        disc = 4*b*b - 12*a*d
        if a and disc >= 0:
            for q in ((-2*b-math.sqrt(disc))/(6*a), (-2*b+math.sqrt(disc))/(6*a)):
                if q > 0 and 6*a*q+2*b < 0:
                    cap = min(cap, q)
        elif not a and b < 0:
            cap = min(cap, -d/(2*b))
        t = c['tax']
        sign = -1 if t['kind'] == 'subsidy' else 1
        alpha = 1-sign*t['rate']/100 if t['type'] == 'revenue' else 1
        unit = sign*t['rate'] if t['type'] == 'unit' else 0
        lump = sign*t['rate'] if t['type'] == 'lump' else 0
        zero = -(fc+lump) if c['kind'] == 'sunk' and c['period'] == 'sr' else 0
        best = (zero, 0)
        quantities = [cap] + [j*.001 for j in range(1, int(cap/.001)+1)]
        for q in quantities:
            profit = alpha*row['P']*q-(a*q**3+b*q*q+d*q+fc)-unit*q-lump
            if profit > best[0]:
                best = (profit, q)
        assert abs(best[0]-row['profit']) < 1e-8, (index, best, row)
        assert abs(best[1]-row['Q']) < 1e-8, (index, best, row)
        assert abs(cap-row['effectiveK']) < 1e-8, (index, cap, row)
    print(f'{len(rows)}/{len(rows)}: независимый Python-перебор совпал с эталонами')


if __name__ == '__main__':
    main()
