"""Импорт комплектов из пакета олимпиад (olympiads_20261029, ADR 0169).

Читает `<слаг>/kits/*.json` и пишет в раздел «Олимпиады»: комплекты, их
классы, записи о файлах PDF и счётчики заданий. Команда —
`manage.py import_olympiads_kits`; здесь вся логика, чтобы её можно было
проверять тестами без запуска команды.

⚠️ В `Problem` ЭТОТ МОДУЛЬ НЕ ПИШЕТ НИЧЕГО И НЕ ЧИТАЕТ. Задания пакета едут
в банк отдельной волной (решение владельца 30.10: «скрытыми», после
дедупликации и эмбеддингов). Поэтому позиций комплекта (`OlympiadVariantItem`)
здесь тоже нет: у них `problem` обязателен (`null=False`, PROTECT), а задачи
в банке ещё не заведены. Всё, что нужно навигатору — числа, — снимается с
пакета в счётчики комплекта.

⚠️ КЛЮЧ КОМПЛЕКТА — `kit_key` (= `kit_id` пакета). Естественный ключ
(олимпиада, сезон, этап, тур, класс, вариант) не годится: в пакете шесть
комплектов совпадают по нему целиком. Комплекты без `kit_key` (12 прежних,
демонстрационные) импорт НЕ ТРОГАЕТ ВООБЩЕ: на них висят попытки, а какой
из нескольких комплектов пакета «тот самый» — решает владелец.
"""
import glob
import hashlib
import json
import os
import shutil
from collections import Counter

from django.core.management.base import CommandError
from django.db import transaction
from django.db.models import F, Sum

from olympiads.models import (
    FactSource, Olympiad, OlympiadStage, OlympiadVariant, OlympiadVariantFile,
    OlympiadVariantGrade,
)

# ⚠️ СПРАВОЧНИКИ ПРЯМО В КОДЕ, не догадки по ходу: незнакомое значение —
# ошибка с номером комплекта, а не тихий пропуск (решение сессии 30.10).
STAGE_CODES = {'final': 'final', 'regional': 'reg', 'qualifying': 'qual'}

# Как называем и куда ставим этап, если его в справочнике ещё нет.
# код → (название, порядок, формат). У ВсОШ порядок сквозной (школьный и
# муниципальный впереди), у остальных — отборочный перед заключительным.
NEW_STAGE_DEFAULTS = {
    'qual': ('Отборочный тур', 1, OlympiadStage.Format.ONLINE),
    'final': ('Заключительный тур', 2, OlympiadStage.Format.OFFLINE),
    'reg': ('Региональный этап', 3, OlympiadStage.Format.OFFLINE),
}
VSEROS_STAGE_NAMES = {'final': ('Заключительный этап', 4),
                      'reg': ('Региональный этап', 3)}

# Олимпиады, которых может не оказаться в базе. Остальные пять слагов
# (`vp`, `vp-ob`, `vp-fingram`, `mosh`, `vseros`) заводит справочник
# (`import_olympiads_data`); если и их нет — тоже заведём, но скрытыми.
HSE = 'НИУ «Высшая школа экономики»'
MOSH_ORG = 'Департамент образования Москвы, МЦНМО'
NEW_OLYMPIAD_DEFAULTS = {
    'vp': (HSE, 'Высшая проба', 'main'),
    'vp-ob': (HSE, 'ВП: основы бизнеса', 'related'),
    'vp-fingram': (HSE, 'ВП: финграмотность', 'related'),
    'mosh': (MOSH_ORG, 'МОШ', 'main'),
    'mosh-fingram': (MOSH_ORG, 'МОШ: финграмотность', 'related'),
    'mosh-entrepreneurship': (MOSH_ORG, 'МОШ: предпринимательство',
                              'related'),
    'vseros': ('Министерство просвещения Российской Федерации', 'ВсОШ',
               'main'),
}
# С этих двух снимаем метку «заглушка»: настоящие данные пакета теперь есть.
CLEAR_PLACEHOLDER = ('vp-ob', 'vp-fingram')

