# -*- coding: utf-8 -*-
r"""Разобрать карточки-заглушки: что из короткого текста вообще не задача.

Зачем. Шлюз качества ищет СЛОМАННУЮ РАЗМЕТКУ и на осмысленность текста
не смотрит вовсе. Поэтому «Привет я задача» и «0.5 за два пункта
(4 задача)» проходят его чистыми: разметка у них в порядке, просто это
не задачи. Пока такие карточки держит `hidden_pending_review`, беды нет;
как только шлюз ручного ревью снимут — они поедут в каталог вместе с
хорошими.

⚠️ **Признак «условие короче 60 символов» сам по себе НЕ работает.**
Замер: из 802 карточек, которые он находит, у 672 полный текст (условие
плюс подпункты) длиннее 100 символов — это нормальные задачи с коротким
ЗАГОЛОВКОМ в поле условия. Одна из них — на 6 043 символа. Поэтому длина
считается по полному тексту, и одной длины всё равно мало.

⚠️ **Короткое ≠ мусор.** Больше половины коротких — настоящие задачи
«верно или неверно»: «Алюминий добывают в шахтах.», «Рецессия не может
сопровождаться инфляцией.». Слова «верно» в них нет, вопросительного
знака нет, математики нет — по признакам они неотличимы от обрывка.
Различает их ЗАКОНЧЕННОСТЬ: задача — целое предложение и кончается
точкой, обрывок («Никак не решусь, куда же сделать первый шаг», «Ваш
балл на регионе в прошлом году учебном году:») — нет.

Мусором признаётся ТОЛЬКО то, что попало в именованное семейство (ниже)
И от чего после вычёркивания пометы ничего не осталось. Всё остальное
короткое и незаконченное — сомнительное, решение за человеком.

Три группы на выходе:

* `junk` — попало в семейство, и остатка нет;
* `real` — длинный текст, признак задачи или законченное предложение;
* `borderline` — короткое и незаконченное. НЕ ТРОГАЕМ.

Замер на 19 617 карточках за шлюзом ручного ревью по семи источникам:
31 мусор, 19 462 настоящих, 124 сомнительных. Весь мусор — в трёх
ЛЕГАСИ-источниках; среди 9 418 задач трёх новых источников мусора нет
ни одного.

Что делает `--apply`: ставит мусору `status='hidden'`. Это механизм
«убрано руками» из корневого CLAUDE.md — редакторское решение, а не
оценка качества. Взят он, а не `needs_quality_review`, потому что
`quality_gate --apply` пересчитывает свои флаги с нуля при каждом прогоне
и снял бы их; и не `hidden_pending_review`, потому что тот означает
«человек ещё не смотрел», а здесь человек как раз посмотрел.

Ничего не удаляется физически. Журнал отката пишется всегда.
"""
import json
import os
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.models import Problem, Source, SourceReference

OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'publish_readiness')
BACKUP_NAME = 'stub_cleanup_backup.json'
#: Полный текст короче этого — карточка вообще рассматривается. Выше —
#: содержания заведомо достаточно, чтобы это была задача.
SHORT_LIMIT = 150

#: Что остаётся от карточки, когда из неё вычеркнули все пометы. Если
#: меньше этого — карточка ИЗ ПОМЕТ И СОСТОИТ.
RESIDUAL_LIMIT = 25

#: Именованные семейства мусора. Каждое собрано по ЖИВЫМ карточкам и
#: названо словами: «что это такое», а не «подозрительный текст».
#:
#: ⚠️ Совпадения ОДНОГО ИЗ НИХ НЕДОСТАТОЧНО, и это главный урок первого
#: захода. Пометы живут и на настоящих задачах: «Ещё задача» стоит
#: заголовком у живой задачи про тётю Олю на 974 символа (#35374), а
#: «Имя и фамилия» — шапкой над настоящим листочком (#4425). Первый
#: набор правил на «совпало где угодно в тексте» дал 123 карточки, из
#: которых больше половины оказались живыми задачами.
#:
#: Поэтому решает ОСТАТОК: помету вычёркиваем и смотрим, что осталось.
#: Осталась задача — значит помета была подписью к задаче. Не осталось
#: ничего — карточка из пометы и состояла.
JUNK_FAMILIES = (
    ('строительные леса LaTeX',
     re.compile(r'\\end\s*\{?\s*document|\\solution|\{ответ или решение\}', re.I)),

    ('заметка о баллах для проверяющего',
     re.compile(r'(?:^|\s)\d[.,]\d\s+за\s|^\s*балл\w*\s+за\s|'
                r'за\s+(?:не\s+)?полн\w*\s+решени|за\s+пол\s+задачи|'
                r'за\s+(?:первый|первые|два|три|пять)\s+пункт', re.I)),

    ('ссылка на другой файл вместо условия',
     re.compile(r'задач[аиу]?\s*\d*\s*в\s+файле|в\s+файле\s+под\s+номером|'
                r'отдельный\s+файл|из\s+решалки\s+вп', re.I)),

    ('шапка бланка',
     re.compile(r'имя\s+и\s+фамилия\s*:?|ваш\s+балл\s+на\s+регионе\s*:?|'
                r'выберите\s+единственный\s+верный\s+ответ\s*:?|'
                r'краткий\s+ответ\s*\([^)]*\)|фамилия\s*:|класс\s*:', re.I)),

    ('проба пера автора',
     re.compile(r'привет\s+я\s+задача|ещё\s+задача|еще\s+задача|'
                r'тут\s+название|а\s+я\s+пунтк|(?:^|\s)fff(?:\s|$)|'
                r'начали\s+нумерацию\s+заново', re.I)),

    ('голая подпись варианта ответа',
     re.compile(r'^\s*\(?\s*(?:множественный\s+выбор|один\s+правильный\s+ответ)'
                r'\s*\)?\s*$', re.I)),

    ('заголовок раздела листочка',
     re.compile(r'^\s*задачи\s+(?:на\s+самостоятельное|посложнее)', re.I)),

    ('реплика автора, не адресованная ученику',
     re.compile(r'посылайте\s+ко\s+мне|как\s+хотите\s+так\s+и\s+принимайте|'
                r'не\s+пишет\s+решалки|очень\s+кайфовое|перечитать\s+требования|'
                r'я\s+извиняюсь', re.I)),
)

