# -*- coding: utf-8 -*-
"""Пульс беты: «Всё ли нравится?» для вернувшегося (18.09.2026).

Ответ ложится в `Feedback` третьим видом (`Kind.PULSE`): оценка — в
`choices` (`['like']` или `['dislike']`), короткий текст — в `comment`.
Своя проверка, потому что правило окна обратной связи «хотя бы одна
галочка из вариантов экрана» к пульсу не подходит; правила `problem` и
`idea` (настроены 17.09) этот модуль не трогает.
"""

CHOICES = ('like', 'dislike')
COMMENT_MAX = 300


def validate(post):
    """(choices, comment) или строка ошибки для ответа 400."""
    chosen = post.getlist('choices')
    if len(chosen) != 1 or chosen[0] not in CHOICES:
        return 'Выберите: нравится или нет.'
    comment = (post.get('comment') or '').strip()
    if len(comment) > COMMENT_MAX:
        return 'Комментарий длиннее %d знаков.' % COMMENT_MAX
    return chosen, comment
