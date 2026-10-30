"""Повторы комплектов пакета олимпиад: один вариант из разных источников.

Один и тот же вариант лежит в пакете по 2–3 раза: vos.olimpiada.ru выкладывает
туры по отдельности, iloveeconomics.ru — тот же тур или оба тура одним файлом,
региональные сайты — тот же региональный вариант. Навигатору нужен один вход
на вариант (решение владельца 30.10, ADR 0171). Модуль только РЕШАЕТ, кто
чей повтор; пишет `mark_olympiad_kit_duplicates`.

⚠️ ПРИЗНАК ПОВТОРА — ТЕКСТ, А НЕ НАБОР ЗАДАЧ БАНКА. Склейка заданий в банк
(S4, ADR 0170) строгая и разводит даже разницу в разметке (жирный шрифт,
`\\over` против `\\frac`), поэтому повторы из разных источников часто указывают
на РАЗНЫЕ задачи банка. Позиции совпадают, если указывают на одну задачу, их
тексты проходят приговор `bank_match` (сходство ≥ 0,90, ни одно число не
заменено, знаки операций те же) или короткий текст совпадает с НАЧАЛОМ
длинного (см. `Matcher._same_prefix`).

Кто может быть повтором кого: комплекты пакета одной олимпиады, одного этапа
и одного сезона; классы основного покрывают классы повтора. Код региона не
мешает: региональный вариант ВсОШ общий на страну, защита — сравнение текста.
Скрытый комплект бывает повтором, но основным — никогда.

- `source` — туры одинаковые (или оба пустые), ≥ 80 % позиций меньшего
  комплекта совпадают с позициями большего;
- `combined` — комплект без тура, у которого есть ≥ 2 комплекта с турами,
  каждый совпадает с ним на ≥ 80 % своих позиций, и вместе они покрывают
  ≥ 80 % его позиций. Указывает на комплект первого тура.
"""
import collections
import difflib

from olympiads import bank_match as bm

SHARE = 0.80            # порог доли совпавших позиций
PREFIX_MIN = 100        # короче (после нормализации) — поправка «начало» не применяется
PREFIX_SLACK = 1.05     # начало длинного берётся чуть длиннее короткого
GRAM = 5                # длина фрагмента грубого отсева поправки
GRAM_SHARE = 0.30       # доля общих фрагментов, ниже которой difflib не зовём

# Порядок туров для «первого тура» сводного файла. Числа — по числу;
# у регионального этапа ВсОШ тест идёт перед задачами, эссе — последним.
_TOUR_WORDS = {'test': 1, 'problems': 2, 'essay': 3}


def tour_order(tour):
    digits = ''.join(ch for ch in tour if ch.isdigit())
    if digits:
        return (0, int(digits), tour)
    return (1, _TOUR_WORDS.get(tour, 9), tour)


class Kit:
    """Комплект в памяти: всё, что нужно правилу, без обращений к базе."""

    def __init__(self, pk, kit_key, group, tour, grades, items, merit,
                 official, locked, hidden, current):
        self.pk = pk
        self.kit_key = kit_key
        self.group = group          # (олимпиада, этап, сезон)
        self.tour = tour
        self.grades = frozenset(grades)   # пусто — «все классы»
        self.items = list(items)    # id задач банка по порядку позиций
        self.merit = merit          # эталоны + критерии + решения по позициям
        self.official = official    # есть файл с official=True
        self.locked = locked        # есть TrainingAttempt — не трогать
        self.hidden = hidden        # скрыт — только повтор, не основной
        self.current = current      # (duplicate_of_id, duplicate_kind) сейчас

    def rank(self):
        """Чем меньше, тем основнее (порядок — решения владельца 30.10).

        Тур основнее сводного; затем шире классы («все» шире любого
        диапазона); затем больше эталонов, критериев и решений; затем есть
        официальный файл; затем меньший `kit_key`.
        """
        breadth = 99 if not self.grades else len(self.grades)
        return (not self.tour, -breadth, -self.merit, not self.official,
                self.kit_key)


def grades_compatible(a, b):
    """Классы одного покрывают классы другого (пусто — все классы)."""
    return covers(a, b) or covers(b, a)


def covers(main, dup):
    """Классы основного покрывают классы повтора: иначе клетка опустеет."""
    return not main.grades or (bool(dup.grades) and dup.grades <= main.grades)


def _grams(text):
    return {text[i:i + GRAM] for i in range(len(text) - GRAM + 1)}


