# -*- coding: utf-8 -*-
"""glm_run_gate — гейт перед боевым прогоном. Считает КОД, а не человек.

Читает `run_parsed.jsonl` и `run_metrics.json` контрольной точки и печатает
две таблицы:

1. **Шестнадцать инвариантов §11 API_RUN_MASTER** — «инвариант · порог ·
   факт · сошлось». Это ЗАМЕР, а не приговор: расхождение здесь означает
   «настройку надо донастроить», а не «деньги будут выброшены».
2. **Восемь условий блокировки** (решение владельца 02.09.2026) — вот они и
   есть приговор. Сработало хотя бы одно — боевой прогон НЕ запускается.

Почему инвариантов именно 16, а не все строки §11: остальные измеряются
только ПОСЛЕ установки полей в банк (`title` у всех задач, заголовки
категории D, «известные 96 сломанных cases») либо требуют внешних данных
(`check_type` SolveHub, 218 задач ВсОШ-регион). Контрольная точка в базу не
пишет вовсе (§ Шаг 8), поэтому их здесь честно нет — а не «сошлись».

⚠️ В базу НИЧЕГО не пишет. Только читает журнал и `Problem`.

Запуск:
    manage.py glm_run_gate
    manage.py glm_run_gate --parsed reports/enrich_pilot/run_parsed.jsonl
"""
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from problems.enrich import taxonomy
from problems.models import AutoTopicAssignment, Problem

REPORT_DIR = Path('reports/enrich_pilot')
PARSED_PATH = REPORT_DIR / 'run_parsed.jsonl'
METRICS_PATH = REPORT_DIR / 'run_metrics.json'
GATE_PATH = REPORT_DIR / 'run_gate.json'

CHECKPOINT_SIZE = 300

_DIGIT_RE = re.compile(r'\d')
_WORD_RE = re.compile(r'\w+', re.UNICODE)

THEME_OTHER_ID = '29'  # «Другое» в data/taxonomy.json


# ---------------------------------------------------------------------------
# Соответствие 23 канонических тем v1 (`apply_topic_mapping.py`, ими размечен
# банк) и 29 тем v2 (`data/taxonomy.json`, их проставляет прогон).
#
# ⚠️ Значение — МНОЖЕСТВО, а не одна тема, и это не поблажка: v1 в трёх
# местах ГРУБЕЕ v2, и требовать точного попадания там значило бы штрафовать
# модель за то, что новая таксономия подробнее старой.
#   «Инфляция и безработица»  -> в v2 это ДВЕ темы (18 и 19);
#   «Финансы и инструменты»   -> проценты/вклады (24) и ценные бумаги (25);
#   «Вмешательство государства» -> у v1 нет темы для внешних эффектов вовсе,
#                                  они жили тут же (10 и 11);
#   «Международная торговля»  -> торговля (15) и валютный рынок (16).
# Тем v2, у которых в v1 дома нет совсем (12 «Асимметрия информации и риск»),
# в таблице нет — задача с такой темой просто не участвует в замере, если
# человек не проставил ей ни одной канонической темы.
# ---------------------------------------------------------------------------

CANON_TO_V2 = {
    'Введение в экономическую теорию': {'1'},
    'Альтернативные издержки и КПВ': {'2'},
    'Спрос и предложение': {'3'},
    'Эластичность': {'4'},
    'Теория потребителя и полезность': {'5'},
    'Теория фирмы: производство и издержки': {'6'},
    'Совершенная конкуренция': {'7'},
    'Монополия и ценовая дискриминация': {'8'},
    'Олигополия и теория игр': {'9'},
    'Вмешательство государства': {'10', '11'},
    'Международная торговля': {'15', '16'},
    'Рынок труда': {'13'},
    'Неравенство доходов': {'14'},
    'ВВП и национальные счета': {'17'},
    'Совокупный спрос и совокупное предложение': {'20'},
    'Инфляция и безработица': {'18', '19'},
    'Фискальная политика': {'21'},
    'Монетарная политика': {'22'},
    'Экономический рост и циклы': {'23'},
    'Финансы и финансовые инструменты': {'24', '25'},
    'Эконометрика и анализ данных': {'27'},
    'Поведенческая экономика': {'26'},
    'Математика и оптимизация': {'28'},
}


