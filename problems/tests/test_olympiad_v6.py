"""Эталон ВП + МОШ v6 (сессия 15.10.2026): правила сборки профиля ECON v6.

9. Эссе без номеров — задание «эссе», а не вступление комплекта.
10. Повтор вопроса теста в файле ответов («6» при «тест-6») — ответ к вопросу,
    а не второе задание; настоящая задача только из файла ответов — задание.
11. Файл решений «повтор задачи с названием → её пункты» (ВП 2019–2020): всё
    до следующего повтора — её; пункт с чужим номером — не решение той задачи.
12. Таблица ключей v5 → v6: повтор, новое задание.

Страницы — выдуманные, во временной папке; модель и база не нужны. Проверки
на настоящем v6 — только если папка данных есть на диске.
"""
import csv
import os
import tempfile

from django.test import SimpleTestCase
from rapidfuzz import fuzz

from problems.olympiad_audit import assemble, econ_rules, fixes, transcribe
from problems.olympiad_audit import version_keys as vk

DATA = os.environ.get('OLYMPIAD_DATA', 'C:/Users/shipu/weconomics-data/olympiads')
SETS = {'vp': 'audit_vp_20261008', 'mosh': 'audit_mosh_20261009'}

KNIGHTS = ('В замке короля Артура есть круглый стол, за которым рассаживаются рыцари, '
           'когда съезжаются на званый обед.')
SODA = ('Правительство страны N предложило установить минимальную цену за литр газировки, '
        'и ассоциация крупных производителей поддержала это предложение.')


