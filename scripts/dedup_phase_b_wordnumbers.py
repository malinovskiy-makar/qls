# -*- coding: utf-8 -*-
"""ФАЗА B — дыра числового гейта: количества, написанные СЛОВАМИ.

Эвристика `dedup_recon_numbers` читает только цифры. Пара 35706/38672 из
выборки («четыре события» против «три события») получает вердикт
«числа совпадают», потому что цифр в различии нет вовсе, — и проходит
гейт как дубль, хотя это разные задачи.

Здесь считается, сколько таких пар в предложенном явном уровне: числительное
есть в симметрической разности слов двух условий.

Только чтение, ничего не применяется.
"""
import argparse
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dedup_phase_b_enrich import connect, fetch_attrs, full_text  # noqa: E402
from dedup_phase_b_textsim import normalize  # noqa: E402

#: Числительные и кратности. Список намеренно короткий и без склонений
#: сверх самых частых: задача — оценить порядок дыры, а не закрыть её.
NUMERALS = {
    'ноль', 'один', 'одна', 'одно', 'два', 'две', 'три', 'четыре', 'пять',
    'шесть', 'семь', 'восемь', 'девять', 'десять', 'одиннадцать',
    'двенадцать', 'двадцать', 'тридцать', 'сорок', 'пятьдесят', 'сто',
    'тысяча', 'первый', 'первая', 'второй', 'вторая', 'третий', 'третья',
    'четвёртый', 'четвертый', 'пятый', 'вдвое', 'втрое', 'вчетверо',
    'удвоился', 'утроился', 'половина', 'треть', 'четверть', 'двух', 'трёх',
    'трех', 'четырёх', 'четырех', 'пяти', 'шести', 'семи', 'восьми',
    'девяти', 'десяти',
}
_WORD_RE = re.compile(r'[а-яё]+')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--explicit', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    z = np.load(args.explicit)
    ia, ib = z['id_a'], z['id_b']

    con = connect()
    ids = np.union1d(ia, ib)
    attrs = fetch_attrs(con, ids)
    con.close()
    слова = {int(i): set(_WORD_RE.findall(normalize(full_text(attrs[int(i)]))))
             for i in ids}

    подозрительные = []
    for a, b in zip(ia, ib):
        разница = слова[int(a)] ^ слова[int(b)]
        общие = разница & NUMERALS
        if общие:
            подозрительные.append({'a': int(a), 'b': int(b),
                                   'числительные в различии': sorted(общие)})

    итог = {
        'пар в явном уровне': int(len(ia)),
        'ПАР С ЧИСЛИТЕЛЬНЫМ В РАЗЛИЧИИ': len(подозрительные),
        'доля': round(len(подозрительные) / max(len(ia), 1), 4),
        'примеры': подозрительные[:20],
    }
    json.dump(итог, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in итог.items() if k != 'примеры'},
                     ensure_ascii=False, indent=1))
    for e in подозрительные[:15]:
        print('  %6d — %6d : %s' % (e['a'], e['b'],
                                    ', '.join(e['числительные в различии'])))


if __name__ == '__main__':
    main()
