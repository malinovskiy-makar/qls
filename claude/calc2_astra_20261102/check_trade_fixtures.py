"""Независимый двумерный перебор выпуска и внутренних продаж, без JavaScript."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'calc2/tests/fixtures/astra_trade_grid.json'


def cases():
    for i in range(24):
        target = ['internal', 'producer', 'trade'][i % 3]
        form = ['unit', 'seller', 'buyer'][(i // 3) % 3]
        if target == 'trade' and form != 'unit':
            form = 'world'
        yield {
            'd0': 100, 'ds': 1 + i % 2,
            'c0': 20 if i % 4 == 0 else i % 5,
            'ca': -1 if i % 4 == 0 else 1 + i % 2,
            'Pw': 30 + 5 * (i % 4),
            'policy': {'kind': 'tax' if i % 2 else 'subsidy',
                       'target': target, 'form': form,
                       'rate': 10 if form == 'unit' else 20},
        }


def grid(c):
    t = c['policy']
    signed = t['rate'] * (1 if t['kind'] == 'tax' else -1)
    cap = -c['c0'] / c['ca'] if c['ca'] < 0 else 80

    def seller(price, applies):
        if not applies:
            return price
        if t['form'] == 'unit':
            return price - signed
        if t['form'] == 'world':
            return price - c['Pw'] * signed / 100
        if t['form'] == 'seller':
            return price / (1 + signed / 100)
        return price * (1 - signed / 100)

    export_price = seller(c['Pw'], t['target'] in ('trade', 'producer'))
    best = (0, 0, 0)
    for j in range(round(cap * 5) + 1):
        output = j / 5
        cost = c['c0'] * output + c['ca'] * output * output / 2
        for k in range(j + 1):
            domestic = k / 5
            price = c['d0'] - c['ds'] * domestic
            if price < 0:
                continue
            net = seller(price, t['target'] != 'trade')
            profit = net * domestic + export_price * (output - domestic) - cost
            if profit > best[0]:
                best = (profit, output, domestic)
    return {'profit': best[0], 'Q': best[1], 'q': best[2]}


def main():
    calculated = [{'config': c, 'grid': grid(c)} for c in cases()]
    if '--write' in sys.argv:
        if DEST.exists():
            raise SystemExit('Existing fixtures must not be overwritten')
        DEST.write_text(json.dumps(calculated, indent=2) + '\n')
    else:
        assert calculated == json.loads(DEST.read_text())
    print(f'{len(calculated)}/{len(calculated)}: independent two-dimensional grid')


if __name__ == '__main__':
    main()
