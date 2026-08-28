# -*- coding: utf-8 -*-
"""Разовый откат content_format для 15 задач, которых блокирует render_preflight_v2.

Карточка Notion «15 задач уже стоят на content_format=markdown, но новый
шлюз их блокирует — показываются сломанными сейчас»
(3cab11c9-2bc1-81d0-ade2-f49d13029441). Источник: фикс-пак МатЭк
(apply_matek_fixed), Фаза A перевода render_legacy_sources на
render_preflight_v2 (fa93497) нашла их попутно и НЕ тронула — только
предупредила. render_legacy_sources и дальше не снимает markdown ни у
кого: снятие флага у уже стоящих задач — отдельное решение владельца,
которое эта команда и исполняет.

Владелец решил: вернуть ровно этих 15 задач на content_format='plain'
(как было раньше — прежнее поведение показа), не трогая statement/
answer/solution/human_review. Починка текста, если понадобится, —
отдельная задача.

    manage.py revert_gate_v2_blocked_markdown            # только показать
    manage.py revert_gate_v2_blocked_markdown --apply     # записать
"""
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.models import Problem

# Список из карточки Notion — ровно эти 15 id, дословно.
TARGET_IDS = [26603, 26632, 27371, 27422, 27496, 27509, 28772, 28775,
             28791, 28827, 28828, 28935, 29146, 29300, 29789]

OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_scaleup')
BACKUP_PATH = os.path.join(OUT_DIR, 'gate_v2_blocked_revert_backup.json')


class Command(BaseCommand):
    help = ('Откатывает content_format с markdown на plain ровно у 15 задач '
            'из карточки Notion (шлюз render_preflight_v2 их блокирует). '
            'Без --apply только показывает.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='записать в базу')

    def handle(self, *args, **opts):
        say = self.stdout.write

        found = {p.id: p for p in Problem.objects.filter(id__in=TARGET_IDS)}
        missing = sorted(set(TARGET_IDS) - set(found))
        if missing:
            raise CommandError(
                'Не найдены в базе {} из 15 целевых id: {}. '
                'Ничего не изменено.'.format(len(missing), missing))

        to_revert = [p for p in found.values()
                    if p.content_format == Problem.ContentFormat.MARKDOWN]
        already_plain = len(found) - len(to_revert)

        say('Целевых id: {}'.format(len(TARGET_IDS)))
        say('  сейчас markdown (откатим): {}'.format(len(to_revert)))
        say('  уже plain (пропустим): {}'.format(already_plain))

        if not opts['apply']:
            say('Это проба. Повторите с --apply, чтобы записать.')
            return

        if len(to_revert) != len(TARGET_IDS):
            raise CommandError(
                'ожидалось изменить ровно {} задач (все целевые сейчас на '
                'markdown), фактически подходит {}. Состояние базы разошлось '
                'с карточкой Notion — проверьте вручную, ничего не '
                'записано.'.format(len(TARGET_IDS), len(to_revert)))

        os.makedirs(OUT_DIR, exist_ok=True)
        backup = [{
            'problem_id': p.id,
            'content_format_before': p.content_format,
            'human_review': p.human_review,
        } for p in sorted(to_revert, key=lambda p: p.id)]
        with open(BACKUP_PATH, 'w', encoding='utf-8') as f:
            json.dump({
                'note': ('Снимок ДО отката content_format markdown->plain '
                        'для 15 задач, заблокированных render_preflight_v2. '
                        'Для отката назад — проставить content_format_before.'),
                'source': 'Notion 3cab11c9-2bc1-81d0-ade2-f49d13029441',
                'count': len(backup),
                'problems': backup,
            }, f, ensure_ascii=False, indent=1)
        say('Бэкап: {} ({} задач)'.format(BACKUP_PATH, len(backup)))

        ids = [p.id for p in to_revert]
        with transaction.atomic():
            changed = Problem.objects.filter(
                id__in=ids, content_format=Problem.ContentFormat.MARKDOWN
            ).update(content_format=Problem.ContentFormat.PLAIN)
            if changed != len(TARGET_IDS):
                raise CommandError(
                    'записано бы {} строк вместо ожидаемых {} — откат '
                    'прерван, ничего не записано.'.format(
                        changed, len(TARGET_IDS)))

        say('ЗАПИСАНО: content_format markdown -> plain у {} задач.'.format(
            changed))
