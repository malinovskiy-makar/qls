"""
Команда dump_for_deploy — порционный JSON-дамп данных для деплоя на PostgreSQL.

Зачем порции:
  1) Некоторые хостинги обрывают долгие внешние транзакции — большой
     дамп в одной транзакции не доезжает. Короткие транзакции (по файлу) переживают.
  2) Меньше памяти при разборе каждого файла.

Что исключается из Problem:
  - поле embedding (46 МБ binary, на проде не нужно — модель там не грузится);
  - M2M similar_problems (self-ref, 105 540 строк) — выгружается ОТДЕЛЬНО последним
    шагом, когда все Problem уже загружены (иначе forward-ссылки через границы
    транзакций ломают FK).

Порядок файлов (по зависимостям, грузить в алфавитном порядке имён):
  10_reference   — независимые справочники (User, Topic, Tag, Source, ...)
  20_problem_*   — Problem порциями (без embedding, без similar_problems)
  30_sourceref_* — SourceReference порциями (FK Problem)
  31_part_*      — ProblemPart порциями (FK Problem)
  40_misc        — мелкие связанные модели (Lesson, Assignment, Submission, ...)
  50_dupcand_*   — DuplicateCandidate порциями (FK Problem)
  51_autotopic_* — AutoTopicAssignment порциями (FK Problem, Topic)
  90_similar_*   — through-таблица similar_problems порциями (грузить ПОСЛЕДНЕЙ)

Запуск:
    ./venv/bin/python manage.py dump_for_deploy --outdir deploy_fixtures --chunk 5000
"""

import json
import os

from django.apps import apps
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError

from problems.management.commands.glm_enrich_run import read_ids_file
from problems.models import DupMark, Problem

# Справочники без FK на Problem (грузятся первыми)
TIER1 = [
    'problems.User', 'problems.Topic', 'problems.Subtopic', 'problems.Tag',
    'problems.Source', 'problems.FileAsset', 'problems.Skill',
    'problems.MistakeTag', 'problems.Template',
    'problems.StudentGroup', 'problems.Job', 'problems.TheoryPage',
    # Справочники обогащения v2 (сессия 07.09.2026). Problem ссылается на них
    # M2M-полями `features_rel` и `econ_concepts`; без них заливка падает на
    # внешнем ключе. Сами по себе оба справочника ни на что не ссылаются.
    'problems.Feature', 'problems.EconConcept',
]

# ---------------------------------------------------------------------------
# --bank-only: только банк задач (решение владельца 2026-09-02, 152-ФЗ).
#
# НЕ входят: User и профили, StudentGroup/Lesson/Assignment/AssignmentItem,
# Submission/TeacherFeedback/StudentTopicProgress/StudentSkillProgress,
# CalendarEvent, ProblemComment и вся геймификация — работы и активность
# учеников/преподавателя. Также не входят Job/Template/ExportRecord/
# ImportSession/DuplicateCandidate/AutoTopicAssignment/ReviewVerdict/
# AnswerSecondOpinion/ProblemVersion/TheoryPage/Collection — служебные или
# аудиторские таблицы, которые каталогу и игре не нужны для показа сайта
# (проверено grep'ом: ни одна не читается вне problems/admin.py и команд).
# Также не входит FileAsset: картинки задач сегодня живут в ProblemFigure
# (chertyozhi/tikz, hex-хеш в тексте задачи), а не в FileAsset.files — этой
# M2M ни каталог, ни игра не читают.
BANK_ONLY = [
    'problems.Topic', 'problems.Subtopic', 'problems.Tag',
    'problems.Source', 'problems.Skill', 'problems.MistakeTag',
    # Справочники обогащения v2 — см. комментарий у TIER1.
    'problems.Feature', 'problems.EconConcept',
]

# Поля Problem, которые --bank-only обязан вырезать: обе ссылаются на
# модели, не входящие в дамп (User, FileAsset), и остались бы висячими
# ссылками при заливке в чистую PostgreSQL.
BANK_ONLY_PROBLEM_STRIP = ['embedding', 'similar_problems', 'owner', 'files']