QUALITY_VALUES = {'clean', 'flagged'}
FILE_URL_MAX = 800


class KitImportError(CommandError):
    """Комплект пакета нельзя разобрать: в тексте всегда номер комплекта."""


# ── нормализация ─────────────────────────────────────────────────────────

def normalize_stage(raw, kit_id):
    try:
        return STAGE_CODES[raw]
    except KeyError:
        raise KitImportError(
            'Комплект {}: неизвестный этап {!r} (известны: {}).'.format(
                kit_id, raw, ', '.join(sorted(STAGE_CODES)))) from None


def normalize_season(raw, kit_id):
    """`2022/2023` → `2022/23`; пустой сезон остаётся пустым (1 комплект)."""
    raw = (raw or '').strip()
    if not raw:
        return ''
    parts = raw.split('/')
    if (len(parts) != 2 or not parts[0].isdigit() or len(parts[0]) != 4
            or not parts[1].isdigit() or len(parts[1]) not in (2, 4)):
        raise KitImportError(
            'Комплект {}: сезон {!r} не похож на «2022/23».'.format(
                kit_id, raw))
    return '{}/{}'.format(parts[0], parts[1][-2:])


def expand_grades(raw, kit_id):
    """`10-11` → [10, 11]; `9` → [9]; `all` и пустое → [] (строк классов нет)."""
    raw = (raw or '').strip()
    if raw in ('', 'all'):
        return []
    try:
        bounds = [int(p) for p in raw.split('-')]
    except ValueError:
        raise KitImportError(
            'Комплект {}: класс {!r} не разобран.'.format(kit_id, raw)
        ) from None
    if len(bounds) > 2 or bounds[0] > bounds[-1]:
        raise KitImportError(
            'Комплект {}: класс {!r} не разобран.'.format(kit_id, raw))
    grades = list(range(bounds[0], bounds[-1] + 1))
    if grades[0] < 1 or grades[-1] > 11:
        raise KitImportError(
            'Комплект {}: класс {!r} вне 1–11.'.format(kit_id, raw))
    return grades


# ── что есть у задания ───────────────────────────────────────────────────

def _filled(value):
    return bool((value or '').strip())


def task_flags(task):
    """Три признака задания — ОДНО определение и для счётчиков комплекта, и
    для будущих позиций (`has_answer`, `has_solution`, `has_criteria`).

    Эталон ответа — непустой `answer` ИЛИ непустой ключ теста (решение
    владельца 30.10: «На время» включается им). Решение и критерии — не
    эталон: это то, что показывают после сдачи и по чему ставит балл ИИ.
    """
    test = task.get('test') or {}
    return {
        'has_answer': _filled(task.get('answer')) or _filled(test.get('key')),
        'has_solution': _filled(task.get('solution_md')),
        'has_criteria': _filled(task.get('criteria_md')),
    }


def compute_counters(tasks, kit_id=''):
    counters = Counter()
    for task in tasks:
        status = (task.get('quality') or {}).get('status')
        if status not in QUALITY_VALUES:
            raise KitImportError(
                'Комплект {}: задание {} — качество {!r}, ждали clean/flagged.'
                .format(kit_id, task.get('ref_key'), status))
        counters['tasks_total'] += 1
        counters['tasks_clean' if status == 'clean' else 'tasks_flagged'] += 1
        flags = task_flags(task)
        counters['tasks_with_answer'] += flags['has_answer']
        counters['tasks_with_solution'] += flags['has_solution']
        counters['tasks_with_criteria'] += flags['has_criteria']
    return {name: counters[name] for name in (
        'tasks_total', 'tasks_clean', 'tasks_flagged', 'tasks_with_answer',
        'tasks_with_solution', 'tasks_with_criteria')}


def compute_visibility(counters):
    """Скрыт комплект, где ВСЕ задания под вопросом (в пакете 30.10 — 8)."""
    if counters['tasks_total'] and not counters['tasks_clean']:
        return OlympiadVariant.Visibility.HIDDEN
    return OlympiadVariant.Visibility.PUBLISHED


# ── чтение пакета ────────────────────────────────────────────────────────

