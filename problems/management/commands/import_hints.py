"""Загрузка подсказок к задачам из JSONL — уровнями, по порядку.

Строка файла:

    {"problem_id": 29025, "hints": ["…", "…"], "generated_by_ai": true, "reviewed": false}

`hints` — список текстов в порядке показа (уровень 1, 2, …); `generated_by_ai`
и `reviewed` — флаги источника (по умолчанию false); подсказка «сгенерировано
ИИ, не проверено человеком» так и подписывается на экране.

⚠️ ПИШЕТ ТОЛЬКО ПОДСКАЗКИ (`Hint`). Условие, ответ и решение задачи команда
не читает и не меняет (ADR 0005). Задачи, у которых подсказки уже есть,
ПРОПУСКАЮТСЯ с отчётом — иначе второй прогон того же файла удваивал бы
подсказки. `--replace` заменяет существующие подсказки перечисленных задач
целиком; перед заменой старые уходят в снимок
`reports/hints/undo_<время>.jsonl` в том же формате (скормить с `--apply
--replace` = откатить).

По умолчанию — сухой прогон с числами; запись — только с `--apply`.
Кнопка «Подсказка 1 из N» на странице задачи появляется сама, как только
подсказки есть в базе (правило нуля).

    ./venv313/bin/python manage.py import_hints hints.jsonl
    ./venv313/bin/python manage.py import_hints hints.jsonl --apply
    ./venv313/bin/python manage.py import_hints hints.jsonl --apply --replace
"""
import json
import os
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.models import Hint, Problem

OUT_DIR = os.path.join('reports', 'hints')
PREVIEW = 20
HINT_MAX = 2000


def parse_line(raw):
    """Одна строка JSONL → (problem_id, тексты, флаги). Неверная — ValueError."""
    try:
        obj = json.loads(raw)
    except ValueError as exc:
        raise ValueError('не JSON: %s' % exc)
    if not isinstance(obj, dict):
        raise ValueError('ожидался объект')
    pk = obj.get('problem_id')
    if isinstance(pk, str) and pk.isdigit():
        pk = int(pk)
    if not isinstance(pk, int) or isinstance(pk, bool) or pk <= 0:
        raise ValueError('нет целого problem_id')
    hints = obj.get('hints')
    if not isinstance(hints, list) or not hints:
        raise ValueError('hints должен быть непустым списком строк')
    texts = []
    for text in hints:
        if not isinstance(text, str) or not text.strip():
            raise ValueError('hints должен быть непустым списком строк')
        if len(text) > HINT_MAX:
            raise ValueError('подсказка длиннее %d знаков' % HINT_MAX)
        texts.append(text.strip())
    flags = {}
    for key in ('generated_by_ai', 'reviewed'):
        value = obj.get(key, False)
        if not isinstance(value, bool):
            raise ValueError('%s должен быть true или false' % key)
        flags[key] = value
    return pk, texts, flags


