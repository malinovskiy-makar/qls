# -*- coding: utf-8 -*-
"""Набор C измерителя (С14) — живые формулировки владельца.

ТОЛЬКО ЧИТАЕТ БАЗУ. Результат — файл `problems/data/eval_set_c.json`.

Владелец — практикующий преподаватель, то есть настоящий пользователь поиска.
Его формулировки — НЕ синтетика: живые данные, просто источник не лог, а
голова. Поэтому набор C приёмочный: абсолютные цифры качества поиска
называются по нему, а не по сгенерированному набору B.

Исходник — .docx, по одной строке на запрос:

    <как искал бы преподаватель>: https://weconomics.site/catalog/problem/<id>/

⚠️ ЧТО ЭТИМ НАБОРОМ МОЖНО СЧИТАТЬ СЕЙЧАС. У каждой строки известен ровно один
правильный ответ, поэтому recall@K и MRR@10 считаются честно и без всякой
дополнительной работы. Полной разметки топ-20 на relevant/acceptable/
irrelevant, которой требует методология, здесь НЕТ — значит nDCG@10 считается
по бинарному признаку «та самая задача или нет» и занижен: задача, которая
преподавателя бы устроила, но не является исходной, засчитывается промахом.
Разметку добирает команда `search_eval_markup`.

⚠️ .docx РАЗБИРАЕТСЯ БЕЗ python-docx, НАМЕРЕННО. Формат — zip с XML, нам нужен
текст абзацев и ничего больше. Тащить зависимость в боевые требования ради
одной разовой команды не стоит: у проекта pip-audit в CI, и каждый лишний
пакет — повод для внепланового обновления.

Запуск:
    manage.py build_eval_set_c
    manage.py build_eval_set_c --source путь/к/файлу.docx
"""
import re
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.eval_sets import DATA_DIR, save_eval_set
from problems.models import Problem
from problems.search_eval_metrics import EvalCase

ССЫЛКА = re.compile(r'https?://\S*?/catalog/problem/(\d+)/?')
_АБЗАЦ = re.compile(r'<w:p[ >].*?</w:p>', re.S)
_ТЕКСТ = re.compile(r'<w:t[^>]*>(.*?)</w:t>', re.S)
_ЗАМЕНЫ = (('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'),
           ('&apos;', "'"))


def читать_абзацы(path: Path) -> list[str]:
    """Достаёт текст абзацев из .docx. Пустые абзацы сохраняются как ''."""
    with zipfile.ZipFile(path) as архив:
        xml = архив.read('word/document.xml').decode('utf-8')
    абзацы = []
    for кусок in _АБЗАЦ.findall(xml):
        текст = ''.join(_ТЕКСТ.findall(кусок))
        for что, на_что in _ЗАМЕНЫ:
            текст = текст.replace(что, на_что)
        абзацы.append(текст.strip())
    return абзацы


def разобрать_строку(строка: str):
    """Делит строку на (формулировка, id задачи). Любая часть может быть None."""
    совпадение = ССЫЛКА.search(строка)
    pid = int(совпадение.group(1)) if совпадение else None
    фраза = ССЫЛКА.sub('', строка).strip().rstrip(':').strip()
    return (фраза or None), pid


class Command(BaseCommand):
    help = 'Собрать эталонный набор C (живые формулировки владельца).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            default=str(Path(settings.BASE_DIR) / 'reports' /
                        'embeddings_scaleup' / 'owner_queries_set_c.docx'),
            help='Файл .docx с формулировками владельца.')
        parser.add_argument(
            '--out', default=str(DATA_DIR / 'eval_set_c.json'),
            help='Куда записать набор.')

    def handle(self, *args, **options):
        источник = Path(options['source'])
        if not источник.exists():
            raise CommandError(f'Файл не найден: {источник}')

        абзацы = читать_абзацы(источник)
        строки = [(n, s) for n, s in enumerate(абзацы, start=1) if s]
        self.stdout.write(f'Непустых строк в файле: {len(строки)}')

        случаи, предупреждения = [], []
        без_id, без_текста = [], []
        for номер, строка in строки:
            фраза, pid = разобрать_строку(строка)
            if pid is None:
                без_id.append(номер)
                continue
            if фраза is None:
                без_текста.append(номер)
                continue
            случаи.append(EvalCase(query=фраза, relevant_ids={pid},
                                   meta={'строка': номер}))

        if без_id:
            предупреждения.append(
                f'Строки без ссылки на задачу, пропущены: {без_id}. '
                'Формулировка есть, правильный ответ неизвестен — измерить '
                'нечем.')
        if без_текста:
            предупреждения.append(
                f'Строки с одной ссылкой и без формулировки, пропущены: '
                f'{без_текста}. Запроса нет — искать нечего.')

        # Проверяем эталон о базу: id может указывать на удалённую задачу или
        # на задачу без вектора. Молча оставить такую — записать себе провал
        # там, где поиск ни при чём.
        ids = {next(iter(c.relevant_ids)) for c in случаи}
        живые = set(Problem.objects.filter(pk__in=ids).values_list('id', flat=True))
        с_вектором = set(Problem.objects
                         .filter(pk__in=ids, embedding__isnull=False)
                         .values_list('id', flat=True))
        пропавшие = sorted(ids - живые)
        без_вектора = sorted(живые - с_вектором)
        if пропавшие:
            предупреждения.append(f'id, которых нет в базе: {пропавшие}')
        if без_вектора:
            предупреждения.append(
                f'id без эмбеддинга (физически недостижимы): {без_вектора}')

        повторы = sorted(pid for pid in ids
                         if sum(1 for c in случаи
                                if next(iter(c.relevant_ids)) == pid) > 1)
        if повторы:
            предупреждения.append(
                f'Один и тот же id под несколькими формулировками: {повторы}. '
                'Это не ошибка: разные формулировки одной задачи — валидный '
                'материал, просто запросов больше, чем уникальных задач.')

        предупреждения.append(
            'Разметки топ-20 (relevant/acceptable/irrelevant) в этом наборе '
            'нет: правильным считается ровно один известный id. recall@K и '
            'MRR@10 честны, nDCG@10 занижен — подходящая, но не исходная '
            'задача засчитывается промахом. Разметку добирает '
            'search_eval_markup.')

        путь = save_eval_set(
            options['out'], name='C',
            description='Живые формулировки владельца-преподавателя. '
                        'Приёмочный набор: абсолютные цифры называются по нему.',
            cases=случаи, warnings=предупреждения, mode='text')

        self.stdout.write(self.style.SUCCESS(
            f'Готово: {len(случаи)} запросов, {len(ids)} уникальных задач.\n'
            f'Пропущено строк: без ссылки {len(без_id)}, '
            f'без формулировки {len(без_текста)}.\n'
            f'Записано: {путь}'))
        for w in предупреждения:
            self.stdout.write(self.style.WARNING(f'  ! {w}'))
