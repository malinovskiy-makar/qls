"""Поиск текстовых копий уже опознанных олимпиадных задач по всему банку.

У части задач банка олимпиада, год и этап известны точно: ссылка на
первоисточник совпала буквально с внешним экспортом SolveHub/ILE (команда
`link_olympiad_refs`, методы `url_exact` и `url_www_normalized`). Такие
задачи здесь называются ЯКОРЯМИ.

Те же самые олимпиадные задачи лежат в банке ещё раз — вставленные из
МатЭк, Школково, Overleaf-архивов, иногда вообще без указания источника.
Эта команда находит их ПО ТЕКСТУ и переносит метаданные олимпиады на
копию отдельной строкой `OlympiadRef`.

    manage.py find_olympiad_text_duplicates            # сухой прогон
    manage.py find_olympiad_text_duplicates --apply    # запись

Каскад из трёх шагов, по возрастанию цены и убыванию уверенности:

  Шаг A  точное совпадение нормализованного текста (SHA-1). Дёшево, без
         эмбеддингов, по всему банку одним проходом. Метод `text_sha1`.
  Шаг B  эмбеддинги как СИТО (косинус ≥ порога), потом числа и текст как
         ПРИГОВОР. Метод `text_fuzzy_numeric`.
  Шаг C  сверка якорей между собой. Только отчёт, в базу не пишет.

⚠️ ЧИСЛА — ПРИГОВОР, ТЕКСТ — ТОЛЬКО ПОДОЗРЕНИЕ. Два условия с одинаковой
структурой фразы, но разными исходными данными («$P = 100 - Q$» против
«$P = 90 - 2Q$») — это РАЗНАЯ задача с другим ответом, а не копия, даже
при сходстве текста 98 %. Мультимножество чисел сверяется ПЕРЕД дорогим
fuzzy-сравнением и не имеет допусков.

⚠️ ПОРОГ СИТА (0,90) НАМЕРЕННО НИЖЕ ПОРОГА ЗАПИСИ (0,97). Косинус здесь
не решает ничего — он только сужает перебор. Замер показал, что даже у
побайтово одинаковых условий косинус не равен единице (медиана 0,99,
минимум 0,77): `problem_to_text` подмешивает в отпечаток заголовок, темы,
теги и `ai_blurb`, а они у копий разные. Порог повыше терял бы настоящие
копии молча.

⚠️ ЯКОРЬ — ЭТО ТОЛЬКО URL-ПРИВЯЗКА, И ЭТО ДЕРЖИТ ИДЕМПОТЕНТНОСТЬ.
Кандидатом считается задача БЕЗ единой строки `OlympiadRef`. После
`--apply` найденные копии перестают быть кандидатами, но якорями НЕ
становятся: иначе пошла бы пропагация копии-с-копии, где ошибка первого
шага размножается без следа. Повторный сухой прогон обязан дать ноль.

⚠️ РАСХОЖДЕНИЕ ТОЛЬКО ПО КЛАССУ — НЕ КОНФЛИКТ (ADR 0058). Одну задачу
олимпиада часто даёт нескольким параллелям сразу. Конфликтом остаётся
расхождение по олимпиаде, году или этапу.

Границы: не меняет `Problem`, `SourceReference`, `ProblemPart`; не трогает
`DuplicateCandidate`; ничего не схлопывает, не скрывает и не помечает
дублем. Только добавляет строки `OlympiadRef`.
"""
import csv
import html
import json
import os
import random
from collections import Counter, defaultdict

import numpy as np
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.embedding_config import EMBEDDING_DIM
from problems.models import OlympiadRef, Problem, SourceReference
from problems.olympiad_grades import (
    classify_refs, event_key, keys_agree, keys_conflict, merge_grades_by_event,
)
from problems.text_dedup import (
    extract_numeric_tokens, fuzzy_ratio, normalize_for_compare,
    numeric_tokens_match, text_fingerprint,
)

# Методы, которые делают задачу ЯКОРЕМ. Текстовые методы сюда не входят
# намеренно — см. предупреждение про идемпотентность в шапке.
ANCHOR_METHODS = ('url_exact', 'url_www_normalized')

REPORTS_DIR = 'reports/olympiad_link'
REVIEW_QUEUE = 'text_dedup_review_queue.csv'
ANCHOR_CONFLICTS = 'anchor_metadata_conflicts.csv'
GRADE_MERGES = 'anchor_grade_merges.csv'
PREVIEW_HTML = 'text_dedup_preview.html'
APPLIED_JOURNAL = 'text_dedup_applied.json'

