"""Д5: в туровом комплекте лежат и задания чужого тура — пометить их.

    manage.py exclude_foreign_tour_items            # сухой прогон, отчёт в reports/
    manage.py exclude_foreign_tour_items --apply    # снимок базы и запись

ВсОШ 2022/23–2025/26: комплект «1 тур» и комплект «2 тур» одного сезона и
класса содержат все задания обоих туров; чужие лежат отдельными задачами
банка (59993 — копия 59997). Правило карточки Notion: задание есть в обоих
туровых комплектах → остаётся там, где у позиции есть максимальный балл, в
другом — `excluded=True`, «не относится к туру». Балл есть в обоих или ни в
одном — «под вопросом».

⚠️ ВТОРОЙ ПРИЗНАК — ФАЙЛ-ИСТОЧНИК (решение дня, подтвердить). Чужие позиции
приносит общий файл решений обоих туров («Решения 11 класс.pdf»), а иногда с
ним и мелкий балл одного пункта (2 вместо 12). Если балл есть в обоих (или ни
в одном), но одна позиция взята ТОЛЬКО из файлов, общих для двух комплектов,
а другая — из файла условий своего тура, исключается первая. Иначе — «под
вопросом».

Одно и то же задание: тот же номер и начало условия (первые 600 знаков без
пробелов и разметки) сходится не меньше чем на `SAME_START`. Позиции не
удаляются; задачи банка не меняются.
"""
import collections
import difflib
import os

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from olympiads import bank_fix as bf
from olympiads import bank_match as bm

SAME_START = 0.6   # у копий 0,70–1,00, у разных заданий с одним номером ≤ 0,26
REASON_EXCLUDED = 'не относится к туру: задание тура {tour} (комплект {kit})'
REASON_TIE = 'задание есть в обоих турах, тур не определён: балл {why}'


def _start(problem):
    return bm.norm(problem.statement or '')[:600]


def _files(item):
    """Файлы-источники позиции: имя без каталога комплекта."""
    return {os.path.basename(path) for path in (item.pages or {}).get('source_file', [])}


def tour_pairs(only='vseros'):
    """[(комплект 1 тура, комплект 2 тура)] одного этапа, сезона и классов."""
    from olympiads import navigator as nav
    groups = collections.defaultdict(list)
    variants = nav.base_variants().filter(olympiad__slug=only).prefetch_related('grades')
    for v in variants:
        grades = tuple(sorted(g.grade for g in v.grades.all()))
        groups[(v.stage_id, v.season, grades)].append(v)
    pairs = []
    for kits in groups.values():
        tours = collections.Counter(v.tour for v in kits)
        if tours.get('1') == 1 and tours.get('2') == 1:
            one = next(v for v in kits if v.tour == '1')
            two = next(v for v in kits if v.tour == '2')
            pairs.append((one, two))
    return sorted(pairs, key=lambda p: (p[0].season, p[0].pk))


def build_plan(only='vseros'):
    plan = {'exclude': [], 'ties': [], 'pairs': 0, 'pairs_shared': 0, 'by_rule': collections.Counter()}
    for one, two in tour_pairs(only):
        plan['pairs'] += 1
        items = {}
        for kit in (one, two):
            items[kit.pk] = {i.number: i for i in kit.items.select_related('problem')
                             .filter(absent_in_last_import=False)}
        a, b = items[one.pk], items[two.pk]
        files_a = set().union(*[_files(i) for i in a.values()]) if a else set()
        files_b = set().union(*[_files(i) for i in b.values()]) if b else set()
        shared_files = files_a & files_b
        shared = 0
        for number in sorted(set(a) & set(b), key=lambda n: (len(n), n)):
            x, y = a[number], b[number]
            if x.excluded or y.excluded:
                continue
            ratio = difflib.SequenceMatcher(None, _start(x.problem), _start(y.problem),
                                            autojunk=False).ratio()
            if ratio < SAME_START:
                continue
            shared += 1
            loser, rule = None, ''
            if (x.max_score is None) != (y.max_score is None):
                loser, rule = (x if x.max_score is None else y), 'балл'
            else:
                x_shared = bool(_files(x)) and _files(x) <= shared_files
                y_shared = bool(_files(y)) and _files(y) <= shared_files
                if x_shared != y_shared:
                    loser, rule = (x if x_shared else y), 'файл'
            if loser is None:
                why = 'в обоих' if x.max_score is not None else 'ни в одном'
                plan['ties'].append({'items': [x.pk, y.pk], 'season': one.season,
                                     'kits': [one.pk, two.pk], 'number': number,
                                     'reason': REASON_TIE.format(why=why)})
                continue
            winner, owner = (y, two) if loser is x else (x, one)
            plan['by_rule'][rule] += 1
            plan['exclude'].append({
                'item': loser.pk, 'kept': winner.pk, 'season': one.season,
                'number': number, 'rule': rule, 'problem': loser.problem_id,
                'reason': REASON_EXCLUDED.format(tour=owner.tour, kit=owner.pk),
                'scores': [str(x.max_score), str(y.max_score)]})
        if shared:
            plan['pairs_shared'] += 1
    return plan


