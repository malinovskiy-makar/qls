"""Финграмотность и основы бизнеса, сессия 2 (13.10.2026).

МОШ «по основам предпринимательства и финансовой грамотности» в реестре;
разбор `event_id` с дефисом в префиксе через реестр (`event_for`); разбор
очереди «на глаза» с заплатками `pages_v2` и сборкой v2 поверх v1; флаг
`auto_publish_ok`. Данные выдуманные; база не нужна.
"""
from django.test import SimpleTestCase

from problems.olympiad_audit import registry
from problems.olympiad_official import Reference


def _row(event_id, number=1):
    return {'event_id': event_id, 'number': number, 'norm_text': 'x'}


class RegistryEntrepreneurshipTests(SimpleTestCase):
    def test_1_new_slug_own_dir_prefix_and_predecessor_note(self):
        entry = registry.get('mosh-entrepreneurship')
        self.assertEqual(entry.audit_dir, 'audit_finbiz_20261013/mosh_entrepreneurship')
        self.assertEqual(entry.event_prefix, 'mosh-entrepreneurship-')
        self.assertEqual(entry.stages, ('qualifying', 'final'))
        self.assertEqual(entry.olympiad_name, 'Московская олимпиада школьников по основам '
                                              'предпринимательства и финансовой грамотности')
        self.assertEqual(entry.compare, 'markup_free')
        self.assertEqual(entry.family, ('mosh-entrepreneurship',))
        note = entry.official_source_defaults['note']
        self.assertIn('mos.olimpiada.ru/tasks/entr', note)
        self.assertIn('предшественник', note)
        names = registry.official_source_names()
        self.assertIn(entry.official_source_name, names)
        self.assertEqual(len(names), len(set(names)))
        # Старые записи не тронуты.
        self.assertEqual(registry.get('mosh-fingram').event_prefix, 'mosh-fingram-')
        self.assertEqual(registry.get('mosh').audit_dir, 'audit_mosh_20261009')


class ParseEventIdTests(SimpleTestCase):
    def test_2_hyphenated_prefixes_by_registry(self):
        cases = {
            'vp-fingram-2019-final-9-10-v1': ('vp-fingram', '2019', 'final', '9-10', 'v1'),
            'vp-ob-2024-final-11-v1': ('vp-ob', '2024', 'final', '11', 'v1'),
            'mosh-fingram-2017-qualifying-5-11-tour2':
                ('mosh-fingram', '2017', 'qualifying', '5-11', 'tour2'),
            'mosh-entrepreneurship-2012-final-8-11-v1':
                ('mosh-entrepreneurship', '2012', 'final', '8-11', 'v1'),
        }
        for event_id, expected in cases.items():
            self.assertEqual(registry.parse_event_id(event_id), expected, event_id)

    def test_3_old_event_ids_as_before(self):
        self.assertEqual(registry.parse_event_id('vp-2020-final-10-v1'),
                         ('vp', '2020', 'final', '10', 'v1'))
        self.assertEqual(registry.parse_event_id('vp-2021-final-10-reserve'),
                         ('vp', '2021', 'final', '10', 'reserve'))
        self.assertEqual(registry.parse_event_id('mosh-2015-final-8-9-day2'),
                         ('mosh', '2015', 'final', '8-9', 'day2'))
        self.assertIsNone(registry.parse_event_id('нечто'))

    def test_4_event_for_hyphenated_and_old(self):
        ref = Reference([_row('vp-fingram-2019-final-9-10-v1'),
                         _row('vp-fingram-2019-final-11-v1'),
                         _row('mosh-fingram-2018-final-10-11-v1'),
                         _row('mosh-fingram-2018-final-10-11-v2')])
        self.assertEqual(ref.event_for(2019, '9-10'), 'vp-fingram-2019-final-9-10-v1')
        self.assertEqual(ref.event_for(2019, 11), 'vp-fingram-2019-final-11-v1')
        self.assertEqual(ref.event_for(2018, '10-11'), 'mosh-fingram-2018-final-10-11-v1')
        self.assertIsNone(ref.event_for(2020, 11))
        old = Reference([_row('vp-2021-final-10-reserve'), _row('vp-2021-final-10-v1'),
                         _row('mosh-2015-final-8-9-day2')])
        self.assertEqual(old.event_for(2021, 10), 'vp-2021-final-10-v1')
        self.assertEqual(old.event_for(2015, '8-9'), 'mosh-2015-final-8-9-day2')