def read_parsed(path):
    rows = []
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def human_topic_match(rows):
    """`(совпало, задач_с_темой_человека, доля_%)`.

    «Проставленная человеком» — тема из `Problem.topics`, которой НЕТ в
    `AutoTopicAssignment` для этой же задачи: автоназначение по соседям
    (`auto_assign_topics`) пишет в тот же M2M, и считать его человеком
    значило бы сверять модель с другой моделью.
    """
    ids = [row['problem_id'] for row in rows]
    auto = set(AutoTopicAssignment.objects
               .filter(problem_id__in=ids)
               .values_list('problem_id', 'topic_id'))
    human = {}
    for pid, topic_id, topic_name in (
            Problem.objects.filter(id__in=ids)
            .values_list('id', 'topics__id', 'topics__name')):
        if topic_id is None or (pid, topic_id) in auto:
            continue
        allowed = CANON_TO_V2.get(topic_name)
        if allowed:
            human.setdefault(pid, set()).update(allowed)

    matched = 0
    compared = 0
    for row in rows:
        allowed = human.get(row['problem_id'])
        if not allowed:
            continue
        compared += 1
        if str(row.get('topic_primary') or '') in allowed:
            matched += 1
    pct = (matched / compared * 100) if compared else 0.0
    return matched, compared, pct


def query_similarity_median(rows):
    """Медиана по задачам от медианы попарной схожести её запросов.

    Схожесть — косинус на МНОЖЕСТВАХ слов (|A∩B| / sqrt(|A|·|B|)), без
    эмбеддингов: инвариант §11 спрашивает «не восемь ли это перефразировок
    одного запроса», и для такого вопроса совпадение слов — прямой и
    проверяемый признак. Эмбеддинги дали бы другое число на той же шкале и
    потребовали бы модели — цена несоразмерна вопросу.
    """
    per_task = []
    for row in rows:
        queries = [q for q in (row.get('search_queries') or [])
                   if isinstance(q, str)]
        token_sets = [set(_WORD_RE.findall(q.lower())) for q in queries]
        token_sets = [t for t in token_sets if t]
        if len(token_sets) < 2:
            continue
        sims = []
        for i in range(len(token_sets)):
            for j in range(i + 1, len(token_sets)):
                a, b = token_sets[i], token_sets[j]
                sims.append(len(a & b) / math.sqrt(len(a) * len(b)))
        if sims:
            per_task.append(statistics.median(sims))
    return statistics.median(per_task) if per_task else 0.0


def digits_in_protected_fields(rows):
    """Сколько ПОЛЕЙ содержат цифру там, где §12.3 их запрещает. Считается
    по финальному ответу — тому, что пойдёт в банк."""
    count = 0
    for row in rows:
        for field in ('given', 'find', 'plot'):
            value = row.get(field)
            if isinstance(value, str) and _DIGIT_RE.search(value):
                count += 1
        for concept in (row.get('econ_concepts') or []):
            if isinstance(concept, str) and _DIGIT_RE.search(concept):
                count += 1
        for query in (row.get('search_queries') or []):
            if isinstance(query, str) and _DIGIT_RE.search(query):
                count += 1
    return count


def single_letter_concepts(rows):
    return sum(1 for row in rows
               for concept in (row.get('econ_concepts') or [])
               if isinstance(concept, str) and len(concept) <= 1)


