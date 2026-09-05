# -*- coding: utf-8 -*-
"""merge_enrichment_v2 — переливка кандидатных полей обогащения v2
(`reports/enrich_pilot/run2_parsed.jsonl`) в боевые поля `Problem`.

Сессия 2026-09-06 (владелец согласовал по переписке): темы/теги/заголовок-
кандидат/подсказки/тип задачи/сложность/согласованность ответа.

⚠️ Правила (зафиксированы владельцем в этой сессии):
  1. Брак (`defect: true`, 19 строк) не льём вообще — старое остаётся.
  2. Тема/теги — ПОЛНАЯ ЗАМЕНА у охваченных обогащением задач: старые связи
     Problem.topics/Problem.tags СНИМАЮТСЯ (сами строки Topic/Tag НЕ
     удаляются), новые — из канонической таксономии v2 (создаётся здесь же,
     идемпотентно, из `data/taxonomy.json`). Задачи вне прогона обогащения
     свои старые темы/теги не теряют — их кандидата попросту нет.
  3. `problem_type` — ПЕРЕЗАПИСЫВАЕТСЯ везде, где есть кандидат (даже поверх
     старого легаси-значения): иначе инвариант «ровно 8 значений» не сойдётся.
     Для 297 задач, у которых старое значение есть, а обогащения нет вовсе,
     применяется детерминированная таблица соответствия `LEGACY_CROSSWALK`
     (не модель, а факт формата источника — проверено 2026-09-06, совпадение
     с моделью на пересечении 96,7%).
  4. `difficulty` — пустое всегда заполняем. Непустое: если оно приехало
     ПЛОСКОЙ КОНСТАНТОЙ источника при импорте (`difficulty_native` пусто —
     AP Economics любых видов, КСИГМА, IEO, 2 159 задач) — перезаписываем,
     это не per-задачное суждение. Если несёт РОДНУЮ метку источника
     (`difficulty_native` непусто — SolveHub/ILE/Бахарев/Шпицруттен, 7 187
     задач) — не трогаем, это факт. Правка владельца 2026-09-06 поверх
     дефолта Фазы 1 — см. `docs проверки` в отчёте сессии.
  5. `title_candidate`/`title_source` — пишем всегда, где кандидат непуст.
     Боевой `title` ТОЖЕ перезаписываем, но ТОЛЬКО для категорий A (пусто/
     заглушка) и B (сломан) — иначе ученик вообще не увидит изменений.
     Категории C (эхо условия) и D (нормальный) `title` не трогают — решение
     об их перезаписи откладывается на отдельную сессию. Правка владельца
     2026-09-06 поверх дефолта Фазы 1.
  6. `hints` (модель `Hint`) — создаём только если у задачи ещё нет ни одной
     подсказки (идемпотентность повторного прогона).
  7. `answer_consistency` — новое поле (0051), пишем всегда, где есть кандидат.

Запуск:
    manage.py merge_enrichment_v2                 # --dry-run по умолчанию
    manage.py merge_enrichment_v2 --apply         # боевая запись, одна транзакция
"""
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from problems.enrich import taxonomy
from problems.enrich.title_rules import classify_and_pick_source
from problems.models import Hint, Problem, Tag, Topic

PARSED_PATH = Path('reports/enrich_pilot/run2_parsed.jsonl')
REPORT_DIR = Path('reports/enrich_pilot')
BACKUP_CSV_PATH = Path(
    r'C:\Users\shipu\weconomics-data\backups\old_markup_20260906_before_v2_merge.csv')

VALID_PROBLEM_TYPES = {
    'единственный_выбор', 'множественный_выбор', 'верно_неверно',
    'сопоставление', 'тест: короткий ответ', 'задача с развёрнутым ответом',
    'несколько_подвопросов', 'не_задача',
}

# Только для задач ВНЕ прогона обогащения (297 шт., проверено 2026-09-06):
# ни одна из них не имеет старое значение «тест: числовой ответ» — то самое,
# что расходится на 28% с «тест: короткий ответ» — поэтому таблица ниже
# однозначна на всём множестве, к которому применяется.
LEGACY_CROSSWALK = {
    'тест: один ответ': 'единственный_выбор',
    'тест: верно/неверно': 'верно_неверно',
    'тест: все верные': 'множественный_выбор',
}