class LayerMetricRepeatedLinesTests(SimpleTestCase):
    """Мерило слоя: строки, повторённые на половине страниц файла (формулировки
    теста, одиночные «1», «2», «3» вариантов), срезаются из слоя как колонтитулы.
    Дословная расшифровка не должна получать за них «лишний текст»."""

    QUESTION = 'Является ли он потребителем по Закону РФ «О защите прав потребителей»?'

    STORIES = ['Авиапассажир смотрит телепрограмму в зале ожидания аэропорта.',
               'Дарья Павловна оставила ребенка в бесплатном детском центре супермаркета.',
               'Геннадий Гаврилович берет в метро бесплатную информационную газету.',
               'Татьяна Андреевна получает молоко на молочной кухне бесплатно.']

    def _layer(self, extra='', story=0):
        return (f'9. Задача 9\n{self.STORIES[story]}\n'
                f'{self.QUESTION}\n1\nНет. Он не является потребителем.\n2\n'
                f'Да. Он является потребителем по определению.\n{extra}')

    def _blocks(self, text_tail=''):
        return [{'type': 'solution', 'number': '9',
                 'text': ('Авиапассажир смотрит телепрограмму в зале ожидания аэропорта.\n\n'
                          f'{self.QUESTION}\n\n1. Нет. Он не является потребителем.\n'
                          '2. Да. Он является потребителем по определению.' + text_tail)}]

    def test_5_repeated_lines_not_extra(self):
        from problems.olympiad_audit import transcribe
        layers = [self._layer(story=i) for i in range(4)]
        footers = transcribe.repeated_lines(layers)
        ratio, numbers_ok, missing, extra, _f = transcribe.layer_metrics(
            self._blocks(), layers[0], footers, page=1)
        self.assertGreaterEqual(ratio, 0.95)
        self.assertEqual(extra, [])
        self.assertTrue(numbers_ok)

    def test_6_real_loss_still_caught(self):
        from problems.olympiad_audit import transcribe
        layers = [self._layer(story=i) for i in range(4)]
        layers[0] = self._layer('Дополнительный абзац о правах пассажира в аэропорту и '
                                'компенсации за задержку рейса составляет 500 рублей.')
        footers = transcribe.repeated_lines(layers)
        ratio, numbers_ok, missing, extra, _f = transcribe.layer_metrics(
            self._blocks(), layers[0], footers, page=1)
        self.assertLess(ratio, 0.90)
        self.assertEqual(missing, ['500'])
        # Выдуманное число, которого нет на странице, — по-прежнему лишнее.
        ratio, numbers_ok, missing, extra, _f = transcribe.layer_metrics(
            self._blocks(' Штраф 7777 рублей.'), self._layer(), footers, page=1)
        self.assertEqual(extra, ['7777'])


class AssembleIntroRepeatTests(SimpleTestCase):
    """МОШ-предпринимательство 2012/13, финал 8-9: вступление второй части
    («Общее время… Максимальное количество баллов…») стоит на КАЖДОЙ странице
    «Ситуаций», а пустая страница теста несёт только «Комплект заданий № 1».
    Такие безномерные блоки — вступление (один раз) или служебная строка, не
    кусок предыдущего задания."""

    INTRO = ('Общее время на выполнение заданий – 60 минут.\nМаксимальное количество '
             'баллов – 19\nДайте правильный и наиболее полный ответ.')

    def test_7_repeated_intro_and_service_line_not_glued(self):
        import shutil
        import tempfile
        from pathlib import Path

        from problems.olympiad_audit import assemble, transcribe
        root = Path(tempfile.mkdtemp(prefix='finbiz2_asm_'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        def page(n, blocks):
            transcribe.Transcriber._write(str(root / 'pages/t' / f'p{n}.json'),
                                          {'status': 'ok', 'blocks': blocks})
        page(1, [{'type': 'task', 'number': '1', 'text': 'Вопрос теста 1.'},
                 {'type': 'task', 'number': '2', 'text': 'Вопрос теста 2.'}])
        page(2, [{'type': 'task', 'number': '', 'text': '**Комплект заданий № 1**'}])
        page(3, [{'type': 'task', 'number': '', 'text': self.INTRO},
                 {'type': 'task', 'number': '3', 'text': 'Ситуация: шуба.'}])
        page(4, [{'type': 'task', 'number': '', 'text': self.INTRO},
                 {'type': 'task', 'number': '4', 'text': 'Ситуация: телефон.'},
                 {'type': 'task', 'number': '', 'text': '(б) кусок условия задания 4'}])
        event = {'event_id': 'mosh-entrepreneurship-2013-final-8-9-v1', 'grade': '8-9',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 4}]}
        tasks, report, _ = assemble.build_event(str(root), event, str(root / 'f'), crop=False)
        by = {t.number: t for t in tasks}
        self.assertEqual(by['2'].statement, ['Вопрос теста 2.'])
        self.assertEqual(by['3'].statement, ['Ситуация: шуба.'])
        # Настоящий безномерной кусок по-прежнему приклеивается.
        self.assertEqual(by['4'].statement, ['Ситуация: телефон.', '(б) кусок условия задания 4'])
        self.assertEqual(event['preamble'], [self.INTRO])
        self.assertEqual(report['служебная строка — мимо'], 1)
        self.assertEqual(report['повтор вступления — мимо'], 1)

    def test_8_statement_repeated_in_solution_file_not_in_solution(self):
        """Файл ответов МОШ повторяет условие: хвост условия на новой странице
        (`task_continuation` с номером) не становится началом решения, а
        абзацы-повтор условия в начале блока решения срезаются (v1 МОШ-финграм:
        364 из 1 307 решений начинались с текста условия)."""
        import shutil
        import tempfile
        from pathlib import Path

        from problems.olympiad_audit import assemble, transcribe
        root = Path(tempfile.mkdtemp(prefix='finbiz2_sol_'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        statement = ('Лена получает 50 тыс. рублей в месяц, а тратит 45 тыс. рублей. У Лены есть '
                     'кредитная карта с беспроцентным периодом до погашения долга 7 числа '
                     'каждого месяца и лимитом 100 тыс. рублей.\n\nОпишите оптимальную стратегию Лены.')

        def page(page_dir, n, blocks):
            transcribe.Transcriber._write(str(root / page_dir / f'p{n}.json'),
                                          {'status': 'ok', 'blocks': blocks})
        page('pages/t', 1, [{'type': 'task', 'number': '4', 'text': statement},
                            {'type': 'task', 'number': '5', 'text': 'Как применить поговорку?'}])
        page('pages/s', 1, [{'type': 'task', 'number': '4', 'text': statement[:60]}])
        page('pages/s', 2, [
            {'type': 'task_continuation', 'number': '4',
             'text': 'долга 7 числа каждого месяца и лимитом 100 тыс. рублей.\n\n'
                     'Опишите оптимальную стратегию Лены.'},
            {'type': 'solution', 'number': '4', 'text': '1) Самый высокий доход приносит вклад.'},
            {'type': 'solution', 'number': '5',
             'text': '**Задача 5**\n\nКак применить поговорку?\n\nПокупать одежду в конце сезона.'}])
        event = {'event_id': 'mosh-fingram-2017-final-10-11-v1', 'grade': '10-11',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 1}],
                 'solution_files': [{'file': 'raw/pdf/s.pdf', 'page_dir': 'pages/s', 'pages': 2}]}
        tasks, report, _ = assemble.build_event(str(root), event, str(root / 'f'), crop=False)
        by = {t.number: t for t in tasks}
        self.assertEqual(by['4'].solution, ['1) Самый высокий доход приносит вклад.'])
        self.assertEqual(by['5'].solution, ['Покупать одежду в конце сезона.'])
        self.assertEqual(report['повтор условия в файле решений — мимо'], 1)
        self.assertEqual(report['повтор условия в начале решения — срезан'], 1)
        # Решение, которое лишь начинается похоже, но несёт ответ, не срезается целиком.
        self.assertEqual(assemble.strip_statement_echo('Как применить поговорку?',
                                                       'Как применить поговорку?'),
                         'Как применить поговорку?')


