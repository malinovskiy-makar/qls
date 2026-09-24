# -*- coding: utf-8 -*-
"""`chat_export` — журнал чата на странице задачи в JSONL, по разговорам.

Решение владельца 15.09.2026: цель беты — понять, подходит ли модель ученикам
(почерк, плохие фото, графики). Одна строка файла — один разговор (`thread`):
реплики по времени с режимом, расшифровкой фото, ответом, токенами, ценой и
ошибкой. Реплика без номера разговора идёт отдельной строкой.

⚠️ ИЗ ПРОФИЛЯ — ТОЛЬКО НОМЕР ПОЛЬЗОВАТЕЛЯ, без имени и почты: разбору хватает
«тот же ли это ученик». Сам файл решения не выгружается — его открывают в
админке, в выгрузке только тип и число картинок.

Команда ТОЛЬКО ЧИТАЕТ базу.

Запуск:
    manage.py chat_export --since 2026-09-15 --out reports/chat_20260915.jsonl
    manage.py chat_export --since 2026-09-15 --until 2026-09-30 --out chat.jsonl
"""
import json
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from problems.models_platform import ChatTurn


def _day(value):
    try:
        return timezone.make_aware(datetime.strptime(value, '%Y-%m-%d'))
    except ValueError:
        raise CommandError('Дата — ГГГГ-ММ-ДД, получено: %r' % value)


class Command(BaseCommand):
    help = 'Журнал чата на странице задачи в JSONL по разговорам. Только читает.'

    def add_arguments(self, parser):
        parser.add_argument('--since', required=True, help='С какой даты, ГГГГ-ММ-ДД.')
        parser.add_argument('--until', default='',
                            help='По какую дату ВКЛЮЧИТЕЛЬНО, ГГГГ-ММ-ДД.')
        parser.add_argument('--out', required=True, help='Файл JSONL.')

    def handle(self, *args, **options):
        qs = (ChatTurn.objects.filter(created_at__gte=_day(options['since']))
              .select_related('attachment').order_by('created_at', 'pk'))
        if options['until']:
            qs = qs.filter(created_at__lt=_day(options['until']) + timedelta(days=1))
        threads = {}
        for turn in qs.iterator(chunk_size=500):
            key = str(turn.thread) if turn.thread else 'turn-%d' % turn.pk
            entry = threads.setdefault(key, {
                'thread': str(turn.thread) if turn.thread else None,
                'user_id': turn.user_id, 'problem_id': turn.problem_id, 'turns': []})
            attachment = turn.attachment
            entry['turns'].append({
                'id': turn.pk,
                'created_at': turn.created_at.isoformat(),
                'mode': turn.mode,
                'user_text': turn.user_text,
                'quote': turn.quote,
                'quote_source': turn.quote_source,
                'attachment': ({'id': attachment.pk, 'mime': attachment.mime,
                                'pages': attachment.pages} if attachment else None),
                'vision_text': turn.vision_text,
                'vision_input_tokens': turn.vision_input_tokens,
                'vision_output_tokens': turn.vision_output_tokens,
                'reply': turn.reply,
                'provider': turn.provider,
                'model': turn.model,
                'input_tokens': turn.input_tokens,
                'output_tokens': turn.output_tokens,
                'cost_usd': str(turn.cost_usd),
                'latency_ms': turn.latency_ms,
                'error': turn.error,
            })
        with open(options['out'], 'w', encoding='utf-8') as handle:
            for entry in threads.values():
                handle.write(json.dumps(entry, ensure_ascii=False) + '\n')
        self.stdout.write('Разговоров %d, реплик %d: %s' % (
            len(threads), sum(len(entry['turns']) for entry in threads.values()),
            options['out']))
