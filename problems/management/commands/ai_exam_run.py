# -*- coding: utf-8 -*-
"""ai_exam_run — прогон экзамена ИИ: «Решатель» и «Утечка».

В базу не пишет ни строки (ни ChatTurn, ни AiUsageLog): расход — в файлах
прогона `<папка экзамена>/runs/<дата>_<suite>_<label>/`. Ключ поставщика —
только из окружения; его значение не печатается никогда.

    manage.py ai_exam_run --suite both --set smoke --limit 10
        только план (вызовов, оценка денег): без --yes реальный поставщик
        не вызывается
    manage.py ai_exam_run --suite both --set smoke --limit 10 --yes --max-usd 1.00 --label smoke
    manage.py ai_exam_run --suite solve --set safe --open-safe "ОТКРЫВАЮ СЕЙФ" --yes

Наборы: work (exam.jsonl, после финала), draft (exam_draft.jsonl), smoke
(кандидаты с ключом exact вне сейфа и резерва — ключи НЕ проверены людьми),
safe (только с фразой, каждое открытие — строка safe_log.jsonl).
Правила — docs/AI_EXAM.md, «Прогон».
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog import chat
from problems.ai import providers
from problems.ai_exam import runner
from problems.management.commands.ai_exam_candidates import DEFAULT_DIR


class Command(BaseCommand):
    help = 'Прогон экзамена ИИ v0 (Решатель / Утечка). Без --yes — только план.'

    def add_arguments(self, parser):
        parser.add_argument('--suite', choices=runner.SUITES, required=True)
        parser.add_argument('--set', dest='set_name', choices=runner.SETS, required=True)
        parser.add_argument('--limit', type=int, default=None, help='первые N задач набора')
        parser.add_argument('--provider', default=None,
                            help='поставщик; по умолчанию — как у чата (CATALOG_CHAT_PROVIDER)')
        parser.add_argument('--model', default=None,
                            help='модель; по умолчанию — как у чата (CATALOG_CHAT_MODEL)')
        parser.add_argument('--workers', type=int, default=4)
        parser.add_argument('--max-usd', type=float, default=1.0,
                            help='дошли до суммы — новые вызовы не начинаются')
        parser.add_argument('--timeout', type=int, default=None,
                            help='секунд на вызов; по умолчанию — Решатель %d, Утечка как '
                                 'у чата на сайте' % runner.solve.TIMEOUT_SECONDS)
        parser.add_argument('--label', default='')
        parser.add_argument('--yes', action='store_true',
                            help='разрешить платные вызовы реального поставщика')
        parser.add_argument('--open-safe', default='', help='фраза открытия сейфа')
        parser.add_argument('--dir', default=DEFAULT_DIR)

    def handle(self, *args, **opts):
        try:
            provider = (providers.get_provider(opts['provider']) if opts['provider']
                        else chat.chat_provider())
        except KeyError as exc:
            raise CommandError(str(exc))
        model = opts['model'] or getattr(settings, 'CATALOG_CHAT_MODEL', '') or None
        self.stdout.write('ключ поставщика %s: %s' % (
            provider.name, 'задан' if provider.is_available() else 'не задан'))
        if opts['set_name'] == 'smoke':
            self.stdout.write(self.style.WARNING('⚠️ %s' % runner.SMOKE_NOTE.upper()))
        try:
            runner.run(opts['dir'], opts['suite'], opts['set_name'], provider=provider,
                       model=model, limit=opts['limit'], workers=opts['workers'],
                       max_usd=opts['max_usd'], label=opts['label'], yes=opts['yes'],
                       phrase=opts['open_safe'], timeout=opts['timeout'],
                       write=self.stdout.write)
        except runner.RunRefused as exc:
            raise CommandError(str(exc))