_WORDS = ['налог', 'вклад', 'акция', 'облигация', 'кредит', 'страховка', 'пенсия', 'ипотека',
          'лизинг', 'франшиза', 'дивиденд', 'бюджет', 'инфляция', 'депозит', 'вексель']


def _q(n, topic):
    a, b, c = _WORDS[n % 15], _WORDS[(n * 4 + 1) % 15], _WORDS[(n * 7 + 3) % 15]
    return (f'{topic.capitalize()}: что из перечисленного верно про {a}, {b} и {c} '
            f'в ситуации {n}?\n\n- A. {a} важнее\n- B. {c} важнее')


class AssembleSectionsTests(SimpleTestCase):
    """МОШ-предпринимательство, финалы: несколько тестов в файле теста,
    повторный сброс нумерации в файле условий, ответы с повтором вопроса."""

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        self.root = Path(tempfile.mkdtemp(prefix='finbiz2_sec_'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def page(self, page_dir, n, blocks):
        from problems.olympiad_audit import transcribe
        transcribe.Transcriber._write(str(self.root / page_dir / f'p{n}.json'),
                                      {'status': 'ok', 'blocks': blocks})

    def build(self, event):
        from problems.olympiad_audit import assemble
        return assemble.build_event(str(self.root), event, str(self.root / 'f'), crop=False)

    def test_9_two_tests_in_test_file_do_not_merge(self):
        self.page('pages/t', 1, [{'type': 'task', 'number': str(n), 'text': _q(n, 'тест1')}
                                 for n in range(1, 11)])
        self.page('pages/t', 2, [{'type': 'task', 'number': '', 'text': 'Тест № 2.'}] +
                  [{'type': 'task', 'number': str(n), 'text': _q(n, 'тест2')} for n in (1, 2, 3)])
        event = {'event_id': 'mosh-entrepreneurship-2010-final-8-11-v1', 'grade': '8-11',
                 'task_files': [{'file': 'raw/pdf/tasks-entr-test-final-2009-10.pdf',
                                 'page_dir': 'pages/t', 'pages': 2}]}
        tasks, report, _ = self.build(event)
        numbers = [t.number for t in tasks]
        self.assertEqual(len(tasks), 13)
        self.assertIn('тест-1.10', numbers)
        self.assertIn('тест-2.3', numbers)
        self.assertEqual({t.number: t for t in tasks}['тест-2.1'].statement, [_q(1, 'тест2')])

    def test_10_second_restart_makes_subquestions_of_next_task(self):
        self.page('pages/t', 1, [{'type': 'task', 'number': str(n), 'text': _q(n, 'тест')}
                                 for n in range(1, 11)])
        self.page('pages/t', 2, [{'type': 'task', 'number': '2', 'text': 'Задание 2. Блок-схема.'},
                                 {'type': 'task', 'number': '3', 'text': 'Задание 3. Задачи.'}])
        self.page('pages/t', 3, [{'type': 'task', 'number': str(n), 'text': f'Кейс, вопрос {n}.'}
                                 for n in (1, 2, 3)])
        event = {'event_id': 'mosh-entrepreneurship-2014-final-10-11-v1', 'grade': '10-11',
                 'task_files': [{'file': 'raw/pdf/tasks-entr-10-11-final-13-4.pdf',
                                 'page_dir': 'pages/t', 'pages': 3}]}
        tasks, report, _ = self.build(event)
        by = {t.number: t for t in tasks}
        self.assertEqual(len(tasks), 15)
        self.assertEqual(by['2'].statement, ['Задание 2. Блок-схема.'])
        self.assertEqual(by['4.1'].statement, ['Кейс, вопрос 1.'])
        self.assertIn('тест-10', by)
        self.assertEqual(report['нумерация снова с 1: подпункты следующего задания'], 1)

    def test_11_answers_with_repeated_question_matched_by_text(self):
        self.page('pages/t', 1, [{'type': 'task', 'number': str(n), 'text': _q(n, 'тест')}
                                 for n in range(1, 11)])
        self.page('pages/t', 2, [{'type': 'task', 'number': str(n), 'text': f'Задача {n}: посчитайте '
                                  f'доход семьи Петровых за {n + 2} года.'} for n in (1, 2)])
        # Ответы: вопрос теста повторён с отмеченным ответом, номер «1»; затем
        # решение без повтора вопроса с номером «7» — только тест-7.
        self.page('pages/s', 1, [
            {'type': 'task', 'number': '1', 'text': _q(1, 'тест'), 'answer': 'A'},
            {'type': 'solution', 'number': '7', 'text': 'Ответ: B'},
            {'type': 'task', 'number': '1', 'text': 'Задача 1: посчитайте доход семьи '
                                                    'Петровых за 3 года.'},
            {'type': 'solution', 'number': '1', 'text': 'Доход 300 тыс.'}])
        event = {'event_id': 'mosh-entrepreneurship-2014-final-8-9-v1', 'grade': '8-9',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 2}],
                 'solution_files': [{'file': 'raw/pdf/s.pdf', 'page_dir': 'pages/s', 'pages': 1}]}
        tasks, report, _ = self.build(event)
        by = {t.number: t for t in tasks}
        self.assertEqual(by['тест-1'].answer, 'A')
        self.assertEqual(by['1'].answer, '')
        self.assertEqual(by['тест-7'].solution, ['Ответ: B'])
        self.assertEqual(by['1'].solution, ['Доход 300 тыс.'])
        self.assertEqual(by['тест-1'].solution, [])

    def test_12_answer_grid_blank_gives_test_answers(self):
        from problems.olympiad_audit import assemble
        marks = ('| 1 | 2 | 3 |\n|---|---|---|\n| 1 | 1 (отмечено) | 1 |\n'
                 '| 2 (отмечено) | 2 | 2 |\n| 3 | 3 | 3 (отмечено) |')
        self.assertEqual(assemble.parse_answer_grid('БЛАНК ОТВЕТОВ\n\n' + marks),
                         {'1': '2', '2': '1', '3': '3'})
        plus = ('**Тест № 1. Ответы**\n\n| № | А | В | С | № | А | В | С |\n'
                '|---|---|---|---|---|---|---|---|\n| 1 | | | + | 11 | + | | |\n'
                '| 2 | + | | | 12 | | + | |')
        self.assertEqual(assemble.parse_answer_grid(plus),
                         {'1': 'С', '2': 'А', '11': 'А', '12': 'В'})
        # Обычная таблица данных — не бланк.
        self.assertEqual(assemble.parse_answer_grid('| Q | P |\n|---|---|\n| 1 | 10 |\n| 2 | 8 |'),
                         {})
        self.page('pages/t', 1, [{'type': 'task', 'number': str(n), 'text': _q(n, 'тест')}
                                 for n in range(1, 4)])
        self.page('pages/s', 1, [{'type': 'task', 'number': '', 'text': 'БЛАНК ОТВЕТОВ\n\n' + marks}])
        event = {'event_id': 'mosh-entrepreneurship-2013-final-7-v1', 'grade': '7',
                 'task_files': [{'file': 'raw/pdf/tasks-finance-7-test-final.pdf',
                                 'page_dir': 'pages/t', 'pages': 1}],
                 'solution_files': [{'file': 'raw/pdf/otvet.pdf', 'page_dir': 'pages/s',
                                     'pages': 1}]}
        tasks, report, _ = self.build(event)
        by = {t.number: t for t in tasks}
        self.assertEqual((by['тест-1'].answer, by['тест-3'].answer), ('2', '3'))
        self.assertEqual(report['бланк ответов → ответы теста'], 3)

    def test_13_kit_number_in_header_is_not_variant(self):
        from problems.olympiad_audit import assemble
        self.assertEqual(assemble._variant_of_header(
            {'variant': 'Комплект заданий № 2 (основы потребительских знаний)'}), '')
        self.assertEqual(assemble._variant_of_header({'variant': 'Решебник, 16 марта 2014 г.'}), '')
        self.assertEqual(assemble._variant_of_header({'variant': '2 Вариант'}), '2')
        self.assertEqual(assemble._variant_of_header({'variant': '1'}), '1')

    def test_14_solution_inside_repeated_statement(self):
        statement = ('Петр приобрел во время весенней распродажи сноуборд. Следующей зимой он '
                     'обнаружил, что основание доски расслоилось. Удастся ли Петру вернуть деньги?')
        self.page('pages/t', 1, [{'type': 'task', 'number': '1', 'text': statement},
                                 {'type': 'task', 'number': '2', 'text': 'Другая ситуация про '
                                  'кастрюлю для индукционной плиты и коробку от другой кастрюли.'}])
        self.page('pages/s', 1, [{'type': 'task', 'number': '1', 'text': statement + '\n\nСТ. 18'},
                                 {'type': 'task', 'number': '2', 'text': 'Другая ситуация про '
                                  'кастрюлю для индукционной плиты и коробку от другой кастрюли.'}])
        event = {'event_id': 'mosh-entrepreneurship-2014-final-7-v1', 'grade': '7',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 1}],
                 'solution_files': [{'file': 'raw/pdf/s.pdf', 'page_dir': 'pages/s', 'pages': 1}]}
        tasks, report, _ = self.build(event)
        by = {t.number: t for t in tasks}
        self.assertEqual(by['1'].solution, ['СТ. 18'])
        self.assertEqual(by['2'].solution, [])
        self.assertEqual(report['решение внутри повтора условия'], 1)
        from problems.olympiad_audit import assemble
        self.assertEqual(assemble.strip_statement_echo(
            '**5. Задача 5**\n\nЧто относится к природным ресурсам Земли?\n\n4. **торф** (отмечено)',
            'Что относится к природным ресурсам Земли?\n\n1. рыба\n4. торф'),
            '4. **торф** (отмечено)')

    def test_15_same_story_other_question_not_matched_by_text(self):
        """МОШ-финграм 2021/22: «Задания 19-20» — тот же сюжет, что задание 17,
        но другой вопрос; по тексту на 17 не ложатся."""
        from collections import OrderedDict

        from problems.olympiad_audit import assemble
        story = ('В текущем году инвестору предлагают вложить деньги в проект, который будет '
                 'приносить доход в течение трёх лет; ставка по депозиту в банке 10 % годовых. ')
        task = assemble.Task('e', '17')
        task.statement = [story + 'Сопоставьте показатели проекта и их значения: 1) NPV 2) IRR.']
        tasks = OrderedDict({('17', ''): task})
        other = 'Задания 19-20. ' + story + 'Найдите чистую приведённую стоимость проекта в рублях.'
        self.assertIsNone(assemble.match_by_text(tasks, other))
        self.assertIs(assemble.match_by_text(tasks, task.statement[0] + '\n\nОтвет: 1-Б; 2-В.'), task)

    def test_16_text_match_only_to_compatible_number(self):
        from collections import OrderedDict

        from problems.olympiad_audit import assemble
        glued = assemble.Task('e', '3')
        q4 = ('Выберите среди приведённых признаков те, которые, помимо указанных в тексте, '
              'тоже характеризуют вид мошенничества, о котором шла речь выше.')
        glued.statement = ['Выберите изображения, иллюстрирующие вид мошенничества.\n\n' + q4]
        tasks = OrderedDict({('3', ''): glued})
        self.assertIsNone(assemble.match_by_text(tasks, q4 + '\n\n- А. звонок', '4'))
        self.assertIs(assemble.match_by_text(tasks, glued.statement[0] + ' Ответ: 2', '3'), glued)
        self.assertTrue(assemble.compatible_number('тест-2.5', '5'))
        self.assertFalse(assemble.compatible_number('16', '18'))

    def test_17_variant_marker_in_text_and_number_answer_table(self):
        """МОШ-финграм, отбор 2019/20: ответы варианта 2 начинаются блоком
        «Правильные ответы / 2 вариант» (не шапкой), ответы теста 1–6 — одной
        таблицей «1 | В / 2 | В …» в блоке с номером 1."""
        from problems.olympiad_audit import assemble
        self.assertEqual(assemble.parse_answer_grid('| 1 | В |\n| 2 | Б, В |\n| 3 | А |'),
                         {'1': 'В', '2': 'Б, В', '3': 'А'})
        self.assertEqual(assemble.parse_answer_grid('| 1 | 100 |\n| 2 | 90 |\n| 3 | 80 |'), {})
        for v, n in (('1', 1), ('2', 2)):
            self.page('pages/t', n, [{'type': 'header', 'variant': v}] + [
                {'type': 'task', 'number': str(k), 'text': _q(k + 10 * n, 'вариант')}
                for k in range(1, 5)])
        self.page('pages/s', 1, [
            {'type': 'header', 'variant': '1'},
            {'type': 'solution', 'number': '1', 'text': '| 1 | В |\n| 2 | Г |\n| 3 | А |'},
            {'type': 'solution', 'number': '4', 'text': 'Решение 4 варианта 1.'},
            {'type': 'task', 'number': '', 'text': '**Правильные ответы**\n\n**2 вариант**'},
            {'type': 'task', 'number': '1', 'text': '| 1 | А, Б |\n| 2 | Б |\n| 3 | В |'},
            {'type': 'solution', 'number': '4', 'text': 'Решение 4 варианта 2.'}])
        event = {'event_id': 'mosh-fingram-2020-qualifying-6-7-v1', 'grade': '6-7',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 2}],
                 'solution_files': [{'file': 'raw/pdf/s.pdf', 'page_dir': 'pages/s', 'pages': 1}]}
        tasks, report, _ = self.build(event)
        by = {(t.number, t.task_variant): t for t in tasks}
        self.assertEqual(len(tasks), 8)
        self.assertEqual(by[('2', '1')].answer, 'Г')
        self.assertEqual(by[('1', '2')].answer, 'А, Б')
        self.assertEqual(by[('3', '2')].answer, 'В')
        self.assertEqual(by[('4', '2')].solution, ['Решение 4 варианта 2.'])
        self.assertEqual(by[('4', '1')].solution, ['Решение 4 варианта 1.'])

    def test_18_answer_key_as_list_and_answer_field(self):
        from problems.olympiad_audit import assemble
        key = 'КЛЮЧИ С ПРАВИЛЬНЫМИ ОТВЕТАМИ\nВариант 1\n\n1. Нет, не является\n2. В\n3. А, Б'
        self.assertEqual(assemble.parse_answer_list(key),
                         {'1': 'Нет, не является', '2': 'В', '3': 'А, Б'})
        self.assertEqual(assemble._variant_marker({'type': 'task', 'number': '', 'text': key}), '1')
        self.assertEqual(assemble.parse_answer_list('Ключи', '1 — А, Б, В; 2 — Г; 3 — А, В, Г'),
                         {'1': 'А, Б, В', '2': 'Г', '3': 'А, В, Г'})
        # Обычное решение списком длинных пунктов — не ключ.
        self.assertEqual(assemble.parse_answer_list(
            '1. Из всех продуктов банка самый высокий доход приносит вклад.\n'
            '2. Кредитная карта выгодна при беспроцентном периоде.\n3. Итог: 600 рублей.'), {})
        # Длинный блок с «вариантом» не в начальных строках — не метка.
        self.assertEqual(assemble._variant_marker(
            {'type': 'task', 'number': '', 'text': 'Условие.\nЕщё строка.\nТретья.\nВариант 2'}), '')