# Правка владельца 2026-09-06: категории A (пусто/заглушка) и B (сломан) —
# помимо title_candidate, пишем и в боевой title. C (эхо условия) и D
# (нормальный) — не трогаем, это отдельное решение будущей сессии.
TITLE_OVERWRITE_CATEGORIES = {'A', 'B'}

# Правка владельца 2026-09-06: из 9 316 задач с непустой боевой сложностью
# 2 159 получили её плоской константой источника при импорте (AP Economics
# любых видов, КСИГМА, IEO — «прежний автоматический проход по коду», НЕ
# per-задачное суждение), у них difficulty_native пусто. Остальные 7 187
# (SolveHub, ILE, Бахарев, Шпицруттен) несут родную метку источника
# (`difficulty_native` непусто) — реальный факт, не трогаем. Проверено
# 2026-09-06 запросом по SourceReference — см. отчёт сессии.


def _is_flat_constant_difficulty(native_label):
    return not native_label

CHUNK = 900  # SQLite "too many SQL variables" — см. CLAUDE.md команд


def chunks(seq, n=CHUNK):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


class Command(BaseCommand):
    help = ('Переливка кандидатных полей обогащения v2 в боевые поля Problem. '
            'По умолчанию --dry-run (ничего не пишет).')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Боевая запись в одной транзакции. Без флага — только отчёт.')
        parser.add_argument('--parsed', type=str, default=str(PARSED_PATH))
        parser.add_argument('--sample-html', type=str,
                            default=str(REPORT_DIR / 'merge_v2_sample_diff.html'))
        parser.add_argument('--out', type=str,
                            default=str(REPORT_DIR / 'merge_v2_dry_run.json'))
        parser.add_argument('--sample-size', type=int, default=20)

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        self.apply_mode = options['apply']
        self.parsed_path = Path(options['parsed'])
        self.sample_html_path = Path(options['sample_html'])
        self.out_path = Path(options['out'])
        self.sample_size = options['sample_size']

        rows = self.load_rows()
        ok_rows = [r for r in rows if not r.get('defect')]
        defect_rows = [r for r in rows if r.get('defect')]
        self.stdout.write('строк в журнале: %d (брак: %d, к переливке: %d)'
                          % (len(rows), len(defect_rows), len(ok_rows)))

        jsonl_ids = {r['problem_id'] for r in rows}
        legacy_only_ids, legacy_old_values = self.find_legacy_only(jsonl_ids)

        taxonomy_plan = self.plan_taxonomy_objects()
        self.stdout.write('')
        self.stdout.write('=== Канонические темы/теги v2 ===')
        self.stdout.write('тем: %d (переиспользуем по имени: %d, создаём заново: %d)'
                          % (len(taxonomy_plan['topics']),
                             taxonomy_plan['topics_reuse'], taxonomy_plan['topics_create']))
        self.stdout.write('тегов: %d (переиспользуем по имени: %d, создаём заново: %d)'
                          % (len(taxonomy_plan['tags']),
                             taxonomy_plan['tags_reuse'], taxonomy_plan['tags_create']))
        if taxonomy_plan['topics_reused_names']:
            self.stdout.write('  переиспользуемые имена тем (13 ожидается): %s'
                              % taxonomy_plan['topics_reused_names'])

        counters, samples, skipped, title_overwrite_rows = self.build_plan(ok_rows)
        legacy_plan = self.build_legacy_plan(legacy_only_ids, legacy_old_values)
        difficulty_crosstab = self.build_difficulty_crosstab(ok_rows)
        contamination = self.report_topic_contamination(
            taxonomy_plan['topics_reused_names'], set(r['problem_id'] for r in ok_rows))

        self.report(counters, skipped, legacy_plan, len(ok_rows), difficulty_crosstab,
                   contamination)
        self.write_sample_html(samples)
        self.write_json_report(counters, skipped, legacy_plan, taxonomy_plan,
                               difficulty_crosstab, contamination)
        self.export_old_titles_csv(title_overwrite_rows)

        if self.apply_mode:
            self.stdout.write('')
            self.stdout.write('=== ПРИМЕНЯЮ (--apply) ===')
            self.apply_all(ok_rows, legacy_only_ids, legacy_old_values, taxonomy_plan)
        else:
            self.stdout.write('')
            self.stdout.write('--dry-run: в базу ничего не записано.')

    # ------------------------------------------------------------------
    # Загрузка журнала
    # ------------------------------------------------------------------

    def load_rows(self):
        rows = []
        with open(self.parsed_path, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def find_legacy_only(self, jsonl_ids):
        """297 (+ бракованные) задач: старый problem_type есть, обогащения нет."""
        old_ptype = dict(Problem.objects.exclude(problem_type='')
                         .values_list('id', 'problem_type'))
        legacy_only_ids = sorted(set(old_ptype) - jsonl_ids)
        legacy_old_values = {pid: old_ptype[pid] for pid in legacy_only_ids}
        return legacy_only_ids, legacy_old_values

    # ------------------------------------------------------------------
    # Каноническая таксономия v2 — план (без записи в dry-run)
    # ------------------------------------------------------------------

    def plan_taxonomy_objects(self):
        theme_names = taxonomy.theme_names()
        tag_names = taxonomy.all_tags()

        existing_topic_rows = list(Topic.objects.filter(name__in=theme_names)
                                   .values_list('id', 'name', 'is_canonical'))
        by_name = defaultdict(list)
        for pk, name, is_canon in existing_topic_rows:
            by_name[name].append((pk, is_canon))

        reuse_names = []
        create_names = []
        for name in theme_names:
            rows_for_name = by_name.get(name, [])
            already_canonical = any(is_canon for _pk, is_canon in rows_for_name)
            if already_canonical:
                continue  # уже канонический — ни считать, ни трогать не нужно
            if rows_for_name:
                reuse_names.append(name)
            else:
                create_names.append(name)

        existing_tag_names = set(Tag.objects.filter(name__in=tag_names, kind='canonical')
                                 .values_list('name', flat=True))
        tags_to_create = [t for t in tag_names if t not in existing_tag_names]

        return {
            'topics': theme_names,
            'topics_reuse': len(reuse_names),
            'topics_create': len(create_names),
            'topics_reused_names': reuse_names,
            'topics_create_names': create_names,
            'tags': tag_names,
            'tags_reuse': len(tag_names) - len(tags_to_create),
            'tags_create': len(tags_to_create),
            'tags_create_names': tags_to_create,
        }

    def ensure_taxonomy_objects(self):
        """Идемпотентно создаёт/повышает канонические Topic/Tag. Вызывается
        ТОЛЬКО в --apply, внутри общей транзакции."""
        topic_by_id = {}
        for theme in taxonomy.themes():
            theme_id = str(theme['id'])
            name = theme['name']
            topic = (Topic.objects.filter(name=name, is_canonical=True).first()
                    or Topic.objects.filter(name=name).first())
            if topic is None:
                topic = Topic(name=name)
            topic.is_canonical = True
            topic.description = theme.get('description', '') or topic.description
            topic.order = theme['id']
            if not topic.slug:
                topic.slug = self._unique_slug(Topic, name)
            topic.save()
            topic_by_id[theme_id] = topic

        tag_by_id = {}
        for theme in taxonomy.themes():
            for index, tag_name in enumerate(theme['tags'], start=1):
                tag_id = '%d.%d' % (theme['id'], index)
                tag = Tag.objects.filter(name=tag_name).first()
                if tag is None:
                    tag = Tag(name=tag_name,
                              slug=self._unique_slug(Tag, tag_name))
                tag.kind = 'canonical'
                tag.save()
                tag_by_id[tag_id] = tag

        return topic_by_id, tag_by_id

    @staticmethod
    def _unique_slug(model, name):
        base = slugify(name)[:100] or 'x'
        slug = base
        n = 1
        while model.objects.filter(slug=slug).exists():
            n += 1
            slug = '%s-%d' % (base, n)
        return slug

    # ------------------------------------------------------------------
    # Сухой прогон — план по каждому полю
    # ------------------------------------------------------------------

    def build_plan(self, ok_rows):
        counters = {
            'topics': Counter(), 'tags': Counter(), 'title': Counter(),
            'hints': Counter(), 'problem_type': Counter(), 'difficulty': Counter(),
            'answer_consistency': Counter(),
        }
        skipped = Counter()
        samples = defaultdict(list)

        ids = [r['problem_id'] for r in ok_rows]
        rows_by_id = {r['problem_id']: r for r in ok_rows}

        title_overwrite_rows = []  # (id, old_title, category) — для CSV-бэкапа

        for chunk_ids in chunks(ids):
            problems = {p.id: p for p in Problem.objects.filter(id__in=chunk_ids)
                       .prefetch_related('topics', 'tags')
                       .only('id', 'title', 'statement', 'problem_type',
                            'difficulty', 'difficulty_native')}
            hint_counts = Counter(Hint.objects.filter(problem_id__in=chunk_ids)
                                  .values_list('problem_id', flat=True))

            for pid in chunk_ids:
                row = rows_by_id[pid]
                problem = problems.get(pid)
                if problem is None:
                    skipped['id_не_найден_в_базе'] += 1
                    continue

                self._plan_topics(problem, row, counters['topics'], skipped, samples)
                self._plan_tags(problem, row, counters['tags'], skipped, samples)
                self._plan_title(problem, row, counters['title'], samples,
                                 title_overwrite_rows)
                self._plan_hints(problem, row, hint_counts.get(pid, 0),
                                 counters['hints'], samples)
                self._plan_problem_type(problem, row, counters['problem_type'],
                                        skipped, samples)
                self._plan_difficulty(problem, row, counters['difficulty'], samples)
                self._plan_answer_consistency(problem, row,
                                              counters['answer_consistency'], samples)

        return counters, samples, skipped, title_overwrite_rows

    def _plan_topics(self, problem, row, counter, skipped, samples):
        old_names = sorted(t.name for t in problem.topics.all())
        candidate_ids = []
        for tid in [row.get('topic_primary')] + list(row.get('topics_secondary') or []):
            if not tid:
                continue
            tid = str(tid)
            if tid not in taxonomy.theme_ids():
                skipped['тема_невалидный_id'] += 1
                continue
            candidate_ids.append(tid)
        if not candidate_ids:
            counter['без_кандидата'] += 1
            return
        new_names = sorted({taxonomy.theme_name_from_id(t) for t in candidate_ids})
        if old_names == new_names:
            counter['совпало_со_старым'] += 1
        elif old_names:
            counter['заменено'] += 1
        else:
            counter['добавлено_впервые'] += 1
        if random.random() < 0.002:
            samples['topics'].append((problem.id, '; '.join(old_names) or '(пусто)',
                                      '; '.join(new_names)))

    def _plan_tags(self, problem, row, counter, skipped, samples):
        old_names = sorted(t.name for t in problem.tags.all())
        candidate_ids = []
        for tid in row.get('tags') or []:
            tid = str(tid)
            if tid not in taxonomy.tag_ids():
                skipped['тег_невалидный_id'] += 1
                continue
            candidate_ids.append(tid)
        if not candidate_ids:
            counter['без_кандидата'] += 1
            return
        new_names = sorted({taxonomy.tag_name_from_id(t) for t in candidate_ids})
        if old_names == new_names:
            counter['совпало_со_старым'] += 1
        elif old_names:
            counter['заменено'] += 1
        else:
            counter['добавлено_впервые'] += 1
        if random.random() < 0.002:
            samples['tags'].append((problem.id, '; '.join(old_names) or '(пусто)',
                                    '; '.join(new_names)))

    def _plan_title(self, problem, row, counter, samples, title_overwrite_rows):
        candidate = (row.get('title_candidate') or '').strip()
        if not candidate:
            counter['кандидат_пуст'] += 1
            return
        category, _source = classify_and_pick_source(problem.title, problem.statement)
        counter['категория_%s' % category] += 1
        counter['получат_title_candidate'] += 1
        if category in TITLE_OVERWRITE_CATEGORIES:
            counter['получат_боевой_title'] += 1
            title_overwrite_rows.append((problem.id, problem.title, category))
        if random.random() < 0.002:
            samples['title'].append((problem.id, problem.title or '(пусто)', candidate,
                                     category))

    def _plan_hints(self, problem, row, existing_hint_count, counter, samples):
        hints = row.get('hints') or []
        if not hints:
            counter['кандидат_пуст'] += 1
            return
        if existing_hint_count > 0:
            counter['уже_есть_подсказки_пропуск'] += 1
            return
        counter['получат_подсказки'] += 1
        counter['всего_строк_подсказок'] += len(hints)
        if random.random() < 0.003:
            samples['hints'].append((problem.id, len(hints), hints[0][:120]))

    def _plan_problem_type(self, problem, row, counter, skipped, samples):
        candidate = row.get('problem_type')
        if not candidate:
            counter['кандидат_пуст'] += 1
            return
        if candidate not in VALID_PROBLEM_TYPES:
            skipped['problem_type_невалидное_значение'] += 1
            return
        old = problem.problem_type
        if old == candidate:
            counter['совпало_со_старым'] += 1
        elif old:
            counter['изменено_с_непустого'] += 1
        else:
            counter['заполнено_впервые'] += 1
        if old and old != candidate and random.random() < 0.05:
            samples['problem_type'].append((problem.id, old, candidate))

    def _plan_difficulty(self, problem, row, counter, samples):
        candidate = row.get('difficulty')
        if candidate is None:
            counter['кандидат_пуст'] += 1
            return
        if problem.difficulty is None:
            counter['заполнено_впервые'] += 1
            if random.random() < 0.002:
                samples['difficulty'].append((problem.id, '(пусто)', candidate))
            return
        if _is_flat_constant_difficulty(problem.difficulty_native):
            # плоская константа источника при импорте — не per-задачное
            # суждение, наша оценка модели точнее (правка владельца 2026-09-06)
            counter['перезаписано_плоская_константа'] += 1
            if random.random() < 0.01:
                samples['difficulty'].append((problem.id, problem.difficulty, candidate))
        else:
            counter['непустое_боевое_не_трогаем_родная_метка'] += 1

    def _plan_answer_consistency(self, problem, row, counter, samples):
        candidate = row.get('answer_consistency')
        if not candidate:
            counter['кандидат_пуст'] += 1
            return
        counter['заполнено'] += 1

    # ------------------------------------------------------------------
    # 297 (+2) вне прогона обогащения — кроссвок problem_type
    # ------------------------------------------------------------------

    def build_legacy_plan(self, legacy_only_ids, legacy_old_values):
        translated = Counter()
        untranslatable = Counter()
        for pid in legacy_only_ids:
            old = legacy_old_values[pid]
            new = LEGACY_CROSSWALK.get(old)
            if new is None:
                untranslatable[old] += 1
            else:
                translated[(old, new)] += 1
        return {
            'total': len(legacy_only_ids),
            'translated': {'%s -> %s' % k: v for k, v in translated.items()},
            'translated_total': sum(translated.values()),
            'untranslatable': dict(untranslatable),
        }

    # ------------------------------------------------------------------
    # Сложность — перекрёстная таблица «старая × новая» по 9 346 задачам
    # с непустой боевой сложностью (правка владельца 2026-09-06)
    # ------------------------------------------------------------------

    def build_difficulty_crosstab(self, ok_rows):
        candidate_by_id = {r['problem_id']: r.get('difficulty') for r in ok_rows}
        have_diff = dict(Problem.objects.exclude(difficulty__isnull=True)
                         .values_list('id', 'difficulty'))
        covered_ids = sorted(set(have_diff) & set(candidate_by_id))

        native_map = {}
        for chunk_ids in chunks(covered_ids):
            native_map.update(dict(Problem.objects.filter(id__in=chunk_ids)
                                   .values_list('id', 'difficulty_native')))

        overwrite = Counter()
        keep = Counter()
        candidate_empty = 0
        for pid in covered_ids:
            old = have_diff[pid]
            new = candidate_by_id[pid]
            if new is None:
                candidate_empty += 1
                continue
            key = '%s->%s' % (old, new)
            if _is_flat_constant_difficulty(native_map.get(pid)):
                overwrite[key] += 1
            else:
                keep[key] += 1
        return {
            'total_with_existing_difficulty': len(covered_ids),
            'candidate_empty_no_action': candidate_empty,
            'crosstab_overwritten_flat_constant': dict(sorted(overwrite.items())),
            'crosstab_kept_native_label': dict(sorted(keep.items())),
            'overwrite_total': sum(overwrite.values()),
            'keep_total': sum(keep.values()),
        }

    # ------------------------------------------------------------------
    # 13 повышенных тем — примесь задач вне охвата обогащения
    # ------------------------------------------------------------------

    def report_topic_contamination(self, reused_names, covered_ids):
        """Для каждой из 13 переиспользуемых по имени тем — сколько задач
        ВНЕ этого прогона обогащения (включая брак) остались привязаны к ней
        по старым связям, которые слияние не трогает."""
        if not reused_names:
            return {}
        topic_ids = dict(Topic.objects.filter(name__in=reused_names)
                         .values_list('name', 'id'))
        result = {}
        for name, topic_id in topic_ids.items():
            all_pids = set(Problem.objects.filter(topics__id=topic_id)
                           .values_list('id', flat=True))
            outside = all_pids - covered_ids
            result[name] = {'всего_привязано': len(all_pids),
                            'вне_охвата_обогащения': len(outside)}
        return result

    # ------------------------------------------------------------------
    # CSV: старые title у задач, которым перезапишем боевой title
    # ------------------------------------------------------------------

    def export_old_titles_csv(self, title_overwrite_rows):
        if not title_overwrite_rows:
            return
        import csv
        BACKUP_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        old_title_by_id = {pid: (title or '', cat) for pid, title, cat in title_overwrite_rows}

        if BACKUP_CSV_PATH.exists():
            with open(BACKUP_CSV_PATH, encoding='utf-8-sig', newline='') as fh:
                reader = csv.reader(fh)
                header = next(reader)
                rows = list(reader)
        else:
            header = ['problem_id', 'old_topics', 'old_tags', 'old_problem_type']
            rows = []

        if 'old_title' not in header:
            header = header + ['old_title', 'old_title_category']
        existing_ids = {row[0] for row in rows}
        for pid, (old_title, cat) in old_title_by_id.items():
            if str(pid) in existing_ids:
                for row in rows:
                    if row[0] == str(pid):
                        while len(row) < len(header):
                            row.append('')
                        row[-2] = old_title
                        row[-1] = cat
                        break
            else:
                new_row = [str(pid), '', '', ''] + [old_title, cat]
                rows.append(new_row)
                existing_ids.add(str(pid))

        with open(BACKUP_CSV_PATH, 'w', encoding='utf-8-sig', newline='') as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerows(rows)
        self.stdout.write('')
        self.stdout.write('Старые title (%d задач, категории A/B) дописаны в %s'
                          % (len(title_overwrite_rows), BACKUP_CSV_PATH))

    # ------------------------------------------------------------------
    # Отчёт
    # ------------------------------------------------------------------

    def report(self, counters, skipped, legacy_plan, n_ok, difficulty_crosstab,
              contamination):
        self.stdout.write('')
        self.stdout.write('=== Сухой прогон: %d задач к переливке ===' % n_ok)
        for field, counter in counters.items():
            self.stdout.write('')
            self.stdout.write('--- %s ---' % field)
            for key, val in counter.most_common():
                self.stdout.write('  %s: %d' % (key, val))
        self.stdout.write('')
        self.stdout.write('--- пропущено предохранителями ---')
        for key, val in skipped.most_common():
            self.stdout.write('  %s: %d' % (key, val))
        self.stdout.write('')
        self.stdout.write('--- 297 (+2 брак) вне прогона обогащения: кроссвок problem_type ---')
        self.stdout.write('всего: %d' % legacy_plan['total'])
        for k, v in legacy_plan['translated'].items():
            self.stdout.write('  %s: %d' % (k, v))
        self.stdout.write('  переведено итого: %d' % legacy_plan['translated_total'])
        if legacy_plan['untranslatable']:
            self.stdout.write('  ⚠️ БЕЗ соответствия в таблице (останутся как есть): %s'
                              % legacy_plan['untranslatable'])

        self.stdout.write('')
        self.stdout.write('--- сложность: перекрёстная таблица «старая × новая» (%d задач) ---'
                          % difficulty_crosstab['total_with_existing_difficulty'])
        self.stdout.write('  кандидат пуст, действий нет: %d'
                          % difficulty_crosstab['candidate_empty_no_action'])
        self.stdout.write('  ПЕРЕЗАПИСЫВАЕМ (плоская константа источника, итого %d):'
                          % difficulty_crosstab['overwrite_total'])
        for k, v in difficulty_crosstab['crosstab_overwritten_flat_constant'].items():
            self.stdout.write('    %s: %d' % (k, v))
        self.stdout.write('  ОСТАВЛЯЕМ (родная метка источника, итого %d):'
                          % difficulty_crosstab['keep_total'])
        for k, v in difficulty_crosstab['crosstab_kept_native_label'].items():
            self.stdout.write('    %s: %d' % (k, v))

        if contamination:
            self.stdout.write('')
            self.stdout.write('--- 13 повышенных тем: примесь вне охвата обогащения ---')
            for name, nums in sorted(contamination.items(),
                                     key=lambda kv: -kv[1]['вне_охвата_обогащения']):
                self.stdout.write('  %s: всего привязано %d, из них вне охвата обогащения %d'
                                  % (name, nums['всего_привязано'],
                                     nums['вне_охвата_обогащения']))

    def write_json_report(self, counters, skipped, legacy_plan, taxonomy_plan,
                          difficulty_crosstab, contamination):
        out = {
            'counters': {f: dict(c) for f, c in counters.items()},
            'skipped': dict(skipped),
            'legacy_plan': legacy_plan,
            'taxonomy_plan': {k: v for k, v in taxonomy_plan.items()
                              if not k.endswith('_names') or len(v) < 50},
            'difficulty_crosstab': difficulty_crosstab,
            'topic_contamination': contamination,
        }
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.out_path, 'w', encoding='utf-8') as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
        self.stdout.write('')
        self.stdout.write('JSON-отчёт: %s' % self.out_path)

    def write_sample_html(self, samples):
        parts = ['<!doctype html><meta charset="utf-8">',
                '<style>body{font-family:sans-serif;font-size:14px}'
                'table{border-collapse:collapse;margin-bottom:24px}'
                'td,th{border:1px solid #ccc;padding:4px 8px;text-align:left;'
                'vertical-align:top;max-width:420px}</style>']
        for field, rows in samples.items():
            parts.append('<h2>%s (%d примеров)</h2>' % (field, len(rows)))
            picked = rows if len(rows) <= self.sample_size else random.sample(rows, self.sample_size)
            parts.append('<table><tr><th>id</th><th>до</th><th>после</th><th></th></tr>')
            for row in picked:
                cells = ''.join('<td>%s</td>' % _esc(c) for c in row)
                parts.append('<tr>%s</tr>' % cells)
            parts.append('</table>')
        self.sample_html_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.sample_html_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(parts))
        self.stdout.write('HTML-предпросмотр: %s' % self.sample_html_path)

    # ------------------------------------------------------------------
    # Боевая запись (--apply)
    # ------------------------------------------------------------------

    def apply_all(self, ok_rows, legacy_only_ids, legacy_old_values, taxonomy_plan):
        with transaction.atomic():
            topic_by_id, tag_by_id = self.ensure_taxonomy_objects()

            ids = [r['problem_id'] for r in ok_rows]
            rows_by_id = {r['problem_id']: r for r in ok_rows}
            written = Counter()

            for chunk_ids in chunks(ids):
                problems = {p.id: p for p in Problem.objects.filter(id__in=chunk_ids)}
                hint_counts = Counter(Hint.objects.filter(problem_id__in=chunk_ids)
                                      .values_list('problem_id', flat=True))
                to_save = []
                new_hints = []

                for pid in chunk_ids:
                    row = rows_by_id[pid]
                    problem = problems.get(pid)
                    if problem is None:
                        continue
                    changed = False

                    topic_ids = [str(t) for t in
                                [row.get('topic_primary')] + list(row.get('topics_secondary') or [])
                                if t and str(t) in taxonomy.theme_ids()]
                    if topic_ids:
                        problem.topics.clear()
                        problem.topics.add(*{topic_by_id[t] for t in topic_ids})

                    tag_ids = [str(t) for t in row.get('tags') or []
                              if str(t) in taxonomy.tag_ids()]
                    if tag_ids:
                        problem.tags.clear()
                        problem.tags.add(*{tag_by_id[t] for t in tag_ids})

                    title_candidate = (row.get('title_candidate') or '').strip()
                    if title_candidate:
                        cat, source = classify_and_pick_source(problem.title, problem.statement)
                        problem.title_candidate = title_candidate
                        problem.title_source = source
                        if cat in TITLE_OVERWRITE_CATEGORIES:
                            problem.title = title_candidate
                            written['title_боевой_перезаписан'] += 1
                        changed = True

                    hints = row.get('hints') or []
                    if hints and hint_counts.get(pid, 0) == 0:
                        for i, text in enumerate(hints, start=1):
                            new_hints.append(Hint(problem=problem, order=i, text=text))
                        written['hints_задач'] += 1

                    ptype = row.get('problem_type')
                    if ptype in VALID_PROBLEM_TYPES:
                        problem.problem_type = ptype
                        changed = True

                    difficulty = row.get('difficulty')
                    if difficulty is not None and (
                            problem.difficulty is None
                            or _is_flat_constant_difficulty(problem.difficulty_native)):
                        problem.difficulty = difficulty
                        changed = True

                    ac = row.get('answer_consistency')
                    if ac:
                        problem.answer_consistency = ac
                        changed = True

                    if changed:
                        to_save.append(problem)
                        written['задач_изменено'] += 1

                Problem.objects.bulk_update(
                    to_save,
                    ['title', 'title_candidate', 'title_source', 'problem_type',
                     'difficulty', 'answer_consistency'])
                if new_hints:
                    Hint.objects.bulk_create(new_hints)
                    written['подсказок_строк'] += len(new_hints)

            # 297 (+2) вне прогона обогащения — только кроссвок problem_type
            legacy_translated = 0
            for pid in legacy_only_ids:
                new_value = LEGACY_CROSSWALK.get(legacy_old_values[pid])
                if new_value is None:
                    continue
                Problem.objects.filter(id=pid).update(problem_type=new_value)
                legacy_translated += 1

            self.stdout.write('задач изменено (обогащение): %d' % written['задач_изменено'])
            self.stdout.write('  из них боевой title перезаписан (категории A/B): %d'
                              % written['title_боевой_перезаписан'])
            self.stdout.write('задач с подсказками: %d (строк: %d)'
                              % (written['hints_задач'], written['подсказок_строк']))
            self.stdout.write('задач переведено кроссвоком (вне прогона): %d' % legacy_translated)

            self.print_invariants()

    def print_invariants(self):
        self.stdout.write('')
        self.stdout.write('=== Инварианты после записи ===')
        total = Problem.objects.count()
        have_topic = Problem.objects.filter(topics__isnull=False).distinct().count()
        have_tags = Problem.objects.filter(tags__isnull=False).distinct().count()
        have_title_candidate = Problem.objects.exclude(title_candidate='').count()
        have_hints = Hint.objects.values('problem_id').distinct().count()
        have_ac = Problem.objects.exclude(answer_consistency='').count()

        pt_dist_active = Counter(
            Problem.objects.exclude(status__in=['duplicate', 'hidden'])
            .exclude(problem_type='').values_list('problem_type', flat=True))
        pt_dist_all = Counter(Problem.objects.exclude(problem_type='')
                              .values_list('problem_type', flat=True))
        diff_dist = Counter(Problem.objects.exclude(difficulty__isnull=True)
                            .values_list('difficulty', flat=True))

        self.stdout.write('задач в базе всего = %d' % total)
        self.stdout.write('получили тему = %d' % have_topic)
        self.stdout.write('получили теги = %d' % have_tags)
        self.stdout.write('получили title_candidate = %d' % have_title_candidate)
        self.stdout.write('получили подсказки (задач) = %d' % have_hints)
        self.stdout.write('получили answer_consistency = %d' % have_ac)
        self.stdout.write('распределение problem_type СРЕДИ АКТИВНЫХ (не duplicate/hidden) '
                          '— значений: %d — %s' % (len(pt_dist_active), dict(pt_dist_active)))
        self.stdout.write('распределение problem_type ПО ВСЕЙ БАЗЕ — значений: %d — %s'
                          % (len(pt_dist_all), dict(pt_dist_all)))
        self.stdout.write('распределение сложности — значений: %d — %s'
                          % (len(diff_dist), dict(diff_dist)))
        non_8_active = {k: v for k, v in pt_dist_active.items()
                        if k not in VALID_PROBLEM_TYPES}
        if non_8_active:
            self.stdout.write('⚠️ среди активных задач остались НЕ-v2 значения problem_type: %s'
                              % non_8_active)
        else:
            self.stdout.write('✓ среди активных задач problem_type — ровно значения из 8 v2 '
                              '(легаси не осталось)')


def _esc(value):
    return (str(value).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))
