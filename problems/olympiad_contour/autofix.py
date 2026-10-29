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

_NUMBER_SPACE = re.compile(r'(?<=\d)[ \u00a0]{2,}(?=\d)')
_ENTITY = re.compile(r'&(?:amp;)*(?:lt|gt|quot|amp|nbsp|#\d{2,5});')
_LR = re.compile(r'\\(?:left|right)\s*(\.|\\[{}]|\\langle|\\rangle|\\lvert|\\rvert|\\\||[()\[\]|/])')


def fix_number_space(text):
    return _NUMBER_SPACE.sub(' ', text)


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
    формулу на месте — правки нет."""
    marks = [c[:60] for c in res.get('currency') or []]
    out, pos = [], 0
    for raw in res.get('math') or []:
        at = text.find(raw, pos)
        if at < 0:
            return None
        out.append(text[pos:at])
        if any(raw.startswith(m) for m in marks) and raw.startswith('$') and not raw.startswith('$$'):
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
            if (not r['currency'] and len(r['errors']) <= len(res['errors'])
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