class TriageTiersTests(SimpleTestCase):
    """Ярусы разбора: B не становится A, ярус D для автопубликации, выбор судье."""

    def rec(self, key, **kw):
        page_dir, _, page = key.rpartition('/p')
        base = {'page_dir': page_dir, 'page': int(page), 'file': 'raw/pdf/t.pdf',
                'has_layer': True, 'status': 'ok', 'needs_eyes': False, 'layer_ratio': 0.99,
                'numbers_ok': True, 'numbers_missing': [], 'numbers_extra': []}
        base.update(kw)
        return base

    def test_19_tiers_b_stays_b_d_for_auto_publish(self):
        from problems.olympiad_audit import triage
        records = [
            self.rec('pages/a/p1', needs_eyes=True, layer_ratio=0.97, numbers_ok=False,
                     numbers_extra=['7'], needs_eyes_reasons=['расходится со слоем PDF']),
            self.rec('pages/a/p2', needs_eyes=True, layer_ratio=0.80,
                     needs_eyes_reasons=['расходится со слоем PDF']),
            self.rec('pages/a/p3', layer_ratio=0.93),         # не в очереди, слой < 0,95
            self.rec('pages/a/p4'),                            # чистая
        ]
        rows = [{'event_id': 'e', 'number': str(n), 'statement_md': 'Условие задания номер '
                 f'{n} про вклады и кредиты.', 'solution_md': 'Ответ.',
                 'source_pages': [f'raw/pdf/t.pdf#p{n}']} for n in (1, 2, 3, 4)]
        plan = triage.build_plan(records, rows, {'raw/pdf/t.pdf': 'pages/a'}, set(),
                                 auto_publish=True)
        tiers = {r['страница']: r['ярус'] for r in plan}
        self.assertEqual(tiers, {'pages/a/p1': 'B', 'pages/a/p2': 'A', 'pages/a/p3': 'D'})
        judged = set(triage.pages_to_judge(plan))
        self.assertIn('pages/a/p3', judged)
        self.assertIn('pages/a/p2', judged)
        # p1 — B в выборке контроля (ярус меньше 20 — весь ярус) — к судье как контроль.
        self.assertEqual(triage.pages_to_judge(plan, only='control'), ['pages/a/p1'])
        # Задачная причина поднимает страницу в A, но B без неё остаётся B.
        risks = triage.task_risks([dict(rows[0], solution_md='')], {'e'}, {'raw/pdf/t.pdf': 'pages/a'})
        plan = triage.build_plan(records, rows, {'raw/pdf/t.pdf': 'pages/a'}, set(), risks=risks)
        self.assertEqual({r['страница']: r['ярус'] for r in plan}['pages/a/p1'], 'A')