def read_package(root, only=''):
    """Все комплекты пакета: список (путь, данные), по слагам по порядку."""
    pattern = os.path.join(root, '*', 'kits', '*.json')
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise KitImportError(
            'В {} нет файлов */kits/*.json — это не папка пакета олимпиад.'
            .format(root))
    kits = []
    for path in paths:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        if only and data['olympiad']['slug'] != only:
            continue
        kits.append((path, data))
    if not kits:
        raise KitImportError('Слаг {!r}: комплектов в пакете нет.'.format(only))
    kit_ids = Counter(data['kit_id'] for _, data in kits)
    dup = [k for k, n in kit_ids.items() if n > 1]
    if dup:
        raise KitImportError('Повторяются kit_id: {}'.format(', '.join(dup)))
    return kits


# ── запись ───────────────────────────────────────────────────────────────

class Report:
    """Что сделал прогон. Те же числа печатает команда и пишет в файл."""

    def __init__(self):
        self.counts = Counter()
        self.summary_package = {}
        self.summary_db = {}
        self.lists = {'olympiads_created': [], 'stages_created': [],
                      'placeholder_cleared': [], 'hidden_kits': [],
                      'absent_kits': [], 'errors': [],
                      'legacy_kits': []}

    def add(self, name, n=1):
        self.counts[name] += n

    def as_dict(self):
        return {'counts': dict(sorted(self.counts.items())),
                'summary_package': self.summary_package,
                'summary_db': self.summary_db, **self.lists}


