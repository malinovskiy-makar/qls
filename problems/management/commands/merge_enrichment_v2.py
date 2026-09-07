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

Сессия 2026-09-07 добавила остальные поля журнала (миграция 0056):

  8. Особенности — связь `ProblemFeature` (двенадцать штук, канон в
     `problems/enrich/features.py`), у каждой видно, кто поставил. Витрина
     каталога `Problem.features` из трёх ключей ПЕРЕСЧИТЫВАЕТСЯ из связи
     единственной функцией `features.catalog_view()`, своего факта не хранит.
     Шесть кодовых особенностей считаются по ВСЕМ активным задачам, а не по
     составу прогона: код не зависит от того, обогащалась задача или нет.
  9. `econ_concepts` — связь со справочником `EconConcept`, наполняемым из
     `data/econ_terms.json`. Понятия вне словаря складываются в
     `concepts_offlist` как диагностика и ученику не показываются.
 10. Тексты (`given`, `find`, `plot`, `difficulty_note`, `text_quality_note`),
     короткие значения (`task_nature`, `text_quality`, `topic_confidence`) и
     `search_queries` кладутся в одноимённые поля. Пустой кандидат непустое
     боевое не затирает, значение вне справочника — не пишется, задача уходит
     в список на разбор.
 11. `content_status` пересуживается по `text_quality`/`problem_type`, но
     ТОЛЬКО в сторону ухудшения: `content_cleanup` сильнее модели.
 12. `character` производен от `task_nature` (`features.character_for()`).
 13. Активные задачи, которых во втором прогоне нет вовсе, берут данные
     ПЕРВОГО прогона с пометкой `enrichment_source='run1'` — их видно и можно
     допрогнать. Данные run1 никогда не перекрывают данные run2.

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

from django.utils import timezone

from problems.enrich import features as feat
from problems.enrich import layout, taxonomy
from problems.enrich.title_rules import classify_and_pick_source
from problems.management.commands.glm_enrich_run import (
    load_solvehub_check_type_index, normalize_legacy_problem_type)
from problems.models import (EconConcept, Hint, OlympiadRef, Problem,
                             ProblemFeature, ProblemFigure, ProblemPart, Tag,
                             Topic)

PARSED_PATH = Path('reports/enrich_pilot/run2_parsed.jsonl')
RUN1_PARSED_PATH = Path('reports/enrich_pilot/run_parsed.jsonl')

#: Чем метится `enrichment_source` у задач из основного журнала. Значение по
#: умолчанию сохраняет прежнее поведение байт в байт; переопределяется
#: флагом `--source-tag` (07.09.2026, журнал третьего прогона).
DEFAULT_SOURCE_TAG = 'run2'