class SplitGluedTests(SimpleTestCase):
    def test_20_glued_questions_split_only_on_number_gap(self):
        import shutil
        import tempfile
        from pathlib import Path

        from problems.olympiad_audit import assemble, transcribe
        root = Path(tempfile.mkdtemp(prefix='finbiz2_glue_'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        glued = ('**Выберите верное утверждение:**\n\n**1. Частное лицо — участник товарищества.**\n\n'
                 '1) верно\n\n2) неверно\n\n**2. Уставный капитал равен сумме акций.**\n\n1) верно\n\n'
                 '2) неверно\n\n**3. Вкладчик становится полным товарищем.**\n\n1) верно\n\n2) неверно')
        legit = 'Ответьте на вопросы:\n\n1. Что такое вклад?\n2. Что такое кредит?'
        transcribe.Transcriber._write(str(root / 'pages/t/p1.json'), {'status': 'ok', 'blocks': [
            {'type': 'task', 'number': '1', 'text': glued},
            {'type': 'task', 'number': '4', 'text': 'Четвёртый вопрос.'},
            {'type': 'task', 'number': '5', 'text': legit},
            {'type': 'task', 'number': '6', 'text': 'Шестой вопрос.'}]})
        event = {'event_id': 'mosh-entrepreneurship-2010-final-8-11-v1', 'grade': '8-11',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 1}]}
        tasks, report, _ = assemble.build_event(str(root), event, str(root / 'f'), crop=False)
        by = {t.number: t for t in tasks}
        self.assertEqual([t.number for t in tasks], ['1', '2', '3', '4', '5', '6'])
        self.assertIn('Частное лицо', by['1'].statement[0])
        self.assertNotIn('Уставный', by['1'].statement[0])
        self.assertTrue(by['2'].statement[0].startswith('**2. Уставный'))
        self.assertIn('неверно', by['3'].statement[0])
        # Подпункты задания 5 без пропуска номеров — не режутся.
        self.assertEqual(by['5'].statement, [legit])
        self.assertEqual(report['склейка заданий разрезана по пропуску номеров'], 2)

    def test_21_number_gap_is_tier_a_risk(self):
        from problems.olympiad_audit import triage
        rows = [{'event_id': 'e', 'number': n, 'statement_md': f'Условие задания {n} о вкладах и '
                 'кредитах в банке.', 'source_pages': [f'raw/pdf/t.pdf#p{i}']}
                for i, n in enumerate(('1', '9', '10'), 1)]
        risks = triage.task_risks(rows, set(), {'raw/pdf/t.pdf': 'pages/t'})
        self.assertEqual(list(risks), ['pages/t/p1'])
        self.assertIn('пропуск номеров до 9', risks['pages/t/p1'][0])

    def test_22_no_split_when_number_exists_later_in_dict(self):
        """ВП-финграм 2024/25, 11 кл.: задание 3 заведено из файла решений в конце
        словаря; подпункт «3.» задания 2 — не склейка (пропуска номеров нет)."""
        from collections import Counter, OrderedDict

        from problems.olympiad_audit import assemble
        two = assemble.Task('e', '2')
        two.statement = ['Евгений поступил в университет.\n1. Посчитайте расходы.\n'
                         '2. Посчитайте вычет.\n3. Сравните варианты.']
        four, three = assemble.Task('e', '4'), assemble.Task('e', '3')
        four.statement, three.statement = ['Четвёртое.'], ['Третье из решений.']
        tasks = OrderedDict([(two.key, two), (four.key, four), (three.key, three)])
        report = Counter()
        assemble.split_glued(tasks, report)
        self.assertEqual(report['склейка заданий разрезана по пропуску номеров'], 0)
        self.assertIn('3. Сравните варианты.', tasks[('2', '')].statement[0])
        self.assertEqual(tasks[('3', '')].statement, ['Третье из решений.'])

    def test_23_compatible_target_follows_sequence_then_single_test(self):
        from collections import OrderedDict

        from problems.olympiad_audit import assemble
        tasks = OrderedDict()
        for n in ('тест-6', '4.5', '4.6', '2.1', '3.1'):
            tasks[(n, '')] = assemble.Task('e', n)
        after = tasks[('4.5', '')]
        self.assertIs(assemble.compatible_target(tasks, '6', '', after), tasks[('4.6', '')])
        self.assertIs(assemble.compatible_target(tasks, '6', '', None), tasks[('тест-6', '')])
        # «1» при подпунктах «2.1», «3.1» — не угадываем.
        self.assertIsNone(assemble.compatible_target(tasks, '1', '', tasks[('3.1', '')]))

    def test_24_date_at_block_start_is_not_task_number(self):
        import shutil
        import tempfile
        from pathlib import Path

        from problems.olympiad_audit import assemble, transcribe
        root = Path(tempfile.mkdtemp(prefix='finbiz2_date_'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        transcribe.Transcriber._write(str(root / 'pages/t/p1.json'), {'status': 'ok', 'blocks': [
            {'type': 'task', 'number': '4', 'text': 'Кейс: прочитайте записи блога.'},
            {'type': 'task', 'number': '20.11', 'text': '**20.11.2013 Бизнес моей мечты**\n\nТекст.'}]})
        event = {'event_id': 'mosh-entrepreneurship-2014-final-10-11-v1', 'grade': '10-11',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 1}]}
        tasks, report, _ = assemble.build_event(str(root), event, str(root / 'f'), crop=False)
        self.assertEqual([t.number for t in tasks], ['4'])
        self.assertIn('20.11.2013 Бизнес', '\n'.join(tasks[0].statement))
        self.assertTrue(assemble.is_date_number({'number': '20.11.2013',
                                                 'text': '**20.11.2013 Бизнес'}))
        self.assertFalse(assemble.is_date_number({'number': '2.10', 'text': 'Подпункт 2.10'}))

    def test_26_solution_right_after_compatible_question_goes_to_it(self):
        """Файл ответов: вопрос «6» (подпункт кейса «4.6», своего «6» нет), за
        ним решение «6» — к «4.6», а не к «тест-6»."""
        import shutil
        import tempfile
        from pathlib import Path

        from problems.olympiad_audit import assemble, transcribe
        root = Path(tempfile.mkdtemp(prefix='finbiz2_follow_'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        transcribe.Transcriber._write(str(root / 'pages/t/p1.json'), {'status': 'ok', 'blocks': [
            {'type': 'task', 'number': 'тест-6', 'text': 'Тестовый вопрос шесть.'},
            {'type': 'task', 'number': '4.5', 'text': 'Кейс, вопрос пять.'},
            {'type': 'task', 'number': '4.6', 'text': 'Кейс, вопрос шесть.'}]})
        transcribe.Transcriber._write(str(root / 'pages/s/p1.json'), {'status': 'ok', 'blocks': [
            {'type': 'criteria', 'number': '4.5', 'text': 'Критерии вопроса пять.'},
            {'type': 'task', 'number': '6', 'text': 'Кейс, вопрос шесть.'},
            {'type': 'solution', 'number': '6', 'text': 'Решение вопроса шесть.'}]})
        event = {'event_id': 'mosh-entrepreneurship-2014-final-10-11-v1', 'grade': '10-11',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 1}],
                 'solution_files': [{'file': 'raw/pdf/s.pdf', 'page_dir': 'pages/s', 'pages': 1}]}
        tasks, report, _ = assemble.build_event(str(root), event, str(root / 'f'), crop=False)
        by = {t.number: t for t in tasks}
        self.assertEqual(by['4.6'].solution, ['Решение вопроса шесть.'])
        self.assertEqual(by['тест-6'].solution, [])


