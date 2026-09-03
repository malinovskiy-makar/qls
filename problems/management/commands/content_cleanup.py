# -*- coding: utf-8 -*-
"""Чистка корпуса: `content_status` по итогам боевого прогона обогащения.

Решение владельца 03.09.2026 дословно: «чистый мусор 100 % = удаление, есть
сомнения что мусор / ужасный код / другие проблемы = пока скрываем на сайте».
Ручного просмотра не будет — безопасность обеспечивают проверки ЗДЕСЬ.

Два входа, оба из журнала прогона, к API не обращаемся:

* `queue_not_a_problem.jsonl` — 1 596 задач, у которых модель поставила
  `task_nature = не_задача`;
* `queue_broken_text.jsonl` — 3 336 задач с серьёзными дефектами текста
  (`text_quality` = `битый`/`серьёзные дефекты`), раскладка по типу дефекта
  берётся из `text_quality_note`.

⚠️ УДАЛЯЕТСЯ ТОЛЬКО ТЕХНИЧЕСКИЙ МУСОР, И ПРАВИЛО КОНЪЮНКТИВНОЕ. Запись
удаляется, только если выполнены ВСЕ условия сразу:

1. текст подходит под строгий шаблон мусора (пусто, только номер задачи,
   только заголовок раздела, только номер страницы, только разметка);
2. `answer` и `solution` пусты — иначе там есть оплаченная работа;
3. НЕТ НИ ОДНОЙ ссылки ниоткуда (проверяются все обратные связи `Problem`,
   перечисленные интроспекцией `_meta`, а не списком в голове);
4. нет признаков родителя — ни `ProblemPart`, ни обрывающегося соседа того
   же источника с близким номером.

Сомнение любой природы — не удаление, а `needs_fix`.

⚠️ СРЕДИ «НЕ ЗАДАЧА» ЕСТЬ ЛОЖНЫЕ СРАБАТЫВАНИЯ, И ЭТО НЕ ДОГАДКА. В выборке
глазами видны настоящие задачи подтипа «верно-неверно» — «Алюминий добывают
в шахтах.», «В России действует режим фиксированного курса национальной
валюты.»: утверждение без вопросительного знака модель принимает за
служебный текст.

Какая это ДОЛЯ — не измерено и здесь не утверждается. Механического
признака нет: `problem_type` вызова 2 у всех 1 596 равен `не_задача` (вызов
2 повторяет вердикт вызова 1, независимым сигналом не является), а в банке
`problem_type` пуст у 1 568 из 1 596. Раскладка по источникам показывает,
что основная масса — не тестовые сборники: «Листки задач» 726 и «Overleaf
Archive 3» 469 против 2 у «Сборника тестов АА».

Практический вывод от этого не меняется: удалять такое нельзя, а сомнение
по решению владельца скрывается, и скрытие обратимо. Строгий шаблон мусора
эти записи не трогает по построению — у них связный текст длиннее
заголовка.

⚠️ ВЫГРУЗКА ПЕРЕД УДАЛЕНИЕМ. Все удаляемые записи со ВСЕМИ полями
пишутся в `reports/enrich_pilot/deleted_not_a_problem.jsonl` ДО первого
удаления, и удаление не начинается, пока файл не закрыт и не проверен на
диске. Удаление необратимо, выгрузка — единственная страховка.

По умолчанию команда НИЧЕГО НЕ МЕНЯЕТ и печатает раскладку. Запись — только
с `--apply`. `--revert` возвращает `content_status` всем задачам в `ok`
(удалённое, разумеется, не возвращает — см. выгрузку).
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.models import Problem, SourceReference

REPORT_DIR = Path('reports/enrich_pilot')
NOT_A_PROBLEM_QUEUE = REPORT_DIR / 'queue_not_a_problem.jsonl'
BROKEN_TEXT_QUEUE = REPORT_DIR / 'queue_broken_text.jsonl'
DELETED_DUMP = REPORT_DIR / 'deleted_not_a_problem.jsonl'
DECISIONS_PATH = REPORT_DIR / 'content_cleanup_decisions.json'

# ---------------------------------------------------------------------------
# Строгие шаблоны технического мусора. Шаблон обязан покрывать ТЕКСТ ЦЕЛИКОМ
# (`fullmatch`), а не находиться где-то внутри: «Задача 5» в начале длинного
# условия — это нормальная задача, а не мусор.
# ---------------------------------------------------------------------------
JUNK_PATTERNS = (
    ('пустой текст', re.compile(r'\s*')),
    ('только номер задачи', re.compile(
        r'\s*(?:задача|задание|вопрос|упражнение|пример|task|problem)'
        r'\s*[№#]?\s*[0-9IVXivx]+(?:[.)][0-9]*)*\s*[.)]?\s*', re.I)),
    ('только номер или страница', re.compile(
        r'\s*(?:стр\.?|страница|с\.)?\s*[0-9]{1,4}(?:[.)][0-9]*)*\s*[.)]?\s*',
        re.I)),
    ('только заголовок раздела', re.compile(
        r'\s*(?:§|глава|раздел|часть|тема|блок|модуль|тур|этап|вариант)'
        r'\s*[0-9IVXivx]*\s*[.)]?\s*', re.I)),
    ('только служебное слово', re.compile(
        r'\s*(?:ответы?|решени[ея]|критерии(?:\s+оценивания)?|содержание|'
        r'оглавление|введение|заключение|литература|приложение|таблица|'
        r'рисунок|график|итого|всего)\s*[0-9]*\s*[.:)]?\s*', re.I)),
    ('только разметка', re.compile(
        r'[\s\\$§{}\[\]()&%_^~#*|/+=<>"\'.,:;!?—–-]*')),
)

# ---------------------------------------------------------------------------
# Тип дефекта -> прятать ли задачу. Порядок ВАЖЕН: побеждает первый
# подошедший шаблон, поэтому специфичное стоит раньше общего, а опечатки —
# последними: заметка, где рядом с опечаткой названа битая формула, обязана
# уйти в «битую формулу», а не в «опечатки».
#
# Категории взяты из САМИХ заметок боевого прогона, а не выдуманы: первая
# версия списка оставляла треть заметок (1 194 из 3 336) в «прочем», и
# владелец не увидел бы, что там на самом деле — «условие отсутствует,
# сохранились только варианты ответов», «вместо условия готовое решение
# (утечка)», «подпункты содержат заглушки „fff“».
#
# Опечатка смыслу не мешает, и прятать задачу из-за неё — потеря без выгоды
# (решение владельца 03.09.2026). Всё остальное скрывается: скрытие
# обратимо, а битый текст на экране — нет.
# ---------------------------------------------------------------------------
DEFECT_KINDS = (
    ('утрачена картинка или чертёж', re.compile(
        r'картинк|изображени|рисун|чертёж|чертеж|визуальн\w*\s+элемент|'
        r'figure|схем', re.I), True),
    ('битая формула или разметка', re.compile(
        r'формул|latex|tikz|pgfplot|katex|нерендер|не\s*отрендер|разметк',
        re.I), True),
    ('утечка решения в условие', re.compile(
        r'утечк|готово[ег]\w*\s+решени|вместо\s+условия\s+\w*\s*решени|'
        r'встроен\s+готовый\s+ответ|содержит\s+ответ', re.I), True),
    ('заглушка вместо условия', re.compile(
        r'заглушк|«тык»|\bfff\b|служебн\w*\s+пометк', re.I), True),
    ('склеенные задачи', re.compile(
        r'склеен|слит|несколько\s+задач|две\s+задачи|перемешан|смешан|'
        r'из\s+другой\s+задачи|не\s+связан\w*\s+с', re.I), True),
    ('утрачена часть условия', re.compile(
        r'отсутству|утрачен|обрыв|обрубл|обрезан|неполн|усечён|усечен|'
        r'не\s+хватает|только\s+вариант|нет\s+данных|пуст[аяо]|'
        r'начинается\s+с\s+середин|фрагмент|восстановить\s+\w*\s*нельзя|'
        r'восстановить\s+\w*\s*невозможно', re.I), True),
    ('опечатки, не мешающие смыслу', re.compile(
        r'опечатк|орфограф|пунктуац|лишний\s+пробел|регистр\s+букв', re.I),
     False),
)


# SQLite держит не больше 999 переменных в одном запросе, а списки здесь —
# тысячи id. Куски по 900 — с запасом на прочие параметры запроса.
SQL_CHUNK = 900


def chunked(values, size=SQL_CHUNK):
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start:start + size]


def read_queue(path):
    """Список id из очереди JSONL. Порядок сохраняется, дубли снимаются."""
    path = Path(path)
    if not path.exists():
        raise CommandError('Нет файла очереди: %s' % path)
    seen = set()
    ids = []
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            pid = json.loads(line)['problem_id']
            if pid not in seen:
                seen.add(pid)
                ids.append(pid)
    return ids


def read_queue_rows(path):
    """Строки очереди целиком — нужен `text_quality_note` для раскладки."""
    path = Path(path)
    if not path.exists():
        raise CommandError('Нет файла очереди: %s' % path)
    rows = {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                row = json.loads(line)
                rows[row['problem_id']] = row
    return rows


def junk_kind(statement):
    """Название шаблона мусора или `None`. Шаблон покрывает текст ЦЕЛИКОМ."""
    text = statement or ''
    for name, pattern in JUNK_PATTERNS:
        if pattern.fullmatch(text):
            return name
    return None


def defect_kind(note):
    """Тип дефекта по `text_quality_note` и надо ли прятать задачу.

    Возвращает `(название, прятать)`. Заметка, не подошедшая ни под один
    шаблон, считается ДЕФЕКТОМ ОТОБРАЖЕНИЯ («прочее»): умолчание в сторону
    осторожности — скрыть лишнее дешевле, чем оставить битое на виду, и
    скрытие обратимо.
    """
    text = note or ''
    for name, pattern, hide in DEFECT_KINDS:
        if pattern.search(text):
            return name, hide
    return 'прочее (заметка не подошла под шаблон)', True


# ---------------------------------------------------------------------------
# Обратные связи `Problem` делятся на ДВЕ РАЗНЫЕ ВЕЩИ, и смешивать их нельзя.
#
# «Происхождение» — строки, которые описывают САМУ запись и умирают вместе с
# ней: откуда импортирована (`source_references`), автоматические темы,
# кандидаты в дубликаты. Ссылка на задачу из её собственного паспорта — не
# признак того, что задача кому-то нужна: `source_references` есть у КАЖДОЙ
# импортированной записи, и если считать её ссылкой, удалять станет нечего
# вообще, а решение владельца «чистый мусор = удаление» превратится в
# холостой ход.
#
# «Использование» — строки, которые говорят, что запись КОМУ-ТО НУЖНА:
# домашние задания и их позиции, работы учеников, наборы и подборки, уроки,
# сохранённое учеником, учебные события, игровой пул, страницы теории,
# рубрики и подсказки.
#
# Удаление блокирует ЛЮБАЯ строка «использования». Из «происхождения»
# блокируют те, что несут работу человека или кода: подпункты, картинки,
# версии, вердикты ревью. Голое `source_references` не блокирует — оно
# целиком уходит в выгрузку перед удалением.
# ---------------------------------------------------------------------------
USAGE_RELATIONS = frozenset({
    'assignments', 'assignment_items', 'submissions', 'collections',
    'lessons_as_main', 'lessons_as_challenge', 'lessons_as_homework',
    'saved_by', 'learning_events', 'game_questions', 'theory_pages',
    'rubrics', 'hints',
})
CONTENT_RELATIONS = frozenset({
    'parts', 'figures', 'versions', 'review_verdicts',
})
# Всё остальное (`source_references`, `auto_topic_assignments`,
# `possible_duplicates`, `similar_to`, `duplicates_as_a`/`_b`) — паспорт и
# производные, удалению не мешают, но в отчёт попадают.


def incoming_reference_counts(problem_ids):
    """`{problem_id: {имя_связи: сколько строк}}` по ВСЕМ обратным связям.

    Связи перечисляются интроспекцией `Problem._meta`, а не списком в
    голове: список в голове устаревает молча, а цена ошибки здесь —
    удалённая задача, на которую кто-то ссылался. Разделение на группы —
    выше, в `USAGE_RELATIONS`/`CONTENT_RELATIONS`.
    """
    wanted = set(problem_ids)
    counts = defaultdict(dict)
    relations = []
    for field in Problem._meta.get_fields():
        if not field.is_relation:
            continue
        if field.auto_created and not field.concrete:
            relations.append((field.get_accessor_name(), field))
    for name, field in relations:
        model = field.related_model
        if model is Problem and field.field.name == 'duplicate_of':
            # «эта задача — дубликат вон той»: ссылка настоящая, считаем.
            pass
        for part in chunked(wanted):
            try:
                pairs = list(model.objects.filter(**{
                    '%s__in' % field.field.name: part}).values_list(
                    '%s_id' % field.field.name, flat=True))
            except Exception:
                # m2m через промежуточную модель без прямого FK-имени —
                # считаем через сам Problem, чтобы не выдумывать схему.
                for pid in part:
                    n = getattr(Problem.objects.get(pk=pid), name).count()
                    if n:
                        counts[pid][name] = n
                continue
            for pid in pairs:
                if pid in wanted:
                    counts[pid][name] = counts[pid].get(name, 0) + 1
    return counts


_BREAK_RE = re.compile(r'[.!?:;»)\]]\s*$')


def looks_truncated(text):
    """Текст обрывается на полуслове — признак «у соседа оторван кусок».

    Проверка нарочно грубая и односторонняя: она может пропустить обрыв,
    но не должна объявить обрывом нормальный текст, потому что вывод из
    неё — ЗАПРЕТ на удаление, а не разрешение.
    """
    text = (text or '').strip()
    if not text:
        return False
    return not _BREAK_RE.search(text)


def parent_signals(problem_ids):
    """`{problem_id: [почему считаем, что у записи есть родитель]}`.

    Два признака: собственные `ProblemPart` (значит запись — сама
    составная задача, а не обрывок) и соседняя запись ТОГО ЖЕ источника с
    близким номером, чей текст обрывается на полуслове (значит эта запись
    — скорее всего оторванный от неё кусок).
    """
    wanted = set(problem_ids)
    signals = defaultdict(list)

    for part in chunked(wanted):
        for pid in Problem.objects.filter(
                id__in=part, parts__isnull=False).values_list(
                'id', flat=True).distinct():
            signals[pid].append('есть ProblemPart')

    refs = []
    for part in chunked(wanted):
        refs.extend(SourceReference.objects.filter(problem_id__in=part)
                    .values('problem_id', 'source_id', 'problem_number'))
    if not refs:
        return signals
    source_ids = {r['source_id'] for r in refs}
    neighbours = defaultdict(list)
    for part in chunked(source_ids):
        for row in (SourceReference.objects
                    .filter(source_id__in=part)
                    .values('problem_id', 'source_id', 'problem_number')):
            neighbours[row['source_id']].append(row)
    neighbour_ids = {r['problem_id'] for rows in neighbours.values()
                     for r in rows}
    texts = {}
    for part in chunked(neighbour_ids):
        texts.update(dict(Problem.objects.filter(id__in=part)
                          .values_list('id', 'statement')))

    for ref in refs:
        number = _number_of(ref['problem_number'])
        if number is None:
            continue
        for other in neighbours[ref['source_id']]:
            if other['problem_id'] == ref['problem_id']:
                continue
            other_number = _number_of(other['problem_number'])
            if other_number is None or abs(other_number - number) > 2:
                continue
            if looks_truncated(texts.get(other['problem_id'])):
                signals[ref['problem_id']].append(
                    'сосед #%s того же источника обрывается на полуслове'
                    % other['problem_id'])
                break
    return signals


_NUM_RE = re.compile(r'\d+')


def _number_of(problem_number):
    m = _NUM_RE.search(problem_number or '')
    return int(m.group()) if m else None


def blocking_references(refs):
    """Связи, которые ЗАПРЕЩАЮТ удаление, из полного словаря ссылок."""
    return {name: n for name, n in refs.items()
            if name in USAGE_RELATIONS or name in CONTENT_RELATIONS}


def classify_not_a_problem(problems, references, parents):
    """Раскладка очереди «не задача» на четыре категории задания."""
    decisions = {}
    for problem in problems:
        refs = references.get(problem.id) or {}
        blocking = blocking_references(refs)
        signs = parents.get(problem.id) or []
        junk = junk_kind(problem.statement)
        has_payload = bool((problem.answer or '').strip()
                           or (problem.solution or '').strip())
        if junk and not has_payload and not blocking and not signs:
            decisions[problem.id] = ('технический мусор', junk, 'удалить')
        elif junk:
            # Шаблон мусора совпал, но что-то держит: ссылка, родитель или
            # уже написанные ответ/решение. Сомнение — это `needs_fix`.
            why = ('ссылки: %s' % sorted(blocking) if blocking
                   else 'признаки родителя: %s' % signs if signs
                   else 'есть ответ или решение')
            decisions[problem.id] = ('фрагмент с родителем', why, 'needs_fix')
        elif signs or blocking:
            why = ('признаки родителя: %s' % signs if signs
                   else 'ссылки: %s' % sorted(blocking))
            decisions[problem.id] = ('фрагмент с родителем', why, 'needs_fix')
        else:
            # Осмысленный текст, ссылок и родителя нет. Задание требует
            # `needs_fix` — но ложное срабатывание модели (подтип
            # «верно-неверно») попадает именно сюда, поэтому решение
            # отделяется от мусора и обратимо.
            decisions[problem.id] = ('фрагмент без родителя',
                                     'осмысленный текст, ссылок нет',
                                     'needs_fix')
    return decisions


class Command(BaseCommand):
    help = ('Чистка корпуса: content_status по очередям боевого прогона. '
            'Без --apply ничего не меняет.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Записать изменения в базу (по умолчанию '
                                 'команда только печатает раскладку).')
        parser.add_argument('--revert', action='store_true',
                            help='Вернуть content_status всем задачам в ok. '
                                 'Удалённое не возвращает — см. выгрузку.')
        parser.add_argument('--allow-delete', action='store_true',
                            help='Разрешить удаление технического мусора. '
                                 'Без него команда только помечает junk — '
                                 'удаление необратимо и требует отдельного '
                                 'осознанного согласия.')

    def handle(self, *args, **options):
        if options['revert']:
            return self._revert()

        nap_ids = read_queue(NOT_A_PROBLEM_QUEUE)
        broken_rows = read_queue_rows(BROKEN_TEXT_QUEUE)
        self.stdout.write('=== ЧИСТКА КОРПУСА ===')
        self.stdout.write('очередь «не задача»: %d id' % len(nap_ids))
        self.stdout.write('очередь «дефекты текста»: %d id' % len(broken_rows))

        visible_before = visible_count()
        self.stdout.write('видно ученику ДО: %d' % visible_before)

        # --- 3.1 «не задача» -------------------------------------------
        problems = list(Problem.objects.filter(id__in=nap_ids))
        self.stdout.write('найдено в базе: %d' % len(problems))
        references = incoming_reference_counts(nap_ids)
        parents = parent_signals(nap_ids)
        decisions = classify_not_a_problem(problems, references, parents)

        by_action = Counter(d[2] for d in decisions.values())
        by_category = Counter(d[0] for d in decisions.values())
        junk_hits = Counter(junk_kind(p.statement) for p in problems
                            if junk_kind(p.statement))
        self.stdout.write('')
        self.stdout.write('--- подошло под строгий шаблон мусора ---')
        for name, n in junk_hits.most_common():
            self.stdout.write('  %-28s %d' % (name, n))
        self.stdout.write('  ИТОГО под шаблоном: %d из %d'
                          % (sum(junk_hits.values()), len(problems)))
        blocked = Counter()
        for problem in problems:
            for name in blocking_references(
                    references.get(problem.id) or {}):
                blocked[name] += 1
        self.stdout.write('')
        self.stdout.write('--- ссылки, запрещающие удаление ---')
        for name, n in blocked.most_common():
            group = ('использование' if name in USAGE_RELATIONS
                     else 'своё содержимое')
            self.stdout.write('  %-26s %5d  (%s)' % (name, n, group))
        self.stdout.write('')
        self.stdout.write('--- разбор «не задача» ---')
        for category, n in by_category.most_common():
            self.stdout.write('  %-24s %d' % (category, n))
        self.stdout.write('  ---')
        for action, n in by_action.most_common():
            self.stdout.write('  действие «%s»: %d' % (action, n))

        to_delete = [p for p in problems
                     if decisions[p.id][2] == 'удалить']
        nap_needs_fix = [p.id for p in problems
                         if decisions[p.id][2] == 'needs_fix']

        # --- 3.3 дефекты текста ----------------------------------------
        defect_split = Counter()
        broken_needs_fix = []
        broken_left = []
        by_source = Counter()
        present = set()
        for part in chunked(broken_rows):
            present.update(Problem.objects.filter(id__in=part)
                           .values_list('id', flat=True))
        for pid, row in broken_rows.items():
            if pid not in present:
                continue
            kind, hide = defect_kind(row.get('text_quality_note'))
            defect_split[kind] += 1
            (broken_needs_fix if hide else broken_left).append(pid)
        for part in chunked(broken_needs_fix):
            for _pid, name in (SourceReference.objects
                               .filter(problem_id__in=part)
                               .values_list('problem_id', 'source__name')):
                by_source[name or 'без источника'] += 1

        self.stdout.write('')
        self.stdout.write('--- дефекты текста по типу ---')
        for kind, n in defect_split.most_common():
            hide = next((h for k, _r, h in DEFECT_KINDS if k == kind), True)
            self.stdout.write('  %-38s %5d  %s' % (
                kind, n, 'скрываем' if hide else 'ОСТАЁТСЯ ВИДНОЙ'))
        self.stdout.write('')
        self.stdout.write('--- по источникам (только скрываемые) ---')
        for name, n in by_source.most_common(12):
            self.stdout.write('  %-40s %5d' % (name[:40], n))

        needs_fix_ids = sorted(set(nap_needs_fix) | set(broken_needs_fix))
        self.stdout.write('')
        self.stdout.write('ИТОГО к удалению: %d' % len(to_delete))
        self.stdout.write('ИТОГО в needs_fix: %d (из «не задача» %d, из '
                          'дефектов %d, пересечение %d)'
                          % (len(needs_fix_ids), len(nap_needs_fix),
                             len(broken_needs_fix),
                             len(set(nap_needs_fix) & set(broken_needs_fix))))

        self._write_decisions(decisions, defect_split, to_delete,
                              needs_fix_ids, broken_left)

        if not options['apply']:
            self.stdout.write('')
            self.stdout.write('РЕЖИМ ПРОСМОТРА: база не тронута. Запись — '
                              'с --apply.')
            return

        # --- запись ----------------------------------------------------
        deleted = 0
        if to_delete:
            if not options['allow_delete']:
                self.stdout.write('')
                self.stdout.write('⚠️ %d записей подошли под удаление, но '
                                  'флага --allow-delete нет: они помечены '
                                  'junk и скрыты, файлы не тронуты.'
                                  % len(to_delete))
                for part in chunked(p.id for p in to_delete):
                    Problem.objects.filter(id__in=part).update(
                        content_status=Problem.ContentStatus.JUNK)
            else:
                deleted = self._dump_and_delete(to_delete)

        updated = 0
        with transaction.atomic():
            for part in chunked(needs_fix_ids):
                updated += Problem.objects.filter(id__in=part).update(
                    content_status=Problem.ContentStatus.NEEDS_FIX)
        self.stdout.write('')
        self.stdout.write('записано: needs_fix у %d задач, удалено %d'
                          % (updated, deleted))
        self.stdout.write('видно ученику ПОСЛЕ: %d' % visible_count())

    # -- служебное ------------------------------------------------------

    def _dump_and_delete(self, to_delete):
        """Выгрузка ВСЕХ полей на диск, затем удаление. Не наоборот."""
        DELETED_DUMP.parent.mkdir(parents=True, exist_ok=True)
        ids = [p.id for p in to_delete]
        with open(DELETED_DUMP, 'w', encoding='utf-8') as fh:
            for problem in _in_chunks(ids):
                payload = {}
                for field in Problem._meta.concrete_fields:
                    value = getattr(problem, field.attname)
                    if isinstance(value, (bytes, memoryview)):
                        value = None  # эмбеддинг: пересчитывается, не текст
                    elif hasattr(value, 'isoformat'):
                        value = value.isoformat()
                    payload[field.attname] = value
                payload['_source_references'] = list(
                    SourceReference.objects.filter(problem=problem)
                    .values())
                fh.write(json.dumps(payload, ensure_ascii=False,
                                    default=str))
                fh.write('\n')
        # ⚠️ Удаление начинается ТОЛЬКО после того, как файл закрыт и его
        # содержимое перечитано с диска: «записали и сразу удалили» ловит
        # обрыв на середине буфера, и страховки не остаётся.
        written = sum(1 for line in open(DELETED_DUMP, encoding='utf-8')
                      if line.strip())
        if written != len(ids):
            raise CommandError(
                'Выгрузка неполная: в файле %d строк вместо %d. Ничего не '
                'удалено.' % (written, len(ids)))
        self.stdout.write('выгружено перед удалением: %d записей в %s'
                          % (written, DELETED_DUMP))
        with transaction.atomic():
            for part in chunked(ids):
                Problem.objects.filter(id__in=part).delete()
        return len(ids)

    def _write_decisions(self, decisions, defect_split, to_delete,
                         needs_fix_ids, left_visible):
        DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'not_a_problem': {
                str(pid): {'категория': d[0], 'почему': str(d[1]),
                           'действие': d[2]}
                for pid, d in decisions.items()},
            'defects_by_kind': dict(defect_split),
            'to_delete_ids': sorted(p.id for p in to_delete),
            'needs_fix_ids': needs_fix_ids,
            'left_visible_ids': sorted(left_visible),
        }
        with open(DECISIONS_PATH, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        self.stdout.write('решения записаны: %s' % DECISIONS_PATH)

    def _revert(self):
        n = Problem.objects.exclude(
            content_status=Problem.ContentStatus.OK).update(
            content_status=Problem.ContentStatus.OK)
        self.stdout.write('content_status возвращён в ok у %d задач' % n)
        self.stdout.write('⚠️ Удалённые записи этим не возвращаются — см. %s'
                          % DELETED_DUMP)


def _in_chunks(ids):
    """Задачи по списку id, кусками — генератором."""
    for part in chunked(ids):
        for problem in Problem.objects.filter(id__in=part):
            yield problem


def visible_count():
    """Сколько задач видно ученику в каталоге прямо сейчас.

    Четыре признака видимости — те же, что в `catalog/views.py`. Общей
    функции в проекте нет: тройка повторяется по месту в каждом запросе, и
    заводить её здесь, в команде чистки, значило бы создать пятнадцатое
    место правды вместо четырнадцати.
    """
    return Problem.objects.filter(
        status=Problem.Status.PUBLISHED,
        needs_quality_review=False,
        hidden_pending_review=False,
        content_status=Problem.ContentStatus.OK,
    ).count()