def tour_check(only='vseros', since=2020):
    """Заключительный с `since`: у каждого тура 4 задания и сумма 48 — исключения списком."""
    from olympiads import navigator as nav
    rows = []
    variants = nav._annotated(nav.base_variants().filter(
        olympiad__slug=only, stage__code='final', tour__in=['1', '2']))
    for v in variants.order_by('season', 'pk'):
        start = nav.season_start(v.season)
        if start is None or start < since:
            continue
        score = float(v.items_score) if v.items_score is not None else None
        ok = v.n_items == 4 and not v.n_unscored and score == 48
        rows.append({'kit': v.pk, 'season': v.season, 'tour': v.tour,
                     'grades': sorted(g.grade for g in v.grades.all()),
                     'tasks': v.n_items, 'unscored': v.n_unscored, 'sum': score, 'ok': ok})
    return rows


def our_tasks(only='vseros'):
    """«Заданий у нас» на странице олимпиады — тем же счётом, что экран."""
    from olympiads import navigator as nav
    ids = nav.base_variants().filter(olympiad__slug=only).values_list('pk', flat=True)
    return nav.problems_count(ids)


class Command(BaseCommand):
    help = 'Д5: пометить задания чужого тура в туровых комплектах. Без --apply — сухой прогон.'

    def add_arguments(self, parser):
        parser.add_argument('--only', default='vseros', help='Олимпиада по слагу.')
        parser.add_argument('--apply', action='store_true', help='Снимок и запись в базу.')
        parser.add_argument('--no-snapshot', action='store_true',
                            help='Не делать снимок (только для тестов).')
        parser.add_argument('--report-dir', default='', help='Куда класть отчёт.')

    def handle(self, *args, **options):
        from olympiads.models import OlympiadVariantItem as Item
        apply, only = options['apply'], options['only']
        plan = build_plan(only)
        tie_reasons = collections.defaultdict(list)
        for tie in plan['ties']:
            for pk in tie['items']:
                tie_reasons[pk].append(tie['reason'])
        flags = []
        for item in Item.objects.filter(pk__in=list(tie_reasons)).order_by('pk'):
            old = list(item.quality_reasons or [])
            new = old + [r for r in tie_reasons[item.pk] if r not in old]
            if new != old or item.quality != Item.Quality.FLAGGED:
                flags.append({'pk': item.pk, 'problem': item.problem_id, 'reasons': (old, new)})
        tasks_before = our_tasks(only)
        excluded_before = Item.objects.filter(excluded=True).count()
        snapshot = ''
        if apply and (plan['exclude'] or flags):
            digest = bf.old_digest()
            if not options['no_snapshot']:
                snapshot = bf.snapshot_database('foreign_tour')
                self.stdout.write('Снимок базы: {}'.format(snapshot))
            now = timezone.now()
            with transaction.atomic():
                for e in plan['exclude']:
                    Item.objects.filter(pk=e['item'], excluded=False).update(
                        excluded=True, excluded_reason=e['reason'], updated_at=now)
                bf.apply_flag_edits(flags, now)
                assert bf.old_digest() == digest, 'изменилась прежняя задача банка'
        excluded_after = Item.objects.filter(excluded=True).count()
        out = self.stdout.write
        out(self.style.SUCCESS('ЗАПИСАНО' if apply else 'СУХОЙ ПРОГОН (в базе ничего не изменено)'))
        out('Пар туровых комплектов: {}; с общими заданиями: {}'.format(
            plan['pairs'], plan['pairs_shared']))
        out('Позиций чужого тура исключено: {} (по баллу {}, по файлу-источнику {})'.format(
            len(plan['exclude']), plan['by_rule']['балл'], plan['by_rule']['файл']))
        out('Пар заданий «под вопросом»: {}; позиций с новой пометкой: {}'.format(
            len(plan['ties']), len(flags)))
        out('Исключённых позиций всего: {} → {}'.format(
            excluded_before, excluded_after if apply else excluded_before + len(plan['exclude'])))
        tasks_after = our_tasks(only) if apply else None
        out('«Заданий у нас» ({}): {} → {}'.format(only, tasks_before, tasks_after or '…'))
        check = tour_check(only)
        bad = [r for r in check if not r['ok']]
        out('Заключительный с 2020/21: туров {}, «4 задания, сумма 48» — {}; исключения:'.format(
            len(check), len(check) - len(bad)))
        for r in bad:
            out('  {season} кл. {grades} тур {tour} (комплект {kit}): заданий {tasks}, '
                'без балла {unscored}, сумма {sum}'.format(**r))
        path = bf.write_report('olympiads_foreign_tour', {
            'applied': apply, 'snapshot': snapshot, 'only': only,
            'pairs': plan['pairs'], 'pairs_shared': plan['pairs_shared'],
            'excluded': plan['exclude'], 'ties': plan['ties'], 'item_flags': flags,
            'by_rule': dict(plan['by_rule']), 'our_tasks_before': tasks_before,
            'our_tasks_after': tasks_after, 'tour_check': check,
        }, options['report_dir'])
        out('Отчёт: {}'.format(path))
