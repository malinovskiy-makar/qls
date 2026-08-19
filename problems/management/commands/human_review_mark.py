"""Простановка `Problem.human_review` по строкам ReviewVerdict.

Поле — денормализованный СВОД по вердиктам, а не второй источник правды:
ходить в ReviewVerdict на каждый запрос каталога дорого, но правда всё равно
там. Поэтому команда идемпотентна и пересчитывает свод целиком.

ПРАВИЛО СТАРШИНСТВА: «брак» сильнее «идеально». Если у задачи есть хоть один
не-perfect вердикт (в любом пакете), задача получает `defect`. Причина —
направление ошибки: одобрить сломанное хуже, чем задержать хорошее. Задача
может попасть в разные пакеты и получить там разные вердикты; это не
переголосование, а два измерения, и осторожное из них — «брак».

«Гагно» (trash) — тоже `defect`: задачу ОСМОТРЕЛИ, просто она кандидат на
выброс, а не на починку. В `approved` она не попадает никогда. Отдельным
состоянием не заводится: кто именно trash, всегда видно по самим вердиктам
(категория trash никуда не девается), а размер пакета на разбор считается
по вердиктам пакета.

⚠️ ИСКЛЮЧЕНИЙ БОЛЬШЕ НЕТ — ПРЕЖНЕЕ ОКАЗАЛОСЬ ОШИБКОЙ (исправлено 2026-08-19).
Семь вердиктов ILE с комментарием «тест» (id 182, 872, 1734, 1988, 2135,
2261, 2499) считались недостоверными: будто ревьюер пробовал оболочку и
ставил метки наугад. Владелец подтвердил, что это неверно. «тест» здесь
означает ТИП ЗАДАЧИ — задание с выбором варианта ответа, ровно то же, что и
в 166 таких комментариях МатЭка. Видно по самим задачам: у #2261 варианты
«а) 15000 б) 30000 …» лежат прямо в условии при пустом `problem_type`.
Вердикты достоверны и учитываются наравне со всеми; все семь — категория
`other`, то есть брак.

Механизм пакет-специфичного исключения оставлен на случай, если недостоверные
вердикты найдутся впредь. Если он понадобится — исключение задавать СПИСКОМ
ID для КОНКРЕТНОГО пакета, а НЕ поиском слова по тексту комментария: поиск
слова «тест» уничтожил бы 166 честных вердиктов МатЭка.

    venv\\Scripts\\python manage.py human_review_mark            # только показать
    venv\\Scripts\\python manage.py human_review_mark --apply
    venv\\Scripts\\python manage.py human_review_mark --revert --apply
"""

import os
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ReviewVerdict
from problems.review_categories import REVIEW_CATEGORIES

# Виды категорий, означающие «человек претензий не имеет».
OK_KINDS = {'ok'}
KIND_BY_KEY = {c['key']: c['kind'] for c in REVIEW_CATEGORIES}

# ПОВТОРНОЕ РЕВЬЮ: пакет -> пакет, который он ОТМЕНЯЕТ.
#
# Пакеты reports/defect_review — это разбор задач, уже забракованных в
# исходном пакете. Там человек смотрит УЖЕ ПОЧИНЕННЫЙ текст и отвечает на
# другой вопрос: «можно ли это публиковать СЕЙЧАС». Поэтому его «идеально»
# обязано перебить прежний брак, иначе починенная задача навсегда осталась бы
# скрытой, а разбор не имел бы смысла.
#
# ⚠️ Это ЕДИНСТВЕННОЕ исключение из правила «брак сильнее идеального». Оно
# работает только между явно названной парой пакетов и только в одну сторону:
# новый отменяет старый, но не наоборот. Вердикты старого пакета из базы НЕ
# удаляются — видно, что задача чинилась.
SUPERSEDES = {
    'defect_ile_20260721': 'ile_20260721',
    'defect_aa_20260728': 'aa_20260728',
    'defect_matek_20260808': 'matek_20260808',
}

# Пакет -> файл со списком НЕДОСТОВЕРНЫХ вердиктов (id задач).
# Только для перечисленных здесь пакетов; для остальных исключений нет.
#
# ⚠️ ПУСТО, И ЭТО НАМЕРЕННО. Здесь стоял ILE со списком reports/ile_triage/
# recheck_ids.txt — семь вердиктов «тест», которые считались пробой оболочки.
# 2026-08-19 владелец подтвердил, что чтение было неверным: «тест» это тип
# задачи, а не проба. Запись убрана, все семь вердиктов учитываются.
# Сам файл recheck_ids.txt не удалён — на него ещё смотрят команды прошлых
# экспериментов (см. отчёт сессии), но НА СОСТОЯНИЕ ЗАДАЧ он больше не влияет.
UNRELIABLE = {}


def read_ids(path):
    """Список id из файла с комментариями «#». Нет файла -> пустое множество."""
    if not os.path.exists(path):
        return set()
    out = set()
    with open(path, encoding='utf-8-sig') as fh:
        for line in fh:
            line = line.split('#', 1)[0].strip()
            if line.isdigit():
                out.add(int(line))
    return out


