# -*- coding: utf-8 -*-
r"""Перенос `title_candidate` в боевой `title` — обратимо, по корзинам.

Решение владельца 07.09.2026: «замени на хорошие заголовки везде, никаких
обрубков первых строк просто». Правило отбора — одно, и живёт оно в
`problems/title_replacement.py`; здесь только запись, снимок и откат.

⚠️ ЭТО ПОЛЕ ВИДИТ УЧЕНИК. Поэтому:

* без `--apply` команда ничего не пишет — только считает и рисует отчёт;
* перед записью кладётся снимок «было» (JSON `id` → старый `title`), и
  `--revert` возвращает заголовки ПОБАЙТОВО из этого снимка;
* пишется РОВНО одно поле. `title_candidate`, `statement`, `answer`,
  `solution` не трогаются — это сверяется отпечатком защищённых полей до и
  после, и расхождение откатывает транзакцию.

    manage.py apply_title_candidates                       # счёт, ничего не пишет
    manage.py apply_title_candidates --report              # + HTML на приёмку
    manage.py apply_title_candidates --apply               # запись + снимок
    manage.py apply_title_candidates --revert --apply      # вернуть как было
"""
import html
import io
import json
import os
import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.functions import Length

from problems import title_replacement as tr
from problems.embedding_provenance import PROTECTED_FIELDS, protected_fingerprint
from problems.models import Problem

OUT_DIR = os.path.join('reports', 'formula_v2')
SNAPSHOT = os.path.join(OUT_DIR, 'title_apply_backup.json')
REPORT = os.path.join(OUT_DIR, 'titles_review.html')

#: Поля, которых хватает для решения о корзине. Тянуть объекты целиком не
#: надо: 41 307 задач с условиями — это сотни мегабайт в память.
FIELDS = ('id', 'title', 'title_candidate', 'title_source', 'statement',
          'status', 'content_status')

CHUNK = 500

#: Сколько примеров каждой корзины показывает отчёт.
SAMPLE = 25
SAMPLE_KEEP = 20
#: Зерно выборки примеров: отчёт обязан быть воспроизводимым, иначе владелец
#: и Claude Code смотрят на разные задачи и спорят о разном.
SAMPLE_SEED = 20260907


class Row:
    """Задача как набор полей — чтобы `title_replacement` не знал про ORM."""

    __slots__ = FIELDS

    def __init__(self, values):
        for имя, значение in zip(FIELDS, values):
            setattr(self, имя, значение)


def rows():
    qs = Problem.objects.order_by('id').values_list(*FIELDS)
    for значения in qs.iterator(chunk_size=2000):
        yield Row(значения)


def classify():
    """Корзина -> список строк. Один проход по банку, ~9 секунд."""
    корзины = {имя: [] for имя in tr.BUCKETS}
    for строка in rows():
        корзины[tr.bucket(строка)].append(строка)
    return корзины