#: Признаки того, что перед нами всё-таки задача. Любой — и карточка
#: уходит в `real`, даже если короткая. Семейства мусора СИЛЬНЕЕ: если
#: карточка попала в семейство и от неё ничего не осталось, подсказки её
#: не спасают.
REAL_HINTS = (
    re.compile(r'\$'),                                   # математика
    re.compile(r'\bверно\b|\bневерно\b|\bда\b\s*[;,.]?\s*\bнет\b|'
               r'1\)\s*да|\bвыберите\b|\bнайдите\b|\bпостройте\b|'
               r'\bвычислите\b|\bдокажите\b|\bизобразите\b|\bнапишите\b|'
               r'\bрешите\b|\bнарисуйте\b|\bотметьте\b|\bприведите\b', re.I),
    re.compile(r'\?'),                                   # вопрос
    #: Блок вариантов ответа: «Варианты ответа», «1. … 2. …», «А) … Б) …».
    re.compile(r'варианты\s+ответа|(?:^|\n)\s*[1-9]\s*[.)]\s+\S|'
               r'[АБВГAB]\s*\)\s*\S', re.I),
)

#: ⚠️ Утверждение, законченное как предложение, — это ТОЖЕ формулировка
#: задачи, а не обрывок. У SolveHub целое семейство задач устроено так:
#: «Алюминий добывают в шахтах.», «Рецессия не может сопровождаться
#: инфляцией.» — ученик отвечает «верно/неверно», и слова «верно» в
#: тексте нет. Без этого правила 469 живых задач трёх новых источников
#: остались бы «сомнительными» из-за формата, а не из-за сомнений.
#:
#: Отличие от обрывка — именно ЗАКОНЧЕННОСТЬ: «Никак не решусь, куда же
#: сделать первый шаг» (заголовок) и «Ваш балл на регионе в прошлом году
#: учебном году:» (поле бланка) точкой не кончаются и сюда не попадают.
_SENTENCE_RE = re.compile(r'[.?]\s*$')
#: Слово — это слово, включая предлоги: «Алюминий добывают в шахтах.»
#: это ЧЕТЫРЕ слова, а не три, и это законченная задача «верно/неверно».
_WORD_RE = re.compile(r'[А-Яа-яЁёA-Za-z]+')
MIN_SENTENCE_WORDS = 4


