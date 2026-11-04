"""Эталон «Ответа» рынка труда для cards_probe Г и Л (сессия «рынок труда», 15.10.2026, ADR 0156).

Числа труда сменились решениями владельца (профсоюз по фонду оплаты …81ac…, безработица при его ставке …813c…,
новый стартовый пример D = 100 − L, S = 10 + 0,5L и МРОТ 45 …81df…, МРОТ в двусторонней на старте выключен
…8168…), и код до сессии (сервер BEFORE) им больше не эталон. Здесь те же величины считаются ПЕРЕБОРОМ, без кода
calc2: сетка по L с шагом 1e-4 (максимумы, пересечения), площади — суммой по сетке. Результат — строка чисел так, как
её собирает answerNums в cards_probe (главные числа «Ответа», «#», значения строк табло; пробелы и скобки сняты).

    python3 claude/calc2_labor/expected_cards.py   → calc2/tests/redesign/labor_cards_expected.json
"""
import json, os

STEP = 1e-4
LMAX = 200.0


def grid(a=0.0, b=LMAX, step=STEP):
    n = int(round((b - a) / step))
    return [a + i * step for i in range(n + 1)]


def cross(f, g, a=0.0, b=LMAX):
    """Первое L на сетке, где f − g меняет знак (уточнено линейно)."""
    prev = None
    for L in grid(a, b, 1e-3):
        d = f(L) - g(L)
        if prev is not None and prev[1] * d <= 0 and prev[1] != d:
            L0, d0 = prev
            return L0 + (L - L0) * d0 / (d0 - d)
        prev = (L, d)
    return None


def area(h, a, b, step=STEP):
    """∫ h dL суммой по средним точкам."""
    if b <= a:
        return 0.0
    n = max(1, int(round((b - a) / step)))
    w = (b - a) / n
    return sum(h(a + (i + 0.5) * w) for i in range(n)) * w


def argmax(h, a, b, step=1e-3):
    best, bl = None, None
    for L in grid(a, b, step):
        v = h(L)
        if best is None or v > best:
            best, bl = v, L
    # уточнение вокруг найденного
    lo, hi = max(a, bl - step), min(b, bl + step)
    for L in grid(lo, hi, step / 1000):
        v = h(L)
        if v > best:
            best, bl = v, L
    return bl


def fmt(x):
    """Как fmt calc2: два знака, без хвостовых нулей, запятая (пробелы тысяч answerNums снимает)."""
    s = ('%.2f' % (round(x + 0.0, 2) + 0.0)).rstrip('0').rstrip('.')
    if s in ('-0', ''):
        s = '0'
    return s.replace('.', ',')


def model(D, S, Wmin):
    eqL = cross(D, S)
    eqW = D(eqL)
    out = {'Lk': eqL, 'Wk': eqW,
           'wcs': area(lambda L: eqW - S(L), 0, eqL), 'fcs': area(lambda L: D(L) - eqW, 0, eqL)}
    # Конкуренция с МРОТ: занятость по спросу, желающих по предложению.
    if Wmin is not None and Wmin > eqW:
        Qd = cross(D, lambda L: Wmin)
        Qs = cross(S, lambda L: Wmin)
        out['comp_min'] = {'emp': Qd, 'un': max(0.0, Qs - Qd),
                           'wcs': area(lambda L: Wmin - S(L), 0, Qd), 'fcs': area(lambda L: D(L) - Wmin, 0, Qd),
                           'dwl': area(lambda L: D(L) - S(L), Qd, eqL)}
    # Монопсония: максимум прибыли ∫(D − W·L)′ = ∫D − S(L)·L.
    prof = lambda L: area(D, 0, L, 1e-2) - S(L) * L
    Lm = argmax(lambda L: area(D, 0, L, 1e-2) - S(L) * L, 0, eqL, 0.01)
    # уточнение: MCL = D (d(S·L)/dL = D) — перебором по сетке
    mcl = lambda L: (S(L + 1e-6) * (L + 1e-6) - S(L - 1e-6) * (L - 1e-6)) / 2e-6
    Lm = cross(mcl, D, max(0.0, Lm - 1), Lm + 1)
    Wm = S(Lm)
    out['mono'] = {'Lm': Lm, 'Wm': Wm, 'dwl': area(lambda L: D(L) - S(L), Lm, eqL)}
    if Wmin is not None and Wmin > Wm:
        Lhat = cross(S, lambda L: Wmin)
        # Прибыль нанимателя при МРОТ: зарплата max(W_min, S(L)) всем.
        p = lambda L: area(D, 0, L, 1e-2) - max(Wmin, S(L)) * L
        Ls = argmax(p, 0, LMAX / 2, 0.01)
        wage = max(Wmin, S(Ls))
        out['mono_min'] = {'L': Ls, 'wage': wage, 'un': max(0.0, Lhat - Ls),
                           'wcs': area(lambda L: wage - S(L), 0, Ls), 'fcs': area(lambda L: D(L) - wage, 0, Ls),
                           'dwl': area(lambda L: D(L) - S(L), Ls, eqL)}
    # Профсоюз: максимум фонда L·D(L) при L ≤ Lk (не больше желающих при W ≥ Wk).
    Lu = argmax(lambda L: L * D(L), 0, eqL, 0.001)
    corner = abs(Lu - eqL) < 1e-3
    if corner:
        Lu = eqL
    Wu = D(Lu)
    Qs = cross(S, lambda L: Wu)
    out['union'] = {'Lu': Lu, 'Wu': Wu, 'fund': Lu * Wu, 'Qs': Qs, 'un': 0.0 if corner else max(0.0, Qs - Lu),
                    'dwl': 0.0 if corner else area(lambda L: D(L) - S(L), Lu, eqL), 'corner': corner}
    return out


