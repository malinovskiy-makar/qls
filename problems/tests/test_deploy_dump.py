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


# ---------------------------------------------------------------------------
# --bank-only: только банк задач, без работ учеников/преподавателя/аккаунтов
# ---------------------------------------------------------------------------
#
# Решение владельца 2026-09-02: на прод заливается ПОЛНЫЙ БАНК И ТОЛЬКО БАНК
# (152-ФЗ) — без Submission/TeacherFeedback/AssignmentItem и без самих
# пользователей. dump_for_deploy получил флаг --bank-only с собственным,
# более узким списком моделей (dfd.BANK_ONLY / dfd.BANK_ONLY_MISC).

BANK_ONLY_EXPLICIT = [
    'problems.Problem', 'problems.SourceReference', 'problems.ProblemPart',
]


def bank_only_dumped_models():
    labels = list(dfd.BANK_ONLY) + list(dfd.BANK_ONLY_MISC) + BANK_ONLY_EXPLICIT
    out = set()
    for label in labels:
        out.add(apps.get_model(*label.split('.')))
    return out


class BankOnlyGraphTests(SimpleTestCase):

    def test_bank_only_has_no_foreign_key_pointing_outside_the_dump(self):
        u"""Тот же граф-замок, что у полного дампа, но для --bank-only.

        Учитывает поля, которые команда сознательно вырезает при сериализации
        (dfd.BANK_ONLY_PROBLEM_STRIP) — иначе Problem.owner (-> User, вне
        дампа) и Problem.files (-> FileAsset, вне дампа) ложно красили бы
        тест, хотя в файл они не попадают вовсе."""
        dumped = bank_only_dumped_models()
        problem_model = apps.get_model('problems', 'Problem')
        stripped = {problem_model: set(dfd.BANK_ONLY_PROBLEM_STRIP)}
        holes = []
        for model in sorted(dumped, key=lambda m: m.__name__):
            skip = stripped.get(model, set())
            for field in model._meta.get_fields():
                if field.name in skip:
                    continue
                if not (getattr(field, 'many_to_one', False)
                        or getattr(field, 'one_to_one', False)
                        or getattr(field, 'many_to_many', False)):
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
            u'--bank-only ссылается на модели, которых в дампе нет. Заливка '
            u'в чистую PostgreSQL упадёт на внешнем ключе:\n  '
            + '\n  '.join(holes))


class BankOnlyNoPersonLinkedFieldTests(SimpleTestCase):
    u"""Ловит будущее добавление в --bank-only модели, привязанной к
    человеку — пользователю, ученику или преподавателю.

    Проверяются только КОНКРЕТНЫЕ поля (обычные, FK/O2O, M2M) — то, что
    реально сериализуется в JSON. Обратные связи (reverse accessor) в
    сериализацию не попадают, поэтому не проверяются: иначе тест красил бы
    Skill за то, что где-то в другом приложении на Skill ссылается модель
    ученика — а такая ссылка в дамп --bank-only всё равно не пишется."""

    FORBIDDEN = ('user', 'student', 'teacher')

    def test_bank_only_models_have_no_field_naming_a_person(self):
        problem_model = apps.get_model('problems', 'Problem')
        stripped = {problem_model: set(dfd.BANK_ONLY_PROBLEM_STRIP)}
        offenders = []
        for model in bank_only_dumped_models():
            skip = stripped.get(model, set())
            for field in model._meta.get_fields():
                if not getattr(field, 'concrete', False):
                    continue
                if field.name in skip:
                    continue
                lowered = field.name.lower()
                if any(word in lowered for word in self.FORBIDDEN):
                    offenders.append('%s.%s' % (model.__name__, field.name))
        self.assertEqual(
            offenders, [],
            u'В --bank-only попала модель с полем, ссылающимся на человека '
            u'(ученика/преподавателя/пользователя) — заливка вынесет его '
            u'данные на прод в обход решения владельца о банке-и-только-'
            u'банке:\n  ' + '\n  '.join(offenders))


