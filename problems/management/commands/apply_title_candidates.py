# -*- coding: utf-8 -*-
r"""Перенос `title_candidate` в боевой `title` — обратимо, по корзинам.

Решение владельца 07.09.2026 «Критерий замены заголовков финальный», уточнённое
им же на стоп-гейте 08.09: три правила — метка происхождения, обрубок длиннее
40 символов, технический номер. Авторские клички и осмысленные заголовки любой
длины остаются. Правило отбора живёт в `problems/title_replacement.py`; здесь
только запись, снимок и откат.

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
#: Правило 1 — самая спорная часть критерия: там вперемешку осколки условия и
#: авторские клички. Примеров показываем столько же, сколько остальным.
SAMPLE_FIRSTLINE = 25
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
    help = ('Переносит title_candidate в боевой title по трём правилам: '
            'метка происхождения, обрубок, номер. Без --apply ничего не пишет.')

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
            'под замену (%s): %d' % (' + '.join(tr.REPLACED), len(под_замену))))

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
                 '<p class=note>Третья редакция критерия, решение владельца '
                 '07.09.2026. Заменяются две корзины — «обрубки» и '
                 '«технические номера»; всё остальное остаётся как есть. '
                 'Ничего ещё не записано.</p>',
                 self._table(корзины),
                 '<h2>Из чего сложено правило 2 («обрубки»)</h2>',
                 '<p class=note>Правило 2 — это «обрыв на чёрточке '
                 'безусловно ЛИБО дословное начало условия при длине больше '
                 '40 символов». Таблица показывает, сколько задач '
                 'поймано каждым сочетанием: если правило ловит мало и только '
                 'вместе с другим — оно лишнее.</p>',
                 self._truncation_split(корзины),
                 '<h2>Регулярка технических номеров — что она НЕ хватает</h2>',
                 '<p class=note>Слева — заголовки, начинающиеся с тех же слов '
                 '(«Тест», «Задача», «Задание», «Вопрос», «Упражнение», '
                 '«Пример», «№», <code>task</code>, <code>problem</code>), но '
                 'БЕЗ цифры следом. Они остаются. Если среди них есть '
                 'технический номер — регулярка узка; если есть осмысленное '
                 'название, попавшее в замену, — широка.</p>',
                 self._number_control(корзины, rnd)]
        порядок = [('обрубки', SAMPLE), ('технические номера', SAMPLE),
                   ('первая строка', SAMPLE_FIRSTLINE), ('не трогаем', SAMPLE),
                   ('уже равен кандидату', 5), ('кандидат негоден', 5)]
        for имя, сколько in порядок:
            строки = корзины[имя]
            # «Не трогаем» показываем не случайно, а самой опасной половиной:
            # длинными заголовками, которые критерий решил сохранить. Если он
            # ошибается, ошибается он там.
            выбор = ([с for с in строки if len((с.title or '').strip())
                      > tr.TITLE_LIMIT] if имя == 'не трогаем' else строки)
            образцы = rnd.sample(выбор, min(сколько, len(выбор)))
            образцы.sort(key=lambda с: с.id)
            заголовок = '%s — %d задач, показано %d' % (
                html.escape(имя), len(строки), len(образцы))
            if имя == 'не трогаем':
                заголовок += (' из %d длиннее %d символов'
                              % (len(выбор), tr.TITLE_LIMIT))
            куски.append('<h2>%s</h2>' % заголовок)
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
        строки.append('<tr class=total><td>под замену (%s)<td class=num>%d<td>'
                      % (' + '.join(tr.REPLACED),
                         sum(len(корзины[и]) for и in tr.REPLACED)))
        строки.append('</table>')
        return '\n'.join(строки)

    @staticmethod
    def _truncation_split(корзины):
        """Какое сочетание правил поймало каждый обрубок (правило 2)."""
        клетки = {}
        for с in корзины['обрубки']:
            ключ = (tr.starts_statement(с.title, с.statement),
                    tr.ends_with_dash(с.title))
            клетки[ключ] = клетки.get(ключ, 0) + 1
        строки = ['<table class=counts><tr><th>Заголовок начинает условие'
                  '<th>Обрыв на чёрточке<th>Задач']
        for ключ in sorted(клетки, key=lambda k: -клетки[k]):
            строки.append('<tr>%s<td class=num>%d'
                          % (''.join('<td>%s' % ('да' if f else '—')
                                     for f in ключ), клетки[ключ]))
        строки.append('</table>')
        return '\n'.join(строки)

    @staticmethod
    def _number_control(корзины, rnd):
        """Контроль регулярки: слова из списка БЕЗ цифры следом — остаются."""
        слова = ('тест', 'задача', 'задание', 'вопрос', 'упражнение',
                 'пример', 'task', 'problem', '№')
        мимо = [с for имя in ('не трогаем', 'обрубки') for с in корзины[имя]
                if (с.title or '').strip().lower().startswith(слова)
                and not tr.is_technical_number(с.title)]
        поймано = корзины['технические номера']
        образцы_мимо = sorted(rnd.sample(мимо, min(10, len(мимо))),
                              key=lambda с: с.id)
        образцы_в = sorted(rnd.sample(поймано, min(10, len(поймано))),
                           key=lambda с: с.id)
        строки = ['<table class=samples><tr><th>Осталось (цифры нет) — %d'
                  '<th>Заменяется (цифра есть) — %d' % (len(мимо), len(поймано))]
        for левый, правый in zip(образцы_мимо + [None] * 10,
                                 образцы_в + [None] * 10):
            if левый is None and правый is None:
                break
            строки.append('<tr><td class=keep>%s<td class=old>%s'
                          % (html.escape(левый.title or '') if левый else '',
                             html.escape(правый.title or '') if правый else ''))
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
    'обрубки': '<p class=note>Заголовок — не название, а кусок условия: он '
               'дословно начинает условие, обрывается чёрточкой переноса, или '
               'совпадает с условием хотя бы первыми сорока символами. '
               'Проверено по самому условию задачи, а не по длине.</p>',
    'технические номера': '<p class=note>Заголовок начинается со слова «Тест», '
                          '«Задача», «Задание», «Вопрос», «Упражнение», '
                          '«Пример», «№», <code>task</code>, '
                          '<code>problem</code> и цифры. Это не авторское '
                          'название, а его отсутствие.</p>',
    'первая строка': '<p class=note><b>Правило 1, самая новая часть '
                     'критерия.</b> Эти задачи не поймали ни правило 2 '
                     '(обрубок длиннее 40 символов), ни правило 3 (номер) — '
                     'их берёт только метка происхождения '
                     '<code>title_source=model-firstline</code>: заголовок '
                     'вытащен прогоном из первой строки условия, а не '
                     'придуман автором.</p>',
    'не трогаем': '<p class=note><b>Самая опасная половина.</b> Показаны '
                  'только ДЛИННЫЕ заголовки, которые критерий решил сохранить: '
                  'если он ошибается, ошибается он именно здесь. Длина сама по '
                  'себе не порок — это прямое решение владельца 07.09.</p>',
    'уже равен кандидату': '<p class=note>Боевой заголовок уже равен '
                           'кандидату — категории A и B решения 06.09, '
                           'переписанные мержем. Заменять нечего.</p>',
    'кандидат негоден': '<p class=note>Кандидат пуст, длиннее 40 символов, '
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
