# -*- coding: utf-8 -*-
"""Инвентарь цветов по всему коду — СТРАХОВКА ПЕРЕД ДИЗАЙН-РАБОТОЙ.

Зачем. Через две недели после большой правки палитры вопрос «а какой тут был
цвет до того?» задаётся регулярно, а ответить на него по памяти нельзя. Этот
скрипт снимает полный слепок: каждое вхождение цвета в `.html`, `.css` и `.js`
с файлом, номером строки, значением и тем, в каком свойстве оно стоит.

Скрипт НИЧЕГО НЕ МЕНЯЕТ. Он только читает и пишет два отчёта в `reports/`.

⚠️ ВХОЖДЕНИЯ В КОММЕНТАРИЯХ СЧИТАЮТСЯ ОТДЕЛЬНО, И ЭТО ВАЖНО. В этом проекте
объяснения у токенов длинные и цитируют старые значения («было #b26b00, стало
#96500c») — если мешать их с живым кодом, счётчик покажет работы вдвое больше,
чем есть. Головные числа отчёта — по ЖИВЫМ вхождениям; сколько ушло в
комментарии, сказано рядом.

Запуск:
    python scripts/color_inventory.py [--date ГГГГММДД]
"""
import argparse
import colorsys
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTS = ('.html', '.css', '.js', '.mjs')

# Каталоги, которых в инвентаре быть не должно: чужой код, слепки прошлых
# прогонов и собственная папка отчётов.
SKIP_DIRS = {
    'node_modules', 'vendor', 'reports', '.git', 'venv', 'venv312', 'venv313',
    '__pycache__', 'staticfiles', 'media', '_incoming', 'htmlcov', '.ruff_cache',
}

# ── Разбор значений ──────────────────────────────────────────────────────
HEX = re.compile(r'#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b')
FUNC = re.compile(r'\b(rgba?|hsla?)\s*\(([^()]*)\)', re.I)

# Свойство или токен, внутри которого стоит цвет: последнее `имя:` слева.
PROP = re.compile(r'(--[A-Za-z0-9_-]+|[A-Za-z-]+)\s*:\s*[^;:{}]*$')


def _norm_hex(raw):
    body = raw[1:]
    if len(body) in (3, 4):
        body = ''.join(ch * 2 for ch in body)
    body = body.lower()
    if len(body) == 8 and body[6:] == 'ff':
        body = body[:6]
    return '#' + body


def _num(text, scale=255.0):
    text = text.strip()
    if text.endswith('%'):
        return float(text[:-1]) / 100 * scale
    return float(text)


def _norm_func(kind, args):
    """`rgb/rgba/hsl/hsla` → канонический вид: hex для непрозрачных, rgba иначе."""
    parts = [p.strip() for p in args.replace('/', ',').split(',') if p.strip()]
    if len(parts) < 3:
        return None
    try:
        if kind.lower().startswith('rgb'):
            rgb = tuple(int(round(_num(p))) for p in parts[:3])
        else:
            hue = float(re.sub(r'(deg|turn|rad)$', '', parts[0])) / 360.0
            sat = _num(parts[1], 1.0)
            lig = _num(parts[2], 1.0)
            rgb = tuple(int(round(c * 255))
                        for c in colorsys.hls_to_rgb(hue % 1.0, lig, sat))
        alpha = float(parts[3]) if len(parts) >= 4 else 1.0
    except ValueError:
        return None
    rgb = tuple(max(0, min(255, c)) for c in rgb)
    if alpha >= 1.0:
        return '#%02x%02x%02x' % rgb
    return 'rgba(%d,%d,%d,%g)' % (rgb + (round(alpha, 4),))