# Поля метаданных олимпиады, переносимые из якорной строки БУКВАЛЬНО.
# source_site и record_id тоже копируются: они описывают, ОТКУДА взялись
# метаданные, а пропагация источник метаданных не меняет.
COPIED_FIELDS = (
    'source_site', 'olympiad_slug', 'olympiad_name', 'academic_year', 'year',
    'stage', 'grade', 'variant', 'number', 'record_id', 'official_url',
)

EVENT_ID_MAX = OlympiadRef._meta.get_field('event_id').max_length


def _grade_for(merged_side, key):
    """Что сказала о классе одна сторона про тур `key`.

    Ключи сторон могут отличаться этапом («» против `final`), поэтому
    поиск идёт по СОГЛАСИЮ ключей — той же функцией `keys_agree`, что
    решает вопрос о конфликте, а не отдельным сравнением.
    """
    for known, value in merged_side.items():
        if keys_agree(known, key):
            return value
    return ''


class Match:
    """Одно найденное совпадение «якорь → кандидат»."""

    __slots__ = ('candidate_id', 'anchor_id', 'method', 'score', 'cosine',
                 'fuzzy', 'numeric_match')

    def __init__(self, candidate_id, anchor_id, method, score,
                 cosine=None, fuzzy=None, numeric_match=True):
        self.candidate_id = candidate_id
        self.anchor_id = anchor_id
        self.method = method
        self.score = score
        self.cosine = cosine
        self.fuzzy = fuzzy
        self.numeric_match = numeric_match