# Мелкие модели, зависящие от Problem/ProblemPart — грузятся одним файлом
# после TIER 2/3, как TIER4_MISC у полного дампа. ProblemFigure — это и есть
# «чертежи/tikz» из задания: сгенерированные картинки, на которые в тексте
# задачи ссылается маркер [[FIGURE:<hash>]] (problems/models.py, ADR 0031).
#
# ⚠️ ПОРЯДОК ЗНАЧИМ: всё это пишется в ОДИН файл 40_misc.json и грузится
# подряд, поэтому ссылающаяся модель не может стоять раньше той, на кого она
# ссылается (Rubric раньше RubricCriterion). Держит тест
# test_misc_lists_are_ordered_by_dependency.
BANK_ONLY_MISC = [
    'problems.Hint', 'problems.ProblemFigure',
    # Связь задача↔особенность. У M2M `Problem.features_rel` СВОЯ through-модель
    # с полем `source`, а такие M2M сериализатор Django внутрь Problem не
    # пишет вовсе (serializers/python.py: only if through._meta.auto_created).
    # Без этой строки 44 992 связи просто исчезли бы из дампа молча — без
    # ошибки внешнего ключа, просто пустой фильтр «есть график» на проде.
    'problems.ProblemFeature',
    # Олимпиадные координаты задачи. Ссылается только на Problem, данных
    # человека не содержит; без неё вся привязка к олимпиадам на прод не едет.
    'problems.OlympiadRef',
    # Рубрики оценивания задачи — содержимое банка, а не работа ученика:
    # ни одного поля, ссылающегося на человека.
    'problems.Rubric', 'problems.RubricCriterion',
]

#: Сколько id кладём в один `__in`. SQLite рвётся на «too many SQL variables»
#: задолго до тысячи (CLAUDE.md команд, раздел ловушек), поэтому выборка по
#: списку идёт кусками, а не одним запросом.
ID_CHUNK = 900

#: Как добраться от модели до `Problem.id`. Явная таблица, а НЕ угадывание по
#: полям: модель, которой здесь нет, при `--ids-file` роняет команду, и это
#: намеренно. Молча выгрузить её целиком значило бы увезти на прод строки,
#: ссылающиеся на задачи, которых там нет, — ровно тот висячий внешний ключ,
#: ради которого весь `--ids-file` и заведён.
PROBLEM_PATH = {
    'problems.Problem': 'pk__in',
    'problems.SourceReference': 'problem_id__in',
    'problems.ProblemPart': 'problem_id__in',
    'problems.Hint': 'problem_id__in',
    'problems.ProblemFigure': 'problem_id__in',
    'problems.ProblemFeature': 'problem_id__in',
    'problems.OlympiadRef': 'problem_id__in',
    'problems.Rubric': 'problem_id__in',
    'problems.RubricCriterion': 'rubric__problem_id__in',
    'problems.DupMark': 'problem_id__in',
    'problems.DupHumanChoice': 'chosen_problem_id__in',
}


def chunked_ids(ids, size=ID_CHUNK):
    """Отсортированный список id кусками по `size` штук."""
    ordered = sorted(ids)
    for start in range(0, len(ordered), size):
        yield ordered[start:start + size]


def whole_groups_inside(ids):
    """Строки `DupMark`, у которых ВСЯ группа внутри переносимого множества.

    Половина группы на проде — это пометка «копия чего-то», чего там нет:
    человек увидел бы пустую отсылку, а будущая команда выбора канонической
    версии посчитала бы группу из одного участника. Поэтому группа едет
    целиком или не едет вовсе — включая группы из трёх и более версий.
    """
    inside = set(ids)
    members = {}
    for group, pid in DupMark.objects.values_list('group', 'problem_id'):
        members.setdefault(group, []).append(pid)
    good = {group for group, pids in members.items()
            if all(pid in inside for pid in pids)}
    return DupMark.objects.filter(group__in=sorted(good)).order_by('pk')