class OverlayTests(SimpleTestCase):
    def test_25_fixed_reread_that_lost_numbers_not_applied(self):
        import json
        import os
        import shutil
        import tempfile

        from problems.olympiad_audit import triage
        root = tempfile.mkdtemp(prefix='finbiz2_ovl_')
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        base = {'page_dir': 'pages/x', 'page': 1, 'needs_eyes': True, 'blocks': [
            {'type': 'solution', 'number': str(n), 'text': f'Ответ {n}', 'answer': 'А'}
            for n in (1, 2, 3)]}
        os.makedirs(os.path.join(root, 'pages_v2', 'x'))
        patch = {'status': 'fixed', 'blocks': [{'type': 'solution', 'number': '',
                                                'text': 'Ответы 1–3 одним блоком'}]}
        with open(os.path.join(root, 'pages_v2', 'x', 'p1.json'), 'w', encoding='utf-8') as h:
            json.dump(patch, h)
        out = triage.PageOverlay(root, patches='pages_v2').apply('pages/x', 1, base)
        self.assertEqual(out['blocks'], base['blocks'])
        self.assertEqual(out['status'], triage.SKELETON_LOST)
        self.assertTrue(out['needs_eyes'])
        # Номера сохранились (тип сменился) — перечитанное применяется.
        patch['blocks'] = [{'type': 'task', 'number': str(n), 'text': f'Вопрос {n}'} for n in (1, 2, 3)]
        with open(os.path.join(root, 'pages_v2', 'x', 'p1.json'), 'w', encoding='utf-8') as h:
            json.dump(patch, h)
        out = triage.PageOverlay(root, patches='pages_v2').apply('pages/x', 1, base)
        self.assertEqual(out['blocks'], patch['blocks'])
        self.assertFalse(out['needs_eyes'])


