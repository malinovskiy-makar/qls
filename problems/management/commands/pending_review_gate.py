"""Скрытие задач, которых ЧЕЛОВЕК ЕЩЁ НЕ СМОТРЕЛ.

⚠️ ТРЕТИЙ, ОТДЕЛЬНЫЙ МЕХАНИЗМ СКРЫТИЯ. В проекте их теперь три, и смешивать
их нельзя, потому что они отвечают на РАЗНЫЕ вопросы:

    status='hidden'          — «убрано руками» (решение редактора);
    needs_quality_review     — «скрыто, потому что ПЛОХОЕ» (quality_gate:
                               битый рендер условия);
    hidden_pending_review    — «скрыто, потому что человек НЕ СМОТРЕЛ».

Третье — не оценка качества. Задача может быть прекрасной; мы про неё просто
ничего не знаем, а на сайте показываем только проверенное.

⚠️ ЧУЖИЕ СОСТОЯНИЯ НЕ ТРОГАЕМ. Команда ставит и снимает ТОЛЬКО свой признак.
Задача, спрятанная раньше шлюзом качества или руками, останется спрятанной и
после `--revert`, а её прежняя причина останется различимой. Иначе откат
превратился бы в массовую публикацию того, что прятали по другим поводам.

ОБРАТИМОСТЬ. `--apply` ставит признак ровно тем, у кого `human_review` не
равен `approved`; `--revert` снимает его у всех. Множество вычисляется, а не
запоминается, поэтому apply -> revert -> apply даёт то же самое.

    venv\\Scripts\\python manage.py pending_review_gate            # только счёт
    venv\\Scripts\\python manage.py pending_review_gate --apply
    venv\\Scripts\\python manage.py pending_review_gate --revert --apply
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from problems.models import Problem

OUT_DIR = os.path.join('reports', 'publication_check')
HIDDEN_LIST = os.path.join(OUT_DIR, 'hidden_pending_ids.txt')


def target_qs():
    """Кого прячем: всё, что НЕ одобрено человеком.

    Считаем по всей базе, а не только по видимому: признак должен быть
    проставлен и у черновиков, иначе публикация задачи в обход шлюза
    вернула бы её в каталог непроверенной.
    """
    return Problem.objects.exclude(human_review=Problem.HumanReview.APPROVED)


class Command(BaseCommand):
    help = ('Прячет из каталога задачи, которых человек ещё не смотрел. '
            'Без --apply только считает.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='записать в базу')
        parser.add_argument('--revert', action='store_true',
                            help='снять признак у всех задач')

    def handle(self, *args, **opts):
        say = self.stdout.write
        os.makedirs(OUT_DIR, exist_ok=True)

        HR = Problem.HumanReview
        published = Q(status=Problem.Status.PUBLISHED)

        if opts['revert']:
            n = Problem.objects.filter(hidden_pending_review=True).count()
            if not opts['apply']:
                say('ОТКАТ (проба): снял бы признак у {} задач. '
                    'Повторите с --apply.'.format(n))
                return
            Problem.objects.filter(hidden_pending_review=True).update(
                hidden_pending_review=False)
            say('ОТКАТ: признак снят у {} задач.'.format(n))
            say('⚠️ Задачи, спрятанные шлюзом качества или руками, остались '
                'спрятанными — их причина другая.')
            return

        # ── счёт до ────────────────────────────────────────────────────
        visible_now = Problem.objects.filter(
            published, needs_quality_review=False, hidden_pending_review=False)
        n_before = visible_now.count()
        n_approved = visible_now.filter(human_review=HR.APPROVED).count()
        n_defect = visible_now.filter(human_review=HR.DEFECT).count()
        n_unseen = visible_now.filter(human_review=HR.NONE).count()

        say('=== КАТАЛОГ СЕЙЧАС ===')
        say('  видно задач                : {}'.format(n_before))
        say('    из них одобрено человеком : {}'.format(n_approved))
        say('    из них человек нашёл брак : {}'.format(n_defect))
        say('    из них НЕ СМОТРЕЛИ        : {}'.format(n_unseen))
        say('')
        say('=== ЕСЛИ ПРИМЕНИТЬ ===')
        say('  будет спрятано             : {}'.format(n_defect + n_unseen))
        say('  останется в каталоге       : {}'.format(n_approved))
        say('  счётчик каталога: {} -> {}'.format(n_before, n_approved))

        # ── чужие механизмы: показываем, что не перепутались ───────────
        say('')
        say('=== ЧУЖИЕ МЕХАНИЗМЫ СКРЫТИЯ (не трогаем) ===')
        say('  status=hidden              : {}'.format(
            Problem.objects.filter(status='hidden').count()))
        say('  needs_quality_review=True  : {}'.format(
            Problem.objects.filter(needs_quality_review=True).count()))
        say('  спрятано И тем, и другим   : {}'.format(
            Problem.objects.filter(status='hidden',
                                   needs_quality_review=True).count()))

        want = set(target_qs().values_list('id', flat=True))
        have = set(Problem.objects.filter(hidden_pending_review=True)
                   .values_list('id', flat=True))
        say('')
        say('ПРИЗНАК: поставить {}, снять {} (сейчас стоит у {})'.format(
            len(want - have), len(have - want), len(have)))

        if not opts['apply']:
            say('')
            say('⚠️ СТОП-ГЕЙТ. Это только счёт, база не тронута.')
            say('   Применить: pending_review_gate --apply')
            return

        # ── применение ────────────────────────────────────────────────
        to_set = sorted(want - have)
        to_clear = sorted(have - want)
        for i in range(0, len(to_set), 500):
            Problem.objects.filter(id__in=to_set[i:i + 500]).update(
                hidden_pending_review=True)
        for i in range(0, len(to_clear), 500):
            Problem.objects.filter(id__in=to_clear[i:i + 500]).update(
                hidden_pending_review=False)

        with open(HIDDEN_LIST, 'w', encoding='utf-8') as fh:
            fh.write('# Задачи, спрятанные признаком hidden_pending_review.\n')
            fh.write('# Снять всё: pending_review_gate --revert --apply\n')
            for pid in sorted(want):
                fh.write('{}\n'.format(pid))

        after = Problem.objects.filter(
            published, needs_quality_review=False,
            hidden_pending_review=False).count()
        say('')
        say('ПРИМЕНЕНО. В каталоге стало: {} (было {}).'.format(
            after, n_before))
        say('Список спрятанных: {}'.format(HIDDEN_LIST))