# Мелкие модели, зависящие от Problem/User (грузятся после Problem одним файлом)
TIER4_MISC = [
    'problems.ProblemVersion', 'problems.Hint', 'problems.Rubric',
    'problems.RubricCriterion', 'problems.StudentSkillProgress',
    # См. BANK_ONLY_MISC: through-модель `Problem.features_rel` и олимпиадные
    # координаты. В полном дампе их не было по той же причине — молча.
    'problems.ProblemFeature', 'problems.OlympiadRef',
    'problems.Collection', 'problems.ExportRecord', 'problems.ImportSession',
    'problems.Lesson', 'problems.Assignment',
    # ⚠️ ПОРЯДОК ЗДЕСЬ ЗНАЧИМ, И ЭТИ ТРИ СТРОКИ ПОЯВИЛИСЬ НЕ ЗРЯ.
    # Заливка в ЧИСТУЮ PostgreSQL падала: `Submission.problem_item` ссылается
    # на `AssignmentItem`, а его в выгрузке не было вовсе:
    #   IntegrityError: Key (problem_item_id)=(18) is not present in table
    #   "problems_assignmentitem"
    # На SQLite это не воспроизводится (внешние ключи там не проверяются так
    # строго), а на проде строки уже лежали — поэтому дыра прожила незамеченной
    # до первой репетиции на чистой базе (сессия «Wecon Rush», фаза 8).
    # `AssignmentItem` тянет за собой `CustomProblem` и его варианты, иначе
    # дыра просто переезжает на шаг дальше. Замкнутость графа держит тест
    # problems/tests/test_deploy_dump.py.
    'problems.CustomProblem', 'problems.CustomProblemOption',
    'problems.SavedFolder', 'problems.SavedGraph',
    'problems.AssignmentItem',
    'problems.Submission',
    'problems.TeacherFeedback', 'problems.StudentTopicProgress',
    'problems.CalendarEvent',
]


