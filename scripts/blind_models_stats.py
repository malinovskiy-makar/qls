# -*- coding: utf-8 -*-
"""blind_models_stats — числа по слепому сравнению веток. ДЕНЕГ НЕ ТРАТИТ.

Читает `blind_models.html` и `blind_models_key.json`, собранные командой
`blind_models_export`, и считает то, ради чего страница делалась: где ветки
расходятся и связано ли расхождение с уверенностью модели в теме.

⚠️ Ключ здесь ОТКРЫВАЕТСЯ — значит скрипт запускается ПОСЛЕ того, как
владелец разметил страницу, а не до. Ничего слепого он не печатает.

⚠️ Читается страница, а не сырые ответы: страница есть у любого прогона, в
том числе у прогона 02.09.2026, сделанного до того, как команда научилась
сохранять `blind_models_rows.json`. Восемь показанных полей — ровно те, по
которым владелец и выбирает.

Запуск:
    python scripts/blind_models_stats.py
"""
import difflib
import html as html_lib
import json
import re
import statistics
from collections import Counter, defaultdict

HTML = 'reports/enrich_pilot/blind_models.html'
KEY = 'reports/enrich_pilot/blind_models_key.json'

key = json.load(open(KEY, encoding='utf-8'))
columns_key = key['columns']
BRANCHES = key['branches']

page = open(HTML, encoding='utf-8').read()
blocks = re.split(r'<h2>Задача #(\d+)</h2>', page)[1:]

FIELD_RE = re.compile(r'<div class="field"><b>([^<]+):</b> (.*?)</div>', re.S)

data = defaultdict(dict)  # problem_id -> branch -> {поле: значение}
for i in range(0, len(blocks), 2):
    pid = blocks[i]
    body = blocks[i + 1]
    cells = re.findall(r'<td>(.*?)</td>', body, re.S)
    letters = re.findall(r'<th>Колонка ([A-D])</th>', body)
    assert len(cells) == len(letters), (pid, len(cells), len(letters))
    for letter, cell in zip(letters, cells):
        branch = columns_key[pid][letter]
        fields = {name: html_lib.unescape(value).strip()
                  for name, value in FIELD_RE.findall(cell)}
        data[pid][branch] = fields

print('разобрано задач: %d, веток: %d' % (len(data), len(BRANCHES)))
ids = sorted(data, key=int)


def sim(a, b):
    return difflib.SequenceMatcher(None, a or '', b or '').ratio()


def tagset(value):
    # «Название (12.3), Другое (12.7)» → {'12.3', '12.7'}
    return set(re.findall(r'\(([0-9.]+)\)', value or ''))


def conceptset(value):
    if not value or value == '—':
        return set()
    return {x.strip() for x in value.split(',') if x.strip()}


def compare(left, right, label):
    same_topic = 0
    tags_full = tags_part = tags_zero = 0
    concepts_same = 0
    given_sims, find_sims = [], []
    n = 0
    for pid in ids:
        a, b = data[pid].get(left), data[pid].get(right)
        if not a or not b:
            continue
        n += 1
        if a.get('Тема') == b.get('Тема'):
            same_topic += 1
        ta, tb = tagset(a.get('Теги')), tagset(b.get('Теги'))
        if ta == tb:
            tags_full += 1
        elif ta & tb:
            tags_part += 1
        else:
            tags_zero += 1
        if conceptset(a.get('Понятия')) == conceptset(b.get('Понятия')):
            concepts_same += 1
        given_sims.append(sim(a.get('Дано'), b.get('Дано')))
        find_sims.append(sim(a.get('Найти'), b.get('Найти')))

    def p10(values):
        values = sorted(values)
        return values[max(0, int(round(0.1 * (len(values) - 1))))]

    print('')
    print('=== %s (n=%d) ===' % (label, n))
    print('  тема совпала:            %d (%.0f%%), разошлась %d (%.0f%%)'
          % (same_topic, 100 * same_topic / n, n - same_topic,
             100 * (n - same_topic) / n))
    print('  теги полное совпадение:  %d (%.0f%%)' % (tags_full, 100 * tags_full / n))
    print('  теги частичное:          %d (%.0f%%)' % (tags_part, 100 * tags_part / n))
    print('  теги НУЛЕВОЕ пересечение:%d (%.0f%%)' % (tags_zero, 100 * tags_zero / n))
    print('  понятия совпали:         %d (%.0f%%)' % (concepts_same, 100 * concepts_same / n))
    print('  «дано»  близость: медиана %.3f, p10 %.3f'
          % (statistics.median(given_sims), p10(given_sims)))
    print('  «найти» близость: медиана %.3f, p10 %.3f'
          % (statistics.median(find_sims), p10(find_sims)))
    return n


compare('base', 'luna-luna', 'Terra (base) против Luna (luna-luna), вызов 1')
compare('base', 'terra-low', 'Terra none против Terra low, вызов 1')
compare('base', 'terra-gen', 'вызов 2: Luna против Terra (call1 у обоих одинаков)')

# --- главная таблица: расхождение против уверенности Luna -----------------
print('')
print('=== РАСХОЖДЕНИЕ ПРОТИВ УВЕРЕННОСТИ LUNA ===')
buckets = defaultdict(lambda: {'n': 0, 'topic': 0, 'tags': 0})
for pid in ids:
    luna = data[pid].get('luna-luna')
    terra = data[pid].get('base')
    if not luna or not terra:
        continue
    conf = (luna.get('Уверенность') or '—').strip()
    slot = buckets[conf]
    slot['n'] += 1
    if luna.get('Тема') != terra.get('Тема'):
        slot['topic'] += 1
    if tagset(luna.get('Теги')) != tagset(terra.get('Теги')):
        slot['tags'] += 1

print('| Уверенность Luna | задач | разошлась тема | разошлись теги |')
print('|---|---:|---:|---:|')
for conf in ('высокая', 'средняя', 'низкая'):
    slot = buckets.get(conf)
    if not slot:
        print('| %s | 0 | — | — |' % conf)
        continue
    print('| %s | %d | %d (%.0f%%) | %d (%.0f%%) |'
          % (conf, slot['n'], slot['topic'], 100 * slot['topic'] / slot['n'],
             slot['tags'], 100 * slot['tags'] / slot['n']))
other = {k: v for k, v in buckets.items() if k not in ('высокая', 'средняя', 'низкая')}
if other:
    print('прочие значения уверенности:', {k: v['n'] for k, v in other.items()})

# --- сложность и заголовки ------------------------------------------------
print('')
print('=== сложность по веткам ===')
for branch in BRANCHES:
    counts = Counter(data[pid].get(branch, {}).get('Сложность', '—')
                     for pid in ids)
    print('  %-11s %s' % (branch, dict(sorted(counts.items()))))

print('')
print('=== заголовки: длина в словах ===')
for branch in BRANCHES:
    lengths = [len((data[pid].get(branch, {}).get('Заголовок') or '').split())
               for pid in ids]
    bad = [pid for pid in ids
           if not 1 <= len((data[pid].get(branch, {}).get('Заголовок') or '').split()) <= 4]
    print('  %-11s медиана %.1f, вне правила 1–4 слова: %d %s'
          % (branch, statistics.median(lengths), len(bad), bad[:6]))