class KitImporter:
    def __init__(self, report):
        self.report = report
        self._olympiads = {}
        self._stages = {}

    # -- справочник
    def olympiad(self, data):
        slug = data['olympiad']['slug']
        if slug not in self._olympiads:
            obj = Olympiad.objects.filter(slug=slug).first()
            if obj is None:
                org, short, group = NEW_OLYMPIAD_DEFAULTS[slug]
                obj = Olympiad.objects.create(
                    slug=slug, name_full=data['olympiad']['name'],
                    name_short=short, organizer=org, display_group=group,
                    is_published=False, is_placeholder=False)
                self.report.add('olympiads_created')
                self.report.lists['olympiads_created'].append(slug)
            elif slug in CLEAR_PLACEHOLDER and obj.is_placeholder:
                obj.is_placeholder = False
                obj.save(update_fields=['is_placeholder'])
                self.report.add('placeholder_cleared')
                self.report.lists['placeholder_cleared'].append(slug)
            self._olympiads[slug] = obj
        return self._olympiads[slug]

    def stage(self, olympiad, code):
        key = (olympiad.pk, code)
        if key not in self._stages:
            obj = OlympiadStage.objects.filter(
                olympiad=olympiad, code=code).first()
            if obj is None:
                name, order, fmt = NEW_STAGE_DEFAULTS[code]
                if olympiad.slug == 'vseros' and code in VSEROS_STAGE_NAMES:
                    name, order = VSEROS_STAGE_NAMES[code]
                obj = OlympiadStage.objects.create(
                    olympiad=olympiad, code=code, name=name, order=order,
                    format=fmt)
                self.report.add('stages_created')
                self.report.lists['stages_created'].append(
                    '{}/{}'.format(olympiad.slug, code))
            self._stages[key] = obj
        return self._stages[key]

    def fact_source(self, data):
        url = data.get('official_url') or ''
        if not url or len(url) > FactSource._meta.get_field('url').max_length:
            return None
        obj, created = FactSource.objects.get_or_create(
            url=url, defaults={
                'title': 'Задания: {}'.format(data['olympiad']['name']),
                'doc_type': (FactSource.DocType.PDF
                             if url.lower().endswith('.pdf')
                             else FactSource.DocType.SITE),
                'publisher': data['olympiad']['name'],
            })
        if created:
            self.report.add('fact_sources_created')
        return obj

    # -- один комплект
    def import_kit(self, data):
        """Один комплект целиком, в своей транзакции. Возвращает 'created' /
        'updated' / 'unchanged'."""
        with transaction.atomic():
            return self._import_kit(data)

    def _import_kit(self, data):
        kit_id = data['kit_id']
        olympiad = self.olympiad(data)
        stage = self.stage(olympiad, normalize_stage(data['stage'], kit_id))
        grades = expand_grades(data['grade'], kit_id)
        counters = compute_counters(data['tasks'], kit_id)
        visibility = compute_visibility(counters)
        source = self.fact_source(data)
        region = data.get('region') or {}
        official_url = data.get('official_url') or ''
        fields = {
            'olympiad': olympiad,
            'stage': stage,
            'year': data.get('year'),
            'grade': grades[0] if len(grades) == 1 else None,
            'variant_label': data.get('variant') or '',
            'problem_count': counters['tasks_total'],
            'has_solutions': counters['tasks_with_solution'] > 0,
            'original_url': official_url,
            'original_source': (OlympiadVariant.OriginalSource.OFFICIAL
                                if official_url
                                else OlympiadVariant.OriginalSource.NONE),
            'ref_event_id': kit_id,
            'is_placeholder': False,
            'source': source,
            'season': normalize_season(data.get('season'), kit_id),
            'tour': data.get('tour') or '',
            'grade_raw': data.get('grade') or '',
            'subject': data.get('subject') or '',
            'region_code': region.get('code') or '',
            'region_name': region.get('name') or '',
            'reference_version': data.get('reference_version') or '',
            'open_issues': data.get('open_issues') or [],
            'visibility': visibility,
            'absent_in_last_import': False,
            **counters,
        }
        variant = OlympiadVariant.objects.filter(kit_key=kit_id).first()
        if variant is None:
            variant = OlympiadVariant.objects.create(kit_key=kit_id, **fields)
            outcome = 'created'
        else:
            changed = [name for name, value in fields.items()
                       if getattr(variant, name) != value]
            for name in changed:
                setattr(variant, name, fields[name])
            if changed:
                variant.save(update_fields=changed)
            outcome = 'updated' if changed else 'unchanged'
        if visibility == OlympiadVariant.Visibility.HIDDEN:
            self.report.lists['hidden_kits'].append(kit_id)

        grades_changed = self._sync_grades(variant, grades)
        files_changed = self._sync_files(variant, data.get('files') or [])
        if outcome == 'unchanged' and (grades_changed or files_changed):
            outcome = 'updated'
        self.report.add('kits_' + outcome)
        return outcome

    def _sync_grades(self, variant, grades):
        have = set(variant.grades.values_list('grade', flat=True))
        want = set(grades)
        stale = have - want
        if stale:
            variant.grades.filter(grade__in=stale).delete()
            self.report.add('grades_deleted', len(stale))
        for grade in sorted(want - have):
            OlympiadVariantGrade.objects.create(variant=variant, grade=grade)
        if want - have:
            self.report.add('grades_created', len(want - have))
        return bool(stale or want - have)

    def _sync_files(self, variant, files):
        existing = {f.sha256: f for f in variant.files.all()}
        changed = False
        for order, item in enumerate(files):
            fields = {
                'kind': item['kind'],
                'url': item.get('url') or '',
                'official': bool(item.get('official', True)),
                'size': item.get('size'),
                'original_name': item.get('original_name') or '',
                'original_path': item.get('original_path') or '',
                'note': item.get('note') or '',
                'order': order,
            }
            if len(fields['url']) > FILE_URL_MAX:
                raise KitImportError(
                    'Комплект {}: адрес файла длиннее {} знаков.'.format(
                        variant.kit_key, FILE_URL_MAX))
            row = existing.get(item['sha256'])
            if row is None:
                OlympiadVariantFile.objects.create(
                    variant=variant, sha256=item['sha256'], **fields)
                self.report.add('files_created')
                changed = True
                continue
            diff = [n for n, v in fields.items() if getattr(row, n) != v]
            for name in diff:
                setattr(row, name, fields[name])
            if diff:
                row.save(update_fields=diff)
                self.report.add('files_updated')
                changed = True
            else:
                self.report.add('files_unchanged')
        return changed