class Command(BaseCommand):
    help = ('Ищет текстовые копии олимпиадных задач по всему банку и '
            'переносит на них метаданные олимпиады (OlympiadRef).')

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Записать найденное в OlympiadRef. Без флага — сухой прогон.')
        parser.add_argument(
            '--cosine', type=float, default=0.90,
            help='Порог косинуса для попадания в шорт-лист Шага B (0,90).')
        parser.add_argument(
            '--fuzzy-auto', type=float, default=0.97,
            help='Порог текстового сходства для автозаписи (0,97).')
        parser.add_argument(
            '--fuzzy-min', type=float, default=0.90,
            help='Ниже этого не копия вовсе — не пишем даже в очередь (0,90).')
        parser.add_argument(
            '--min-length', type=int, default=200,
            help='Короче этого текст не опознаёт задачу — предохранитель (200).')
        parser.add_argument(
            '--batch', type=int, default=200,
            help='Сколько якорей брать за раз в матрицу косинусов (200).')
        parser.add_argument(
            '--sample', type=int, default=20,
            help='Сколько примеров автозаписи показать в сухом прогоне (20).')
        parser.add_argument(
            '--seed', type=int, default=20260902,
            help='Зерно выборки примеров — прогон воспроизводим.')
        parser.add_argument(
            '--skip-embeddings', action='store_true',
            help='Только Шаг A. Для быстрой проверки, не для боевого прогона.')
        parser.add_argument(
            '--reports-dir', default=REPORTS_DIR,
            help=f'Куда класть отчёты ({REPORTS_DIR}).')

    # ── общая часть ──────────────────────────────────────────────────────

    def handle(self, *args, **options):
        self.opts = options
        self.reports_dir = options['reports_dir']
        os.makedirs(self.reports_dir, exist_ok=True)

        self._load_anchors()
        self._load_corpus()

        matches_a, anchor_pairs_a, numeric_rejects_a = self._step_a()
        if options['skip_embeddings']:
            self.stdout.write(self.style.WARNING(
                '\n--skip-embeddings: Шаг B и его часть Шага C ПРОПУЩЕНЫ. '
                'Это неполный прогон.'))
            matches_b, anchor_pairs_b = [], []
            shortlist_total = numeric_rejects_b = fuzzy_dropped = 0
            queue_band = []
        else:
            (matches_b, queue_band, shortlist_total, numeric_rejects_b,
             fuzzy_dropped) = self._step_b(matches_a)
            anchor_pairs_b = self._step_c_embeddings(anchor_pairs_a)

        all_matches = matches_a + matches_b
        decided, conflicts = self._resolve_conflicts(all_matches)
        conflict_rows = self._step_c_report(anchor_pairs_a + anchor_pairs_b)

        self._write_review_queue(queue_band, conflicts)
        self._write_preview(decided)

        self._report(
            matches_a=matches_a, matches_b=matches_b, decided=decided,
            conflicts=conflicts, queue_band=queue_band,
            shortlist_total=shortlist_total,
            numeric_rejects_a=numeric_rejects_a,
            numeric_rejects_b=numeric_rejects_b,
            fuzzy_dropped=fuzzy_dropped, conflict_rows=conflict_rows,
        )

        if options['apply']:
            self._apply(decided)
        else:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'СУХОЙ ПРОГОН: в базу ничего не записано. '
                'Запись — тем же вызовом с --apply.'))

    # ── загрузка ─────────────────────────────────────────────────────────

    def _load_anchors(self):
        """Якоря и их строки. Кандидат — задача БЕЗ единой строки OlympiadRef."""
        self.refs_by_anchor = defaultdict(list)
        self.problems_with_any_ref = set()
        for ref in OlympiadRef.objects.all():
            self.problems_with_any_ref.add(ref.problem_id)
            if ref.match_method in ANCHOR_METHODS:
                self.refs_by_anchor[ref.problem_id].append(ref)
        self.anchor_ids = set(self.refs_by_anchor)

        # Разбор строк ВНУТРИ каждого якоря — та же `classify_refs`, что
        # считала предпроверку по 379 многострочным задачам. Числа обязаны
        # совпасть с ней до единицы; расхождение означает, что правило
        # где-то живёт в двух экземплярах.
        self.self_classes = Counter(
            classify_refs(refs) for refs in self.refs_by_anchor.values())
        self.self_conflicts = [
            (pid, refs) for pid, refs in self.refs_by_anchor.items()
            if classify_refs(refs) == 'conflict']

        self.stdout.write('=' * 72)
        self.stdout.write('ПОИСК ТЕКСТОВЫХ КОПИЙ ОЛИМПИАДНЫХ ЗАДАЧ')
        self.stdout.write('=' * 72)
        self.stdout.write(f'Строк OlympiadRef в базе        : '
                          f'{OlympiadRef.objects.count()}')
        self.stdout.write(f'Задач хотя бы с одной строкой   : '
                          f'{len(self.problems_with_any_ref)}')
        self.stdout.write(f'Из них ЯКОРЕЙ (url-привязка)    : '
                          f'{len(self.anchor_ids)}')
        multi = sum(n for k, n in self.self_classes.items() if k != 'single')
        self.stdout.write('')
        self.stdout.write(f'СТРОКИ ВНУТРИ ОДНОГО ЯКОРЯ (ADR 0058), многострочных: {multi}')
        self.stdout.write(f'   agree      тур и класс совпали  : '
                          f'{self.self_classes["agree"]}')
        self.stdout.write(f'   grade_only тур совпал, класс нет: '
                          f'{self.self_classes["grade_only"]}  ← объединяем, не конфликт')
        self.stdout.write(f'   conflict   спор об олимпиаде/годе/этапе: '
                          f'{self.self_classes["conflict"]}')
        for pid, refs in self.self_conflicts:
            self.stdout.write(f'      #{pid}: {self._describe(refs)}')

    def _load_corpus(self):
        """Тексты, отпечатки и векторы всего банка одним проходом."""
        self.norm_text, self.raw_text, self.fingerprint = {}, {}, {}
        self.embedding_version = {}
        vectors = {}
        no_vector = 0

        query = (Problem.objects.prefetch_related('parts')
                 .only('id', 'statement', 'embedding', 'embedding_version'))
        for problem in query.iterator(chunk_size=500):
            chunks = [problem.statement or '']
            chunks.extend(part.statement or '' for part in problem.parts.all())
            raw = ' \n '.join(chunks)
            self.raw_text[problem.id] = raw
            normalized = normalize_for_compare(raw)
            self.norm_text[problem.id] = normalized
            self.fingerprint[problem.id] = text_fingerprint(normalized)
            self.embedding_version[problem.id] = problem.embedding_version
            blob = problem.embedding
            if blob and len(bytes(blob)) == EMBEDDING_DIM * 4:
                vectors[problem.id] = np.frombuffer(bytes(blob), dtype=np.float32)
            else:
                no_vector += 1

        self.vectors = vectors
        self.numeric_cache = {}
        self.stdout.write(f'Задач в банке                   : {len(self.norm_text)}')
        self.stdout.write(f'Из них с пригодным вектором     : {len(vectors)}')
        if no_vector:
            self.stdout.write(self.style.WARNING(
                f'⚠️  Без вектора нужного размера  : {no_vector} — '
                f'в Шаге B не участвовали'))
        versions = Counter(self.embedding_version.values())
        self.stdout.write(f'Версии формулы эмбеддинга       : {dict(versions)}')
        if len(versions) > 1:
            self.stdout.write(
                '   Версии сравниваются между собой сознательно: замер на '
                'побайтово одинаковых текстах дал медиану косинуса 0,9884 '
                'между версиями против 0,9898 внутри версии. Косинус здесь '
                'только сито — приговор выносят числа и текст.')

    def numeric(self, pid):
        """Мультимножество чисел СЫРОГО текста задачи (с кэшем)."""
        got = self.numeric_cache.get(pid)
        if got is None:
            got = extract_numeric_tokens(self.raw_text[pid])
            self.numeric_cache[pid] = got
        return got

    def _long_enough(self, pid):
        """Предохранитель коротких текстов.

        ⚠️ Не формальность. В банке 62 задачи с пустым условием, 14 с текстом
        «тык», 11 с «(тык)» — их отпечатки совпадают между собой идеально.
        Правило «точный текст — нечего дальше проверять» на них неверно.
        """
        return len(self.norm_text[pid]) >= self.opts['min_length']

    # ── Шаг A: точное совпадение нормализованного текста ──────────────────

    def _step_a(self):
        groups = defaultdict(list)
        for pid, fp in self.fingerprint.items():
            if self._long_enough(pid):
                groups[fp].append(pid)

        matches, anchor_pairs, numeric_rejects = [], [], 0
        for ids in groups.values():
            if len(ids) < 2:
                continue
            anchors = [i for i in ids if i in self.anchor_ids]
            if not anchors:
                continue
            candidates = [i for i in ids
                          if i not in self.problems_with_any_ref]
            for a in range(len(anchors)):
                for b in range(a + 1, len(anchors)):
                    anchor_pairs.append(
                        (anchors[a], anchors[b], 'text_sha1', None, 1.0))
            for cand in candidates:
                for anchor in anchors:
                    # Числа берутся из СЫРОГО текста, а нормализация применяет
                    # NFKC — «Q²» и «Q2» после неё неразличимы. Сито дешёвое,
                    # а цена ошибки здесь — неверная олимпиада у задачи.
                    if not numeric_tokens_match(self.numeric(cand),
                                                self.numeric(anchor)):
                        numeric_rejects += 1
                        continue
                    matches.append(Match(cand, anchor, 'text_sha1', 1.0,
                                         cosine=None, fuzzy=1.0))
        self.exact_pairs = {(m.candidate_id, m.anchor_id) for m in matches}
        return matches, anchor_pairs, numeric_rejects

    # ── Шаг B: эмбеддинги как сито, числа и текст как приговор ────────────

    def _pool(self, ids):
        """Список id с вектором и матрица их векторов."""
        usable = [i for i in ids if i in self.vectors]
        if not usable:
            return [], np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        return usable, np.vstack([self.vectors[i] for i in usable])

    def _step_b(self, matches_a):
        anchor_ids, anchor_matrix = self._pool(sorted(self.anchor_ids))
        candidate_ids, candidate_matrix = self._pool(sorted(
            pid for pid in self.norm_text
            if pid not in self.problems_with_any_ref
            and self._long_enough(pid)))

        self.stdout.write('')
        self.stdout.write(f'Шаг B: якорей с вектором {len(anchor_ids)}, '
                          f'кандидатов {len(candidate_ids)}')

        matches, queue_band = [], []
        shortlist_total = numeric_rejects = fuzzy_dropped = 0
        step = max(1, self.opts['batch'])
        threshold = self.opts['cosine']

        for start in range(0, len(anchor_ids), step):
            chunk = anchor_ids[start:start + step]
            sims = anchor_matrix[start:start + step] @ candidate_matrix.T
            rows, cols = np.where(sims >= threshold)
            shortlist_total += len(rows)
            for row, col in zip(rows, cols):
                anchor = chunk[row]
                cand = candidate_ids[col]
                if (cand, anchor) in self.exact_pairs:
                    continue
                if not numeric_tokens_match(self.numeric(cand),
                                            self.numeric(anchor)):
                    numeric_rejects += 1
                    continue
                cosine = float(sims[row, col])
                ratio = fuzzy_ratio(self.norm_text[cand], self.norm_text[anchor])
                if ratio >= self.opts['fuzzy_auto']:
                    matches.append(Match(cand, anchor, 'text_fuzzy_numeric',
                                         ratio, cosine=cosine, fuzzy=ratio))
                elif ratio >= self.opts['fuzzy_min']:
                    queue_band.append(Match(cand, anchor, 'text_fuzzy_numeric',
                                            ratio, cosine=cosine, fuzzy=ratio))
                else:
                    fuzzy_dropped += 1
            self.stdout.write(
                f'   якоря {start + 1}–{start + len(chunk)}: '
                f'шорт-лист {shortlist_total}, автозапись {len(matches)}, '
                f'в очередь {len(queue_band)}', ending='\r')
        self.stdout.write('')
        return matches, queue_band, shortlist_total, numeric_rejects, fuzzy_dropped

    # ── Шаг C: сверка якорей между собой ─────────────────────────────────

    def _step_c_embeddings(self, already):
        """Пары якорь-якорь по эмбеддингам. В базу не пишет ничего."""
        ids, matrix = self._pool(sorted(
            pid for pid in self.anchor_ids if self._long_enough(pid)))
        seen = {(min(a, b), max(a, b)) for a, b, *_ in already}
        pairs = []
        step = max(1, self.opts['batch'])
        for start in range(0, len(ids), step):
            sims = matrix[start:start + step] @ matrix.T
            rows, cols = np.where(sims >= self.opts['cosine'])
            for row, col in zip(rows, cols):
                left, right = ids[start + row], ids[col]
                if left >= right:
                    continue                       # верхний треугольник и без себя
                if (left, right) in seen:
                    continue
                if not numeric_tokens_match(self.numeric(left),
                                            self.numeric(right)):
                    continue
                ratio = fuzzy_ratio(self.norm_text[left], self.norm_text[right])
                if ratio >= self.opts['fuzzy_auto']:
                    pairs.append((left, right, 'text_fuzzy_numeric',
                                  float(sims[row, col]), ratio))
        return pairs

    def _step_c_report(self, pairs):
        """Согласны ли якоря о метаданных. Только отчёт, база не меняется.

        ADR 0058: сначала олимпиада/год/этап, и только их расхождение —
        конфликт. Разные классы при совпавшем туре объединяются в диапазон.
        """
        conflict_rows, grade_rows = [], []
        for left, right, method, cosine, ratio in pairs:
            left_refs = self.refs_by_anchor[left]
            right_refs = self.refs_by_anchor[right]
            left_keys = {event_key(r) for r in left_refs}
            right_keys = {event_key(r) for r in right_refs}
            merged_left = merge_grades_by_event(left_refs)
            merged_right = merge_grades_by_event(right_refs)
            if keys_conflict(left_keys, right_keys):
                conflict_rows.append({
                    'problem_a': left, 'problem_b': right,
                    'method': method,
                    'cosine': '' if cosine is None else f'{cosine:.4f}',
                    'fuzzy': f'{ratio:.4f}',
                    'a_site': '/'.join(sorted({r.source_site for r in left_refs})),
                    'b_site': '/'.join(sorted({r.source_site for r in right_refs})),
                    'a_says': self._describe(left_refs),
                    'b_says': self._describe(right_refs),
                    'a_text_300': self.raw_text[left][:300],
                    'b_text_300': self.raw_text[right][:300],
                })
                continue
            # Тур один и тот же. Расходятся ли классы?
            # ⚠️ Группировку делает merge_grades_by_event, а не своя копия
            # логики здесь: числа этого отчёта обязаны совпадать с
            # предпроверкой по 379 задачам до единицы, а две реализации
            # одного правила расходятся всегда.
            merged_both = merge_grades_by_event(left_refs + right_refs)
            for key, merged in sorted(merged_both.items(),
                                      key=lambda kv: (kv[0][0], kv[0][1] or 0, kv[0][2])):
                left_says = _grade_for(merged_left, key)
                right_says = _grade_for(merged_right, key)
                if left_says != merged or right_says != merged:
                    grade_rows.append({
                        'problem_a': left, 'problem_b': right,
                        'olympiad_slug': key[0], 'year': key[1], 'stage': key[2],
                        'a_grade': left_says,
                        'b_grade': right_says,
                        'merged_grade': merged,
                        'fuzzy': f'{ratio:.4f}',
                    })
        self._write_csv(ANCHOR_CONFLICTS, conflict_rows, [
            'problem_a', 'problem_b', 'method', 'cosine', 'fuzzy',
            'a_site', 'b_site', 'a_says', 'b_says', 'a_text_300', 'b_text_300'])
        self._write_csv(GRADE_MERGES, grade_rows, [
            'problem_a', 'problem_b', 'olympiad_slug', 'year', 'stage',
            'a_grade', 'b_grade', 'merged_grade', 'fuzzy'])
        self.step_c_pairs = len(pairs)
        self.step_c_grade_rows = grade_rows
        return conflict_rows

    @staticmethod
    def _describe(refs):
        parts = []
        for r in refs:
            parts.append(f'{r.olympiad_slug} {r.year} {r.stage or "-"} кл.{r.grade or "-"}')
        return ' | '.join(sorted(set(parts)))

    # ── противоречия при пропагации ──────────────────────────────────────

    def _resolve_conflicts(self, matches):
        """Кандидат, у якорей которого расходится ТУР, не пишется вовсе.

        ADR 0058: класс в ключ тура не входит, поэтому «задача для двух
        параллелей» конфликтом не считается и пишется от каждого якоря.
        """
        by_candidate = defaultdict(list)
        for m in matches:
            by_candidate[m.candidate_id].append(m)

        decided, conflicts = [], []
        for cand, group in by_candidate.items():
            key_sets = [
                {event_key(r) for r in self.refs_by_anchor[m.anchor_id]}
                for m in group
            ]
            # Сравнение попарно и той же функцией, что в Шаге C: пустой этап
            # согласен с любым, поэтому наборы, не равные как множества,
            # могут описывать один и тот же тур.
            disputed = any(
                keys_conflict(key_sets[i], key_sets[j])
                for i in range(len(key_sets)) for j in range(i + 1, len(key_sets))
            )
            (conflicts if disputed else decided).extend(group)
        return decided, conflicts

    # ── отчёты ───────────────────────────────────────────────────────────

    def _write_csv(self, name, rows, columns):
        path = os.path.join(self.reports_dir, name)
        with open(path, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def _queue_row(self, match, reason, conflict, variants=''):
        refs = self.refs_by_anchor[match.anchor_id]
        merged = merge_grades_by_event(refs)
        first = refs[0]
        return {
            'reason': reason,
            'conflict': 'true' if conflict else 'false',
            'candidate_id': match.candidate_id,
            'anchor_id': match.anchor_id,
            'method': match.method,
            'cosine': '' if match.cosine is None else f'{match.cosine:.4f}',
            'fuzzy': '' if match.fuzzy is None else f'{match.fuzzy:.4f}',
            'numeric_match': 'true',
            'olympiad_slug': first.olympiad_slug,
            'olympiad_name': first.olympiad_name,
            'year': first.year,
            'stage': first.stage,
            'grade_merged': ' / '.join(sorted(merged.values())),
            'variants': variants,
            'candidate_text_300': self.raw_text[match.candidate_id][:300],
            'anchor_text_300': self.raw_text[match.anchor_id][:300],
        }

    def _write_review_queue(self, queue_band, conflicts):
        rows = [self._queue_row(m, 'band_0.90_0.97', False) for m in queue_band]
        by_candidate = defaultdict(list)
        for m in conflicts:
            by_candidate[m.candidate_id].append(m)
        for cand, group in by_candidate.items():
            variants = ' || '.join(sorted(
                f'#{m.anchor_id}: {self._describe(self.refs_by_anchor[m.anchor_id])}'
                for m in group))
            rows.extend(self._queue_row(m, 'anchor_conflict', True, variants)
                        for m in group)
        self._write_csv(REVIEW_QUEUE, rows, [
            'reason', 'conflict', 'candidate_id', 'anchor_id', 'method',
            'cosine', 'fuzzy', 'numeric_match', 'olympiad_slug',
            'olympiad_name', 'year', 'stage', 'grade_merged', 'variants',
            'candidate_text_300', 'anchor_text_300'])
        self.queue_rows = rows

    def _write_preview(self, decided):
        """HTML с парами текстов рядом — то, что смотрится глазами."""
        rng = random.Random(self.opts['seed'])
        half = max(1, self.opts['sample'] // 2)
        by_method = defaultdict(list)
        for m in decided:
            by_method[m.method].append(m)
        chosen = []
        for method in ('text_sha1', 'text_fuzzy_numeric'):
            pool = by_method[method]
            chosen.extend(rng.sample(pool, min(half, len(pool))))
        queue_sample = rng.sample(self.queue_rows, min(10, len(self.queue_rows)))

        pieces = ["""<meta charset="utf-8"><title>Текстовые копии олимпиадных задач</title>
<style>body{font:15px/1.55 system-ui,sans-serif;margin:24px;max-width:1400px}
h1{font-size:22px}h2{font-size:17px;margin-top:32px;border-bottom:2px solid #ccc;padding-bottom:4px}
table{border-collapse:collapse;width:100%;margin:10px 0 26px}
td,th{border:1px solid #ccc;padding:9px 11px;vertical-align:top;width:50%}
th{background:#f2f2f2;text-align:left}
.meta{background:#eef4ff;font-size:13px;padding:7px 11px;border:1px solid #ccd}
.q{background:#fff8e6}code{background:#f4f4f4;padding:1px 4px}</style>
<h1>Текстовые копии олимпиадных задач — предпросмотр</h1>
<p>Слева задача-кандидат (копия), справа якорь с известной олимпиадой.
Смотреть надо на <b>числа в условии</b>: если они разошлись — это разные
задачи, и такая пара не должна была сюда попасть.</p>"""]

        pieces.append(f'<h2>Автозапись — {len(chosen)} случайных примеров '
                      f'(зерно {self.opts["seed"]})</h2>')
        for m in chosen:
            refs = self.refs_by_anchor[m.anchor_id]
            merged = ' / '.join(sorted(merge_grades_by_event(refs).values()))
            pieces.append(
                f'<div class="meta">метод <code>{m.method}</code>, '
                f'сходство {m.score:.4f}'
                + (f', косинус {m.cosine:.4f}' if m.cosine is not None else '')
                + f' · <b>{self._describe(refs)}</b> · объединённый класс '
                  f'<b>{html.escape(merged) or "—"}</b></div>'
                + '<table><tr><th>кандидат #%d</th><th>якорь #%d</th></tr>'
                  '<tr><td>%s</td><td>%s</td></tr></table>' % (
                      m.candidate_id, m.anchor_id,
                      html.escape(self.raw_text[m.candidate_id][:1800]),
                      html.escape(self.raw_text[m.anchor_id][:1800])))

        pieces.append(f'<h2>Очередь ручного разбора — {len(queue_sample)} из '
                      f'{len(self.queue_rows)}</h2>')
        for row in queue_sample:
            pieces.append(
                f'<div class="meta q">причина <code>{row["reason"]}</code>, '
                f'конфликт {row["conflict"]}, косинус {row["cosine"]}, '
                f'сходство {row["fuzzy"]} · {html.escape(str(row["variants"]) or row["olympiad_slug"])}</div>'
                + '<table><tr><th>кандидат #%s</th><th>якорь #%s</th></tr>'
                  '<tr><td>%s</td><td>%s</td></tr></table>' % (
                      row['candidate_id'], row['anchor_id'],
                      html.escape(row['candidate_text_300']),
                      html.escape(row['anchor_text_300'])))

        path = os.path.join(self.reports_dir, PREVIEW_HTML)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('\n'.join(pieces))
        self.preview_path = path
        self.preview_sample = chosen
        self.queue_sample = queue_sample

    def _report(self, **k):
        w = self.stdout.write
        w('')
        w('─' * 72)
        w('НАЙДЕНО')
        w('─' * 72)
        w(f'Шаг A, точное совпадение текста (text_sha1)   : {len(k["matches_a"])} пар')
        w(f'Шаг B, сходство + числа (text_fuzzy_numeric)  : {len(k["matches_b"])} пар')
        w(f'  из них прошло в запись после снятия конфликтов: {len(k["decided"])}')
        w(f'  снято конфликтом якорей (ничего не пишем)     : {len(k["conflicts"])}')
        w('')
        w(f'В очередь ручного разбора, всего строк        : {len(self.queue_rows)}')
        w(f'  причина «сходство 0,90–0,97»                : {len(k["queue_band"])}')
        w(f'  причина «конфликт якорей»                   : {len(k["conflicts"])}')
        w('')
        w('ЧТО ОТСЕЯЛИ')
        w(f'  шорт-лист косинуса (пар ≥ {self.opts["cosine"]})            : '
          f'{k["shortlist_total"]}')
        w(f'  ОТБРОШЕНО ЧИСЛОВОЙ ПРОВЕРКОЙ (Шаг B)        : '
          f'{k["numeric_rejects_b"]}')
        w(f'  отброшено числовой проверкой (Шаг A)        : '
          f'{k["numeric_rejects_a"]}')
        w(f'  отброшено как «сходство ниже {self.opts["fuzzy_min"]}»         : '
          f'{k["fuzzy_dropped"]}')

        candidates = {m.candidate_id for m in k['decided']}
        w('')
        w(f'РАЗНЫЕ ЗАДАЧИ-КОПИИ, готовые к записи        : {len(candidates)}')
        w(f'Строк OlympiadRef будет создано              : '
          f'{self._planned_row_count(k["decided"])}')

        w('')
        w('РАЗБИВКА КАНДИДАТОВ ПО ИСТОЧНИКУ')
        by_source = Counter()
        seen_with_source = set()
        for pid, name in SourceReference.objects.filter(
                problem_id__in=candidates).values_list('problem_id', 'source__name'):
            by_source[name] += 1
            seen_with_source.add(pid)
        for name, count in by_source.most_common():
            w(f'   {count:6d}  {name}')
        without = len(candidates - seen_with_source)
        w(f'   {without:6d}  (без SourceReference вовсе)')

        w('')
        w('ШАГ C — СВЕРКА ЯКОРЕЙ МЕЖДУ СОБОЙ (в базу не пишет)')
        w(f'  пар якорей, совпавших по тексту и числам   : {self.step_c_pairs}')
        w(f'  из них РАСХОДЯТСЯ по олимпиаде/году/этапу  : {len(k["conflict_rows"])}')
        w(f'  объединено классов (grade-only, НЕ конфликт): '
          f'{len(self.step_c_grade_rows)}')
        for row in k['conflict_rows'][:5]:
            w(f'    #{row["problem_a"]} [{row["a_site"]}] {row["a_says"]}')
            w(f'    #{row["problem_b"]} [{row["b_site"]}] {row["b_says"]}')
            w(f'      сходство {row["fuzzy"]}')
        merges = Counter(r['merged_grade'] for r in self.step_c_grade_rows)
        if merges:
            w(f'  какие диапазоны получились: {dict(merges.most_common(10))}')
            for row in self.step_c_grade_rows[:5]:
                w(f'    #{row["problem_a"]} + #{row["problem_b"]}  '
                  f'{row["olympiad_slug"]} {row["year"]} {row["stage"] or "-"}: '
                  f'{row["a_grade"]!r} + {row["b_grade"]!r} → {row["merged_grade"]!r}')

        w('')
        w('ОТЧЁТЫ')
        for name in (REVIEW_QUEUE, ANCHOR_CONFLICTS, GRADE_MERGES):
            w(f'   {os.path.join(self.reports_dir, name)}')
        w(f'   {self.preview_path}   ← открыть двойным кликом')

        w('')
        w(f'ПРИМЕРЫ АВТОЗАПИСИ — {len(self.preview_sample)} шт., текстом')
        for m in self.preview_sample:
            w('')
            w(f'  [{m.method}] сходство {m.score:.4f}'
              + (f', косинус {m.cosine:.4f}' if m.cosine is not None else '')
              + f' · {self._describe(self.refs_by_anchor[m.anchor_id])}')
            w(f'    кандидат #{m.candidate_id}: '
              f'{self.raw_text[m.candidate_id][:260]!r}')
            w(f'    якорь    #{m.anchor_id}: '
              f'{self.raw_text[m.anchor_id][:260]!r}')

        w('')
        w(f'ПРИМЕРЫ ИЗ ОЧЕРЕДИ — {len(self.queue_sample)} шт.')
        for row in self.queue_sample:
            w('')
            w(f'  [{row["reason"]}] косинус {row["cosine"]}, '
              f'сходство {row["fuzzy"]}, конфликт {row["conflict"]}')
            w(f'    кандидат #{row["candidate_id"]}: '
              f'{row["candidate_text_300"][:220]!r}')
            w(f'    якорь    #{row["anchor_id"]}: '
              f'{row["anchor_text_300"][:220]!r}')

    def _planned_row_count(self, decided):
        return sum(len(self.refs_by_anchor[m.anchor_id]) for m in decided)

    # ── запись ───────────────────────────────────────────────────────────

    def _apply(self, decided):
        """Только ВСТАВКА новых строк OlympiadRef. Ничего не меняет и не удаляет."""
        for m in decided:
            if m.candidate_id in self.problems_with_any_ref:
                raise CommandError(
                    f'Задача #{m.candidate_id} уже имеет строку OlympiadRef, '
                    f'а по построению кандидатом быть не может. Прогон '
                    f'остановлен: выбирать, какую версию оставить, '
                    f'самостоятельно нельзя.')

        created, skipped_long = [], []
        with transaction.atomic():
            for m in decided:
                for ref in self.refs_by_anchor[m.anchor_id]:
                    event_id = (f'{ref.event_id}__propagated_{m.method}'
                                f'__from{m.anchor_id}')
                    if len(event_id) > EVENT_ID_MAX:
                        skipped_long.append((m.candidate_id, event_id))
                        continue
                    row = OlympiadRef(
                        problem_id=m.candidate_id,
                        event_id=event_id,
                        match_method=m.method,
                        match_score=m.score,
                        reviewed_by_human=False,
                        raw_meta={
                            'propagated_from_problem_id': m.anchor_id,
                            'propagated_from_event_id': ref.event_id,
                            'cosine': m.cosine,
                            'fuzzy_ratio': m.fuzzy,
                            'numeric_match': True,
                        },
                        **{f: getattr(ref, f) for f in COPIED_FIELDS},
                    )
                    row.save()
                    created.append(row.id)

        journal = os.path.join(self.reports_dir, APPLIED_JOURNAL)
        with open(journal, 'w', encoding='utf-8') as handle:
            json.dump({
                'created_olympiadref_ids': created,
                'candidates': sorted({m.candidate_id for m in decided}),
                'how_to_revert': (
                    'OlympiadRef.objects.filter(id__in=created_olympiadref_ids)'
                    '.delete() — строки только добавлялись, Problem и '
                    'SourceReference не менялись.'),
            }, handle, ensure_ascii=False, indent=2)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'ЗАПИСАНО: {len(created)} строк OlympiadRef на '
            f'{len({m.candidate_id for m in decided})} задач.'))
        if skipped_long:
            self.stdout.write(self.style.WARNING(
                f'⚠️  Пропущено по длине event_id (>{EVENT_ID_MAX}): '
                f'{len(skipped_long)}'))
        self.stdout.write(f'Журнал отката: {journal}')