from problems.tests.test_olympiad_triage import (FULL, HintProvider,  # noqa: E402
                                                 RunnerBase, StubProvider, page_reply,
                                                 verdict_json)


class PagesV2RunnerTests(RunnerBase):
    """Судья и перечитывание с заплатками `pages_v2` (эталон v1, финграм/бизнес)."""

    def runner(self, cls, provider):
        return cls(root=self.root, provider=provider, budget=__import__(
            'problems.olympiad_audit.transcribe', fromlist=['Budget']).Budget(1.0, 0.001),
            cost_log=self.costs, workers=1, sleep=lambda _s: None,
            plan={'pages/abc/p1': {'ярус': 'A', 'контроль': ''}}, patches='pages_v2')

    def v2patch(self):
        from problems.olympiad_audit import triage
        return triage.read_json(triage.v3_path(self.root, 'pages/abc', 1, 'pages_v2'))

    def test_27_judge_remark_is_not_ok_judge_and_goes_to_pages_v2(self):
        import os

        from problems.olympiad_audit import judge
        old = self.write_v2()
        status = self.runner(judge.JudgeRunner, StubProvider([verdict_json(['пропущена строка'])])
                             ).transcribe_page(self.job())
        self.assertEqual(status, 'needs_fix')
        self.assertEqual(self.v2patch()['status'], 'needs_fix')
        self.assertFalse(os.path.exists(os.path.join(self.root, 'pages_v3')))
        self.assert_v2_untouched(old)

    def test_28_reread_writes_pages_v2_old_json_untouched(self):
        from problems.olympiad_audit import judge
        old = self.write_v2()
        self.runner(judge.JudgeRunner, StubProvider([verdict_json(
            ['пропущены абзацы'], numbers=[('100', True, False)])])).transcribe_page(self.job())
        provider = HintProvider([page_reply(FULL), verdict_json(numbers=[])])
        status = self.runner(judge.RereadRunner, provider).transcribe_page(self.job())
        self.assertEqual(status, 'fixed')
        self.assertEqual(self.v2patch()['blocks'][0]['text'], FULL[0]['text'])
        self.assert_v2_untouched(old)
        self.assertEqual(judge.select_for_reread(['pages/abc/p1'], self.root, 'pages_v2'), [])