def package_summary(kits):
    """Числа пакета, посчитанные заново по файлам — сверка с базой."""
    tasks = [t for _, d in kits for t in d['tasks']]
    developed = lambda d: [t for t in d['tasks'] if not t.get('test')]  # noqa: E731
    flags = [task_flags(t) for t in tasks]
    return {
        'kits': len(kits),
        'grade_rows': sum(len(expand_grades(d['grade'], d['kit_id']))
                          for _, d in kits),
        'files': sum(len(d.get('files') or []) for _, d in kits),
        'tasks': len(tasks),
        'tasks_clean': sum(t['quality']['status'] == 'clean' for t in tasks),
        'tasks_flagged': sum(t['quality']['status'] != 'clean' for t in tasks),
        'tasks_tests': sum(bool(t.get('test')) for t in tasks),
        'tasks_developed': sum(not t.get('test') for t in tasks),
        'tasks_with_criteria': sum(f['has_criteria'] for f in flags),
        'kits_criteria_for_all_developed': sum(
            1 for _, d in kits if developed(d)
            and all(task_flags(t)['has_criteria'] for t in developed(d))),
        'kits_without_any_criteria': sum(
            1 for _, d in kits
            if not any(task_flags(t)['has_criteria'] for t in d['tasks'])),
        'kits_answer_for_all': sum(
            1 for _, d in kits if d['tasks']
            and all(task_flags(t)['has_answer'] for t in d['tasks'])),
        'kits_hidden': sum(
            1 for _, d in kits if compute_visibility(
                compute_counters(d['tasks'], d['kit_id'])
            ) == OlympiadVariant.Visibility.HIDDEN),
    }


def database_summary(kit_ids):
    """Те же числа, но ИЗ БАЗЫ — после записи (до отката в сухом прогоне)."""
    qs = OlympiadVariant.objects.filter(kit_key__in=kit_ids)
    sums = qs.aggregate(
        tasks=Sum('tasks_total'), tasks_clean=Sum('tasks_clean'),
        tasks_flagged=Sum('tasks_flagged'),
        tasks_with_answer=Sum('tasks_with_answer'),
        tasks_with_solution=Sum('tasks_with_solution'),
        tasks_with_criteria=Sum('tasks_with_criteria'))
    return {
        'kits': qs.count(),
        'grade_rows': OlympiadVariantGrade.objects.filter(
            variant__in=qs).count(),
        'files': OlympiadVariantFile.objects.filter(variant__in=qs).count(),
        **{k: v or 0 for k, v in sums.items()},
        'kits_hidden': qs.filter(
            visibility=OlympiadVariant.Visibility.HIDDEN).count(),
        'kits_without_any_criteria': qs.filter(
            tasks_with_criteria=0).count(),
        'kits_answer_for_all': qs.filter(
            tasks_total__gt=0, tasks_with_answer=F('tasks_total')).count(),
        'kits_with_open_issues': qs.exclude(open_issues=[]).count(),
        'kits_without_year': qs.filter(year__isnull=True).count(),
        'kits_without_season': qs.filter(season='').count(),
    }


def mark_absent(seen_kit_ids, slugs, report):
    """Комплект, которого в пакете больше нет, помечается, а не удаляется."""
    stale = OlympiadVariant.objects.filter(
        kit_key__isnull=False, olympiad__slug__in=slugs,
        absent_in_last_import=False).exclude(kit_key__in=seen_kit_ids)
    ids = list(stale.values_list('kit_key', flat=True))
    stale.update(absent_in_last_import=True)
    report.add('kits_marked_absent', len(ids))
    report.lists['absent_kits'].extend(ids)