def _clean_nul(value):
    """Рекурсивно убирает байт NUL (0x00) из строк — PostgreSQL его запрещает,
    а SQLite хранит. Невидимый мусорный символ, удаление безопасно."""
    if isinstance(value, str):
        return value.replace('\x00', '')
    if isinstance(value, list):
        return [_clean_nul(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean_nul(v) for k, v in value.items()}
    return value


# Потолок размера одного файла фикстур. `loaddata` разбирает файл целиком в
# память, и на сервере с 2 ГБ ОЗУ полугигабайтный файл — это отказ выкатки, а
# не «медленно». 48 МБ выбрано с запасом: разбор такого файла Django стоит
# порядка нескольких сотен мегабайт.
MAX_FILE_BYTES = 48 * 1024 * 1024


def split_by_size(objects, limit=MAX_FILE_BYTES):
    """Режет список объектов на группы, укладывающиеся в limit байт.

    Одиночный объект тяжелее лимита не режется — он неделим, и лучше
    большой файл, чем потерянная строка."""
    part = []
    size = 0
    for obj in objects:
        weight = len(json.dumps(obj, ensure_ascii=False).encode('utf-8')) + 1
        if part and size + weight > limit:
            yield part
            part, size = [], 0
        part.append(obj)
        size += weight
    if part:
        yield part


def serialize_qs(qs, strip_fields=None):
    """Сериализует queryset в список dict, удаляя ненужные поля и NUL-байты."""
    data = json.loads(serializers.serialize('json', qs))
    for obj in data:
        if strip_fields:
            for f in strip_fields:
                obj['fields'].pop(f, None)
        obj['fields'] = _clean_nul(obj['fields'])
    return data


class Command(BaseCommand):
    help = 'Порционный дамп данных для деплоя (без embedding, similar отдельно)'

    def add_arguments(self, parser):
        parser.add_argument('--outdir', type=str, default='deploy_fixtures')
        parser.add_argument('--chunk', type=int, default=5000)
        parser.add_argument(
            '--bank-only', action='store_true',
            help='Только банк задач: без пользователей, работ учеников, '
                 'назначений и служебных таблиц — см. BANK_ONLY* в этом файле.',
        )
        parser.add_argument(
            '--ids-file',
            help='Выгрузить ТОЛЬКО эти задачи (id по одному на строку, '
                 '«#» — комментарий) и всё, что на них ссылается. Справочники '
                 'выгружаются целиком: они маленькие и нужны любой задаче.',
        )
        parser.add_argument(
            '--with-dupmark', action='store_true',
            help='Добавить пометки групп копий (DupMark). Едут только группы, '
                 'у которых ВСЕ участники будут на проде, — иначе получился бы '
                 'внешний ключ в пустоту.',
        )
        parser.add_argument(
            '--dupmark-scope-file',
            help='Список задач, которые будут на проде ПОСЛЕ заливки: нынешние '
                 'плюс переносимые. Нужен потому, что группа копий может стоять '
                 'одной ногой в уже залитой задаче, а сама задача во второй раз '
                 'не выгружается. По умолчанию — тот же --ids-file.',
        )

    def write_file(self, outdir, name, objects):
        path = os.path.join(outdir, name)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(objects, f, ensure_ascii=False)
        self.stdout.write(f'  {name}: {len(objects)} объектов')

    def dump_model_chunked(self, outdir, prefix, model_label, chunk, strip=None,
                           problem_ids=None):
        """Дамп одной модели порциями по chunk объектов.

        Порция ограничена и по числу объектов, и по РАЗМЕРУ файла. Одного
        счётчика объектов мало: у `ProblemFigure` в строке лежит и svg, и сама
        картинка, поэтому 2 498 строк давали файл на 504 МБ — ровно то, против
        чего порционность и заведена (см. шапку файла)."""
        model = apps.get_model(*model_label.split('.'))
        qs = model.objects.all().order_by('pk')
        if model_label == 'problems.Problem':
            qs = qs.defer('embedding')

        if problem_ids is not None:
            lookup = PROBLEM_PATH.get(model_label)
            if lookup is None:
                raise CommandError(
                    f'--ids-file: не знаю, как сузить {model_label} до списка '
                    f'задач. Добавьте её в PROBLEM_PATH — выгружать целиком '
                    f'нельзя, на проде получится ссылка в пустоту.')
            self._dump_by_ids(outdir, prefix, qs, lookup, problem_ids, strip)
            return

        total = qs.count()
        if total == 0:
            return
        n = 0
        idx = 0
        while n < total:
            batch = list(qs[n:n + chunk])
            data = serialize_qs(batch, strip_fields=strip)
            for part in split_by_size(data):
                idx += 1
                self.write_file(outdir, f'{prefix}_{idx:04d}.json', part)
            n += len(batch)

    def _dump_by_ids(self, outdir, prefix, qs, lookup, problem_ids, strip):
        """Выгрузка по списку задач: один файл на кусок id.

        Кусок, а не общий `__in`: список на восемь тысяч номеров рвёт SQLite
        («too many SQL variables»). Заодно это и есть порционность — размер
        файла всё равно дополнительно режется `split_by_size`."""
        idx = 0
        for piece in chunked_ids(problem_ids):
            data = serialize_qs(qs.filter(**{lookup: piece}), strip_fields=strip)
            if not data:
                continue
            for part in split_by_size(data):
                idx += 1
                self.write_file(outdir, f'{prefix}_{idx:04d}.json', part)

    def handle(self, *args, **options):
        outdir = options['outdir']
        chunk = options['chunk']
        bank_only = options['bank_only']

        problem_ids = None
        if options['ids_file']:
            problem_ids = sorted(set(read_ids_file(options['ids_file'])))
            known = set()
            for piece in chunked_ids(problem_ids):
                known.update(Problem.objects.filter(pk__in=piece)
                             .values_list('pk', flat=True))
            missing = [pid for pid in problem_ids if pid not in known]
            if missing:
                raise CommandError(
                    '--ids-file: в базе нет %d из %d задач списка, первые: %s. '
                    'Молча пропустить нельзя: выгрузка вышла бы меньше '
                    'заказанной, а отчиталась бы об успехе.'
                    % (len(missing), len(problem_ids), missing[:10]))
        if options['with_dupmark'] and problem_ids is None:
            raise CommandError('--with-dupmark работает только вместе с --ids-file: '
                               'без списка «вся группа внутри выгрузки» нечем проверить')
        dupmark_scope = problem_ids
        if options['dupmark_scope_file']:
            if not options['with_dupmark']:
                raise CommandError('--dupmark-scope-file без --with-dupmark '
                                   'ничего не делает')
            dupmark_scope = sorted(set(read_ids_file(options['dupmark_scope_file'])))
            if not set(problem_ids) <= set(dupmark_scope):
                raise CommandError(
                    '--dupmark-scope-file обязан включать весь --ids-file: '
                    'иначе выгруженная задача осталась бы вне области видимости '
                    'групп и её пометка не уехала бы')

        os.makedirs(outdir, exist_ok=True)

        # Чистим старые файлы
        for fn in os.listdir(outdir):
            if fn.endswith('.json'):
                os.remove(os.path.join(outdir, fn))

        tier1 = BANK_ONLY if bank_only else TIER1
        misc = BANK_ONLY_MISC if bank_only else TIER4_MISC
        problem_strip = list(BANK_ONLY_PROBLEM_STRIP) if bank_only \
            else ['embedding', 'similar_problems']

        label = ' (--bank-only)' if bank_only else ''
        self.stdout.write(f'TIER 1 — справочники{label}:')
        ref_objects = []
        for m_label in tier1:
            try:
                model = apps.get_model(*m_label.split('.'))
            except LookupError:
                continue
            ref_objects.extend(serialize_qs(model.objects.all()))
        self.write_file(outdir, '10_reference.json', ref_objects)

        self.stdout.write(f'TIER 2 — Problem (вырезаны: {", ".join(problem_strip)}):')
        self.dump_model_chunked(
            outdir, '20_problem', 'problems.Problem', chunk,
            strip=problem_strip, problem_ids=problem_ids,
        )

        self.stdout.write('TIER 3 — SourceReference / ProblemPart:')
        self.dump_model_chunked(outdir, '30_sourceref', 'problems.SourceReference',
                                chunk, problem_ids=problem_ids)
        self.dump_model_chunked(outdir, '31_part', 'problems.ProblemPart',
                                chunk, problem_ids=problem_ids)

        # ⚠️ TIER 4 пишется ПОРЦИЯМИ, как и всё остальное, а не одним файлом.
        # Раньше здесь был единственный 40_misc.json, и на боевом банке он
        # вырос до 504 МБ: `ProblemFigure` хранит и svg, и картинку целиком.
        # Такой файл сводит на нет весь смысл порционного дампа, ради которого
        # команда и написана (см. шапку файла): и память при разборе, и длина
        # одной транзакции. Номер модели в имени (`40_misc_01_hint_0001.json`)
        # сохраняет порядок загрузки: файлы грузятся по алфавиту.
        self.stdout.write(f'TIER 4 — мелкие связанные модели порциями{label}:')
        for i, m_label in enumerate(misc, start=1):
            try:
                model = apps.get_model(*m_label.split('.'))
            except LookupError:
                continue
            prefix = '40_misc_%02d_%s' % (i, model._meta.model_name)
            self.dump_model_chunked(outdir, prefix, m_label, chunk,
                                    problem_ids=problem_ids)

        if options['with_dupmark']:
            # ⚠️ 60_, а не 40_: файлы грузятся по алфавиту, а DupMark ссылается
            # на Problem и обязан идти ПОСЛЕ всех 20_problem_*.
            rows = whole_groups_inside(dupmark_scope)
            data = serialize_qs(rows)
            groups = len({obj['fields']['group'] for obj in data})
            self.stdout.write(
                'TIER 6 — DupMark: %d пометок в %d целиком вошедших группах'
                % (len(data), groups))
            for idx, part in enumerate(split_by_size(data), start=1):
                self.write_file(outdir, f'60_dupmark_{idx:04d}.json', part)

        if bank_only:
            # DuplicateCandidate/AutoTopicAssignment/similar_problems —
            # аудиторские/производные данные, не нужны каталогу и игре и
            # пересобираются на месте (cache_similar и т.п.). Обе ссылаются
            # на модели вне --bank-only графа, дампить их здесь нельзя.
            files = sorted(f for f in os.listdir(outdir) if f.endswith('.json'))
            self.stdout.write(self.style.SUCCESS(
                f'\n--bank-only готово: {len(files)} файлов в {outdir}/'
            ))
            return

        self.stdout.write('TIER 4b — DuplicateCandidate / AutoTopicAssignment:')
        self.dump_model_chunked(outdir, '50_dupcand', 'problems.DuplicateCandidate', chunk)
        self.dump_model_chunked(outdir, '51_autotopic', 'problems.AutoTopicAssignment', chunk)

        self.stdout.write('TIER 5 — similar_problems through (грузить ПОСЛЕДНЕЙ):')
        through = Problem.similar_problems.through
        through_label = through._meta.label
        qs = through.objects.all().order_by('pk')
        total = qs.count()
        n = idx = 0
        while n < total:
            batch = list(qs[n:n + chunk])
            data = json.loads(serializers.serialize('json', batch))
            idx += 1
            self.write_file(outdir, f'90_similar_{idx:04d}.json', data)
            n += len(batch)

        files = sorted(f for f in os.listdir(outdir) if f.endswith('.json'))
        self.stdout.write(self.style.SUCCESS(
            f'\nГотово: {len(files)} файлов в {outdir}/'
        ))
        self.stdout.write(f'through-модель: {through_label}')