class Command(BaseCommand):
    help = ('Переносит title_candidate в боевой title по корзинам A/B/C. '
            'Без --apply ничего не пишет.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='записать в базу (без флага — только счёт)')
        parser.add_argument('--revert', action='store_true',
                            help='вернуть заголовки из снимка')
        parser.add_argument('--snapshot', default=SNAPSHOT,
                            help='путь к снимку «было»')
        parser.add_argument('--report', action='store_true',
                            help='нарисовать HTML с корзинами и примерами')
        parser.add_argument('--report-path', default=REPORT)

    def handle(self, *args, **opts):
        if opts['revert']:
            return self._revert(opts)

        корзины = classify()
        for имя in tr.BUCKETS:
            self.stdout.write('%-22s %6d' % (имя, len(корзины[имя])))
        под_замену = [с for имя in tr.REPLACED for с in корзины[имя]]
        self.stdout.write(self.style.WARNING(
            'под замену (A+B+C): %d' % len(под_замену)))

        if opts['report']:
            путь = self._report(корзины, opts['report_path'])
            self.stdout.write('отчёт: %s' % путь)

        if not opts['apply']:
            self.stdout.write('это прогон без записи; боевая запись — --apply')
            return

        self._apply(под_замену, opts['snapshot'])

    # --- запись ---------------------------------------------------------- #

    def _apply(self, под_замену, путь_снимка):
        if not под_замену:
            self.stdout.write('менять нечего')
            return
        снимок = {str(с.id): с.title for с in под_замену}
        os.makedirs(os.path.dirname(путь_снимка) or '.', exist_ok=True)
        with io.open(путь_снимка, 'w', encoding='utf-8') as fh:
            json.dump(снимок, fh, ensure_ascii=False)
        self.stdout.write('снимок «было»: %s (%d задач)'
                          % (путь_снимка, len(снимок)))

        до = protected_fingerprint(Problem.objects.all(), PROTECTED_FIELDS)
        with transaction.atomic():
            записано = self._write(
                {с.id: tr.candidate_of(с) for с in под_замену})
            после = protected_fingerprint(Problem.objects.all(), PROTECTED_FIELDS)
            if после != до:
                raise CommandError(
                    'отпечаток защищённых полей изменился (%s -> %s) — '
                    'команда тронула то, чего не должна; транзакция откачена'
                    % (до, после))
            плохие = self._field_name_titles()
            if плохие:
                raise CommandError(
                    'после замены %d задач получили заголовком имя поля '
                    '(например %s) — транзакция откачена'
                    % (len(плохие), плохие[:5]))
            if записано != len(под_замену):
                raise CommandError(
                    'записано %d задач, а корзины насчитали %d — '
                    'транзакция откачена' % (записано, len(под_замену)))
            длинные = (Problem.objects.filter(id__in=[с.id for с in под_замену])
                       .annotate(длина=Length('title'))
                       .filter(длина__gt=tr.TITLE_LIMIT).count())
            if длинные:
                raise CommandError(
                    'среди изменённых %d заголовков длиннее %d символов — '
                    'транзакция откачена' % (длинные, tr.TITLE_LIMIT))
        self.stdout.write(self.style.SUCCESS('записано задач: %d' % записано))

    @staticmethod
    def _write(новые):
        """Порциями, но в одной транзакции: `bulk_update` на 29 тысяч строк
        одним запросом SQLite не переваривает (999 переменных на запрос)."""
        записано = 0
        идентификаторы = sorted(новые)
        for начало in range(0, len(идентификаторы), CHUNK):
            кусок = идентификаторы[начало:начало + CHUNK]
            задачи = list(Problem.objects.filter(id__in=кусок).only('id', 'title'))
            for p in задачи:
                p.title = новые[p.id]
            Problem.objects.bulk_update(задачи, ['title'])
            записано += len(задачи)
        return записано

    @staticmethod
    def _field_name_titles():
        """Задачи, чей заголовок равен имени поля модели, — брак вида 882."""
        return list(Problem.objects.filter(
            title__in=sorted(tr.FIELD_NAME_MARKERS)).values_list('id', flat=True))

    def _revert(self, opts):
        путь = opts['snapshot']
        if not os.path.exists(путь):
            raise CommandError('снимка нет: %s' % путь)
        with io.open(путь, encoding='utf-8') as fh:
            снимок = json.load(fh)
        self.stdout.write('в снимке задач: %d' % len(снимок))
        if not opts['apply']:
            self.stdout.write('это прогон без записи; откат — --revert --apply')
            return
        with transaction.atomic():
            вернули = self._write({int(k): v for k, v in снимок.items()})
        self.stdout.write(self.style.SUCCESS('возвращено задач: %d' % вернули))

    # --- отчёт ----------------------------------------------------------- #

    def _report(self, корзины, путь):
        rnd = random.Random(SAMPLE_SEED)
        куски = [_HEAD, '<h1>Замена боевых заголовков — на приёмку</h1>',
                 '<p class=note>Решение владельца 07.09.2026. Корзины A, B и C '
                 'заменяются; «C-оставляем» и обе D — нет. '
                 'Ничего ещё не записано.</p>',
                 self._table(корзины),
                 '<h2>Из чего сложена корзина C</h2>',
                 '<p class=note>Критерий сработал по двум условиям сразу, и '
                 'важно, какое именно решило дело: «длиннее 40 символов» и '
                 '«нет термина словаря». Заменяются три клетки из четырёх; '
                 'четвёртая — «C-оставляем».</p>',
                 self._c_split(корзины)]
        порядок = [('A', SAMPLE), ('B', SAMPLE), ('C', SAMPLE),
                   ('C-оставляем', SAMPLE_KEEP),
                   ('D-совпадает', 5), ('D-кандидат негоден', 5)]
        for имя, сколько in порядок:
            строки = корзины[имя]
            образцы = rnd.sample(строки, min(сколько, len(строки)))
            образцы.sort(key=lambda с: с.id)
            куски.append('<h2>%s — %d задач, показано %d</h2>'
                         % (html.escape(имя), len(строки), len(образцы)))
            куски.append(_ОПИСАНИЯ.get(имя, ''))
            куски.append(self._samples(образцы, заменяем=имя in tr.REPLACED))
        куски.append('</body></html>')
        os.makedirs(os.path.dirname(путь) or '.', exist_ok=True)
        with io.open(путь, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(куски))
        return путь

    @staticmethod
    def _table(корзины):
        строки = ['<table class=counts><tr><th>Корзина<th>Задач<th>Что будет']
        for имя in tr.BUCKETS:
            строки.append('<tr><td>%s<td class=num>%d<td>%s'
                          % (html.escape(имя), len(корзины[имя]),
                             'заменяем' if имя in tr.REPLACED else 'не трогаем'))
        строки.append('<tr class=total><td>под замену (A+B+C)<td class=num>%d<td>'
                      % sum(len(корзины[и]) for и in tr.REPLACED))
        строки.append('</table>')
        return '\n'.join(строки)

    @staticmethod
    def _c_split(корзины):
        клетки = {}
        for имя in ('C', 'C-оставляем'):
            for с in корзины[имя]:
                ключ = (len(tr.normalized(с.title)) > tr.TITLE_LIMIT,
                        tr.has_econ_term(с.title))
                клетки[ключ] = клетки.get(ключ, 0) + 1
        строки = ['<table class=counts><tr><th>Длина заголовка<th>Термин '
                  'словаря<th>Задач<th>Что будет']
        for длинный in (True, False):
            for термин in (True, False):
                n = клетки.get((длинный, термин), 0)
                строки.append(
                    '<tr><td>%s<td>%s<td class=num>%d<td>%s'
                    % ('длиннее 40' if длинный else '40 и короче',
                       'есть' if термин else 'нет', n,
                       'оставляем' if (термин and not длинный) else 'заменяем'))
        строки.append('</table>')
        return '\n'.join(строки)

    @staticmethod
    def _samples(образцы, заменяем):
        куски = ['<table class=samples><tr><th>id<th>боевой заголовок'
                 '<th>кандидат<th>первые 120 символов условия']
        for с in образцы:
            куски.append(
                '<tr><td class=id>%s<td class="%s">%s<td class=new>%s'
                '<td class=stmt>%s'
                % (с.id, 'old' if заменяем else 'keep',
                   html.escape(с.title or ''),
                   html.escape(tr.candidate_of(с)),
                   html.escape((с.statement or '')[:120])))
        куски.append('</table>')
        return '\n'.join(куски)


_ОПИСАНИЯ = {
    'A': '<p class=note>Обрубок первой строки условия '
         '(<code>title_source=model-firstline</code>). Заменяем безусловно — '
         'ровно ради них решение и принято.</p>',
    'B': '<p class=note>Эхо условия: боевой заголовок — префикс условия или '
         'его первое предложение. Заменяем безусловно.</p>',
    'C': '<p class=note>Спорные <code>kept</code>, которые критерий отправил '
         'на замену: заголовок длиннее 40 символов ИЛИ в нём нет ни одного '
         'термина словаря экономики.</p>',
    'C-оставляем': '<p class=note><b>Самая опасная половина.</b> Критерий '
                   'решил ОСТАВИТЬ: заголовок короткий И термин в нём есть. '
                   'Если критерий ошибается, он ошибается именно здесь.</p>',
    'D-совпадает': '<p class=note>Боевой заголовок уже равен кандидату — '
                   'категории A и B решения 06.09, переписанные мержем.</p>',
    'D-кандидат негоден': '<p class=note>Кандидат пуст, длиннее 40 символов, '
                          'с цифрой, <code>$</code> или обратным слэшем, либо '
                          'баговое литеральное <code>title_candidate</code> '
                          '(882 задачи).</p>',
}

_HEAD = """<!doctype html><html lang=ru><meta charset=utf-8>
<title>Замена заголовков — приёмка</title><style>
body{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:24px;
     color:#1a1a1a;background:#fbfbfa;max-width:1200px}
h1{font-size:24px} h2{font-size:19px;margin-top:34px;border-top:1px solid #ddd;
   padding-top:14px}
.note{color:#555;max-width:70ch}
table{border-collapse:collapse;width:100%;margin:10px 0}
th,td{border:1px solid #ddd;padding:6px 8px;vertical-align:top;text-align:left}
th{background:#f0efec;font-weight:600}
.counts{width:auto} .num{text-align:right;font-variant-numeric:tabular-nums}
.total td{font-weight:600}
.id{color:#888;font-variant-numeric:tabular-nums;width:64px}
.old{color:#a11;text-decoration:line-through} .keep{color:#161}
.new{color:#0a5;font-weight:600} .stmt{color:#666;font-size:13px;width:34%}
code{background:#eee;padding:1px 4px;border-radius:3px}
</style><body>"""