def hide_legacy_kits(report):
    """Скрыть прежние комплекты (`kit_key` пуст) — решение владельца 30.10.

    Прежние 12 ВсОШ не связываются с пакетными (однозначной пары нет, связывать
    руками — гадать) и не удаляются: пакет даёт настоящие версии тех же туров.
    Только `visibility='hidden'`; `OlympiadRef` и всё остальное не трогаем.
    Вернуть обратно одной строкой:

        OlympiadVariant.objects.filter(kit_key__isnull=True).update(
            visibility='published')

    Идемпотентно: уже скрытые в счёт «скрыто сейчас» не идут.
    """
    legacy = OlympiadVariant.objects.filter(kit_key__isnull=True)\
        .select_related('olympiad', 'stage').order_by('id')
    rows = []
    for variant in legacy:
        rows.append({
            'id': variant.pk, 'name': str(variant), 'grade': variant.grade,
            'ref_event_id': variant.ref_event_id,
            'was_hidden': variant.visibility == OlympiadVariant.Visibility.HIDDEN,
        })
    now = legacy.exclude(visibility=OlympiadVariant.Visibility.HIDDEN)\
        .update(visibility=OlympiadVariant.Visibility.HIDDEN)
    report.add('legacy_kits_total', len(rows))
    report.add('legacy_kits_hidden_now', now)
    report.lists['legacy_kits'] = rows


def existing_overlaps(kits):
    """Прежние комплекты без `kit_key` и комплекты пакета с тем же годом,
    этапом и классом. Только список: прежних импорт не трогает."""
    from olympiads.models import TrainingAttempt
    rows = []
    for old in OlympiadVariant.objects.filter(kit_key__isnull=True)\
            .select_related('olympiad', 'stage'):
        stage_code = old.stage.code if old.stage else None
        matches = []
        for _, data in kits:
            if data['olympiad']['slug'] != old.olympiad.slug:
                continue
            if data.get('year') != old.year:
                continue
            if STAGE_CODES.get(data['stage']) != stage_code:
                continue
            grades = expand_grades(data['grade'], data['kit_id'])
            if old.grade is not None and old.grade not in grades:
                continue
            matches.append(data['kit_id'])
        rows.append({
            'id': old.pk, 'olympiad': old.olympiad.slug, 'year': old.year,
            'stage': stage_code, 'grade': old.grade,
            'ref_event_id': old.ref_event_id,
            'attempts': TrainingAttempt.objects.filter(variant=old).count(),
            'package_kits': matches,
        })
    return rows


# ── файлы на диск ────────────────────────────────────────────────────────

def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def copy_files(kits, root, media_root, report, apply):
    """Оригиналы PDF → `MEDIA_ROOT/olympiads/<слаг>/<event_id>/<sha8>_<имя>`.

    Каждая копия сверяется по SHA-256 с тем, что записано в пакете: битый
    файл не должен оказаться «залитым». Уже лежащий на месте файл с тем же
    хешем не перекладывается.
    """
    for _, data in kits:
        variant = OlympiadVariant.objects.filter(kit_key=data['kit_id']).first()
        for item in data.get('files') or []:
            src = os.path.join(root, item['path'])
            rel = os.path.join('olympiads', data['olympiad']['slug'],
                               data['kit_id'], os.path.basename(item['path']))
            if len(rel) > OlympiadVariantFile._meta.get_field('file').max_length:
                raise KitImportError(
                    'Комплект {}: путь файла длиннее допустимого.'.format(
                        data['kit_id']))
            if not os.path.isfile(src):
                report.add('files_missing_in_package')
                report.lists['errors'].append('нет файла: ' + item['path'])
                continue
            if sha256_of(src) != item['sha256']:
                report.add('files_bad_sha')
                report.lists['errors'].append('хеш не сошёлся: ' + item['path'])
                continue
            dst = os.path.join(media_root, rel)
            if os.path.isfile(dst) and sha256_of(dst) == item['sha256']:
                report.add('files_already_on_disk')
            else:
                report.add('files_to_copy' if not apply else 'files_copied')
                report.add('bytes', os.path.getsize(src))
                if apply:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(src, dst)
                    if sha256_of(dst) != item['sha256']:
                        os.remove(dst)
                        raise KitImportError(
                            'После копирования хеш не сошёлся: ' + rel)
            if apply and variant is not None:
                row = variant.files.filter(sha256=item['sha256']).first()
                if row is not None and row.file.name != rel:
                    row.file.name = rel
                    row.save(update_fields=['file'])
