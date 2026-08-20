# -*- coding: utf-8 -*-
"""СВЕРКА ЖУРНАЛА СЕССИИ 21.08 С ФАКТИЧЕСКИМ ПАТЧЕМ.

Тот же смысл, что у сверки 20.08: отчёт сессии — это заявление, и у каждой
заявленной правки обязан быть след в ФАЙЛАХ, а не в тексте отчёта. Пропущенное
должно всплыть до того, как я отчитаюсь.

Запуск: ./venv/bin/python scripts/calc2_session21_audit.py
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = lambda p: open(os.path.join(ROOT, p), encoding='utf8').read()

# (пункт, файл, что обязано быть, что обязано ИСЧЕЗНУТЬ)
CLAIMS = [
    # ── Фаза 1 · окно идёт за формулой, а не за буквой ────────────────
    ('Ф1 · признак «перерисовка только из-за буквы» заведён один раз',
     'calc2/static/calc2/52-modes.js', r'function redrawKeepingWindow\(', None),
    ('Ф1 · авто-подгонка осей его слушает',
     'calc2/static/calc2/52-modes.js', r'if \(_paramOnlyRedraw\) \{ _wantRangeAnim = false; return; \}', None),
    ('Ф1 · то же у масштаба сцен торговли',
     'calc2/static/calc2/52-modes.js', r'applyTradeRanges[\s\S]{0,200}_paramOnlyRedraw', None),
    ('Ф1 · ползунок буквы перерисовывает, не трогая окно',
     'calc2/static/calc2/60-overlays.js', r'redrawKeepingWindow\(\);\s+// окно подбирается под формулу', None),

    # ── Фаза 2 · заголовок карточки не врёт ───────────────────────────
    ('Ф2 · реестр карточек ввода заведён',
     'calc2/static/calc2/86-workspace.js', r'const INPUT_CARDS = \[', None),
    ('Ф2 · имя достаётся только карточке из реестра',
     'calc2/static/calc2/86-workspace.js', r'visible\.find\(s => INPUT_CARDS\.indexOf\(s\.id\) >= 0\)', None),
    ('Ф2 · ярче та карточка, где лежит живое поле формулы',
     'calc2/static/calc2/86-workspace.js', r'function cardWithFormula\(', None),
    ('Ф2 · прежнее «первая видимая получает имя» снято',
     'calc2/static/calc2/86-workspace.js', None, r'all\.forEach\(s => \{ if \(!first && s\.style\.display'),

    # ── Фаза 3.1 · полоса захвата во всех сценах с кривыми ────────────
    ('Ф3.1 · кривые макромоделей отдаются общему списку',
     'calc2/static/calc2/60-overlays.js', r'function macroSnapTargets\(', None),
    ('Ф3.1 · кривые потребителя тоже',
     'calc2/static/calc2/60-overlays.js', r'function consumerSnapTargets\(', None),
    ('Ф3.1 · и кривая Лоренца',
     'calc2/static/calc2/60-overlays.js', r'function ineqSnapTargets\(', None),
    ('Ф3.1 · три режима подключены к snapTargets',
     'calc2/static/calc2/60-overlays.js',
     r"mode === 'macro'[\s\S]{0,200}mode === 'consumer'[\s\S]{0,200}mode === 'inequality'", None),

    # ── Фаза 3.2 · цель двойного щелчка ──────────────────────────────
    ('Ф3.2 · цель переименования не меньше 24 px',
     'calc2/static/calc2/70-scenes-math.js', r'const RENAME_HIT_PX = 24', None),
    ('Ф3.2 · прямоугольник стоит ПОД подписью',
     'calc2/static/calc2/70-scenes-math.js', r"insert\('rect', \(\) => node\)", None),
    ('Ф3.2 · в выгрузку он не идёт',
     'calc2/static/calc2/70-scenes-math.js', r"data-rename-hit", None),
    ('Ф3.2 · щелчок по имени кривой взводит саму кривую',
     'calc2/static/calc2/30-curves.js', r'\}, curveShortName\(o\.curve\)\);', None),

    # ── Фаза 3.3 · имя кривой и её формула — разные поля ──────────────
    ('Ф3.3 · теневого поля с формулой у кривой больше нет',
     'calc2/static/calc2/80-ui.js', None, r'name: expr|curve\.name = expr'),
    ('Ф3.3 · и его не заводит строка «Построения графиков»',
     'calc2/static/calc2/60-overlays.js', None, r'name: txt,'),
    ('Ф3.3 · подсказка сдвига называет кривую по имени',
     'calc2/static/calc2/88-params.js', r"'Сдвиг кривой ' \+ curveShortName\(c\)", None),

    # ── Фаза 3.4 · мёртвый код перетаскивания ────────────────────────
    ('Ф3.4 · механизма перетаскивания в коде нет',
     'calc2/static/calc2/30-curves.js', None,
     r'const CURVE_MOUSE_DRAG|function curveDraggable\(|function attachDrag\('),
    ('Ф3.4 · признак «вписал человек» тоже убран',
     'calc2/static/calc2/80-ui.js', None, r'curve\.handTyped = true'),
    ('Ф3.4 · ползунки сдвига НЕ тронуты',
     'calc2/static/calc2/30-curves.js', r'function setCurveFreeTerm\(', None),
    ('Ф3.4 · и по-прежнему зовутся из правой панели',
     'calc2/static/calc2/88-params.js', r'setCurveFreeTerm\(cur, parseFloat\(sl\.value\)\)', None),

    # ── Фаза 3.5 · пунктир к оси и задвоенное число ───────────────────
    ('Ф3.5 · число точки на мини-панели помечено своим классом',
     'calc2/static/calc2/42-scenes-mono.js', r"\.attr\('class', 'coord-num'\)", None),
    ('Ф3.5 · одно место — одно число',
     'calc2/static/calc2/20-plane.js', r'function coordAlreadyAt\(', None),
    ('Ф3.5 · проверка стоит у обеих осей',
     'calc2/static/calc2/20-plane.js',
     r'coordAlreadyAt\(px, true[\s\S]{0,2500}coordAlreadyAt\(py, false', None),
    ('Ф3.5 · точка эластичности на предложении подписывает обе проекции',
     'calc2/static/calc2/40-scenes-market.js',
     r"axisValueX\(g, px, oy, fmt\(e\.q\), ''\);\s*\n\s*axisValueY\(g, ox, py, fmt\(e\.p\), ''\);", None),
]

# Приборы сессии: заявлены — значит лежат на диске и разбираются.
PROBES = ['scripts/calc2_repro_probe.js', 'scripts/calc2_paramlive_probe.js',
          'scripts/calc2_hitband_probe.js', 'scripts/calc2_labelhit_probe.js',
          'scripts/calc2_dashaxis_probe.js']


def main():
    bad = []
    print('── СЛЕД В КОДЕ ' + '─' * 45)
    for name, path, must, gone in CLAIMS:
        try:
            src = S(path)
        except OSError:
            bad.append(name + ' — файла нет: ' + path); print('✗ ' + name); continue
        ok = True
        if must and not re.search(must, src): ok = False
        if gone and re.search(gone, src): ok = False
        print(('✓ ' if ok else '✗ ') + name)
        if not ok: bad.append(name)

    print('\n── ПРИБОРЫ ' + '─' * 49)
    for p in PROBES:
        full = os.path.join(ROOT, p)
        ok = os.path.exists(full)
        print(('✓ ' if ok else '✗ ') + p)
        if not ok: bad.append('прибор: ' + p)

    print()
    if bad:
        print('НЕ ПОДТВЕРДИЛОСЬ: %d' % len(bad))
        for b in bad: print('   · ' + b)
        sys.exit(1)
    print('ВСЁ ЗАЯВЛЕННОЕ ПОДТВЕРЖДАЕТСЯ ПАТЧЕМ')


main()