class AssembleSuffixOverlayTests(SimpleTestCase):
    def test_29_assemble_suffix_v2_overlay_keeps_v1(self):
        import json
        import shutil
        import tempfile
        from io import StringIO
        from pathlib import Path

        from django.core.management import call_command

        from problems.olympiad_audit import registry, transcribe
        root = Path(tempfile.mkdtemp(prefix='finbiz2_cmd_'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        audit = root / registry.get('mosh-entrepreneurship').audit_dir
        dig = audit / 'digitized'
        (audit / 'raw').mkdir(parents=True)
        transcribe.Transcriber._write(str(dig / 'pages/t/p1.json'), {'status': 'ok', 'blocks': [
            {'type': 'task', 'number': '1', 'text': 'Условие 1.'}]})
        transcribe.Transcriber._write(str(dig / 'pages_v2/t/p1.json'), {
            'status': 'fixed', 'blocks': [{'type': 'task', 'number': '1', 'text': 'Условие 1 (исправлено).'}]})
        event = {'event_id': 'mosh-entrepreneurship-2014-final-7-v1', 'grade': '7',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 1}],
                 'solution_files': [], 'criteria_files': []}
        (dig / 'events_files.jsonl').write_text(json.dumps(event, ensure_ascii=False) + '\n',
                                                encoding='utf-8')
        v1 = dig / 'reference_problems_v1.jsonl'
        v1.write_text('{"event_id": "x", "number": "1", "statement_md": "старое"}\n', encoding='utf-8')
        before = v1.read_bytes()
        call_command('olympiad_digitize', 'assemble', '--olympiad', 'mosh-entrepreneurship',
                     '--suffix', 'v2', '--overlay', '--no-crop', '--data-root', str(root),
                     stdout=StringIO())
        self.assertEqual(v1.read_bytes(), before)
        rows = [json.loads(x) for x in open(dig / 'reference_problems_v2.jsonl', encoding='utf-8')]
        self.assertEqual(rows[0]['statement_md'], 'Условие 1 (исправлено).')
        self.assertTrue((dig / 'compare_v1_v2_overlay.json').is_file())
        self.assertFalse((dig / 'figures').exists())     # вырезки v2 — не в общую figures\\
