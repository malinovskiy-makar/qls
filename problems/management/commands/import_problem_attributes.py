"""Загрузка разметки характера и особенностей задач из JSONL.

Строка файла:

    {"id": 29025, "character": "quant", "features": ["graph"]}

`character` — «qual», «quant» или «» (снять); `features` — список из
«graph», «table», «proof» (пустой список — снять). Поле, которого в строке
нет, не трогается. Ключи характера — `catalog.filters.CHARACTERS`; ключи особенностей —
ВИТРИНЫ (`problems/enrich/features.py: CATALOG_VIEW_LABELS`), а не фильтра.

⚠️ ПИШЕТ ТОЛЬКО ДВА СВОИХ ПОЛЯ. `statement`, `answer`, `solution` и всё
остальное команда не читает и не меняет (ADR 0005): запись идёт
`bulk_update` с явным списком полей. Эмбеддинги пересчитывать не нужно —
текст задач не менялся.

По умолчанию — сухой прогон с числами и предпросмотром; запись — только с
`--apply`. Перед записью старые значения изменяемых задач уходят в снимок
`reports/problem_attributes/undo_<время>.jsonl` в том же формате: скормить
его команде с `--apply` — значит откатить. Повторный сухой прогон после
записи обязан дать ноль изменений (идемпотентность).

Поля появились заранее (правило нуля, решение владельца 04.09.2026): как
только владелец загрузит файл, группы «Характер задачи» и «Особенности» в
фильтрах и облачка на странице задачи включатся сами.

    ./venv313/bin/python manage.py import_problem_attributes attrs.jsonl
    ./venv313/bin/python manage.py import_problem_attributes attrs.jsonl --apply
"""
import json
import os
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.filters import CHARACTERS
from problems.enrich.features import CATALOG_VIEW_LABELS
from problems.models import Problem

OUT_DIR = os.path.join('reports', 'problem_attributes')
CHARACTER_KEYS = ('',) + tuple(key for key, _label in CHARACTERS)
# ⚠️ КЛЮЧИ ВИТРИНЫ, А НЕ ФИЛЬТРА (13.09.2026). Команда пишет
# `Problem.features` — витрину из трёх ключей; фильтр каталога с того же дня
# спрашивает СВЯЗЬ `ProblemFeature` и знает все двенадцать особенностей
# (ADR 0101). Читать список у фильтра значило бы ждать во входном файле
# имена особенностей, а писать в поле, которое их не хранит.
FEATURE_KEYS = tuple(CATALOG_VIEW_LABELS)
BATCH = 500
PREVIEW = 20


def parse_line(raw):
    """Одна строка JSONL → (id, что менять). Неверная строка — ValueError."""
    try:
        obj = json.loads(raw)
    except ValueError as exc:
        raise ValueError('не JSON: %s' % exc)
    if not isinstance(obj, dict):
        raise ValueError('ожидался объект')
    pk = obj.get('id')
    if isinstance(pk, str) and pk.isdigit():
        pk = int(pk)
    if not isinstance(pk, int) or isinstance(pk, bool) or pk <= 0:
        raise ValueError('нет целого id')
    updates = {}
    if 'character' in obj:
        value = obj['character']
        if value is None:
            value = ''
        if value not in CHARACTER_KEYS:
            raise ValueError('неизвестный character %r (ждём %s)'
                             % (value, ', '.join(repr(k) for k in CHARACTER_KEYS)))
        updates['character'] = value
    if 'features' in obj:
        value = obj['features']
        if value is None:
            value = []
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError('features должен быть списком строк')
        unknown = sorted(set(value) - set(FEATURE_KEYS))
        if unknown:
            raise ValueError('неизвестные features %s (ждём %s)'
                             % (', '.join(unknown), ', '.join(FEATURE_KEYS)))
        # Канонический порядок и без повторов — иначе второй прогон того же
        # файла считал бы перестановку ключей изменением.
        updates['features'] = [key for key in FEATURE_KEYS if key in value]
    if not updates:
        raise ValueError('нет ни character, ни features')
    return pk, updates