class Build(SimpleTestCase):
    """Комплект из выдуманных страниц: {page_dir: [страница → блоки]}."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def files(self, pages_by_dir, names):
        out = []
        for page_dir, pages in pages_by_dir.items():
            for n, blocks in enumerate(pages, 1):
                transcribe.Transcriber._write(
                    os.path.join(self.root, page_dir, f'p{n}.json'),
                    {'status': 'ok', 'blocks': blocks, 'layer_ratio': 0.97, 'numbers_ok': True,
                     'retries': 0, 'needs_eyes': False})
            out.append({'file': names[page_dir], 'page_dir': page_dir, 'pages': len(pages)})
        return out

    def build(self, tasks, solutions=None, event_id='mosh-2010-final-10-v1', names=None):
        names = names or {}
        names = {d: names.get(d, f'raw/pdf/{d.split("/")[-1]}.pdf')
                 for d in list(tasks) + list(solutions or {})}
        event = {'event_id': event_id, 'year': 2010, 'stage': 'final', 'grade': '10',
                 'task_files': self.files(tasks, names),
                 'solution_files': self.files(solutions or {}, names)}
        built, report, _ = assemble.build_event(self.root, event, 'figs', crop=False,
                                                profile=assemble.ECON)
        return {(t.number, t.task_variant): t for t in built}, event, report


def task_block(number, text, title='', **kw):
    return {'type': 'task', 'number': number, 'title': title, 'text': text, **kw}


# ── 9. Эссе ──────────────────────────────────────────────────────────────────

class EssayTests(Build):
    def test_9a_essay_file_is_one_task(self):
        """Файл эссе без номеров: заголовок «ЭССЕ…» — задание «эссе», продолжение
        на следующей странице и «Вопросы:» — его, во вступление не попадает."""
        essay = {'pages/esse': [
            [task_block('', '**Проблемная ситуация:**\n\nМоногорода остались от плановой экономики',
                        title='ЭССЕ. ПРОБЛЕМЫ МОНОГОРОДОВ')],
            [{'type': 'task_continuation', 'number': '', 'text': 'градообразующая компания уволила людей'},
             task_block('', '1. Какие пути решения вы могли бы предложить?', title='Вопросы:')]],
            'pages/tasks': [[task_block('1', 'Фирма-монополист выбирает объём выпуска.')]]}
        tasks, event, report = self.build(essay)
        self.assertEqual(list(tasks), [(econ_rules.ESSAY_NUMBER, ''), ('1', '')])
        essay_task = tasks[(econ_rules.ESSAY_NUMBER, '')]
        self.assertEqual(essay_task.title, 'ЭССЕ. ПРОБЛЕМЫ МОНОГОРОДОВ')
        text = assemble.join_pieces(essay_task.statement)
        for part in ('Моногорода остались', 'градообразующая компания', '**Вопросы:**',
                     'Какие пути решения'):
            self.assertIn(part, text)
        self.assertFalse(any('Моногорода' in p for p in event['preamble']))
        self.assertEqual(report['v6: эссе — задание'], 1)

    def test_9b_untitled_intro_still_preamble(self):
        """Безномерный блок без «Эссе» в начале файла — по-прежнему вступление."""
        tasks, event, _ = self.build({'pages/tasks': [[
            task_block('', 'Время выполнения заданий — 90 минут.'),
            task_block('1', 'Фирма-монополист выбирает объём выпуска.')]]})
        self.assertEqual(list(tasks), [('1', '')])
        self.assertIn('Время выполнения заданий — 90 минут.', event['preamble'])


# ── 10. Повтор вопроса теста в файле ответов ─────────────────────────────────

JEANS = 'Рост цены на джинсы может привести к уменьшению спроса на них.\n1) верно\n2) неверно'
SKI = 'Если увеличивается цена на лыжи, спрос на лыжные ботинки возрастёт.\n1) верно\n2) неверно'


class RepeatTests(Build):
    NAMES = {'pages/test': 'raw/pdf/tasks-econ-10-test-final.pdf',
             'pages/ans': 'raw/pdf/ans-econ-10-test-final.pdf'}

    def test_10a_repeat_goes_to_test_question(self):
        """«6» в файле ответов — вопрос «тест-6» с отмеченным ответом: ответ — к
        «тест-6», задания «6» нет; задача 8 только из файла ответов — задание."""
        tasks, _, report = self.build(
            {'pages/test': [[task_block('6', JEANS), task_block('7', SKI)]]},
            {'pages/ans': [[
                task_block('6', JEANS.replace('2) неверно', '2) **неверно** (отмечено)'), answer='2'),
                task_block('7', SKI.replace('1) верно', '1) **верно** (отмечено)'), answer='1'),
                task_block('8', 'Три бригады, производящие товары А и В, решили объединиться. '
                                'Постройте общую КПВ.')]]},
            names=self.NAMES)
        self.assertEqual(list(tasks), [('тест-6', ''), ('тест-7', ''), ('8', '')])
        self.assertEqual(tasks[('тест-6', '')].answer, '2')
        self.assertEqual(tasks[('тест-7', '')].answer, '1')
        self.assertNotIn('отмечено', assemble.join_pieces(tasks[('тест-6', '')].statement))
        self.assertEqual(report['v6: повтор вопроса в файле ответов → к вопросу'], 2)

    def test_10b_stem_in_title_still_matches(self):
        """Формулировка «тест-9» — в названии, в условии только «1) да 2) нет»:
        повтор с формулировкой в файле ответов всё равно к нему."""
        stem = 'Если при выпуске 2000 штук VC=7000, а ATC=4,5, то постоянные издержки равны 2000?'
        tasks, _, _ = self.build(
            {'pages/test': [[task_block('9', '1) да 2) нет', title=stem)]]},
            {'pages/ans': [[task_block('9', f'{stem}\n\n1) да\n2) **нет** (отмечено)', answer='2')]]},
            names=self.NAMES)
        self.assertEqual(list(tasks), [('тест-9', '')])
        self.assertEqual(tasks[('тест-9', '')].answer, '2')

    def test_10d_many_marks_still_match(self):
        """Вопрос «выберите все верные» с несколькими пометками «(отмечено)»."""
        q = 'К деньгам относятся:\n1) банкноты\n2) векселя\n3) монеты\n4) чеки'
        marked = ('К деньгам относятся:\n1) **банкноты** (отмечено)\n2) векселя\n'
                  '3) **монеты** (отмечено)\n4) **чеки** (отмечено)')
        tasks, _, _ = self.build({'pages/test': [[task_block('3', q)]]},
                                 {'pages/ans': [[task_block('3', marked, answer='1, 3, 4')]]},
                                 names=self.NAMES)
        self.assertEqual(list(tasks), [('тест-3', '')])
        self.assertEqual(tasks[('тест-3', '')].answer, '1, 3, 4')

    def test_10f_marks_and_stem_in_title(self):
        """Формулировка — в названии, отмечены все варианты: без снятия пометок
        повтор не узнать (ни по «тест-N», ни по тексту условия)."""
        stem, options = 'К деньгам относятся:', '1) рубль 2) евро 3) чек'
        marked = f'{stem}\n1) **рубль** (отмечено)\n2) **евро** (отмечено)\n3) **чек** (отмечено)'
        tasks, _, _ = self.build({'pages/test': [[task_block('36', options, title=stem)]]},
                                 {'pages/ans': [[task_block('36', marked, answer='1, 2, 3')]]},
                                 names=self.NAMES)
        self.assertEqual(list(tasks), [('тест-36', '')])

    def test_10e_answer_file_tasks_not_absorbed(self):
        """Условий нет (финал МОШ 2017/18): задачи 1 и 2 кейса с общим текстом
        заведены файлом ответов — задача 2 не поглощается задачей 1."""
        case = ('Прочитайте текст о рынке труда учителей в маленьком городе и ответьте на вопрос. '
                'В городе одна школа, она нанимает всех учителей. Предложение труда учителей '
                'задано функцией L = 2w, а предельная доходность труда в школе равна 100 − L. '
                'Других работодателей для учителей в городе нет, переезд в соседний город '
                'занимает слишком много времени, поэтому учителя работают только здесь.')
        tasks, _, _ = self.build({}, {'pages/ans': [[
            task_block('1', f'{case}\n\nВопрос 1. Какая это структура рынка?'),
            task_block('2', f'{case}\n\nВопрос 2. Как изменится зарплата при росте спроса?')]]})
        self.assertEqual(list(tasks), [('1', ''), ('2', '')])

    def test_10c_misnumbered_repeat_by_text(self):
        """Номер в файле ответов перепутан (вопрос 19 записан как 20): к 19 по тексту."""
        graph = ('На графике представлены кривые производственных возможностей экономики, '
                 'производящей только телефоны и компьютеры. Что могло привести к сдвигу КПВ?\n'
                 '1) рост квалификации\n2) снижение безработицы')
        tasks, _, _ = self.build({'pages/tasks': [[task_block('19', graph)]]},
                                 {'pages/ans': [[task_block('20', graph.replace(
                                     '1) рост', '1) **рост') + ' (отмечено)', answer='1')]]})
        self.assertEqual(list(tasks), [('19', '')])
        self.assertEqual(tasks[('19', '')].answer, '1')


# ── 11. Файл решений: повтор задачи и её пункты ──────────────────────────────

class RegionTests(Build):
    def solution_file(self, title1='«Рыцари при дворе короля Артура»', title2='«Газировка»',
                      second_header='2'):
        return {'pages/sol': [
            [{'type': 'solution', 'number': '1', 'text': '**Время на выполнение заданий — 120 минут**'},
             task_block('1', f'{KNIGHTS}\n\n1. *(4 балла)* Какое максимальное число рыцарей?\n\n'
                             '**Ответ.** 12 рыцарей, поскольку при n ≥ 13 удовольствие неположительно.',
                        title=title1, points=25),
             task_block('2', 'Какое количество приглашённых оптимально с точки зрения рыцаря?',
                        points=8),
             {'type': 'solution', 'number': '2', 'text': '**Ответ.** 6 или 7 рыцарей, вершина параболы.'},
             {'type': 'criteria', 'number': '2', 'text': '(8 баллов) Полный балл за ответ «6 или 7».'}],
            [{'type': 'solution', 'number': second_header, 'title': title2, 'text': SODA},
             {'type': 'task_continuation', 'number': '',
              'text': f'{SODA}\n\n**Ответ к пункту.** Ассоциация защищает свою долю рынка.'},
             {'type': 'solution', 'number': '1',
              'text': '**Ответ.** Крупные производители хотят вытеснить мелких конкурентов.'},
             # пункт 2 задачи 2: номер совпал с номером задачи, но у блока баллы
             task_block('2', 'Какую стратегию вы посоветуете мелким производителям газировки?',
                        points=6),
             {'type': 'solution', 'number': '2', 'text': '**Ответ.** Конкурировать качеством напитка.'},
             {'type': 'criteria', 'number': '1', 'text': '(6 баллов) За идею вытеснения конкурентов.'}]]}

    def task_file(self, title1='«Рыцари при дворе короля Артура»', title2='«Газировка»'):
        return {'pages/tasks': [[
            task_block('1', f'{KNIGHTS}\n\n1. Какое максимальное число рыцарей?\n'
                            '2. Какое количество приглашённых оптимально с точки зрения рыцаря?',
                       title=title1, points=25),
            task_block('2', f'{SODA}\n\n1. Чем может быть обосновано решение ассоциации?\n'
                            '2. Какую стратегию вы посоветуете мелким производителям газировки?',
                       title=title2, points=25)]]}

    def test_11a_items_stay_with_their_task(self):
        """Ответ на пункт 2 задачи 1 — у задачи 1, а не у задачи 2; повтор задачи 2,
        размеченный «решением», открывает её часть; правила работы — во вступление."""
        tasks, event, report = self.build(self.task_file(), self.solution_file(),
                                          event_id='vp-2019-final-8-v1')
        one, two = tasks[('1', '')], tasks[('2', '')]
        sol1, sol2 = '\n\n'.join(one.solution), '\n\n'.join(two.solution)
        self.assertIn('12 рыцарей', sol1)
        self.assertIn('2) (8 баллов) Какое количество приглашённых', sol1)
        self.assertIn('6 или 7 рыцарей', sol1)
        self.assertNotIn('6 или 7', sol2)
        self.assertIn('вытеснить мелких', sol2)
        self.assertNotIn('вытеснить мелких', sol1)
        self.assertEqual(one.criteria, ['(8 баллов) Полный балл за ответ «6 или 7».'])
        self.assertEqual(two.criteria, ['(6 баллов) За идею вытеснения конкурентов.'])
        self.assertNotIn(SODA[:40], sol2)                       # повтор условия — не решение
        self.assertIn('Ассоциация защищает свою долю рынка', sol2)
        self.assertIn('2) (6 баллов) Какую стратегию вы посоветуете', sol2)
        self.assertLess(sol2.index('Какую стратегию'), sol2.index('Конкурировать качеством'))
        self.assertNotIn('Время на выполнение', sol1)
        self.assertIn('**Время на выполнение заданий — 120 минут**', event['preamble'])
        self.assertEqual(report['v6: файл решений — повтор задачи и её пункты'], 1)

    def test_11b_generic_titles_keep_old_assembly(self):
        """«Задача 1»/«Задача 2» — не названия: правило не включается, решения —
        по номерам, как в v5 (mosh-2011-final-10: «Задание 1:» — пункт задачи 2)."""
        tasks, _, report = self.build(self.task_file('Задача 1', 'Задача 2'),
                                      self.solution_file('Задача 1', 'Задача 2'))
        self.assertEqual(report['v6: файл решений — повтор задачи и её пункты'], 0)
        self.assertIn('6 или 7 рыцарей', '\n\n'.join(tasks[('2', '')].solution))

    def test_11c_headers_out_of_order_keep_old_assembly(self):
        """Повторы задач не по порядку (1, 2, снова 1) — правило не включается."""
        solutions = self.solution_file()
        solutions['pages/sol'].append([task_block('1', KNIGHTS, title='«Рыцари при дворе короля Артура»')])
        _, _, report = self.build(self.task_file(), solutions)
        self.assertEqual(report['v6: файл решений — повтор задачи и её пункты'], 0)


# ── 12. Ключи v5 → v6 ────────────────────────────────────────────────────────

def row(**kw):
    base = dict(event_id='e', number='1', task_variant='', title='', statement_md='',
                section_md='', answer='', statement_from_solution_file=False)
    base.update(kw)
    return base


class KeyTableV6Tests(SimpleTestCase):
    def test_12a_repeat_and_new_rows(self):
        stem = 'Если при выпуске 2000 штук VC=7000, а ATC=4,5, то постоянные издержки фирмы равны:'
        options = '1. 5000; 2. 4000; 3. 2000; 4. 9000.'
        jeans = 'Рост цены на джинсы может привести к уменьшению спроса на них. 1) верно 2) неверно'
        bank = 'Сумма вкладов в банке составляет 500 млн рублей. Банк выдал кредитов на 400 млн.'
        old = [row(number='тест-5', statement_md=jeans), row(number='тест-9', title=stem, statement_md=options),
               row(number='5', statement_md=jeans.replace('неверно', '**неверно** (отмечено)'),
                   statement_from_solution_file=True),
               row(number='9', statement_md=f'{stem} 1. 5000; 2. **4000;** (отмечено) 3. 2000; 4. 9000.',
                   statement_from_solution_file=True)]
        new = [row(number='тест-5', statement_md=jeans), row(number='тест-9', title=stem, statement_md=options),
               row(number='5', statement_md=bank, statement_from_solution_file=True),
               row(number=econ_rules.ESSAY_NUMBER, statement_md='Проблемная ситуация: моногорода.')]
        rows, changed = vk.key_table(old, new, 'mosh', repeats=True, new_rows=True)
        verdicts = {(r[2], r[5]): r[7] for r in rows}
        self.assertEqual(verdicts[('5', 'тест-5')], vk.REPEAT)
        self.assertEqual(verdicts[('9', 'тест-9')], vk.REPEAT)
        self.assertEqual(verdicts[('тест-9', 'тест-9')], vk.SAME)
        self.assertEqual(verdicts[('', '5')], vk.NEW)
        self.assertEqual(verdicts[('', econ_rules.ESSAY_NUMBER)], vk.NEW)
        self.assertEqual(len([r for r in rows if r[1]]), len(old))
        self.assertEqual(vk.columns('v5', 'v6')[1:7], ['v5_event', 'v5_number', 'v5_variant',
                                                       'v6_event', 'v6_number', 'v6_variant'])

    def test_12e_stem_in_title_picks_right_question(self):
        """Варианты одинаковые («1) верно 2) неверно»), формулировка — в названии:
        повтор «6» указывает на «тест-6», а не на соседний «тест-7»."""
        yes_no = '1) верно 2) неверно'
        s6 = 'Армия является примером чистого общественного блага.'
        s7 = 'Фаза спада экономического цикла сопровождается ростом безработицы.'
        tests = [row(number='тест-6', title=s6, statement_md=yes_no),
                 row(number='тест-7', title=s7, statement_md=yes_no)]
        old = tests + [row(number='6', statement_md=f'{s6} 1) **верно** (отмечено) 2) неверно',
                           statement_from_solution_file=True)]
        rows, _ = vk.key_table(old, tests, 'mosh', repeats=True)
        self.assertEqual([r[5] for r in rows if r[2] == '6'], ['тест-6'])


# ── Настоящий v6 ─────────────────────────────────────────────────────────────

def _data(name, sub):
    return os.path.join(DATA, SETS[name], 'digitized', sub)


class DataV6Tests(SimpleTestCase):
    def rows(self, name):
        path = _data(name, 'v6/reference_problems_v6.jsonl')
        if not os.path.isfile(path):
            self.skipTest('нет данных v6')
        return fixes.read_rows(path)

    def test_12b_no_duplicate_keys_and_table_covers_v5(self):
        for name in SETS:
            rows = self.rows(name)
            self.assertEqual(vk.duplicates(rows), [], name)
            with open(_data(name, 'v6/v5_to_v6_keys.csv'), encoding='utf-8-sig', newline='') as fh:
                table = [r for r in list(csv.reader(fh, delimiter=';'))[1:] if r[1]]
            v5 = fixes.read_rows(_data(name, 'v5/reference_problems_v5.jsonl'))
            self.assertEqual(sorted(tuple(r[1:4]) for r in table), sorted(vk.key(r) for r in v5), name)

    def test_12c_no_test_question_repeats_left(self):
        rows = self.rows('mosh')
        keys = {vk.key(r) for r in rows}
        left = [vk.key(r) for r in rows if r.get('statement_from_solution_file')
                and (r['event_id'], f'тест-{r["number"]}', r.get('task_variant') or '') in keys
                and fuzz.partial_ratio(vk.plain(econ_rules.unmark(r['statement_md']))[:300],
                                       vk.question(next(x for x in rows if vk.key(x) == (
                                           r['event_id'], f'тест-{r["number"]}',
                                           r.get('task_variant') or '')))) >= 90]
        # mosh-2010-final-9 «5» — вопрос 5 второго теста; «тест-5» склеен с его
        # вариантами в файле условий, но формулировки там нет — это не повтор.
        self.assertEqual(left, [])

    def test_12d_vp_2019_final_8_and_essays(self):
        vp = {vk.key(r): r for r in self.rows('vp')}
        three = vp[('vp-2019-final-8-v1', '3', '')]['solution_md']
        self.assertIn('Воспользуемся полученной таблицей', three)
        self.assertIn('График $P(w)$', three)
        self.assertNotIn('оппозиционной партии', three)
        self.assertNotIn('Воспользуемся полученной таблицей', vp[('vp-2019-final-8-v1', '2', '')]['solution_md'])
        mosh = {vk.key(r): r for r in self.rows('mosh')}
        essay = mosh[('mosh-2010-final-10-v1', econ_rules.ESSAY_NUMBER, '')]['statement_md']
        self.assertIn('² «Как спасти Качканар?»', essay)
        self.assertIn('градообразующая компания', essay)
        self.assertIn(('mosh-2010-final-11-v1', econ_rules.ESSAY_NUMBER, ''), mosh)
        self.assertIn('максимизацмию', mosh[('mosh-2022-final-9-v1', '2', '')]['solution_md'])