# ---------------------------------------------------------------------------
# Усиление 07.09.2026: списка моделей мало
# ---------------------------------------------------------------------------
#
# Проверка «каждый FK ведёт в выгруженную модель» ловит только ГРОМКУЮ беду —
# падение заливки на внешнем ключе. Но есть беда ТИХАЯ: связь может пропасть
# из дампа без единой ошибки. Сериализатор Django пишет M2M внутрь объекта,
# только если through-таблица создана автоматически
# (django/core/serializers/python.py: `if field.remote_field.through._meta.auto_created`).
# У M2M со СВОЕЙ through-моделью (`Problem.features_rel` через
# `ProblemFeature` с полем `source`) связи не попадут никуда, если саму
# through-модель не выгрузить отдельно. На чистой базе это выглядит не как
# ошибка, а как пустой фильтр в каталоге.
#
# Ровно так 44 992 связи задача↔особенность и жили вне дампа с момента
# слияния обогащения v2, пока это не нашли на репетиции заливки.


def _m2m_through_holes(dumped):
    u"""Возвращает M2M-поля выгруженных моделей, чья through-модель в дамп
    не попала (значит, связи потеряются молча)."""
    problem_model = apps.get_model('problems', 'Problem')
    stripped = {problem_model: set(dfd.BANK_ONLY_PROBLEM_STRIP)}
    holes = []
    for model in sorted(dumped, key=lambda m: m.__name__):
        skip = stripped.get(model, set())
        for field in model._meta.get_fields():
            if not getattr(field, 'concrete', False):
                continue
            if not getattr(field, 'many_to_many', False):
                continue
            if field.name in skip:
                continue
            through = field.remote_field.through
            if through._meta.auto_created:
                continue          # связи уедут внутри самого объекта
            if through in dumped:
                continue          # through выгружается отдельной моделью
            holes.append('%s.%s (through %s)'
                         % (model.__name__, field.name, through.__name__))
    return holes


def _misc_order_problems(labels):
    u"""Список `labels` пишется в ОДИН файл и грузится подряд, поэтому
    ссылающаяся модель не может стоять раньше той, на кого она ссылается.
    Проверка общая — не список пар руками, а обход настоящих FK."""
    order = {}
    models = []
    for i, label in enumerate(labels):
        try:
            model = apps.get_model(*label.split('.'))
        except LookupError:
            continue
        order[model] = i
        models.append(model)
    wrong = []
    for model in models:
        for field in model._meta.get_fields():
            if not getattr(field, 'concrete', False):
                continue
            if not (getattr(field, 'many_to_one', False)
                    or getattr(field, 'one_to_one', False)):
                continue
            target = field.related_model
            if target is None or target is model:
                continue
            if target not in order:
                continue          # грузится более ранним файлом — не наше дело
            if order[target] > order[model]:
                wrong.append('%s обязан идти РАНЬШЕ %s (ссылка .%s)'
                             % (target.__name__, model.__name__, field.name))
    return wrong


class M2MThroughIsDumpedTests(SimpleTestCase):

    def test_full_dump_keeps_links_of_m2m_with_own_through_model(self):
        holes = _m2m_through_holes(dumped_models())
        self.assertEqual(
            holes, [],
            u'У M2M со своей through-моделью связи в дамп не попадут: '
            u'сериализатор их не пишет, а сама through-модель не выгружается. '
            u'Ошибки не будет — связи просто исчезнут:\n  '
            + '\n  '.join(holes))

    def test_bank_only_keeps_links_of_m2m_with_own_through_model(self):
        holes = _m2m_through_holes(bank_only_dumped_models())
        self.assertEqual(
            holes, [],
            u'То же для --bank-only:\n  ' + '\n  '.join(holes))


class MiscFileOrderTests(SimpleTestCase):
    u"""Общая проверка порядка внутри одного файла 40_misc.json —
    в дополнение к списку пар, записанному вручную выше."""

    def test_misc_lists_are_ordered_by_dependency(self):
        wrong = (_misc_order_problems(dfd.TIER4_MISC)
                 + _misc_order_problems(dfd.BANK_ONLY_MISC))
        self.assertEqual(wrong, [], '\n  '.join(wrong))