# ── Маска комментариев ───────────────────────────────────────────────────
COMMENT_SPANS = (
    (re.compile(r'/\*.*?\*/', re.S), None),
    (re.compile(r'<!--.*?-->', re.S), None),
    (re.compile(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}', re.S), None),
    (re.compile(r'^[ \t]*(?://|#)[^\n]*$', re.M), None),
)


def _comment_mask(text):
    """Множество индексов символов, лежащих внутри комментария.

    ⚠️ Грубо, и намеренно: разбирать HTML+Django+CSS+JS полноценным парсером
    ради инвентаря — избыточно. Ошибка в спорных случаях идёт в сторону
    «считать комментарием», то есть живых вхождений в отчёте не больше
    настоящего, а не меньше.
    """
    mask = bytearray(len(text))
    for pattern, _ in COMMENT_SPANS:
        for hit in pattern.finditer(text):
            mask[hit.start():hit.end()] = b'\x01' * (hit.end() - hit.start())
    return mask


# ── Обход ────────────────────────────────────────────────────────────────
def walk():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith('.'))
        for name in sorted(files):
            if name.endswith(EXTS):
                yield os.path.join(base, name)


def scan(path):
    with open(path, encoding='utf-8', errors='replace') as handle:
        text = handle.read()
    mask = _comment_mask(text)
    starts = [0]
    for i, ch in enumerate(text):
        if ch == '\n':
            starts.append(i + 1)

    def line_of(pos):
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    found = []
    for hit in HEX.finditer(text):
        found.append((hit.start(), hit.end(), _norm_hex(hit.group(0)), hit.group(0)))
    for hit in FUNC.finditer(text):
        value = _norm_func(hit.group(1), hit.group(2))
        if value:
            found.append((hit.start(), hit.end(), value, hit.group(0)))

    rel = os.path.relpath(path, ROOT).replace('\\', '/')
    out = []
    for start, end, value, raw in sorted(found):
        line_no = line_of(start)
        line_text = text[starts[line_no - 1]:end]
        prop = PROP.search(line_text)
        out.append({
            'file': rel,
            'line': line_no,
            'value': value,
            'raw': raw,
            'where': prop.group(1) if prop else None,
            'in_comment': bool(mask[start]),
        })
    return out


# ── Группировка по экранам ───────────────────────────────────────────────
def screen_of(rel):
    if rel.startswith('problems/review_bundle_assets/') \
            or rel.endswith('teacher/assignment_print.html'):
        return 'печатные и офлайн-выгрузки'
    if rel.startswith('calc2/'):
        return 'calc2'
    if rel.startswith('game/'):
        return 'game'
    # ⚠️ `calendar_stub` добавлен к сайту СВЕРХ списка из задания (там были
    # названы templates/catalog/student/teacher/problems). Это тоже экран,
    # который видит человек, и мерить его в одной корзине с `scripts/` и
    # `deploy/` значило бы занизить масштаб работы по сайту. Предположение
    # явное — если владелец считает иначе, строка убирается одна.
    if rel.split('/', 1)[0] in ('templates', 'catalog', 'student', 'teacher',
                                'problems', 'calendar_stub'):
        return 'сайт'
    return 'прочее'


