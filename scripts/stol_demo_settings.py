"""Настройки демо-сервера «Стола» для снимков и видео (дневная сессия 18.09.2026).

Локально ключей ИИ нет, и панель помощи без них рисуется без разговора и без
проверки решения (правило нуля) — снимать нечего. Здесь чат и проверка идут
через подставного поставщика `fake` (`problems/ai/providers.py`), а его ответ
собирается по запросу: реплика чата — текст с формулами, проверка решения —
разбор по шагам. В сеть ничего не уходит.

Запуск: `manage.py runserver 8611 --settings=scripts.stol_demo_settings`
(конфигурация `stol-demo` в `.claude/launch.json`). Только для снимков.
"""
import json

from config.settings import *  # noqa: F401,F403 — демо поверх обычных настроек

AI_PROVIDER = 'fake'
CATALOG_CHAT_PROVIDER = 'fake'

CHAT_REPLY = (
    'Начните с ограничения участия: покупатель согласится на тариф, только если его '
    'излишек не отрицателен.\n\n'
    '**План:**\n'
    '- выразите излишек покупателя при покупке $Q > k$ единиц;\n'
    '- приравняйте его к нулю и найдите максимальную цену $p_1$.\n\n'
    '$$CS = \\int_0^{k} (20 - Q)\\,dQ - p_1 k$$\n\n'
    'Дальше подставьте $k$ и проверьте знак.'
)
CHECK_REPLY = {
    'score': 6, 'verdict': 'partial', 'first_error_step': 2, 'confidence': 'medium',
    'needs_human': False, 'summary': 'Идея верна, во втором шаге потерян множитель.',
    'steps': [
        {'n': 1, 'title': 'Ограничение участия', 'verdict': 'ok', 'comment': 'Записано верно.'},
        {'n': 2, 'title': 'Максимальная цена', 'verdict': 'bad', 'comment': 'Потерян множитель $k$.'},
    ],
}


def AI_FAKE_REPLY(system_blocks, user_text):  # noqa: N802 — имя настройки
    if 'ВОПРОС УЧЕНИКА:' in user_text:
        return json.dumps({'reply': CHAT_REPLY}, ensure_ascii=False)
    return json.dumps(CHECK_REPLY, ensure_ascii=False)