#: Метка задач, подмешанных из журнала ПЕРВОГО прогона (`--parsed-run1`).
#: От `--source-tag` не зависит: они и правда оттуда.
RUN1_SOURCE_TAG = 'run1'
# Задачи этих статусов раскладку не получают: дубль схлопнут, скрытое убрано
# руками — ни то ни другое ученику не показывается ни при каких фильтрах.
INACTIVE_STATUSES = ('duplicate', 'hidden')
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
        parser.add_argument(
            '--parsed-run1', type=str, default=str(RUN1_PARSED_PATH),
            help='Журнал ПЕРВОГО прогона: из него берутся активные задачи, '
                 'которых во втором прогоне нет вовсе.')
        parser.add_argument(
            '--no-run1', action='store_true',
            help='Не подмешивать данные первого прогона.')
        parser.add_argument(
            '--source-tag', type=str, default=DEFAULT_SOURCE_TAG,
            help='Чем метить `enrichment_source` у задач из ОСНОВНОГО журнала '
                 '(по умолчанию «%s» — поведение прежнее). ⚠️ Метка '
                 'вычислялась жёстко из двух вариантов, run1/run2: журнал '
                 'третьего прогона она пометила бы как run2, и в банке '
                 'осталась бы неправда — поле утверждало бы, что данные из '
                 'второго прогона. Прослеживаемость после этого не '
                 'восстановить ничем. Задачи, подмешанные из журнала первого '
                 'прогона (--parsed-run1), метятся «run1» независимо от '
                 'этого флага: они и правда оттуда.' % DEFAULT_SOURCE_TAG)

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        self.apply_mode = options['apply']
        self.parsed_path = Path(options['parsed'])
        self.sample_html_path = Path(options['sample_html'])
        self.out_path = Path(options['out'])
        self.sample_size = options['sample_size']
        self.run1_path = Path(options['parsed_run1'])
        self.use_run1 = not options['no_run1']
        self.source_tag = options['source_tag']

        rows = self.load_rows()
        ok_rows = [r for r in rows if not r.get('defect')]
        defect_rows = [r for r in rows if r.get('defect')]
        self.stdout.write('строк в журнале: %d (брак: %d, к переливке: %d)'
                          % (len(rows), len(defect_rows), len(ok_rows)))

        jsonl_ids = {r['problem_id'] for r in rows}
        legacy_only_ids, legacy_old_values = self.find_legacy_only(jsonl_ids)

        # Ветка run1: активные задачи, которых во втором прогоне нет вовсе.
        # Их пометили `needs_fix` ПО ДАННЫМ ПЕРВОГО прогона и потому не взяли
        # во второй — замкнутый круг, который разрывает допрогон. До него
        # данные первого прогона всё же лучше пустоты, но помечены как run1.
        covered_by_run2 = {r['problem_id'] for r in ok_rows}
        self.run1_rows = (self.load_run1_rows(covered_by_run2)
                          if self.use_run1 else [])
        if self.run1_rows:
            self.stdout.write(
                'из первого прогона (активные вне run2): %d задач'
                % len(self.run1_rows))

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

        counters, samples, skipped, title_overwrite_rows = self.build_plan(
            ok_rows, self.run1_rows)
        code_plan = self.plan_code_features()
        legacy_plan = self.build_legacy_plan(legacy_only_ids, legacy_old_values)
        difficulty_crosstab = self.build_difficulty_crosstab(ok_rows)
        contamination = self.report_topic_contamination(
            taxonomy_plan['topics_reused_names'], set(r['problem_id'] for r in ok_rows))

        self.report(counters, skipped, legacy_plan, len(ok_rows), difficulty_crosstab,
                   contamination)
        self.report_layout(counters, skipped, code_plan)
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

    def load_run1_rows(self, run2_ok_ids):
        """Строки первого прогона для АКТИВНЫХ задач без годных данных run2.

        Данные run1 слабее (без чтения решений, другой уровень рассуждения),
        поэтому они никогда не перекрывают run2: множества не пересекаются по
        построению — берутся только id, для которых во втором прогоне НЕТ
        годной строки.

        ⚠️ «Годной», а не «никакой». Задача, забракованная во втором прогоне
        (`defect: true`), данных из него не получила вовсе — и если бы мы
        считали её покрытой, она осталась бы с легаси-типом навсегда. Именно
        так #7468 сохранила «тест: один ответ» и сорвала инвариант «ноль
        значений вне восьми» на первой записи 07.09.2026.
        """
        if not self.run1_path.exists():
            self.stdout.write(self.style.WARNING(
                'журнала первого прогона нет: %s — ветка run1 пропущена'
                % self.run1_path))
            return []
        active_ids = set(Problem.objects
                         .exclude(status__in=INACTIVE_STATUSES)
                         .values_list('id', flat=True))
        wanted = active_ids - run2_ok_ids
        rows = []
        with open(self.run1_path, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                pid = row.get('problem_id')
                if pid is None or int(pid) not in wanted or row.get('defect'):
                    continue
                row['problem_id'] = int(pid)
                rows.append(row)
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

    def build_plan(self, ok_rows, run1_rows=()):
        counters = {
            'topics': Counter(), 'tags': Counter(), 'title': Counter(),
            'hints': Counter(), 'problem_type': Counter(), 'difficulty': Counter(),
            'answer_consistency': Counter(),
            # раскладка 07.09.2026
            'given': Counter(), 'find': Counter(), 'plot': Counter(),
            'difficulty_note': Counter(), 'text_quality_note': Counter(),
            'task_nature': Counter(), 'text_quality': Counter(),
            'topic_confidence': Counter(), 'search_queries': Counter(),
            'econ_concepts': Counter(), 'concepts_offlist': Counter(),
            'features_модель': Counter(), 'content_status': Counter(),
            'источник': Counter(),
        }
        skipped = Counter()
        samples = defaultdict(list)
        self.invalid_value_ids = defaultdict(list)   # поле -> [(id, значение)]
        self.concept_lookup = layout.concept_lookup(layout.load_terms())
        # ⚠️ Журнал ПЕРВОГО прогона несёт отменённое значение
        # `problem_type='открытый_ответ'` (557 активных задач на 07.09.2026).
        # Схема v2 его не содержит, и без нормализации эти задачи остались бы
        # вовсе без типа — то есть вне каталога и вне инварианта «ноль
        # активных без problem_type». Правило разведения — то же, что у
        # прогона (`glm_enrich_run.normalize_legacy_problem_type`, §5.5).
        self.check_types = load_solvehub_check_type_index()

        all_rows = list(ok_rows) + [dict(r, _run1=True) for r in run1_rows]
        ids = [r['problem_id'] for r in all_rows]
        rows_by_id = {r['problem_id']: r for r in all_rows}

        title_overwrite_rows = []  # (id, old_title, category) — для CSV-бэкапа

        for chunk_ids in chunks(ids):
            problems = {p.id: p for p in Problem.objects.filter(id__in=chunk_ids)
                       .prefetch_related('topics', 'tags')
                       .only('id', 'title', 'statement', 'problem_type',
                            'difficulty', 'difficulty_native', 'content_status',
                            'given', 'find', 'plot', 'difficulty_note',
                            'text_quality_note', 'task_nature', 'text_quality',
                            'topic_confidence', 'search_queries')}
            hint_counts = Counter(Hint.objects.filter(problem_id__in=chunk_ids)
                                  .values_list('problem_id', flat=True))

            for pid in chunk_ids:
                row = rows_by_id[pid]
                problem = problems.get(pid)
                if problem is None:
                    skipped['id_не_найден_в_базе'] += 1
                    continue

                counters['источник'][
                    'run1' if row.get('_run1') else 'run2'] += 1
                self._plan_scalars(problem, row, counters, skipped)
                self._plan_concepts(problem, row, counters)
                self._plan_features_model(problem, row, counters['features_модель'])
                self._plan_content_status(problem, row, counters['content_status'])
                # ⚠️ Ветка run1 проходит ВСЕ планировщики. «run1 не перекрывает
                # run2» значит «не пишет поверх данных второго прогона», а не
                # «не пишет вовсе»: у этих задач данных run2 нет ни одного, и
                # без темы с типом они выпали бы из инвариантов и из каталога.
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

    # ── раскладка 07.09.2026 ─────────────────────────────────────────

    def _plan_scalars(self, problem, row, counters, skipped):
        """Тексты, короткие значения из справочников и `search_queries`."""
        values, invalid = layout.row_scalar_fields(row)
        for field, value in invalid.items():
            skipped['%s_невалидное_значение' % field] += 1
            self.invalid_value_ids[field].append((problem.id, value))
        for field in ('given', 'find', 'plot', 'difficulty_note',
                      'text_quality_note', 'task_nature', 'text_quality',
                      'topic_confidence', 'search_queries'):
            counter = counters[field]
            if field not in values:
                counter['кандидат_пуст'] += 1
                continue
            old = getattr(problem, field)
            if old == values[field]:
                counter['совпало_со_старым'] += 1
            elif old:
                counter['заменено'] += 1
            else:
                counter['заполнено_впервые'] += 1

    def _plan_concepts(self, problem, row, counters):
        found, missing = layout.match_concepts(
            row.get('econ_concepts'), self.concept_lookup)
        if found:
            counters['econ_concepts']['задач_с_понятиями'] += 1
            counters['econ_concepts']['связей_всего'] += len(found)
        else:
            counters['econ_concepts']['кандидат_пуст'] += 1
        # Понятие, которого нет в словаре, — не ошибка модели, а дыра в
        # словаре: складываем в диагностику, ученику не показываем.
        offlist = list(missing) + list(row.get('concepts_offlist') or [])
        if offlist:
            counters['concepts_offlist']['задач'] += 1
            counters['concepts_offlist']['терминов_всего'] += len(offlist)

    def _plan_features_model(self, problem, row, counter):
        keys = [k for k in (row.get('features_1') or []) if k in feat.MODEL_KEYS]
        bad = [k for k in (row.get('features_1') or []) if k not in feat.MODEL_KEYS]
        if bad:
            counter['невалидная_особенность'] += len(bad)
            self.invalid_value_ids['features_1'].append((problem.id, ','.join(bad)))
        if keys:
            counter['задач_с_особенностью'] += 1
            counter['связей_всего'] += len(keys)
        else:
            counter['кандидат_пуст'] += 1

    def _plan_content_status(self, problem, row, counter):
        new_value = layout.content_status_for(
            problem.content_status, row.get('text_quality'), row.get('problem_type'))
        if new_value == problem.content_status:
            counter['без_изменений'] += 1
        else:
            counter['%s -> %s' % (problem.content_status, new_value)] += 1

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

    def _problem_type_candidate(self, problem, row):
        """Кандидат на `problem_type` с разведением легаси-значения."""
        candidate = row.get('problem_type')
        candidate, was_legacy = normalize_legacy_problem_type(
            candidate, self.check_types.get(problem.id))
        return candidate, was_legacy

    def _plan_problem_type(self, problem, row, counter, skipped, samples):
        candidate, was_legacy = self._problem_type_candidate(problem, row)
        if was_legacy:
            counter['легаси_открытый_ответ_разведён'] += 1
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

    # ------------------------------------------------------------------
    # Кодовые особенности — по ВСЕМ активным задачам
    # ------------------------------------------------------------------

    def iter_code_features(self, only_active=False):
        """(id задачи, множество кодовых особенностей).

        Считается по данным банка, а не по составу прогона: обогащалась
        задача или нет, наличие таблицы в её условии от этого не зависит.
        По умолчанию идёт по ВСЕЙ базе — дубль, которого завтра «раздублируют»,
        иначе остался бы без особенностей молча. `only_active` нужен отчёту:
        порог показа в каталоге считается от активных задач.
        """
        active = Problem.objects.all()
        if only_active:
            active = active.exclude(status__in=INACTIVE_STATUSES)
        figure_ids = set(
            Problem.objects.filter(figures__isnull=False)
            .values_list('id', flat=True))
        rubric_ids = set(
            Problem.objects.filter(rubrics__isnull=False)
            .values_list('id', flat=True))
        olympiad_ids = set(OlympiadRef.objects.values_list('problem_id', flat=True))
        # Картинка, привязанная к РЕШЕНИЮ, — код-доказательство особенности
        # «Графическое решение»: модель её не видит вовсе.
        solution_figure_ids = set(
            ProblemFigure.objects.filter(source_field='solution')
            .values_list('problem_id', flat=True))
        parts = defaultdict(list)
        for pid, text in ProblemPart.objects.values_list('problem_id', 'statement'):
            parts[pid].append(text)
        for pid, statement in active.values_list('id', 'statement').iterator(
                chunk_size=2000):
            yield pid, layout.code_features(
                statement, parts.get(pid) or [],
                has_figure=pid in figure_ids,
                parts_count=len(parts.get(pid) or []),
                has_rubric=pid in rubric_ids,
                has_olympiad_ref=pid in olympiad_ids,
                has_solution_figure=pid in solution_figure_ids)

    def plan_code_features(self):
        counter = Counter()
        total = 0
        for _pid, keys in self.iter_code_features(only_active=True):
            total += 1
            for key in keys:
                counter[key] += 1
        counter['_активных'] = total
        return counter

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

    def report_layout(self, counters, skipped, code_plan):
        """Отчёт по полям, добавленным раскладкой 07.09.2026."""
        self.stdout.write('')
        self.stdout.write('=== Раскладка остальных полей журнала ===')
        self.stdout.write('источник строк: %s'
                          % dict(counters['источник']))
        for field in ('given', 'find', 'plot', 'difficulty_note',
                      'text_quality_note', 'task_nature', 'text_quality',
                      'topic_confidence', 'search_queries'):
            self.stdout.write('  --- %s ---' % field)
            for name, value in counters[field].most_common():
                self.stdout.write('    %-34s %6d' % (name, value))
        self.stdout.write('  --- econ_concepts ---')
        for name, value in counters['econ_concepts'].most_common():
            self.stdout.write('    %-34s %6d' % (name, value))
        self.stdout.write('  --- concepts_offlist (диагностика) ---')
        for name, value in counters['concepts_offlist'].most_common():
            self.stdout.write('    %-34s %6d' % (name, value))
        self.stdout.write('  --- особенности от модели ---')
        for name, value in counters['features_модель'].most_common():
            self.stdout.write('    %-34s %6d' % (name, value))
        self.stdout.write('  --- content_status (только ухудшение) ---')
        for name, value in counters['content_status'].most_common():
            self.stdout.write('    %-34s %6d' % (name, value))

        total = code_plan.get('_активных', 0)
        self.stdout.write('')
        self.stdout.write('=== Особенности от кода (все %d активных задач) ==='
                          % total)
        for key in feat.CODE_KEYS:
            n = code_plan.get(key, 0)
            share = (100.0 * n / total) if total else 0.0
            gate = ''
            if key in feat.COVERAGE_GATED and share < feat.MIN_CATALOG_COVERAGE * 100:
                gate = '  ← в фильтре каталога СКРЫТА (порог %.0f %%)' % (
                    feat.MIN_CATALOG_COVERAGE * 100)
            self.stdout.write('  %-34s %6d  (%.2f %%)%s' % (key, n, share, gate))

        if self.invalid_value_ids:
            self.stdout.write('')
            self.stdout.write('=== Значения вне справочника — задачи на разбор ===')
            for field, pairs in sorted(self.invalid_value_ids.items()):
                self.stdout.write('  %s: %d задач, первые пять: %s'
                                  % (field, len(pairs), pairs[:5]))

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
            concept_by_name = self.ensure_concepts()

            all_rows = list(ok_rows) + [dict(r, _run1=True) for r in self.run1_rows]
            ids = [r['problem_id'] for r in all_rows]
            rows_by_id = {r['problem_id']: r for r in all_rows}
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

                    changed = self._apply_scalars(problem, row, written) or changed
                    self._apply_concepts(problem, row, concept_by_name, written)
                    new_status = layout.content_status_for(
                        problem.content_status, row.get('text_quality'),
                        row.get('problem_type'))
                    if new_status != problem.content_status:
                        problem.content_status = new_status
                        written['content_status_ухудшен'] += 1
                        changed = True
                    character = feat.character_for(row.get('task_nature'))
                    if character and problem.character != character:
                        problem.character = character
                        changed = True
                    source_tag = (RUN1_SOURCE_TAG if row.get('_run1')
                                  else self.source_tag)
                    if problem.enrichment_source != source_tag:
                        problem.enrichment_source = source_tag
                        changed = True
                    problem.enrichment_at = timezone.now()

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

                    ptype, _legacy = self._problem_type_candidate(problem, row)
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
                     'difficulty', 'answer_consistency',
                     'given', 'find', 'plot', 'difficulty_note',
                     'text_quality_note', 'task_nature', 'text_quality',
                     'topic_confidence', 'search_queries', 'concepts_offlist',
                     'content_status', 'character',
                     'enrichment_source', 'enrichment_at'])
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

            self.apply_features(all_rows, written)
            self.print_invariants()

    # ------------------------------------------------------------------
    # Применение раскладки 07.09.2026
    # ------------------------------------------------------------------

    def ensure_concepts(self):
        """Справочник понятий из `data/econ_terms.json`. Идемпотентно."""
        terms = layout.load_terms()
        existing = dict(EconConcept.objects.values_list('canonical', 'id'))
        new_rows = [EconConcept(canonical=name, section=section)
                    for name, section in terms.items() if name not in existing]
        if new_rows:
            EconConcept.objects.bulk_create(new_rows, batch_size=500)
            self.stdout.write('понятий заведено в справочник: %d' % len(new_rows))
        return {c.canonical: c for c in EconConcept.objects.all()}

    def _apply_scalars(self, problem, row, written):
        values, _invalid = layout.row_scalar_fields(row)
        changed = False
        for field, value in values.items():
            if getattr(problem, field) != value:
                setattr(problem, field, value)
                written['поле_%s' % field] += 1
                changed = True
        return changed

    def _apply_concepts(self, problem, row, concept_by_name, written):
        found, missing = layout.match_concepts(
            row.get('econ_concepts'), self.concept_lookup)
        if found:
            problem.econ_concepts.set([concept_by_name[n] for n in found])
            written['понятий_связей'] += len(found)
        offlist = list(dict.fromkeys(
            list(missing) + list(row.get('concepts_offlist') or [])))
        if offlist and problem.concepts_offlist != offlist:
            problem.concepts_offlist = offlist

    def apply_features(self, all_rows, written):
        """Особенности: модельные из журналов, кодовые по всем активным.

        Пишется связь `ProblemFeature`, и ТОЛЬКО ПОТОМ из неё пересчитывается
        витрина `Problem.features` — одной функцией `features.catalog_view()`.
        Обратный порядок означал бы второй источник правды.

        ⚠️ **Прогон отвечает только за задачи СВОЕГО журнала** (починено
        07.09.2026). Кодовая половина считается по всем активным задачам —
        таблица в условии есть или её нет, от состава прогона это не зависит.
        А модельная у задачи ВНЕ журнала берётся из того, что уже стоит в
        базе: прогон её не видел и сказать о ней нечего.

        Пока журнал был полным (боевой run2 на 37 тысячах), разницы не было:
        в журнале была почти каждая задача, и `.get(pid, set())` почти всегда
        попадал. Допрогон подал журнал на 1 740 задач — и прежний код снял
        модельные особенности у всех остальных: 18 771 связь `source='model'`
        превратилась в 1 019, задач с особенностями стало 21 518 вместо
        27 517. Стережёт `problems/tests/test_merge_features_scope.py`.
        """
        feature_by_key = layout.ensure_features()
        key_by_fid = {f.id: k for k, f in feature_by_key.items()}
        in_journal = {row['problem_id'] for row in all_rows}
        model_keys_by_id = {}
        for row in all_rows:
            keys = [k for k in (row.get('features_1') or []) if k in feat.MODEL_KEYS]
            if keys:
                model_keys_by_id[row['problem_id']] = set(keys)

        existing = defaultdict(dict)
        for pid, fid, src in ProblemFeature.objects.values_list(
                'problem_id', 'feature_id', 'source'):
            existing[pid][fid] = src

        to_create, to_update, view_updates = [], [], []
        drop_ids = []
        for pid, code_keys in self.iter_code_features():
            if pid in in_journal:
                model_keys = model_keys_by_id.get(pid, set())
            else:
                # Задачи в журнале нет — модельную половину оставляем как есть.
                model_keys = {
                    key_by_fid[fid] for fid, src in existing.get(pid, {}).items()
                    if src in (feat.BY_MODEL, feat.BY_BOTH) and fid in key_by_fid
                }
            wanted = layout.merge_feature_sources(model_keys, code_keys)
            have = existing.get(pid, {})
            wanted_by_fid = {feature_by_key[k].id: src for k, src in wanted.items()}
            for fid, src in wanted_by_fid.items():
                if fid not in have:
                    to_create.append(ProblemFeature(
                        problem_id=pid, feature_id=fid, source=src))
                elif have[fid] != src:
                    to_update.append((pid, fid, src))
            drop_ids += [(pid, fid) for fid in have if fid not in wanted_by_fid]
            view_updates.append((pid, feat.catalog_view(wanted)))

        if to_create:
            ProblemFeature.objects.bulk_create(to_create, batch_size=1000)
        for pid, fid, src in to_update:
            ProblemFeature.objects.filter(problem_id=pid, feature_id=fid).update(source=src)
        for chunk in chunks([pid for pid, _fid in drop_ids]):
            pairs = {(p, f) for p, f in drop_ids if p in set(chunk)}
            for pid, fid in pairs:
                ProblemFeature.objects.filter(problem_id=pid, feature_id=fid).delete()

        # витрина каталога — из связи, пакетами
        by_id = {pid: view for pid, view in view_updates}
        for chunk_ids in chunks(list(by_id)):
            objs = list(Problem.objects.filter(id__in=chunk_ids).only('id', 'features'))
            dirty = []
            for obj in objs:
                view = sorted(by_id[obj.id])
                if sorted(obj.features or []) != view:
                    obj.features = view
                    dirty.append(obj)
            if dirty:
                Problem.objects.bulk_update(dirty, ['features'])
                written['витрина_обновлена'] += len(dirty)

        written['особенностей_связей_создано'] += len(to_create)
        written['особенностей_связей_снято'] += len(drop_ids)
        self.stdout.write(
            'особенности: связей создано %d, снято %d, витрина обновлена у %d задач'
            % (len(to_create), len(drop_ids), written['витрина_обновлена']))

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