class Command(BaseCommand):
    help = ('Загружает подсказки к задачам из JSONL. Без --apply только считает; '
            'задачи с подсказками пропускаются, если нет --replace.')

    def add_arguments(self, parser):
        parser.add_argument('path', help='файл JSONL')
        parser.add_argument('--apply', action='store_true',
                            help='записать в базу (по умолчанию сухой прогон)')
        parser.add_argument('--replace', action='store_true',
                            help='заменить существующие подсказки перечисленных задач')
        parser.add_argument('--snapshot-dir', default=OUT_DIR,
                            help='куда класть снимок заменённых подсказок')

    def handle(self, *args, **opts):
        say = self.stdout.write
        path = opts['path']
        if not os.path.isfile(path):
            raise CommandError('нет файла %s' % path)
        with open(path, encoding='utf-8') as fh:
            lines = fh.read().splitlines()

        rows, errors, n_lines, duplicates = {}, [], 0, 0
        for number, raw in enumerate(lines, 1):
            if not raw.strip():
                continue
            n_lines += 1
            try:
                pk, texts, flags = parse_line(raw)
            except ValueError as exc:
                errors.append((number, str(exc)))
                continue
            if pk in rows:
                duplicates += 1          # поздняя строка побеждает
            rows[pk] = (texts, flags)

        found = set(Problem.objects.filter(pk__in=list(rows)).values_list('pk', flat=True))
        missing = [pk for pk in rows if pk not in found]
        existing = {}
        for hint in Hint.objects.filter(problem_id__in=list(found)).order_by('order', 'pk'):
            existing.setdefault(hint.problem_id, []).append(hint)

        to_create, skipped, to_replace = [], [], []
        for pk, (texts, flags) in rows.items():
            if pk not in found:
                continue
            if existing.get(pk):
                if opts['replace']:
                    to_replace.append(pk)
                else:
                    skipped.append(pk)
                    continue
            to_create.append((pk, texts, flags))
        n_hints = sum(len(texts) for _pk, texts, _flags in to_create)

        say('Строк: %d · разобрано: %d · с ошибками: %d · повторов id: %d'
            % (n_lines, len(rows), len(errors), duplicates))
        say('Задач найдено: %d · не найдено id: %d' % (len(found), len(missing)))
        say('Подсказок будет создано: %d у %d задач · задач с уже существующими '
            'подсказками: %d (%s)'
            % (n_hints, len(to_create), len(skipped) + len(to_replace),
               'заменяются' if opts['replace'] else 'пропущены'))
        for number, reason in errors[:PREVIEW]:
            say('  ошибка в строке %d: %s' % (number, reason))
        if missing:
            say('  не найдено id: %s%s' % (', '.join(str(pk) for pk in missing[:PREVIEW]),
                                           ' …' if len(missing) > PREVIEW else ''))
        if skipped:
            say('  пропущены (уже есть подсказки, нужен --replace): %s%s'
                % (', '.join(str(pk) for pk in skipped[:PREVIEW]),
                   ' …' if len(skipped) > PREVIEW else ''))
        if to_create:
            say('Предпросмотр (первые %d из %d):' % (min(PREVIEW, len(to_create)), len(to_create)))
            for pk, texts, flags in to_create[:PREVIEW]:
                say('  #%d  %d подск.%s%s  1) %s' % (
                    pk, len(texts), ' ИИ' if flags['generated_by_ai'] else '',
                    ' проверено' if flags['reviewed'] else '', texts[0][:70]))

        if not opts['apply']:
            say('Сухой прогон: в базу ничего не записано. Для записи добавьте --apply.')
            return
        if not to_create:
            say('Записывать нечего.')
            return

        snapshot = ''
        if to_replace:
            # ⚠️ СНИМОК ЗАМЕНЯЕМЫХ ПОДСКАЗОК ДО ЗАПИСИ — обратимость.
            os.makedirs(opts['snapshot_dir'], exist_ok=True)
            snapshot = os.path.join(opts['snapshot_dir'],
                                    'undo_%s.jsonl' % time.strftime('%Y%m%d_%H%M%S'))
            with open(snapshot, 'w', encoding='utf-8') as fh:
                for pk in to_replace:
                    old = existing[pk]
                    fh.write(json.dumps({
                        'problem_id': pk, 'hints': [h.text for h in old],
                        'generated_by_ai': all(h.generated_by_ai for h in old),
                        'reviewed': all(h.reviewed for h in old),
                    }, ensure_ascii=False) + '\n')

        created = 0
        with transaction.atomic():
            if to_replace:
                Hint.objects.filter(problem_id__in=to_replace).delete()
            for pk, texts, flags in to_create:
                Hint.objects.bulk_create([
                    Hint(problem_id=pk, order=order, text=text,
                         generated_by_ai=flags['generated_by_ai'],
                         reviewed=flags['reviewed'])
                    for order, text in enumerate(texts, 1)])
                created += len(texts)

        say('Записано: %d подсказок у %d задач.%s' % (
            created, len(to_create),
            (' Снимок заменённых: %s' % snapshot) if snapshot else ''))
        say('Повторный сухой прогон того же файла без --replace пропустит все эти задачи.')
