# -*- coding: utf-8 -*-
"""Безопасные автоисправления — только детерминированные и однозначные.

В базу ничего не пишется: исправление кладётся предложением (`proposed`,
`confidence: 1.0`, `auto: true`) в очередь; применяет его сессия проверки
вместе с решениями людей. Четыре вида:

* `currency` — валютный «$», который сайт принимает за формулу
  («5$ за штуку, а 10$») → «\\$». Кандидат — «$», к которому вплотную
  примыкает цифра; принимается, только если после правки KaTeX не видит
  валюты-формулы, ошибок и непарных «$» не прибавилось, а все прочие
  формулы поля остались теми же строками.
* `left_right` — формула с непарным `\\left`/`\\right` (ошибка KaTeX): у неё
  снимаются `\\left`/`\\right` при скобках (размер скобок, а не смысл);
  принимается, если формула после этого разбирается.
* `number_space` — два и больше пробела между цифрами → один.
* `html_entity` — мусорные сущности (`&amp;lt;`, `&lt;`, `&nbsp;`…) → символ.
"""
from __future__ import annotations

import html as htmlmod
import re

from problems.olympiad_contour import katex

KINDS = ('currency', 'left_right', 'number_space', 'html_entity')

# \u0442\u043e\u043b\u044c\u043a\u043e \u0433\u0440\u0443\u043f\u043f\u0430 \u0440\u0430\u0437\u0440\u044f\u0434\u043e\u0432 \u00ab1  000\u00bb: \u0440\u043e\u0432\u043d\u043e \u0442\u0440\u0438 \u0446\u0438\u0444\u0440\u044b \u043f\u043e\u0441\u043b\u0435. \u00ab100  2x\u00bb \u0432 \u0444\u043e\u0440\u043c\u0443\u043b\u0435 \u2014
# \u0441\u043b\u0435\u0434 \u043f\u0440\u043e\u043f\u0430\u0432\u0448\u0435\u0433\u043e \u0437\u043d\u0430\u043a\u0430 (\u043c\u0438\u043d\u0443\u0441\u0430, \u0441\u0442\u0440\u0435\u043b\u043a\u0438), \u0435\u0433\u043e \u0441\u0445\u043b\u043e\u043f\u044b\u0432\u0430\u043d\u0438\u0435 \u0441\u043f\u0440\u044f\u0442\u0430\u043b\u043e \u0431\u044b \u043f\u043e\u0442\u0435\u0440\u044e
_NUMBER_SPACE = re.compile(r'(?<![\d.,])(\d{1,3})[ \u00a0]{2,}(\d{3})(?!\d|[.,]\d)')
_NUMBER_ONLY = re.compile(r'[\d\s.,|+\-–—:;%()]*\d[\d\s.,|+\-–—:;%()]*')
_ENTITY = re.compile(r'&(?:amp;)*(?:lt|gt|quot|amp|nbsp|#\d{2,5});')
_LR = re.compile(r'\\(?:left|right)\s*(\.|\\[{}]|\\langle|\\rangle|\\lvert|\\rvert|\\\||[()\[\]|/])')


def fix_number_space(text):
    return _NUMBER_SPACE.sub(r'\1 \2', text)


def fix_html_entity(text):
    def one(m):
        s = m.group(0)
        prev = None
        while prev != s:
            prev, s = s, htmlmod.unescape(s)
        return s
    return _ENTITY.sub(one, text)


def currency_fix(text, res):
    """Экранировать разделители тех «формул», что разбор сайта счёл валютой.

    Формулы поля (`res['math']`, по порядку) ищутся в тексте по очереди; у
    валютных одиночный «$» в начале и в конце становится «\\$». Не нашли
    формулу на месте — правки нет.

    Правка только однозначная: в поле нет других поломок формул (непарный «$»,
    ошибка KaTeX, слова в формуле) — иначе «валюта» бывает следствием сбитой
    пары выше по тексту (29.10, #1530: экранировался разделитель настоящей
    формулы), и цифра примыкает к ОБОИМ «$» валютной пары («5$ … 10$»,
    «$10 … $15»)."""
    if res.get('unpaired') or res.get('errors') or res.get('text_in_math'):
        return None
    marks = [c[:60] for c in res.get('currency') or []]
    out, pos = [], 0
    for raw in res.get('math') or []:
        at = text.find(raw, pos)
        if at < 0:
            return None
        out.append(text[pos:at])
        if any(raw.startswith(m) for m in marks) and raw.startswith('$') and not raw.startswith('$$'):
            end = at + len(raw)
            open_digit = text[at - 1:at].isdigit() or raw[1:2].isdigit()
            close_digit = raw[-2:-1].isdigit() or text[end:end + 1].isdigit()
            if not (open_digit and close_digit):
                return None
            out.append('\\$' + raw[1:-1] + '\\$')
        else:
            out.append(raw)
        pos = at + len(raw)
    out.append(text[pos:])
    return ''.join(out)


def strip_left_right(tex):
    return _LR.sub(lambda m: '' if m.group(1) == '.' else m.group(1), tex)


def propose(texts, katex_check=katex.check_texts):
    """[текст] → [(новый текст или None, [виды])] — пакетом, с проверкой KaTeX."""
    before = katex_check(texts, full=True)
    stage = []
    for text, res in zip(texts, before):
        lr = {}
        for err in res.get('errors') or []:
            if '\\left' in err['tex'] or '\\right' in err['tex']:
                lr[err['tex']] = strip_left_right(err['tex'])
        cur = currency_fix(text, res) if res.get('currency') else None
        stage.append((text, lr, cur))
    # проверка: формулы после снятия \left/\right и поля после экранирования валюты
    probe = []
    for _text, lr, cur in stage:
        probe.extend(lr.values())
        if cur is not None:
            probe.append(cur)
    probed = iter(katex_check(probe, full=True) if probe else [])
    out = []
    for res, (text, lr, cur) in zip(before, stage):
        new, kinds = text, []
        good_lr = []
        for raw, fixed in lr.items():
            r = next(probed)
            if not r['errors'] and not r['unpaired'] and len(r.get('math') or []) == 1:
                good_lr.append((raw, fixed))
        if cur is not None:
            r = next(probed)
            marks = [c[:60] for c in res['currency']]
            others = [m for m in res.get('math') or [] if not any(m.startswith(c) for c in marks)]
            # другие «формулы» из одних чисел («$10 + $») — та же валюта, но сайт
            # её валютой не опознал: поле целиком — людям (vp-fingram-2024-final-11 №3)
            numeric = [m for m in others if _NUMBER_ONLY.fullmatch(m.strip('$'))]
            if (not r['currency'] and not numeric and len(r['errors']) <= len(res['errors'])
                    and r['unpaired'] <= res['unpaired'] and r.get('math') == others):
                new, kinds = cur, ['currency']
        for raw, fixed in good_lr:
            if raw in new:
                new = new.replace(raw, fixed)
                if 'left_right' not in kinds:
                    kinds.append('left_right')
        for kind, fn in (('number_space', fix_number_space), ('html_entity', fix_html_entity)):
            changed = fn(new)
            if changed != new:
                new, kinds = changed, kinds + [kind]
        out.append((new if kinds else None, kinds))
    return out
