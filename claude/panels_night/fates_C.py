# Таблица судеб поясняющих строк «Условия» (L), «Вида» (V) и панели точек (P) — этап В (тихие панели 14.10).
# Каждая строка hints описи «до» (B_after.json): «Разбор» (текст найден в explain.text описи «после»,
# C_after.json, по этой же модели) или «убрана: интерфейс» с причиной. Код 1 — строка с судьбой «Разбор»
# в «Разборе» не найдена или судьба не назначена.
import json, re, sys
B = json.load(open('claude/panels_night/B_after.json', encoding='utf-8'))['models']
C = json.load(open('claude/panels_night/C_after.json', encoding='utf-8'))['models']
norm = lambda s: re.sub(r'[\s   ​«»"().,;:!?·*′\'_{}^\\|−-]+', '', str(s or '').lower())
# Судьба по классу / тексту строки (README пакета 6, 10).
INTERFACE = [
  (lambda h: h['id'] == 'btn-howto' or 'btn-howto' in h['cls'], 'переехала: таблица «Как писать» — разделом окна клавиатуры поля (82-input.js, addHowToTab)'),
  (lambda h: 'hint-row' in h['cls'] and h['text'].startswith('Ответ ищем на отрезке'), 'на месте: подпись поля «Ответ ищем на отрезке» (строка .seg-lab-row); убрана только «?», первая фраза плашки — в «Разборе» (data-explain)'),
  (lambda h: 'hint-row' in h['cls'], 'убрана: «?» и плашка (README 10.2); экономика плашки — в «Разборе» (data-explain), инструкция интерфейса — нет'),
  (lambda h: 'crow-auto' in h['cls'], 'убрана: интерфейс («считается по группам, правке не подлежит», README 10.3)'),
  (lambda h: 'wrench-note' in h['cls'], 'убрана: интерфейс («На графике заголовок можно перенести мышью…», README 10.3)'),
]
rows, bad = [], 0
for k, m in B.items():
    ex = norm(C[k]['explain']['text'])
    for h in m['hints']:
        if h['side'] not in 'LVP': continue
        fate = None
        for test, why in INTERFACE:
            if test(h): fate = why; break
        if fate is None:
            key = norm(h['text'])[:60]
            if key and key in ex: fate = '«Разбор» (найдено)'
            else: fate = 'НЕ НАЙДЕНО в «Разборе»'; bad += 1
        rows.append((h['side'], k, h['cls'] or h['id'], h['text'][:60], fate))
# Сводка: одинаковые строки разных моделей — одной строкой таблицы.
agg = {}
for side, k, cls, text, fate in rows:
    a = agg.setdefault((side, cls, text, fate), [])
    a.append(k)
print('| Сторона | Класс | Текст (начало) | Модели | Судьба |')
print('|---|---|---|---|---|')
for (side, cls, text, fate), ks in sorted(agg.items()):
    print('| %s | `%s` | %s | %s | %s |' % (side, cls, text.replace('|', '/'), (str(len(ks)) + ': ' + ', '.join(ks[:4]) + ('…' if len(ks) > 4 else '')), fate))
print('\nстрок описи «до» (L, V, P): %d; «Разбор» не найден: %d' % (len(rows), bad))
sys.exit(1 if bad else 0)