def strings(D, S, Wmin_on):
    m = model(D, S, 45.0 if Wmin_on else None)
    f = fmt
    u, mo = m['union'], m['mono']
    r = {}
    # Конкуренция (labor), МРОТ 45 на старте.
    sb = [f(m['Lk']), f(m['Wk']), f(m['wcs']), f(m['fcs'])]
    c = m.get('comp_min')
    if c:
        sb += ['45', f(c['emp']) + 'было' + f(m['Lk'])] + ([f(c['un'])] if c['un'] > 1e-6 else []) + [f(c['wcs']), f(c['fcs']), f(c['dwl'])]
    r['labor'] = '|'.join([f(m['Lk']), f(m['Wk'])]) + '#' + '|'.join(sb)
    # Монопсония (labor-mono), МРОТ 45.
    sb = [f(mo['Lm']), f(mo['Wm']), f(m['Lk']), f(m['Wk']), f(mo['dwl'])]
    mm = m.get('mono_min')
    if mm:
        sb += ['45', f(mm['L']) + 'было' + f(mo['Lm']), f(mm['wage'])] + ([f(mm['un'])] if mm['un'] > 1e-6 else []) + [f(mm['wcs']), f(mm['fcs']), f(mm['dwl'])]
    r['labor-mono'] = '|'.join([f(mo['Lm']), f(mo['Wm']), f(mo['dwl'])]) + '#' + '|'.join(sb)
    # Профсоюз (labor-union), монополист.
    sb = [f(u['Lu']), f(u['Wu']), f(u['fund'])]
    if not u['corner']:
        sb += [f(u['Qs'])] + ([f(u['un'])] if u['un'] > 1e-6 else [])
    sb += [f(m['Lk']), f(m['Wk'])] + ([] if u['corner'] else [f(u['dwl'])])
    r['labor-union'] = '|'.join([f(u['Lu']), f(u['Wu'])]) + '#' + '|'.join(sb)
    # Двусторонняя (labor-bilat), МРОТ на старте выключен.
    lo, hi = min(mo['Wm'], u['Wu']), max(mo['Wm'], u['Wu'])
    sb = [f(mo['Wm']), f(u['Wu']), f(lo) + '…' + f(hi), f(m['Wk']), f(mo['Lm']) + 'и' + f(u['Lu']), '0и' + f(u['un'])]
    r['labor-bilat'] = '|'.join([f(mo['Wm']), f(u['Wu'])]) + '#' + '|'.join(sb)
    return r, m


if __name__ == '__main__':
    S = lambda L: 10 + 0.5 * L                       # стартовое предложение (решение …81df…)
    g, mg = strings(lambda L: 90 - L, S, True)       # контрольный ввод cards_probe Г: D = 90 − L
    l, ml = strings(lambda L: 100 - L, S, True)      # контрольный ввод cards_probe Л: D = 100 − L (старт)
    out = {
        'why': 'рынок труда, ADR 0156: эталон «Ответа» труда после контрольного ввода — перебор '
               'claude/calc2_labor/expected_cards.py, а не код до сессии (решения …81ac…, …813c…, …81df…, …8168…)',
        'cases': {k + '|': v for k, v in g.items()},   # ключи как в cards_probe: <модель>|<подпись случая>
        'labor100L': l['labor'],
        'numbers_90L': {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in (v.items() if isinstance(v, dict) else [])}
                        for k, v in mg.items() if isinstance(v, dict)},
    }
    p = os.path.join(os.path.dirname(__file__), '..', '..', 'calc2', 'tests', 'redesign', 'labor_cards_expected.json')
    with open(os.path.normpath(p), 'w', encoding='utf8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    print(json.dumps({'cases': out['cases'], 'labor100L': out['labor100L']}, ensure_ascii=False, indent=1))