SCREENS = ['сайт', 'calc2', 'game', 'печатные и офлайн-выгрузки', 'прочее']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', default='20260831',
                        help='метка даты в именах файлов отчёта (ГГГГММДД)')
    args = parser.parse_args()

    rows = []
    for path in walk():
        rows.extend(scan(path))

    live = [r for r in rows if not r['in_comment']]

    by_value = {}
    for row in live:
        box = by_value.setdefault(row['value'], {'count': 0, 'files': {}, 'screens': {}})
        box['count'] += 1
        box['files'][row['file']] = box['files'].get(row['file'], 0) + 1
        screen = screen_of(row['file'])
        box['screens'][screen] = box['screens'].get(screen, 0) + 1

    order = sorted(by_value.items(), key=lambda kv: (-kv[1]['count'], kv[0]))
    per_screen = {s: {} for s in SCREENS}
    for row in live:
        per_screen[screen_of(row['file'])].setdefault(row['value'], 0)
        per_screen[screen_of(row['file'])][row['value']] += 1

    os.makedirs(os.path.join(ROOT, 'reports'), exist_ok=True)
    json_path = os.path.join(ROOT, 'reports', 'color_inventory_%s.json' % args.date)
    md_path = os.path.join(ROOT, 'reports', 'color_inventory_%s.md' % args.date)

    with open(json_path, 'w', encoding='utf-8') as handle:
        json.dump({
            'всего_вхождений': len(rows),
            'живых_вхождений': len(live),
            'в_комментариях': len(rows) - len(live),
            'уникальных_цветов': len(by_value),
            'по_экранам': {s: {'уникальных': len(per_screen[s]),
                               'вхождений': sum(per_screen[s].values())}
                           for s in SCREENS},
            'сводка': {v: {'count': b['count'], 'files': b['files'], 'screens': b['screens']}
                       for v, b in order},
            'вхождения': rows,
        }, handle, ensure_ascii=False, indent=1)

    lines = []
    add = lines.append
    add('# Инвентарь цветов, %s-%s-%s' % (args.date[:4], args.date[4:6], args.date[6:]))
    add('')
    add('Снят `scripts/color_inventory.py` перед большой дизайн-работой, чтобы')
    add('через две недели можно было сказать, каким цвет был до правки, и вернуть.')
    add('Скрипт только читает; ни один цвет этой съёмкой не изменён.')
    add('')
    add('## Числа')
    add('')
    add('| | |')
    add('|---|---:|')
    add('| Живых вхождений (вне комментариев) | %d |' % len(live))
    add('| Вхождений в комментариях (историю цитируют, кода не красят) | %d |'
        % (len(rows) - len(live)))
    add('| Всего найдено | %d |' % len(rows))
    add('| Уникальных цветов (живых) | %d |' % len(by_value))
    add('')
    add('Уникальных по экранам:')
    add('')
    add('«Сайт» — `templates/`, `catalog/`, `student/`, `teacher/`, `problems/`')
    add('и `calendar_stub/`. «Прочее» — то, чего человек на экране не видит:')
    add('одноразовые скрипты замеров в `scripts/` и заглушка nginx в `deploy/`.')
    add('')
    add('| Экран | Уникальных цветов | Вхождений |')
    add('|---|---:|---:|')
    for screen in SCREENS:
        add('| %s | %d | %d |' % (screen, len(per_screen[screen]),
                                  sum(per_screen[screen].values())))
    add('')
    add('## Цвета по убыванию частоты')
    add('')
    add('| Цвет | Раз | В каких файлах |')
    add('|---|---:|---|')
    for value, box in order:
        files = sorted(box['files'].items(), key=lambda kv: (-kv[1], kv[0]))
        shown = ', '.join('`%s` ×%d' % (f, n) for f, n in files[:6])
        if len(files) > 6:
            shown += ' и ещё %d' % (len(files) - 6)
        add('| `%s` | %d | %s |' % (value, box['count'], shown))
    add('')
    add('## По экранам')
    add('')
    for screen in SCREENS:
        box = per_screen[screen]
        if not box:
            continue
        add('### %s — %d уникальных, %d вхождений'
            % (screen, len(box), sum(box.values())))
        add('')
        add('| Цвет | Раз |')
        add('|---|---:|')
        for value, count in sorted(box.items(), key=lambda kv: (-kv[1], kv[0])):
            add('| `%s` | %d |' % (value, count))
        add('')
    with open(md_path, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')

    print('живых вхождений: %d, в комментариях: %d, уникальных цветов: %d'
          % (len(live), len(rows) - len(live), len(by_value)))
    for screen in SCREENS:
        print('  %-28s уникальных %3d, вхождений %4d'
              % (screen, len(per_screen[screen]), sum(per_screen[screen].values())))
    print('топ-15:')
    for value, box in order[:15]:
        print('  %-22s %4d  (%s)' % (value, box['count'],
                                     ', '.join(sorted(box['screens']))))
    print('отчёты: %s, %s' % (os.path.relpath(md_path, ROOT),
                              os.path.relpath(json_path, ROOT)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