class Matcher:
    """Совпадение позиций по тексту задач банка — приговором `bank_match`."""

    def __init__(self, rows, parts):
        self.index = bm.BankIndex(rows, parts)
        self.parts = parts
        self.cache = {}
        self.ops = {}

    def _task(self, pid):
        return {'statement_md': self.index.ours[pid][0] or '', 'section_md': '',
                'parts': [{'text': t} for t in self.parts.get(pid, ())]}

    def same(self, a, b):
        if a == b:
            return True
        key = (a, b) if a < b else (b, a)
        if key not in self.cache:
            self.cache[key] = self._same(*key) or self._same_prefix(*key)
        return self.cache[key]

    def _same(self, a, b):
        full_a, full_b = self.index.ourfull[a], self.index.ourfull[b]
        # Короткие тексты («Верно ли, что…») совпадают случайно; у пустых
        # `ratio` и вовсе 1,0. Для них — только одна и та же задача банка.
        if len(full_a) < bm.MIN_LEN or len(full_b) < bm.MIN_LEN:
            return False
        # Верхняя граница сходства по одним длинам: дешёвый отсев до difflib.
        stmt_a, stmt_b = self.index.ournorm[a], self.index.ournorm[b]
        bound = max(2 * min(len(full_a), len(full_b)) / (len(full_a) + len(full_b)),
                    2 * min(len(stmt_a), len(stmt_b)) / max(1, len(stmt_a) + len(stmt_b)))
        if bound < bm.ACCEPT:
            return False
        _score, why = self.index.verdict(self._task(a), b)
        return why is None

    def _ops(self, pid, whole):
        key = (pid, whole)
        if key not in self.ops:
            raw = self.index.ourraw[pid] if whole else (self.index.ours[pid][0] or '')
            self.ops[key] = bm.operator_sequence(raw)
        return self.ops[key]

    def _same_prefix(self, a, b):
        """Короткий текст совпадает с НАЧАЛОМ длинного (решение владельца 30.10).

        Так выглядят обе грязи оцифровки: условие, записанное дважды подряд,
        и решение, вклеенное в условие. Общее вступление («Рассмотрим рынок
        совершенной конкуренции…») способно совпасть с началом чужой задачи,
        поэтому защита та же, что у `bank_match`, но на совпавшем отрезке:
        сходство ≥ 0,90 с началом длинного, ни одно число короткого в этом
        начале не заменено, знаки операций короткого — начало знаков длинного.
        Короче 100 знаков после нормализации — не применяется.
        """
        for whole, texts in ((True, self.index.ourfull), (False, self.index.ournorm)):
            short, long_ = (a, b) if len(texts[a]) <= len(texts[b]) else (b, a)
            s, l = texts[short], texts[long_]
            # Начало длинного = весь длинный: это уже решил `_same`.
            if len(s) < PREFIX_MIN or len(l) <= len(s) * PREFIX_SLACK:
                continue
            head = l[:int(len(s) * PREFIX_SLACK)]
            # Грубый отсев: при сходстве ≥ 0,90 общих 5-знаковых фрагментов
            # заведомо больше трети; чужие тексты на одном языке — 5–15 %.
            grams = _grams(s)
            if len(grams & _grams(head)) < GRAM_SHARE * len(grams):
                continue
            if (difflib.SequenceMatcher(None, s, head, autojunk=False).quick_ratio()
                    < bm.ACCEPT or bm.ratio(s, head) < bm.ACCEPT):
                continue
            if bm.number_replaced(s, head):
                continue
            ops_s, ops_l = self._ops(short, whole), self._ops(long_, whole)
            if ops_l[:len(ops_s)] != ops_s:
                continue
            return True
        return False


def matched_positions(small, large, matcher):
    """Номера позиций `small`, у которых есть совпадение в `large`."""
    return {i for i, pid in enumerate(small.items)
            if any(matcher.same(pid, other) for other in large.items)}


def share(small, large, matcher):
    return len(matched_positions(small, large, matcher)) / len(small.items)


def pair_share(a, b, matcher):
    """Доля позиций МЕНЬШЕГО комплекта, найденных в большем."""
    if len(a.items) != len(b.items):
        small, large = (a, b) if len(a.items) < len(b.items) else (b, a)
        return share(small, large, matcher)
    return max(share(a, b, matcher), share(b, a, matcher))