def build_invariants(rows, metrics):
    """Список `(раздел, название, порог_текстом, факт_текстом, сошлось)` —
    шестнадцать инвариантов §11, измеримых на контрольной точке."""
    total = len(rows)
    ok_rows = [r for r in rows if not r['defect']]
    n_ok = len(ok_rows) or 1

    topics = Counter(str(r.get('topic_primary') or '') for r in ok_rows
                     if r.get('topic_primary'))
    top_theme_pct = (max(topics.values()) / n_ok * 100) if topics else 0.0
    other_pct = topics.get(THEME_OTHER_ID, 0) / n_ok * 100

    matched, compared, human_pct = human_topic_match(ok_rows)

    unique_tags = {tag for r in ok_rows for tag in (r.get('tags') or [])}
    tag_counts = Counter(len(r.get('tags') or []) for r in ok_rows)
    one_tag_pct = tag_counts.get(1, 0) / n_ok * 100
    five_tag_pct = tag_counts.get(5, 0) / n_ok * 100
    second_topic_pct = sum(
        1 for r in ok_rows if (r.get('topics_secondary') or [])) / n_ok * 100

    given_lens = [len(r['given']) for r in ok_rows if r.get('given')]
    given_median = statistics.median(given_lens) if given_lens else 0
    sim_median = query_similarity_median(ok_rows)

    concept_counter = Counter(c for r in ok_rows
                              for c in set(r.get('econ_concepts') or []))
    top3 = [c for c, _ in concept_counter.most_common(3)]
    top3_cover = sum(1 for r in ok_rows
                     if set(r.get('econ_concepts') or []) & set(top3))
    top3_pct = top3_cover / n_ok * 100
    offlist_pct = sum(
        1 for r in ok_rows if (r.get('concepts_offlist') or [])) / n_ok * 100

    not_task_pct = sum(
        1 for r in ok_rows if r.get('text_quality') == 'не_задача') / n_ok * 100
    problem_type_pct = sum(
        1 for r in ok_rows if r.get('problem_type')) / n_ok * 100

    sweep_changed = metrics['sweep_detector']['changed']
    first_pass_pct = (
        (total - metrics['retried_rows']) / total * 100) if total else 0.0

    return [
        ('Тема и теги', 'Ни одна тема не покрывает больше',
         '15 % корпуса', '%.1f %%' % top_theme_pct, top_theme_pct <= 15),
        ('Тема и теги', '«Другое»',
         '<= 2 %', '%.1f %%' % other_pct, other_pct <= 2),
        ('Тема и теги', 'Совпадение с темой, проставленной человеком',
         '>= 70 %', '%.1f %% (%d из %d)' % (human_pct, matched, compared),
         human_pct >= 70),
        ('Тема и теги', 'Уникальных тегов на 300 задач',
         '>= 90', '%d' % len(unique_tags), len(unique_tags) >= 90),
        ('Тема и теги', 'Доля задач ровно с 1 тегом / ровно с 5',
         '<= 30 % / <= 15 %', '%.1f %% / %.1f %%' % (one_tag_pct, five_tag_pct),
         one_tag_pct <= 30 and five_tag_pct <= 15),
        ('Тема и теги', 'Доля задач с непустой второй темой',
         '25-40 %', '%.1f %%' % second_topic_pct,
         25 <= second_topic_pct <= 40),

        ('Текстовые поля', 'Цифры в given, find, econ_concepts, plot, запросах',
         '0', '%d' % digits_in_protected_fields(ok_rows),
         digits_in_protected_fields(ok_rows) == 0),
        ('Текстовые поля', 'Медианная длина given',
         '40-120 символов', '%d' % given_median, 40 <= given_median <= 120),
        ('Текстовые поля', 'Медианная попарная схожесть запросов одной задачи',
         '< 0,85', '%.3f' % sim_median, sim_median < 0.85),

        ('Понятия и словарь', 'Верхние три термина покрывают',
         '< 50 % задач', '%.1f %%' % top3_pct, top3_pct < 50),
        ('Понятия и словарь', 'Доля заполненного concepts_offlist',
         '2-8 %', '%.1f %%' % offlist_pct, 2 <= offlist_pct <= 8),
        ('Понятия и словарь', 'Однобуквенные обозначения в econ_concepts',
         '0', '%d' % single_letter_concepts(ok_rows),
         single_letter_concepts(ok_rows) == 0),

        ('Диагностика', 'Доля «не задача» в text_quality',
         '< 5 %', '%.1f %%' % not_task_pct, not_task_pct < 5),
        ('Диагностика', 'problem_type заполнен у всех задач',
         '100 %', '%.1f %%' % problem_type_pct, problem_type_pct >= 100),

        ('Техника и деньги', 'Свип-детектор: расхождения в защищённых полях',
         '0', '%d' % sweep_changed, sweep_changed == 0),
        ('Техника и деньги', 'Доля ответов, прошедших схему с первого раза',
         '>= 95 %', '%.1f %%' % first_pass_pct, first_pass_pct >= 95),
    ]


def build_blockers(rows, metrics):
    """Восемь условий «результат негоден» (решение владельца 02.09.2026).
    Каждое — `(номер, формулировка, факт, сработало_ли)`. Сработало хотя бы
    одно — боевой прогон НЕ запускается."""
    total = metrics['total_processed']
    defect_pct = metrics['defect_pct']
    sweep_changed = metrics['sweep_detector']['changed']
    ok_rows = [r for r in rows if not r['defect']]
    n_ok = len(ok_rows) or 1

    _, _, human_pct = human_topic_match(ok_rows)
    unique_tags = {tag for r in ok_rows for tag in (r.get('tags') or [])}
    topics = Counter(str(r.get('topic_primary') or '') for r in ok_rows
                     if r.get('topic_primary'))
    top_theme_pct = (max(topics.values()) / len(rows) * 100) if topics else 0.0
    not_task_pct = sum(
        1 for r in ok_rows if r.get('text_quality') == 'не_задача') / n_ok * 100
    images_sent = metrics['problems_image_sent']

    return [
        (1, 'обработано меньше 300', '%d' % total, total < CHECKPOINT_SIZE),
        (2, 'финальный брак >= 5 %', '%.1f %%' % defect_pct, defect_pct >= 5),
        (3, 'свип-детектор по защищённым полям != 0',
         '%d' % sweep_changed, sweep_changed != 0),
        (4, 'совпадение с темой человека < 60 %',
         '%.1f %%' % human_pct, human_pct < 60),
        (5, 'уникальных тегов на 300 задач < 70',
         '%d' % len(unique_tags), len(unique_tags) < 70),
        (6, 'одна тема покрывает > 25 % выборки',
         '%.1f %%' % top_theme_pct, top_theme_pct > 25),
        (7, 'доля «не задача» > 10 %',
         '%.1f %%' % not_task_pct, not_task_pct > 10),
        (8, 'задач с растром, отправленных с изображением, меньше 40',
         '%d' % images_sent, images_sent < 40),
    ]


