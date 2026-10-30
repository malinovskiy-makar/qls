"""Общее для механических починок задач пакета олимпиад (день 30.10, этапы Д1–Д4).

Каждая команда этапа устроена как `clean_olympiad_package_tasks` (ADR 0172):
сухой прогон по умолчанию, отчёт в `reports/`, снимок базы перед `--apply`,
запись одной транзакцией, повторный прогон — 0 изменений. Сомнительное текст
не меняет, а получает «под вопросом» на позициях комплектов этой задачи.

⚠️ ПРАВИТСЯ ТОЛЬКО ЗАДАЧА S4 (`editable_ids`): создана заливкой пакета (id не
меньше `S4_FIRST`), черновик, скрыта до ревью, ревью пустое. Прежний банк не
меняется никогда — после записи это сверяется отпечатком `old_digest`, и
расхождение откатывает транзакцию.
"""
import datetime
import json
import os
import sqlite3

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection

from olympiads import package_clean as pc
from olympiads import tasks_import as ti

# Первая задача заливки S4 (ADR 0170). Ниже — прежний банк.
S4_FIRST = 53709


def editable_ids():
    """Задачи, которые починки дня вправе менять."""
    return {pk for pk in pc.s4_problem_ids() if pk >= S4_FIRST}


def old_digest():
    """Отпечаток прежнего банка: поля задач, пункты, число рисунков."""
    return ti.existing_digest(S4_FIRST - 1)


def snapshot_database(tag):
    """Копия базы перед записью (только SQLite). Путь — в вывод и в отчёт."""
    if connection.vendor != 'sqlite':
        raise CommandError('Снимок автоматически делается только для SQLite. '
                           'Сделайте дамп базы руками и повторите запуск.')
    name = str(connection.settings_dict['NAME'])
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    base, ext = os.path.splitext(name)
    target = '{}.before_{}_{}{}'.format(base, tag, stamp, ext or '.sqlite3')
    source = sqlite3.connect(name)
    try:
        dest = sqlite3.connect(target)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    return target


def write_report(name, payload, directory=''):
    """JSON-отчёт этапа в `reports/` (или в `directory`). Возвращает путь."""
    directory = directory or os.path.join(settings.BASE_DIR, 'reports')
    os.makedirs(directory, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(directory, '{}_{}.json'.format(name, stamp))
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, default=str)
    return path


def flag_edits(reasons_by_problem):
    """Правки позиций «под вопросом»: {задача: [причины]} → список правок.

    Причина, которая у позиции уже есть, второй раз не дописывается — поэтому
    повторный прогон даёт 0 правок.
    """
    from olympiads.models import OlympiadVariantItem as Item
    edits = []
    items = Item.objects.filter(problem_id__in=list(reasons_by_problem))
    for item in items.order_by('pk'):
        old = list(item.quality_reasons or [])
        new = old + [r for r in reasons_by_problem[item.problem_id] if r not in old]
        if new != old or item.quality != Item.Quality.FLAGGED:
            edits.append({'pk': item.pk, 'problem': item.problem_id,
                          'reasons': (old, new)})
    return edits


def apply_flag_edits(edits, now):
    """Записать «под вопросом». Вызывать внутри `transaction.atomic()`."""
    from olympiads.models import OlympiadVariantItem as Item
    rows = {i.pk: i for i in Item.objects.filter(pk__in=[e['pk'] for e in edits])}
    for edit in edits:
        item = rows[edit['pk']]
        item.quality = Item.Quality.FLAGGED
        item.quality_reasons = edit['reasons'][1]
        item.updated_at = now
    Item.objects.bulk_update(list(rows.values()),
                             ['quality', 'quality_reasons', 'updated_at'],
                             batch_size=500)
