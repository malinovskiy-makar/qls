# -*- coding: utf-8 -*-
"""СВЕРКА ЖУРНАЛА СЕССИИ 20.08 С ФАКТИЧЕСКИМ ПАТЧЕМ.

Отчёт сессии — это заявление. Проверяет его этот скрипт: у каждой заявленной
задачи есть след в коде, и след ищется в ФАЙЛАХ, а не в тексте отчёта.

Смысл ровно в том, чтобы пропущенное всплыло ДО того, как я отчитаюсь.

Запуск: ./venv/bin/python scripts/calc2_session20_audit.py
"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = lambda p: open(os.path.join(ROOT, p), encoding='utf8').read()

# (пункт, файл, что обязано быть в файле, что обязано ИСЧЕЗНУТЬ)
CLAIMS = [
    ('Фаза 1 · договор о параметрах: правило записано один раз',
     'calc2/static/calc2/30-curves.js', r'function sceneDrawsCurveList\(', None),
    ('Фаза 1 · карточку списка прячут оба места видимости',
     'calc2/static/calc2/52-modes.js', r'syncCurveListVisibility\(\)', None),
    ('Фаза 1 · то же у под-режимов монополии',
     'calc2/static/calc2/42-scenes-mono.js', r'syncCurveListVisibility\(\)', None),
    ('Фаза 1 · ползунки не заводятся из нерисуемого списка',
     'calc2/static/calc2/60-overlays.js', r'sceneDrawsCurveList\(\)\) \{\s*\n\s*STATE\.curves\.forEach', None),
    ('Фаза 2 · перетаскивание кривых снято одной константой',
     'calc2/static/calc2/30-curves.js', r'const CURVE_MOUSE_DRAG = false', None),
    ('Фаза 2 · curveDraggable читает эту константу первой строкой',
     'calc2/static/calc2/30-curves.js', r'if \(!CURVE_MOUSE_DRAG\) return false', None),
    ('Фаза 3 · значение принимается и числом, и строкой',
     'calc2/static/calc2/20-plane.js', r'function coordValue\(', None),
    ('Фаза 3 · прежняя проверка isFinite(value) убрана',
     'calc2/static/calc2/20-plane.js', None, r'isFinite\(px\) \|\| !isFinite\(value\)'),
    ('Фаза 3 · подпись координаты не разворачивается внутрь',
     'calc2/static/calc2/20-plane.js', r"'end', 'middle', \{ noFlip: true \}", None),
    ('Фаза 3 · у haloText появилась опция «не разворачивать»',
     'calc2/static/calc2/40-scenes-market.js', r'const noFlip = !!\(opts && opts\.noFlip\)', None),
    ('Фаза 3 · левое поле держит запас под подпись координаты',
     'calc2/static/calc2/20-plane.js', r'const COORD_LABEL_PAD = \d+', None),
    ('Фаза 3 · выгрузка не выбрасывает подписи координат',
     'calc2/static/calc2/70-scenes-math.js', r"classList\.contains\('coord-num'\)", None),
    ('Фаза 3 · пунктир к оси цены получил число во «Внешних эффектах»',
     'calc2/static/calc2/40-scenes-market.js', r"axisValueY\(g, ox, pym, fmt\(e\.Pmkt\), 'рын'\)", None),
    ('Фаза 3 · и в естественной монополии',
     'calc2/static/calc2/42-scenes-mono.js', r'axisValueY\(g, ox, py, fmt\(P\), idx', None),
    ('Фаза 4.1 · тумблер четверти помнит окно до включения',
     'calc2/static/calc2/86-workspace.js', r'STATE\.quadSaved = \{ was: quadWindow', None),
    ('Фаза 4.1 · память самоочищается сверкой окна',
     'calc2/static/calc2/86-workspace.js', r'quadSameWindow\(saved\.made', None),
    ('Фаза 4.2 · числа на осях считаются занятым местом',
     'calc2/static/calc2/30-curves.js', r'anchored\.push\(rec\)', None),
    ('Фаза 4.2 · подпись координаты ходит только поперёк оси',
     'calc2/static/calc2/30-curves.js', r"rec\.only = \(t\.getAttribute\('text-anchor'\)", None),
    ('Фаза 4.2 · сдвиг ограничен боковыми краями холста',
     'calc2/static/calc2/30-curves.js', r'left < box\.left \+ 2 \|\| right > box\.left \+ box\.width - 2', None),
    ('Фаза 4.3 · пустое поле не затирает прежнее значение',
     'calc2/static/calc2/82-input.js', r'const restorable = !isNum', None),
    ('Фаза 4.3 · Tab открывает правку в поле, куда привёл',
     'calc2/static/calc2/82-input.js', r"addEventListener\('focus', \(\) => \{ if \(!el\.classList\.contains\('editing'\)\) begin", None),
    ('Фаза 4.3 · до границы не доезжает нечисло',
     'calc2/static/calc2/88-params.js', r'if \(!isFinite\(parseFloat\(v\)\)\) return;', None),
    ('Фаза 4.4 · значение параметра выделяется целиком',
     'calc2/static/calc2/88-params.js', r'try \{ inp\.select\(\); \} catch', None),
    ('Фаза 4.5 · обрез имени кривой снят',
     'calc2/static/calc2/30-curves.js', None, r"nm\.length > 14"),
    ('Фаза 4.6 · проза образца уходит текстом',
     'calc2/static/calc2/82-input.js', r'function placeholderTex\(', None),
    ('Фаза 4.7 · настройки MathLive ставятся у экземпляра',
     'calc2/static/calc2/82-input.js', r'mf\.smartMode = false', None),
    ('Фаза 4.7 · и не передаются в конструктор',
     'calc2/static/calc2/82-input.js', None, r'new window\.MathfieldElement\(\{[^}]*smartMode'),
    ('Фаза 4.8 · одна дверь к KaTeX',
     'calc2/static/calc2/82-input.js', r'function katexInto\(', None),
    ('Фаза 4.8 · и сам приводитель записи',
     'calc2/static/calc2/82-input.js', r'function katexSafe\(', None),
    ('Фаза 4.9 · класс шкалы у полного плана',
     'calc2/static/calc2/70-scenes-math.js', r"\.attr\('y', oy \+ 7\)\.attr\('class', 'axis-num'\)", None),
    ('Фаза 4.9 · у панелей производства',
     'calc2/static/calc2/44-scenes-firm.js', r"\.attr\('class', 'axis-num'\)", None),
    ('Фаза 4.9 · у мини-графиков дискриминации',
     'calc2/static/calc2/42-scenes-mono.js', r"\.attr\('class', 'axis-num'\)", None),
    ('Фаза 4.9 · у панелей мировой цены',
     'calc2/static/calc2/54-scenes-ppf.js', r"\.attr\('class', 'axis-num'\)", None),
]

# Проверки, которые обязаны существовать в наборе регрессии.
TESTS = [
    ('деления не двигаются разведением', 'calc2/tests/calc2_math.mjs',
     r'Числа на осях не двигаются разведением подписей'),
    ('имя кривой целиком', 'calc2/tests/calc2_math.mjs', r'Имя кривой не обрезается многоточием'),
    ('образец и настройки поля', 'calc2/tests/calc2_math.mjs', r'Строка ввода: проза текстом'),
    ('правила katexSafe', 'calc2/tests/calc2_math.mjs', r'KaTeX: узкий пробел и кириллица'),
    ('Б34 пересчитан под запрет мыши', 'calc2/tests/calc2_math.mjs',
     r'в потолке подвижен только сам потолок'),
    ('Б8 пересчитан под подпись за осью', 'calc2/tests/calc2_math.mjs',
     r'anchor=east\[\^;\]\*xshift=-3pt'),
]

# Приборы сессии: заявлены — значит лежат на диске и разбираются.
PROBES = ['scripts/calc2_params_probe.js', 'scripts/calc2_nodrag_probe.js',
          'scripts/calc2_coordlabel_probe.js', 'scripts/calc2_bounds20_probe.js',
          'scripts/calc2_console_probe.js']

def main():
    bad = []
    print('── СЛЕД В КОДЕ ' + '─' * 45)
    for name, path, must, gone in CLAIMS:
        try:
            src = S(path)
        except OSError as e:
            bad.append(name + ' — файла нет: ' + path); print('✗ ' + name); continue
        ok = True
        if must and not re.search(must, src): ok = False
        if gone and re.search(gone, src): ok = False
        print(('✓ ' if ok else '✗ ') + name)
        if not ok: bad.append(name)

    print('\n── ПРОВЕРКИ В НАБОРЕ ' + '─' * 39)
    for name, path, pat in TESTS:
        ok = bool(re.search(pat, S(path)))
        print(('✓ ' if ok else '✗ ') + name)
        if not ok: bad.append('проверка: ' + name)

    print('\n── ПРИБОРЫ ' + '─' * 49)
    for p in PROBES:
        full = os.path.join(ROOT, p)
        ok = os.path.exists(full)
        if ok:
            ok = subprocess.call(['node', '--check', full],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
        print(('✓ ' if ok else '✗ ') + p)
        if not ok: bad.append('прибор: ' + p)

    print('\n' + ('ВСЁ ЗАЯВЛЕННОЕ ПОДТВЕРЖДАЕТСЯ ПАТЧЕМ'
                  if not bad else 'НЕ ПОДТВЕРДИЛОСЬ: ' + str(len(bad))))
    for b in bad: print('   · ' + b)
    return 1 if bad else 0

sys.exit(main())
