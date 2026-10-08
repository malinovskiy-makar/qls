# -*- coding: utf-8 -*-
"""`ai_beta_dialogs` — разговоры чата беты: dialogs.jsonl и читалка reader.html.

Строка файла — разговор: номер, номер пользователя, сотрудник ли, задача и
её темы, реплики по времени (режим, текст ученика, цитата, файлы, расшифровка
фото, ответ, ошибка, время ответа, цена). Читалка лежит рядом с папкой
`media/` (из неё — фото по относительному пути) и открывается с file://.
Устройство — `problems/ai_beta/dialogs.py`, правила — docs/AI_BETA.md.

Команда ТОЛЬКО ЧИТАЕТ базу. Запускается на копии боя:
    DATABASE_URL=postgres://…/weco_beta_20261007 manage.py ai_beta_dialogs \\
        --settings=config.settings_test_pg --out C:/Users/…/beta_20261007

⚠️ В файлах — тексты учеников. Пишутся только в папку вне репозитория;
сама команда печатает лишь счётчики.
"""
import json
import os

from django.core.management.base import BaseCommand, CommandError

from problems.ai_beta import metrics as m
from problems.ai_beta.dialogs import collect_threads, reader_html, statement_html
from problems.management.commands.ai_beta_report import TEAM_FILE, _day, _window

DIALOGS = 'dialogs.jsonl'
READER = 'reader.html'


class Command(BaseCommand):
    help = 'Разговоры чата беты: dialogs.jsonl и reader.html. Только читает.'

    def add_arguments(self, parser):
        parser.add_argument('--out', required=True,
                            help='Папка вне репозитория; рядом должна лежать media/chat/.')
        parser.add_argument('--since', default='', help='С какой даты, ГГГГ-ММ-ДД (МСК).')
        parser.add_argument('--until', default='', help='По какую дату ВКЛЮЧИТЕЛЬНО (МСК).')
        parser.add_argument('--team-file', default='',
                            help='Номера команды (по умолчанию <out>/team_user_ids.txt, если есть).')

    def handle(self, *args, **options):
        from problems.models import Problem, User
        from problems.models_platform import ChatTurn

        out = options['out']
        os.makedirs(out, exist_ok=True)
        team_file = options['team_file'] or os.path.join(out, TEAM_FILE)
        team = set()
        if os.path.exists(team_file):
            with open(team_file, encoding='utf-8') as handle:
                team = m.read_team_ids(handle)
        elif options['team_file']:
            raise CommandError('Нет файла команды: %s' % team_file)
        staff = m.staff_ids(User.objects.values('id', 'is_staff', 'is_superuser'), team)

        turns = _window(ChatTurn.objects.all(), 'created_at',
                        _day(options['since']) if options['since'] else None,
                        _day(options['until'], end=True) if options['until'] else None)
        turns = (turns.select_related('attachment').prefetch_related('attachments')
                 .order_by('created_at', 'pk'))
        problem_ids = set(turns.exclude(problem=None).values_list('problem_id', flat=True))
        topics = {}
        for pid, name in (Problem.topics.through.objects.filter(problem_id__in=problem_ids)
                          .values_list('problem_id', 'topic__name')):
            topics.setdefault(pid, []).append(name)
        threads = collect_threads(turns, staff, topics)
        statements = {p.pk: statement_html(p) for p in
                      Problem.objects.filter(pk__in=problem_ids).prefetch_related('parts')}

        with open(os.path.join(out, DIALOGS), 'w', encoding='utf-8') as handle:
            for entry in threads:
                handle.write(json.dumps(entry, ensure_ascii=False) + '\n')
        with open(os.path.join(out, READER), 'w', encoding='utf-8') as handle:
            handle.write(reader_html(threads, statements))
        files = [f for t in threads for turn in t['turns'] for f in turn['files']]
        missing = sum(1 for f in files for p in [f['path']] + f['pages']
                      if not os.path.exists(os.path.join(out, 'media', p)))
        self.stdout.write('Разговоров %d, реплик %d, файлов %d (нет на диске: %d). '
                          'Файлы: %s, %s' % (
                              len(threads), sum(len(t['turns']) for t in threads),
                              len(files), missing, DIALOGS, READER))
