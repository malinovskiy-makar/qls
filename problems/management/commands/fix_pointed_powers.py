# -*- coding: utf-8 -*-
"""
Сессия H4, этап 3h — ТОЧЕЧНЫЕ правки потерянных степеней (по ручному разбору
преподавателя). Массово степени НЕ трогаем (см. detect_power_candidates).

Каждая правка — явная пара (поле, искомая_строка → замена). Применяется ТОЛЬКО
если искомая строка присутствует ровно как указано (иначе пропуск с предупреждением).
Идемпотентна (после замены искомой строки больше нет).

Запуск:
  ./venv/bin/python manage.py fix_pointed_powers --dry-run
  ./venv/bin/python manage.py fix_pointed_powers --apply
"""
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart

CHANGED_IDS_FILE = 'reports/sessionH4/changed_ids_H4.txt'

# (problem_id, part_label|None, find, replace)
# part_label=None → Problem.statement; иначе ProblemPart.statement с этой меткой.
FIXES = [
    # #5442 Шпиц: X 3Y → X^3 Y  (U_2 = X³Y)
    (5442, None, '$U_2 = X 3Y$', '$U_2 = X^3 Y$'),
    # #5443 Шпиц: (K+3)L 2 → (K+3)L^2
    (5443, None, '$Q = (K + 3)L 2$', '$Q = (K + 3)L^2$'),
    # #5451 Шпиц: X a Y 1 - a → X^a Y^{1-a}  (Кобба-Дугласа)
    (5451, None, '$U = X a Y 1 - a$', '$U = X^a Y^{1 - a}$'),
    # #7732 Шпиц: голая math-italic 𝑈= 𝑋𝑌2 → $U = XY^2$
    (7732, None, '𝑈= 𝑋𝑌2', '$U = XY^2$'),
    # #47671 ОЭШ: TC= Q_2 → TC= Q^2
    (47671, None, '$TC= Q_2$', '$TC= Q^2$'),
    # #47653 ОЭШ: издержки Q_2/Q_3 → Q^2/Q^3 (по подпунктам)
    (47653, 'a', '$TC= Q_2 + 6$', '$TC= Q^2 + 6$'),
    (47653, 'd', '$TC= Q_2$\n4 + 20Q', '$TC= Q^2/4 + 20Q$'),
    (47653, 'e', '$TC= 30Q-Q_2, Q\\le 15$', '$TC= 30Q-Q^2, Q\\le 15$'),
    (47653, 'f', '$TC= Q_3$', '$TC= Q^3$'),
    (47653, 'g', '$TC= Q_2$', '$TC= Q^2$'),
]


class Command(BaseCommand):
    help = 'H4 этап 3h: точечные правки потерянных степеней (3+ задачи)'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **o):
        os.makedirs('reports/sessionH4', exist_ok=True)
        apply = o['apply']
        changed_ids = set()
        applied = skipped = 0

        for pid, label, find, repl in FIXES:
            if label is None:
                try:
                    p = Problem.objects.get(id=pid)
                except Problem.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f'#{pid} нет в базе')); skipped += 1; continue
                field_val = p.statement or ''
                target = p
                save_kw = dict(update_fields=['statement'])
                attr = 'statement'
            else:
                pt = ProblemPart.objects.filter(problem_id=pid, label=label).first()
                if not pt:
                    self.stdout.write(self.style.ERROR(f'#{pid} part {label!r} нет')); skipped += 1; continue
                field_val = pt.statement or ''
                target = pt
                save_kw = dict(update_fields=['statement'])
                attr = 'statement'

            cnt = field_val.count(find)
            if cnt == 0:
                # уже исправлено? проверим наличие replace
                if repl in field_val:
                    self.stdout.write(f'#{pid} {label or "stmt"}: уже исправлено (skip)')
                else:
                    self.stdout.write(self.style.WARNING(
                        f'#{pid} {label or "stmt"}: искомая строка НЕ найдена — пропуск'))
                skipped += 1
                continue
            if cnt > 1:
                self.stdout.write(self.style.WARNING(
                    f'#{pid} {label or "stmt"}: найдено {cnt} вхождений — пропуск (неоднозначно)'))
                skipped += 1
                continue

            new_val = field_val.replace(find, repl)
            self.stdout.write(f'#{pid} {label or "stmt"}: {find!r} → {repl!r}')
            applied += 1
            changed_ids.add(pid)
            if apply:
                setattr(target, attr, new_val)
                with transaction.atomic():
                    target.save(**save_kw)

        mode = 'БОЕВОЙ' if apply else 'DRY-RUN'
        self.stdout.write(self.style.SUCCESS(
            f'\n{mode}: применимо {applied}, пропущено {skipped}.'))
        if apply and changed_ids:
            with open(CHANGED_IDS_FILE, 'a', encoding='utf-8') as f:
                f.write('\n'.join(map(str, sorted(changed_ids))) + '\n')
