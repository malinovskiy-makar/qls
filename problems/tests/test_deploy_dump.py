# -*- coding: utf-8 -*-
u"""
Выгрузка для заливки в прод: граф внешних ключей обязан быть ЗАМКНУТ.

⚠️ ЗАЧЕМ ЭТОТ ТЕСТ ВООБЩЕ ПОЯВИЛСЯ. `dump_for_deploy` выгружал
`Submission`, но не выгружал `AssignmentItem`, на который тот ссылается.
Заливка в ЧИСТУЮ PostgreSQL падала:

    IntegrityError: insert or update on table "problems_submission"
    violates foreign key constraint ...
    DETAIL: Key (problem_item_id)=(18) is not present in table
    "problems_assignmentitem".

Локально этого не видно (SQLite), на проде не видно (строки уже лежали),
и дыра прожила незамеченной до первой репетиции выкатки на чистой базе
(сессия «Wecon Rush», фаза 8). Пересборка выгрузки ловится теперь здесь, а
не на боевом сервере в час выкатки.
"""
from django.apps import apps
from django.test import SimpleTestCase

from problems.management.commands import dump_for_deploy as dfd

# Модели, которые выгружаются отдельными файлами, а не через TIER-списки.
EXPLICIT = [
    'problems.Problem', 'problems.SourceReference', 'problems.ProblemPart',
    'problems.DuplicateCandidate', 'problems.AutoTopicAssignment',
]


def dumped_models():
    labels = list(dfd.TIER1) + list(dfd.TIER4_MISC) + EXPLICIT
    out = set()
    for label in labels:
        try:
            out.add(apps.get_model(*label.split('.')))
        except LookupError:
            pass
    return out


class DumpGraphTests(SimpleTestCase):

    def test_no_foreign_key_points_outside_the_dump(self):
        u"""Каждая ссылка выгруженной модели ведёт в выгруженную же."""
        dumped = dumped_models()
        holes = []
        for model in sorted(dumped, key=lambda m: m.__name__):
            for field in model._meta.get_fields():
                if not (getattr(field, 'many_to_one', False)
                        or getattr(field, 'one_to_one', False)):
                    continue
                if not getattr(field, 'concrete', False):
                    continue
                target = field.related_model
                if target is None or target in dumped:
                    continue
                holes.append('%s.%s -> %s'
                             % (model.__name__, field.name, target.__name__))
        self.assertEqual(
            holes, [],
            u'В выгрузке есть ссылки на модели, которых в ней нет. Заливка '
            u'в чистую PostgreSQL упадёт на внешнем ключе:\n  '
            + '\n  '.join(holes))

    def test_referenced_models_are_listed_before_those_that_need_them(self):
        u"""Порядок в TIER4_MISC не случаен: файл 40_misc.json грузится
        по порядку, и ссылающийся не может идти раньше того, на кого
        ссылается."""
        order = {label: i for i, label in enumerate(dfd.TIER4_MISC)}
        pairs = [
            ('problems.CustomProblem', 'problems.CustomProblemOption'),
            ('problems.CustomProblem', 'problems.AssignmentItem'),
            ('problems.Assignment', 'problems.AssignmentItem'),
            ('problems.SavedFolder', 'problems.SavedGraph'),
            ('problems.SavedGraph', 'problems.AssignmentItem'),
            ('problems.AssignmentItem', 'problems.Submission'),
            ('problems.Submission', 'problems.TeacherFeedback'),
        ]
        wrong = []
        for first, second in pairs:
            if first not in order or second not in order:
                wrong.append('%s или %s нет в списке' % (first, second))
                continue
            if order[first] > order[second]:
                wrong.append('%s обязан идти РАНЬШЕ %s' % (first, second))
        self.assertEqual(wrong, [], '\n  '.join(wrong))