def decide(kits, matcher):
    """Желаемое состояние: {pk: (duplicate_of pk | None, kind)} и отчёт.

    Ничего не пишет. Комплекты с попытками (`locked`) повтором не становятся
    никогда, но основным — могут: основной в базе не меняется. Скрытые —
    наоборот: повтором могут, основным нет.
    """
    groups = collections.defaultdict(list)
    for kit in kits:
        groups[kit.group].append(kit)

    parent, kind = {}, {}
    pairs, combined_rows, skipped = [], [], collections.defaultdict(list)
    for group in sorted(groups):
        members = sorted(groups[group], key=lambda k: k.kit_key)
        compatible = [(a, b) for i, a in enumerate(members) for b in members[i + 1:]
                      if grades_compatible(a, b)]
        # ── сводные ──────────────────────────────────────────────────────
        combined = set()
        for c in members:
            if c.tour:
                continue
            parts = []
            for t in members:
                if t is c or not t.tour or not grades_compatible(c, t):
                    continue
                if share(t, c, matcher) >= SHARE:
                    parts.append(t)
            if len(parts) < 2:
                continue
            covered = set()
            for t in parts:
                covered |= matched_positions(c, t, matcher)
            coverage = len(covered) / len(c.items)
            row = {'kit': c.kit_key, 'tours': [t.kit_key for t in parts],
                   'coverage': round(coverage, 4)}
            combined_rows.append(row)
            visible = [t for t in parts if not t.hidden]
            if coverage < SHARE or not visible:
                continue
            first = min(visible, key=lambda t: (tour_order(t.tour), t.kit_key))
            main, dup = sorted([c, first], key=Kit.rank)
            if main.hidden or not covers(main, dup):
                skipped['grades_or_hidden'].append(dup.kit_key)
                continue
            if dup.locked:
                skipped['locked'].append(dup.kit_key)
                continue
            row['marked'] = True
            parent[dup.pk], kind[dup.pk] = main.pk, 'combined'
            combined.add(dup.pk)
        # ── повторы из другого источника ────────────────────────────────
        edges = collections.defaultdict(set)
        for a, b in compatible:
            same_tour = a.tour == b.tour
            value = pair_share(a, b, matcher)
            pairs.append({'a': a.kit_key, 'b': b.kit_key, 'tour_a': a.tour,
                          'tour_b': b.tour, 'items_a': len(a.items),
                          'items_b': len(b.items), 'same_tour': same_tour,
                          'share': round(value, 4)})
            if same_tour and value >= SHARE:
                edges[a.pk].add(b.pk)
                edges[b.pk].add(a.pk)
        # ⚠️ ЖАДНО ОТ ЛУЧШЕГО, А НЕ СВЯЗНЫМИ КОМПОНЕНТАМИ. Комплект «все
        # классы» совместим и с 9, и с 11 классом; компонента склеила бы 9 и
        # 11 через него. Повтор цепляется только к основному, с которым
        # совпал НАПРЯМУЮ и чьи классы покрывают его классы.
        taken = set(combined)
        for main in sorted(members, key=Kit.rank):
            if main.pk in taken or main.hidden:
                continue
            taken.add(main.pk)
            for dup in sorted(members, key=Kit.rank):
                if dup.pk in taken or dup.pk not in edges[main.pk]:
                    continue
                if not covers(main, dup):
                    continue
                if dup.locked:
                    skipped['locked'].append(dup.kit_key)
                    continue
                parent[dup.pk], kind[dup.pk] = main.pk, 'source'
                taken.add(dup.pk)

    # ── цепочки → прямая ссылка на корень ────────────────────────────────
    def root(pk):
        seen = set()
        while pk in parent and pk not in seen:
            seen.add(pk)
            pk = parent[pk]
        return pk

    desired = {}
    for kit in kits:
        if kit.pk in parent:
            desired[kit.pk] = (root(kit.pk), kind[kit.pk])
        else:
            desired[kit.pk] = (None, '')
    return desired, {'pairs': pairs, 'combined': combined_rows,
                     'skipped': {k: sorted(set(v)) for k, v in skipped.items()}}


def load(only=''):
    """Кандидаты из базы: list[Kit] и Matcher по их задачам.

    ⚠️ Прежние комплекты (пустой `kit_key`) не участвуют вовсе, скрытые —
    участвуют, но только как повторы.
    """
    from django.db.models import Count, Q

    from olympiads.models import (OlympiadVariant, OlympiadVariantGrade,
                                  OlympiadVariantItem)
    from problems.models import Problem, ProblemPart

    qs = (OlympiadVariant.objects
          .filter(kit_key__isnull=False, stage__isnull=False)
          .exclude(kit_key='').exclude(season='')
          .annotate(n_attempts=Count('attempts', distinct=True),
                    n_official=Count('files', filter=Q(files__official=True),
                                     distinct=True)))
    if only:
        qs = qs.filter(olympiad__slug=only)
    variants = list(qs)
    ids = [v.pk for v in variants]
    items = collections.defaultdict(list)
    merit = collections.Counter()
    for vid, pid, ans, crit, sol in (
            OlympiadVariantItem.objects
            .filter(variant_id__in=ids, absent_in_last_import=False)
            .order_by('variant_id', 'order', 'id')
            .values_list('variant_id', 'problem_id', 'has_answer',
                         'has_criteria', 'has_solution')):
        items[vid].append(pid)
        merit[vid] += ans + crit + sol
    grades = collections.defaultdict(list)
    for vid, grade in (OlympiadVariantGrade.objects
                       .filter(variant_id__in=ids).values_list('variant_id', 'grade')):
        grades[vid].append(grade)

    hidden = OlympiadVariant.Visibility.HIDDEN
    kits = [Kit(v.pk, v.kit_key, (v.olympiad_id, v.stage_id, v.season), v.tour,
                grades[v.pk], items[v.pk], merit[v.pk], v.n_official > 0,
                v.n_attempts > 0, v.visibility == hidden,
                (v.duplicate_of_id, v.duplicate_kind))
            for v in variants if items[v.pk]]

    pids = {pid for kit in kits for pid in kit.items}
    rows = Problem.objects.filter(id__in=pids).values_list(
        'id', 'statement', 'status', 'duplicate_of_id', 'human_review')
    parts = collections.defaultdict(list)
    for pid, text in (ProblemPart.objects.filter(problem_id__in=pids)
                      .order_by('problem_id', 'order', 'id')
                      .values_list('problem_id', 'statement')):
        parts[pid].append(text or '')
    return kits, Matcher(rows, parts)