class Command(BaseCommand):
    help = ('Разобрать карточки-заглушки на мусор / настоящие / сомнительные. '
            'Без --apply — сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--sources', required=True,
                            help='id источников через запятую')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--revert', action='store_true')
        parser.add_argument('--report-dir', default=OUT_DIR)

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        report_dir = options['report_dir']
        backup_path = os.path.join(report_dir, BACKUP_NAME)
        if options['revert']:
            return self._revert(backup_path)

        scope = self._scope(options['sources'])
        groups = self.classify(scope)

        for name in ('junk', 'real', 'borderline'):
            self.stdout.write('  %-12s %5d' % (name, len(groups[name])))
        by_family = {}
        for rec in groups['junk']:
            by_family.setdefault(rec['family'], []).append(rec['id'])
        self.stdout.write('\n  мусор по семействам:')
        for family, ids in sorted(by_family.items(), key=lambda kv: -len(kv[1])):
            self.stdout.write('    %-42s %4d' % (family, len(ids)))

        os.makedirs(report_dir, exist_ok=True)
        with open(os.path.join(report_dir, 'stub_classification.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(groups, fh, ensure_ascii=False, indent=1)

        if not options['apply']:
            self.stdout.write('\nСУХОЙ ПРОГОН — в базе ничего не изменено.')
            return

        ids = [r['id'] for r in groups['junk']]
        rows = list(Problem.objects.filter(id__in=ids)
                    .values_list('id', 'status'))
        with open(backup_path, 'w', encoding='utf-8') as fh:
            json.dump({'note': 'id → статус ДО браковки мусора',
                       'count': len(rows), 'rows': [list(r) for r in rows]},
                      fh, ensure_ascii=False)

        total_before = Problem.objects.count()
        with transaction.atomic():
            changed = Problem.objects.filter(id__in=ids).update(
                status=Problem.Status.HIDDEN)
        if Problem.objects.count() != total_before:
            raise CommandError('ИНВАРИАНТ НАРУШЕН: число задач изменилось')
        self.stdout.write(self.style.SUCCESS(
            '\nЗАПИСАНО: status=hidden у %d задач. Журнал отката: %s'
            % (changed, backup_path)))

    # ------------------------------------------------------------------
    def classify(self, scope_ids):
        """Три группы по полному тексту задачи (условие + подпункты)."""
        parts = {}
        for pid, text in ProblemPartRows(scope_ids):
            parts.setdefault(pid, []).append(text or '')

        groups = {'junk': [], 'real': [], 'borderline': []}
        for problem in (Problem.objects.filter(id__in=scope_ids)
                        .order_by('id').only('id', 'statement')):
            task = ' '.join([problem.statement or '']
                            + parts.get(problem.id, [])).strip()
            rec = {'id': problem.id, 'len': len(task), 'text': task[:400]}
            group, family, residual = self.group_for(task)
            if group == 'junk':
                rec = dict(rec, family=family, residual=residual)
            groups[group].append(rec)
        return groups

    @classmethod
    def group_for(cls, task):
        """`('junk'|'real'|'borderline', семейство, остаток)` по тексту.

        Единственное место, где принимается решение о группе: и команда,
        и тесты зовут ЕГО, а не повторяют условие у себя. Дубликат этой
        логики в тестах уже один раз обесценил проверку — она осталась
        зелёной, когда правило в команде сломали."""
        families, residual = cls._strip_families(task)
        if families and len(residual) < RESIDUAL_LIMIT:
            return 'junk', families[0], residual
        if len(task) >= SHORT_LIMIT or cls._looks_real(task):
            return 'real', None, residual
        return 'borderline', None, residual

    @staticmethod
    def _strip_families(task):
        r"""`([имена сработавших семейств], что осталось)`.

        Остаток чистится от пунктуации, маркеров списка и обломков
        нумерации (`[1]`, `(3 задача)`): сами по себе они содержанием не
        являются, и оставлять их — значит считать «(3 задача)» задачей."""
        families, text = [], task
        for name, pattern in JUNK_FAMILIES:
            if pattern.search(text):
                families.append(name)
                text = pattern.sub(' ', text)
        text = re.sub(r'\[\s*\d+\s*\]|\(\s*\d+\s*задача\s*\)', ' ', text)
        text = re.sub(r'[\s•·\-—–.,:;!?()\[\]{}«»"\'|]+', ' ', text)
        return families, text.strip()

    @classmethod
    def _looks_real(cls, task):
        if any(p.search(task) for p in REAL_HINTS):
            return True
        return cls._is_complete_sentence(task)

    @staticmethod
    def _is_complete_sentence(task):
        """Законченное предложение из четырёх и более слов — формулировка."""
        return bool(_SENTENCE_RE.search(task.strip())
                    and len(_WORD_RE.findall(task)) >= MIN_SENTENCE_WORDS)

    @staticmethod
    def _scope(raw):
        try:
            ids = [int(p) for p in (raw or '').split(',') if p.strip()]
        except ValueError:
            raise CommandError('--sources: ожидаются id через запятую')
        known = set(Source.objects.filter(id__in=ids).values_list('id', flat=True))
        missing = sorted(set(ids) - known)
        if missing:
            raise CommandError('--sources: нет таких источников: %s'
                               % ', '.join(map(str, missing)))
        return set(
            Problem.objects.filter(
                id__in=SourceReference.objects.filter(source_id__in=ids)
                .values_list('problem_id', flat=True),
                status=Problem.Status.PUBLISHED,
                needs_quality_review=False,
                hidden_pending_review=True,
            ).values_list('id', flat=True))

    def _revert(self, backup_path):
        if not os.path.isfile(backup_path):
            raise CommandError('нет журнала отката: %s' % backup_path)
        with open(backup_path, encoding='utf-8') as fh:
            rows = json.load(fh)['rows']
        with transaction.atomic():
            n = sum(Problem.objects.filter(id=pid).update(status=status)
                    for pid, status in rows)
        self.stdout.write(self.style.SUCCESS('ОТКАЧЕНО: %d задач' % n))


def ProblemPartRows(scope_ids):
    """`(problem_id, текст подпункта)` — порциями, чтобы не собрать
    гигантский `IN (...)` на несколько тысяч id."""
    from problems.models import ProblemPart
    ids = list(scope_ids)
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        for row in (ProblemPart.objects.filter(problem_id__in=chunk)
                    .order_by('problem_id', 'order')
                    .values_list('problem_id', 'statement')):
            yield row
