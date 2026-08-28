# -*- coding: utf-8 -*-
"""С13 «Диагностика всего корпуса» — одиннадцать чисел Уровня 0.

Список чисел и их формулировки взяты дословно из `EMBEDDINGS.md`, раздел
«Диагностические числа, которые считаются здесь же». Команда **только читает**:
ни одного `.save()`/`.update()` здесь нет и быть не должно — устаревание
считается по артефактам фикс-паков, а не по правке базы.

Запуск:
    manage.py corpus_diagnostics                  # всё, отчёт в JSON
    manage.py corpus_diagnostics --skip-external  # без неимпортированных источников

⚠️ Бюджет обрезки (500 символов) — не именованная константа, а литерал внутри
`problem_to_text` (`build_embeddings.py`). Сменится он — число «доля потерянного
текста» устареет молча. Здесь он продублирован осознанно и помечен.
"""
import glob
import json
import os
import re
import statistics
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from problems import econ_terms
from problems.embedding_config import CANONICAL_TAG_NAMES  # noqa: F401 (симметрия отчёта)
from problems.models import (
    AiUsageLog, Assignment, Collection, DuplicateCandidate, Problem, Source,
)

#: Бюджет условия в отпечатке. Литерал из problem_to_text — см. шапку.
STATEMENT_BUDGET = 500
#: Бюджет суммарного текста подпунктов — там же.
PARTS_BUDGET = 500

#: Служебный источник: фикстуры рендерера, не содержание банка.
FIXTURE_SOURCE = 'Служебное: фикстуры рендерера (не публиковать)'

OUT_DIR = 'reports/embeddings_scaleup'

#: Токен слова: кириллица и латиница. Цифры и знаки формул отбрасываем —
#: словарь терминов состоит из слов, а не из выражений.
RE_WORD = re.compile(r'[а-яёa-z]+')
RE_DIGIT = re.compile(r'\d')
#: Имя команды LaTeX вместе с обратной косой: `\frac`, `\begin`, `\hline`.
#: Банк написан на LaTeX, и без этого фильтра топ частых «слов» корпуса
#: возглавляют frac, sqrt, begin, hline, cdot и cases — то есть разметка,
#: а не жаргон. Содержимое скобок при этом остаётся: внутри `\text{}`
#: лежит настоящий русский текст.
RE_TEX_COMMAND = re.compile(r'\\[a-zA-Z]+')

#: Служебные слова, которые заведомо не экономический жаргон. Список короткий
#: намеренно: чем он длиннее, тем сильнее мы решаем за читателя, что считать
#: термином. Всё остальное уходит в отчёт как есть, с пометкой.
STOPWORDS = frozenset("""
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы
по только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг
ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом
себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам
чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого
какой совсем ним здесь этом один почти мой тем чтобы нее сейчас были куда зачем
всех никогда можно при наконец два об другой хоть после над больше тот через
эти нас про всего них какая много разве три эту моя впрочем хорошо свою этой
перед иногда лучше чуть том нельзя такой им более всегда конечно всю между
это если то как при этом также однако при этом равно равна равен которые
которая который которых каждый каждая каждое всей всем всеми это этих
""".split())


def _norm(text):
    """Нижний регистр, ё→е — иначе «объём» и «объем» разные строки."""
    return (text or '').lower().replace('ё', 'е')


def _tokens(text):
    return RE_WORD.findall(RE_TEX_COMMAND.sub(' ', _norm(text)))


def _lost_fraction(length, budget):
    """Доля текста, не попавшая в отпечаток."""
    return (length - budget) / length if length > budget else 0.0


def _share(part, whole):
    return round(100.0 * part / whole, 2) if whole else 0.0