class Command(BaseCommand):
    help = ('Загружает характер и особенности задач из JSONL. '
            'Без --apply только считает и показывает предпросмотр.')

    def add_arguments(self, parser):
        parser.add_argument('path', help='файл JSONL')
        parser.add_argument('--apply', action='store_true',
                            help='записать в базу (по умолчанию сухой прогон)')
        parser.add_argument('--snapshot-dir', default=OUT_DIR,
                            help='куда класть снимок старых значений')

    def handle(self, *args, **opts):
        say = self.stdout.write
        path = opts['path']
        if not os.path.isfile(path):
            raise CommandError('нет файла %s' % path)
        with open(path, encoding='utf-8') as fh:
            lines = fh.read().splitlines()

        rows, errors, duplicates = {}, [], 0
        n_lines = 0
        for number, raw in enumerate(lines, 1):
            if not raw.strip():
                continue
            n_lines += 1
            try:
                pk, updates = parse_line(raw)
            except ValueError as exc:
                errors.append((number, str(exc)))
                continue
            if pk in rows:
                duplicates += 1          # поздняя строка побеждает
                rows[pk].update(updates)
            else:
                rows[pk] = updates

        found = {p.pk: p for p in Problem.objects.filter(pk__in=list(rows))
                 .only('pk', 'character', 'features')}
        missing = [pk for pk in rows if pk not in found]

        changes = []
        n_character = n_features = unchanged = 0
        for pk, updates in rows.items():
            problem = found.get(pk)
            if problem is None:
                continue
            old = {'character': problem.character or '',
                   'features': list(problem.features or [])}
            new = {'character': updates.get('character', old['character']),
                   'features': updates.get('features', old['features'])}
            if new == old:
                unchanged += 1
                continue
            n_character += new['character'] != old['character']
            n_features += new['features'] != old['features']
            changes.append((problem, old, new))

        say('Строк: %d · разобрано: %d · с ошибками: %d · повторов id: %d'
            % (n_lines, len(rows), len(errors), duplicates))
        say('Задач найдено: %d · не найдено id: %d' % (len(found), len(missing)))
        say('Изменится: %d (характер: %d, особенности: %d) · без изменений: %d'
            % (len(changes), n_character, n_features, unchanged))
        for number, reason in errors[:PREVIEW]:
            say('  ошибка в строке %d: %s' % (number, reason))
        if missing:
            say('  не найдено id: %s%s'
                % (', '.join(str(pk) for pk in missing[:PREVIEW]),
                   ' …' if len(missing) > PREVIEW else ''))
        if changes:
            say('Предпросмотр (первые %d из %d):' % (min(PREVIEW, len(changes)), len(changes)))
            for problem, old, new in changes[:PREVIEW]:
                say('  #%d  характер %r → %r  особенности %s → %s'
                    % (problem.pk, old['character'], new['character'],
                       old['features'], new['features']))

        if not opts['apply']:
            say('Сухой прогон: в базу ничего не записано. Для записи добавьте --apply.')
            return
        if not changes:
            say('Записывать нечего.')
            return

        # ⚠️ СНИМОК СТАРЫХ ЗНАЧЕНИЙ ДО ЗАПИСИ — обратимость. Тот же формат,
        # что у входа: скормить снимок с --apply = откатить.
        os.makedirs(opts['snapshot_dir'], exist_ok=True)
        snapshot = os.path.join(opts['snapshot_dir'],
                                'undo_%s.jsonl' % time.strftime('%Y%m%d_%H%M%S'))
        with open(snapshot, 'w', encoding='utf-8') as fh:
            for problem, old, _new in changes:
                fh.write(json.dumps({'id': problem.pk, **old}, ensure_ascii=False) + '\n')

        with transaction.atomic():
            for start in range(0, len(changes), BATCH):
                batch = []
                for problem, _old, new in changes[start:start + BATCH]:
                    problem.character = new['character']
                    problem.features = new['features']
                    batch.append(problem)
                # Только два своих поля — ничего другого запись не касается.
                Problem.objects.bulk_update(batch, ['character', 'features'])

        say('Записано: %d задач. Снимок старых значений: %s' % (len(changes), snapshot))
        say('Повторный сухой прогон того же файла должен дать «Изменится: 0».')