class Command(BaseCommand):
    help = ('Гейт перед боевым прогоном: 16 инвариантов §11 и 8 условий '
            'блокировки по журналу контрольной точки. В базу не пишет.')

    def add_arguments(self, parser):
        parser.add_argument('--parsed', type=str, default=str(PARSED_PATH))
        parser.add_argument('--metrics', type=str, default=str(METRICS_PATH))
        parser.add_argument('--out', type=str, default=str(GATE_PATH))
        parser.add_argument(
            '--allow-blocked', action='store_true',
            help='НЕ падать с ошибкой, когда сработало условие блокировки — '
                 'только напечатать. Для разбора, не для запуска прогона.')

    def handle(self, *args, **options):
        parsed_path = Path(options['parsed'])
        metrics_path = Path(options['metrics'])
        if not parsed_path.exists():
            raise CommandError('Нет журнала %s — сначала контрольная точка.'
                               % parsed_path)
        rows = read_parsed(parsed_path)
        with open(metrics_path, encoding='utf-8') as fh:
            metrics = json.load(fh)

        invariants = build_invariants(rows, metrics)
        blockers = build_blockers(rows, metrics)

        self.stdout.write('=== ШЕСТНАДЦАТЬ ИНВАРИАНТОВ §11 (замер, не приговор) ===')
        self.stdout.write('%-18s %-52s %-20s %-22s %s' % (
            'раздел', 'инвариант', 'порог', 'факт', 'сошлось'))
        section = None
        for sec, name, threshold, fact, passed in invariants:
            self.stdout.write('%-18s %-52s %-20s %-22s %s' % (
                sec if sec != section else '', name, threshold, fact,
                'да' if passed else 'НЕТ'))
            section = sec
        failed = [(sec, name, threshold, fact)
                  for sec, name, threshold, fact, passed in invariants
                  if not passed]
        self.stdout.write('')
        self.stdout.write('сошлось %d из %d' % (
            len(invariants) - len(failed), len(invariants)))
        if failed:
            self.stdout.write('НЕ сошлись (%d):' % len(failed))
            for sec, name, threshold, fact in failed:
                self.stdout.write('  · %s — порог %s, факт %s' % (name, threshold, fact))

        self.stdout.write('')
        self.stdout.write('=== ВОСЕМЬ УСЛОВИЙ БЛОКИРОВКИ (приговор) ===')
        tripped = []
        for number, text, fact, hit in blockers:
            self.stdout.write('%d. %-58s факт %-12s %s' % (
                number, text, fact, 'СРАБОТАЛО' if hit else 'нет'))
            if hit:
                tripped.append((number, text, fact))

        self.stdout.write('')
        if tripped:
            verdict = 'ЗАПРЕЩЁН'
            self.stdout.write('🔴 БОЕВОЙ ПРОГОН НЕ ЗАПУСКАЕТСЯ. Сработали условия:')
            for number, text, fact in tripped:
                self.stdout.write('   %d. %s (факт %s)' % (number, text, fact))
        else:
            verdict = 'РАЗРЕШЁН'
            self.stdout.write('🟢 Ни одно условие блокировки не сработало — '
                              'боевой прогон разрешён.')

        out_path = Path(options['out'])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as fh:
            json.dump({
                'verdict': verdict,
                'invariants': [
                    {'section': s, 'name': n, 'threshold': t, 'fact': f,
                     'passed': p}
                    for s, n, t, f, p in invariants],
                'invariants_passed': len(invariants) - len(failed),
                'invariants_total': len(invariants),
                'blockers': [
                    {'number': n, 'condition': c, 'fact': f, 'tripped': h}
                    for n, c, f, h in blockers],
            }, fh, ensure_ascii=False, indent=2)
        self.stdout.write('гейт записан: %s' % out_path)

        if tripped and not options['allow_blocked']:
            raise CommandError(
                'Гейт закрыт: сработало условий — %d. Боевой прогон не '
                'запускать.' % len(tripped))