class Command(BaseCommand):
    help = 'С13: одиннадцать диагностических чисел Уровня 0 (только чтение).'

    def add_arguments(self, parser):
        parser.add_argument('--skip-external', action='store_true',
                            help='Не трогать неимпортированные источники (Фаза 3).')

    # ------------------------------------------------------------------ #

    def handle(self, *args, **options):
        report = {}
        report['корпус'] = self._totals()
        report['провенанс_векторов'] = self._provenance()
        report['устаревшие_векторы'] = self._staleness_audit()
        report['длина_условия'] = self._lengths()
        report['длина_подпунктов'] = self._part_lengths()
        report['поля_обогащения'] = self._enrichment()
        report['темы'] = self._topics()
        report['эталонные_наборы'] = self._reference_sets()
        report['журнал_модели'] = self._ai_log()
        report['цифры_в_условии'] = self._digits()
        report['словарь_терминов'] = self._dictionary()
        report['по_источникам'] = self._per_source()
        if not options['skip_external']:
            report['неимпортированные_источники'] = self._external()

        os.makedirs(OUT_DIR, exist_ok=True)
        path = os.path.join(OUT_DIR, 'corpus_diagnostics_c13.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        self.stdout.write(self.style.SUCCESS(f'Готово: {path}'))
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2)[:2000])

    # ------------------------------------------------------------------ #

    def _real(self):
        """Банк без служебных фикстур рендерера."""
        return Problem.objects.exclude(source_references__source__name=FIXTURE_SOURCE)

    def _totals(self):
        total = Problem.objects.count()
        fixtures = total - self._real().distinct().count()
        return {
            'задач_всего': total,
            'служебных_фикстур': fixtures,
            'содержательных': total - fixtures,
            'опубликованных': Problem.objects.filter(status='published').count(),
            'подпунктов': sum(p for p in Problem.objects.annotate(
                n=Count('parts')).values_list('n', flat=True)),
            'источников': Source.objects.count(),
        }

    def _provenance(self):
        qs = Problem.objects.all()
        with_vec = qs.exclude(embedding__isnull=True)
        return {
            'с_эмбеддингом': with_vec.count(),
            'без_эмбеддинга': qs.filter(embedding__isnull=True).count(),
            'провенанс_проставлен': qs.exclude(embedding_built_at__isnull=True).count(),
            'легаси_версия': qs.filter(embedding_version=0).count(),
            'с_хешем_текста': qs.exclude(embedding_source_hash='').count(),
            'сборки': dict(Counter(
                qs.exclude(embedding_model_build='')
                .values_list('embedding_model_build', flat=True))),
        }

    # --- Фаза 1: ретроспективное устаревание ----------------------------- #

    MATEK_BACKUP = 'reports/corpus_converter_scaleup/matek_fixed_backup.json'
    AA_LOG = 'materials/corpus_sources/aa_fixed_20260821/apply_log_20260822.json'

    def _staleness_audit(self):
        """Сколько векторов устарело из-за правок ПОСЛЕ пересчёта 2026-07-04.

        Считается по артефактам, у которых есть и старый текст, и дата
        применения, — иначе датировать правку нечем. Устаревание определяется
        по ОТПЕЧАТКУ (`corpus_diagnostics.fingerprint_changed`), а не по
        «текст поменялся»: solution и answer в отпечаток не входят.
        """
        from problems import corpus_diagnostics as diag
        from problems import embedding_provenance as prov

        result = {}

        # --- МатЭк: бэкап хранит состояние ДО фикс-пака -------------------
        matek_stale, matek_touched = set(), set()
        if os.path.exists(self.MATEK_BACKUP):
            with open(self.MATEK_BACKUP, encoding='utf-8') as f:
                records = json.load(f)['problems']
            for rec in records:
                problem = (Problem.objects
                           .filter(pk=rec['problem_id'])
                           .prefetch_related('parts', 'topics', 'skills', 'tags')
                           .first())
                if problem is None:
                    continue
                overrides = {}
                for field in ('title', 'statement'):
                    if (rec.get(field) or '') != (getattr(problem, field) or ''):
                        overrides[field] = rec.get(field) or ''
                old_parts = {p['id']: (p.get('statement') or '')
                             for p in rec.get('parts', [])}
                now_parts = {p.pk: (p.statement or '') for p in problem.parts.all()}
                changed_parts = {k: v for k, v in old_parts.items()
                                 if k in now_parts and now_parts[k] != v}
                if changed_parts:
                    overrides['parts'] = changed_parts
                if overrides:
                    matek_touched.add(problem.pk)
                if diag.fingerprint_changed(problem, overrides):
                    matek_stale.add(problem.pk)
            result['МатЭк'] = {
                'артефакт': self.MATEK_BACKUP,
                'коммит': 'd7f2947',
                'применён': '2026-08-27',
                'задач_в_паке': len(records),
                'затронут_отпечаток': len(matek_touched),
                'устарел_вектор': len(matek_stale),
            }

        # --- Сборник АА: журнал применения хранит old/new -----------------
        aa_stale = set()
        if os.path.exists(self.AA_LOG):
            with open(self.AA_LOG, encoding='utf-8') as f:
                log = json.load(f)
            by_problem = {}
            for entry in log:
                pid = (int(entry['problem_id'])
                       if entry['table'] == 'problems_problempart' else int(entry['id']))
                bucket = by_problem.setdefault(pid, {})
                if entry['table'] == 'problems_problempart':
                    bucket.setdefault('parts', {})[int(entry['id'])] = entry['old']
                else:
                    bucket[entry['field']] = entry['old']
            for pid, overrides in by_problem.items():
                problem = (Problem.objects.filter(pk=pid)
                           .prefetch_related('parts', 'topics', 'skills', 'tags').first())
                if problem is not None and diag.fingerprint_changed(problem, overrides):
                    aa_stale.add(pid)
            result['Сборник АА'] = {
                'артефакт': self.AA_LOG,
                'применён': '2026-08-22',
                'правок_в_журнале': len(log),
                'задач_в_журнале': len(prov.apply_log_problem_ids(log)),
                'устарел_вектор': len(aa_stale),
            }

        union = matek_stale | aa_stale
        result['итого'] = {
            'подтверждено_устаревших': len(union),
            'пересечение_паков': len(matek_stale & aa_stale),
            'дата_пересчёта': prov.LEGACY_BUILT_AT.date().isoformat(),
        }
        return result

    # --- 1. Длина условия --------------------------------------------- #

    def _lengths(self):
        lengths = [len(s or '') for s in
                   Problem.objects.values_list('statement', flat=True).iterator(chunk_size=5000)]
        over = [n for n in lengths if n > STATEMENT_BUDGET]
        lost = [_lost_fraction(n, STATEMENT_BUDGET) for n in over]
        return {
            'бюджет_символов': STATEMENT_BUDGET,
            'задач': len(lengths),
            'медиана_длины': int(statistics.median(lengths)) if lengths else 0,
            'среднее': round(statistics.fmean(lengths), 1) if lengths else 0,
            'максимум': max(lengths) if lengths else 0,
            'длиннее_бюджета': len(over),
            'доля_длиннее_бюджета_%': _share(len(over), len(lengths)),
            'медианная_доля_потерянного_текста_%': (
                round(100 * statistics.median(lost), 2) if lost else 0.0),
        }

    # --- 2. То же по подпунктам ---------------------------------------- #

    def _part_lengths(self):
        joined = {}
        rows = Problem.objects.filter(parts__isnull=False).values_list(
            'id', 'parts__statement')
        for pid, st in rows.iterator(chunk_size=5000):
            joined[pid] = joined.get(pid, 0) + len(st or '') + 1
        lengths = list(joined.values())
        over = [n for n in lengths if n > PARTS_BUDGET]
        lost = [_lost_fraction(n, PARTS_BUDGET) for n in over]
        return {
            'бюджет_символов': PARTS_BUDGET,
            'задач_с_подпунктами': len(lengths),
            'медиана_суммарной_длины': int(statistics.median(lengths)) if lengths else 0,
            'длиннее_бюджета': len(over),
            'доля_длиннее_бюджета_%': _share(len(over), len(lengths)),
            'медианная_доля_потерянного_текста_%': (
                round(100 * statistics.median(lost), 2) if lost else 0.0),
        }

    # --- 3, 4. ai_blurb и навыки --------------------------------------- #

    def _enrichment(self):
        total = Problem.objects.count()
        blurb = Problem.objects.exclude(
            Q(ai_blurb__isnull=True) | Q(ai_blurb='')).count()
        skilled = Problem.objects.annotate(n=Count('skills')).filter(n__gt=0).count()
        return {
            'с_ai_blurb': blurb,
            'доля_ai_blurb_%': _share(blurb, total),
            'с_хотя_бы_одним_навыком': skilled,
            'доля_навыков_%': _share(skilled, total),
            'навыков_в_справочнике': Problem.skills.rel.model.objects.count(),
        }

    # --- 5, 6. Темы ----------------------------------------------------- #

    def _topics(self):
        from problems.management.commands.apply_topic_mapping import CANONICAL

        canonical = set(CANONICAL)
        published = Problem.objects.filter(status='published')
        unflagged = published.filter(needs_quality_review=False)

        no_canonical = only_non_canonical = 0
        by_problem = {}
        for pid, name in (published.values_list('id', 'topics__name')
                          .iterator(chunk_size=5000)):
            by_problem.setdefault(pid, set()).add(name)

        unflagged_ids = set(unflagged.values_list('id', flat=True))
        for pid, names in by_problem.items():
            names = {n for n in names if n}
            has_canonical = bool(names & canonical)
            if pid in unflagged_ids and not has_canonical:
                no_canonical += 1
            if names and not has_canonical:
                only_non_canonical += 1

        return {
            'канонических_тем_в_коде': len(canonical),
            'опубликованных': published.count(),
            'опубликованных_незафлагованных': unflagged.count(),
            'без_канонической_темы_среди_незафлагованных': no_canonical,
            'доля_без_канонической_темы_%': _share(no_canonical, unflagged.count()),
            'только_неканоническая_тема': only_non_canonical,
        }

    # --- 7, 8. Эталонные наборы A и D ----------------------------------- #

    def _reference_sets(self):
        confirmed = DuplicateCandidate.objects.filter(status='confirmed')
        both_published = confirmed.filter(
            problem_a__status='published', problem_b__status='published')
        return {
            'набор_A_подтверждённых_пар': confirmed.count(),
            'из_них_порог_0.95': confirmed.filter(similarity__gte=0.95).count(),
            'из_них_обе_задачи_опубликованы': both_published.count(),
            'набор_D_собранных_работ': Assignment.objects.count(),
            'набор_D_подборок_каталога': Collection.objects.count(),
            'набор_D_комментарий': (
                'Assignment — выданные работы, Collection — подборки каталога. '
                'Оба множества двузначные: для эталона D их недостаточно.'
            ),
        }

    # --- 9. Журнал обращений к модели ----------------------------------- #

    def _ai_log(self):
        fields = [f.name for f in AiUsageLog._meta.get_fields()]
        text_fields = [f for f in ('prompt', 'request', 'query', 'text', 'input')
                       if f in fields]
        return {
            'записей': AiUsageLog.objects.count(),
            'виды': dict(Counter(AiUsageLog.objects.values_list('kind', flat=True))),
            'поля': fields,
            'хранит_текст_запроса': bool(text_fields),
            'вывод': (
                'Текст запроса НЕ хранится — только счётчики токенов, стоимость '
                'и вид вызова. Поля под текст в модели нет.'
                if not text_fields else f'Текст запроса в полях: {text_fields}'
            ),
        }

    # --- 10. Цифры в первых 500 символах --------------------------------- #

    def _digits(self):
        total = with_digits = 0
        for st in Problem.objects.values_list('statement', flat=True).iterator(chunk_size=5000):
            total += 1
            if RE_DIGIT.search((st or '')[:STATEMENT_BUDGET]):
                with_digits += 1
        return {
            'задач': total,
            'с_цифрами_в_первых_500': with_digits,
            'доля_%': _share(with_digits, total),
        }

    # --- 11. Покрытие словаря терминов ----------------------------------- #

    def _corpus_ngrams(self):
        """Униграммы (с частотой) и множества би-/три-/четырёхграмм банка."""
        uni = Counter()
        docs = Counter()
        bi, tri, quad = set(), set(), set()
        rows = Problem.objects.values_list('title', 'statement').iterator(chunk_size=2000)
        for title, statement in rows:
            toks = _tokens(title) + _tokens(statement)
            uni.update(toks)
            docs.update(set(toks))
            for i in range(len(toks) - 1):
                bi.add(' '.join(toks[i:i + 2]))
            for i in range(len(toks) - 2):
                tri.add(' '.join(toks[i:i + 3]))
            for i in range(len(toks) - 3):
                quad.add(' '.join(toks[i:i + 4]))
        for st in Problem.objects.filter(parts__isnull=False).values_list(
                'parts__statement', flat=True).iterator(chunk_size=5000):
            toks = _tokens(st)
            uni.update(toks)
            docs.update(set(toks))
            for i in range(len(toks) - 1):
                bi.add(' '.join(toks[i:i + 2]))
            for i in range(len(toks) - 2):
                tri.add(' '.join(toks[i:i + 3]))
        return uni, docs, {1: None, 2: bi, 3: tri, 4: quad}

    @staticmethod
    def _term_forms(entry):
        """Все написания термина: канон, синонимы, английский, словоформы."""
        forms = [entry.get('canonical', '')]
        forms += list(entry.get('synonyms') or [])
        forms += list(entry.get('english') or [])
        forms += list((entry.get('word_forms') or {}).values())
        return [f for f in forms if f]

    def _dictionary(self):
        uni, docs, grams = self._corpus_ngrams()
        entries = econ_terms.terms()

        found, missing_terms = 0, []
        too_long = 0
        for entry in entries:
            hit = False
            for form in self._term_forms(entry):
                toks = _tokens(form)
                if not toks:
                    continue
                n = len(toks)
                if n == 1:
                    if toks[0] in uni:
                        hit = True
                elif n <= 4:
                    if ' '.join(toks) in grams[n]:
                        hit = True
                else:
                    too_long += 1
                if hit:
                    break
            if hit:
                found += 1
            else:
                missing_terms.append(entry.get('canonical'))

        # Обратное направление: частые слова корпуса, которых в словаре нет.
        dict_tokens = set()
        for entry in entries:
            for form in self._term_forms(entry):
                dict_tokens.update(_tokens(form))
        unknown = [(w, docs[w]) for w, _ in uni.most_common()
                   if w not in dict_tokens and w not in STOPWORDS and len(w) > 3]

        return {
            'терминов_в_словаре': len(entries),
            'счётчики_словаря': econ_terms.counts(),
            'встречается_в_банке': found,
            'покрытие_%': _share(found, len(entries)),
            'не_встречается': len(entries) - found,
            'форм_длиннее_4_слов_пропущено': too_long,
            'примеры_ненайденных': missing_terms[:40],
            'топ50_частых_слов_вне_словаря': [
                {'слово': w, 'задач': n} for w, n in unknown[:50]],
            'оговорка': (
                'Совпадение ищется по точной словоформе (канон, синонимы, '
                'английский, четыре падежа из словаря), БЕЗ лемматизации. '
                'Это нижняя оценка покрытия: форма, которой нет в словаре, '
                'не засчитывается. Полная морфология — задача С19.'
            ),
        }

    # --- В разрезе источника --------------------------------------------- #

    def _per_source(self):
        out = {}
        for source in Source.objects.all().order_by('name'):
            qs = Problem.objects.filter(source_references__source=source).distinct()
            total = qs.count()
            if not total:
                continue
            lengths = [len(s or '') for s in qs.values_list('statement', flat=True)]
            over = [n for n in lengths if n > STATEMENT_BUDGET]
            lost = [_lost_fraction(n, STATEMENT_BUDGET) for n in over]
            blurb = qs.exclude(Q(ai_blurb__isnull=True) | Q(ai_blurb='')).count()
            skilled = qs.annotate(n=Count('skills')).filter(n__gt=0).count()
            digits = sum(1 for s in qs.values_list('statement', flat=True)
                         if RE_DIGIT.search((s or '')[:STATEMENT_BUDGET]))
            out[source.name] = {
                'задач': total,
                'опубликованных': qs.filter(status='published').count(),
                'медиана_длины': int(statistics.median(lengths)) if lengths else 0,
                'длиннее_500': len(over),
                'доля_длиннее_500_%': _share(len(over), total),
                'медианная_доля_потерянного_%': (
                    round(100 * statistics.median(lost), 2) if lost else 0.0),
                'доля_ai_blurb_%': _share(blurb, total),
                'доля_навыков_%': _share(skilled, total),
                'доля_цифр_в_500_%': _share(digits, total),
                'с_эмбеддингом': qs.exclude(embedding__isnull=True).count(),
            }
        return out

    # --- Фаза 3: источники, которых нет в базе ---------------------------- #

    def _external(self):
        return {
            'SolveHub': self._external_solvehub(),
            'Школково': self._external_shkolkovo(),
            'ЛЭШ Гамма': self._external_lesh(),
            'N/A_комментарий': (
                'ai_blurb, навыки, темы и эмбеддинг у этих источников '
                'физически отсутствуют — они не импортированы. Это N/A, '
                'а не 0%: ноль означал бы «поле есть и пустое».'
            ),
        }

    def _external_stats(self, texts, name):
        lengths = [len(t or '') for t in texts]
        over = [n for n in lengths if n > STATEMENT_BUDGET]
        lost = [_lost_fraction(n, STATEMENT_BUDGET) for n in over]
        uni = Counter()
        for t in texts:
            uni.update(_tokens(t))
        dict_tokens = set()
        for entry in econ_terms.terms():
            for form in self._term_forms(entry):
                dict_tokens.update(_tokens(form))
        return {
            'источник': name,
            'задач_блоков': len(lengths),
            'медиана_длины': int(statistics.median(lengths)) if lengths else 0,
            'длиннее_500': len(over),
            'доля_длиннее_500_%': _share(len(over), len(lengths)),
            'медианная_доля_потерянного_%': (
                round(100 * statistics.median(lost), 2) if lost else 0.0),
            'с_цифрами_в_первых_500': sum(
                1 for t in texts if RE_DIGIT.search((t or '')[:STATEMENT_BUDGET])),
            'слов_всего': sum(uni.values()),
            'уникальных_слов': len(uni),
            'слов_из_словаря_терминов': len(set(uni) & dict_tokens),
            'ai_blurb': 'N/A — не импортирован',
            'навыки': 'N/A — не импортирован',
            'темы': 'N/A — не импортирован',
            'эмбеддинг': 'N/A — не импортирован',
        }

    def _external_solvehub(self):
        root = os.path.join(os.path.dirname(settings.BASE_DIR),
                            'weconomics-data', 'solvehub', 'problems')
        texts = []
        for path in sorted(glob.glob(os.path.join(root, '*.json'))):
            with open(path, encoding='utf-8') as f:
                texts.append((json.load(f).get('md') or ''))
        return self._external_stats(texts, 'SolveHub')

    def _external_shkolkovo(self):
        root = os.path.join(os.path.dirname(settings.BASE_DIR),
                            'weconomics-data', 'shkolkovo', 'problems')
        texts = []
        for path in sorted(glob.glob(os.path.join(root, '*.json'))):
            with open(path, encoding='utf-8') as f:
                raw = json.load(f)
            texts.append(raw.get('statement_tex') or raw.get('statement')
                         or raw.get('question') or '')
        return self._external_stats(texts, 'Школково')

    def _external_lesh(self):
        """Блоки \\z разбираются ШТАТНЫМ парсером источника, не своей регуляркой.

        Свой разбор дал бы своё число, и расхождение с отчётом
        `corpus_scaleup_lesh` пришлось бы объяснять. Условия лежат в
        «Подборках», решения — в «Решалках»; для диагностики длины нужны
        только условия.
        """
        from problems.corpus_converter.lesh import interpret_z_args, parse_z_blocks
        from problems.management.commands.corpus_scaleup_lesh import (
            _is_reshalka_file, _iter_tex_files,
        )
        conditions, solutions, files_read = [], 0, 0
        for path, rel in _iter_tex_files():
            files_read += 1
            with open(path, encoding='utf-8', errors='replace') as f:
                blocks, _ = parse_z_blocks(f.read())
            for block in blocks:
                parsed = interpret_z_args(block)
                if _is_reshalka_file(rel):
                    solutions += 1
                else:
                    conditions.append(parsed.get('statement') or '')
        stats = self._external_stats(conditions, 'ЛЭШ Гамма')
        stats['файлов_tex_прочитано'] = files_read
        stats['блоков_решений_в_Решалках'] = solutions
        return stats