def collect_states():
    """Состояния по всем вердиктам базы.

    Возвращает (states, dropped, seen_bundle):
      states      — {problem_id: 'approved' | 'defect'},
      dropped     — {пакет: сколько вердиктов отброшено как недостоверные},
      seen_bundle — {пакет: множество задач пакета после отсева}.
    """
    unreliable = {b: read_ids(p) for b, p in UNRELIABLE.items()}

    by_problem = defaultdict(set)          # problem_id -> {kind, ...}
    dropped = Counter()
    overridden = Counter()
    seen_bundle = defaultdict(set)

    rows = list(ReviewVerdict.objects.values_list('problem_id', 'bundle',
                                                  'category'))

    # Какие пары (задача, пакет) отменены повторным ревью этой же задачи.
    superseded = set()
    for pid, bundle, _cat in rows:
        parent = SUPERSEDES.get(bundle)
        if parent:
            superseded.add((pid, parent))

    for pid, bundle, category in rows:
        if pid in unreliable.get(bundle, ()):
            dropped[bundle] += 1
            continue
        if (pid, bundle) in superseded:
            overridden[bundle] += 1
            continue
        by_problem[pid].add(KIND_BY_KEY.get(category, 'defect'))
        seen_bundle[bundle].add(pid)

    states = {}
    for pid, kinds in by_problem.items():
        # Брак сильнее «идеально»: любой не-ok вид даёт defect.
        states[pid] = (Problem.HumanReview.APPROVED
                       if kinds <= OK_KINDS
                       else Problem.HumanReview.DEFECT)
    return states, dropped, seen_bundle, overridden


class Command(BaseCommand):
    help = ('Проставляет Problem.human_review по вердиктам ручного ревью. '
            'Без --apply только показывает.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='записать в базу')
        parser.add_argument('--revert', action='store_true',
                            help='очистить поле у всех задач')

    def handle(self, *args, **opts):
        say = self.stdout.write

        if opts['revert']:
            n = Problem.objects.exclude(
                human_review=Problem.HumanReview.NONE).count()
            if opts['apply']:
                Problem.objects.exclude(
                    human_review=Problem.HumanReview.NONE
                ).update(human_review=Problem.HumanReview.NONE)
                say('ОТКАТ: очищено {} задач.'.format(n))
            else:
                say('ОТКАТ (проба): очистило бы {} задач. '
                    'Повторите с --apply.'.format(n))
            return

        states, dropped, seen_bundle, overridden = collect_states()

        say('=== ВЕРДИКТЫ ПО ПАКЕТАМ ===')
        for bundle in sorted(seen_bundle):
            tail = ('  (выброшено недостоверных: {})'.format(dropped[bundle])
                    if dropped.get(bundle) else '')
            if overridden.get(bundle):
                tail += '  (отменено повторным ревью: {})'.format(
                    overridden[bundle])
            say('  {:20s} задач: {}{}'.format(
                bundle, len(seen_bundle[bundle]), tail))

        want = Counter(states.values())
        say('')
        say('=== СОСТОЯНИЯ ПО ВЕРДИКТАМ ===')
        say('  approved : {}'.format(want[Problem.HumanReview.APPROVED]))
        say('  defect   : {}'.format(want[Problem.HumanReview.DEFECT]))

        # «Гагно» — считаем отдельно, но состояние у него defect.
        trash_ids = set(ReviewVerdict.objects.filter(category='trash')
                        .values_list('problem_id', flat=True))
        say('  из них «Гагно» (кандидаты на выброс): {}'.format(len(trash_ids)))
        for bundle in sorted(seen_bundle):
            n = ReviewVerdict.objects.filter(
                bundle=bundle, category='trash').count()
            if n:
                say('     {}: {}'.format(bundle, n))

        current = dict(Problem.objects.exclude(
            human_review=Problem.HumanReview.NONE
        ).values_list('id', 'human_review'))
        to_set = {pid: st for pid, st in states.items()
                  if current.get(pid) != st}
        to_clear = [pid for pid in current if pid not in states]

        say('')
        say('ИЗМЕНИТСЯ: поставить/переставить {}, очистить {}'.format(
            len(to_set), len(to_clear)))

        if not opts['apply']:
            say('Это проба. Повторите с --apply, чтобы записать.')
            return

        with transaction.atomic():
            for state in (Problem.HumanReview.APPROVED,
                          Problem.HumanReview.DEFECT):
                ids = [pid for pid, st in to_set.items() if st == state]
                for i in range(0, len(ids), 500):
                    Problem.objects.filter(id__in=ids[i:i + 500]).update(
                        human_review=state)
            for i in range(0, len(to_clear), 500):
                Problem.objects.filter(id__in=to_clear[i:i + 500]).update(
                    human_review=Problem.HumanReview.NONE)

        say('ЗАПИСАНО.')
        final = Counter(Problem.objects.values_list('human_review', flat=True))
        say('  approved : {}'.format(final[Problem.HumanReview.APPROVED]))
        say('  defect   : {}'.format(final[Problem.HumanReview.DEFECT]))
        say('  пусто    : {}'.format(final[Problem.HumanReview.NONE]))
