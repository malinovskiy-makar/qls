"""Оцифровка зрячей моделью: расшифровка страниц и сборка эталона v2.

Поставщик — заглушка, но вызов идёт через настоящий `core.run` (тот же
путь, что у боевого прогона: терпимый разбор, расход, log=False).
Страницы, PNG и текстовый слой — выдуманные, во временной папке.
"""
import json
import os
import tempfile
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from problems.ai.providers import Reply
from problems.olympiad_audit import assemble, transcribe

PARA = [
    'Фирма-монополист продаёт товар на двух рынках с разной эластичностью спроса '
    'и может назначать на них разные цены без перепродажи между рынками.',
    'Спрос на первом рынке $Q_1 = 100 - P_1$, на втором $Q_2 = 60 - 2P_2$, '
    'предельные издержки постоянны и равны 10 рублям.',
    'Найдите цены и объёмы на каждом рынке и прибыль фирмы; объясните, кому '
    'выгодна ценовая дискриминация третьей степени.',
]
LAYER = '\n'.join(p.replace('$', '').replace('Q_1', 'Q1').replace('Q_2', 'Q2')
                  .replace('P_1', 'P1').replace('P_2', 'P2') for p in PARA)


def page_reply(blocks, **flags):
    return json.dumps({'blocks': blocks, **flags}, ensure_ascii=False)


class StubProvider:
    """Поставщик-заглушка: отдаёт ответы по очереди (последний — повторно)."""

    name = 'stub'

    def __init__(self, replies, input_tokens=1000, output_tokens=2000):
        self.replies = list(replies)
        self.calls = 0
        self.tokens = (input_tokens, output_tokens)
        self.last_images = None

    def is_available(self):
        return True

    def unavailable_reason(self):
        return ''

    def complete(self, system_blocks, user_text, schema, model, max_tokens,
                 timeout=None, images=None):
        self.calls += 1
        self.last_images = images
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return Reply(text, input_tokens=self.tokens[0], output_tokens=self.tokens[1])


def make_png(path, size=(1000, 1000), dark_box=None):
    from PIL import Image, ImageDraw
    image = Image.new('RGB', size, 'white')
    if dark_box:
        draw = ImageDraw.Draw(image)
        draw.rectangle(dark_box, fill='black')
        draw.line((dark_box[0], dark_box[3], dark_box[2], dark_box[1]), fill='white', width=5)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image.save(path)


class DigitizeBase(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def job(self, page=1, layer=LAYER, has_layer=True, eyes=False, page_dir='pages/abc'):
        png = os.path.join(self.root, page_dir, f'p{page}.png')
        make_png(png)
        return transcribe.PageJob(file='raw/pdf/t.pdf', page_dir=page_dir, page=page,
                                  pages=3, png=png, layer=layer, has_layer=has_layer,
                                  kind='tasks', olympiad_name='МОШ', eyes_sample=eyes)

    def transcriber(self, provider, max_usd=1.0, estimate=0.001, workers=1):
        self.costs = transcribe.CostLog(os.path.join(self.root, 'transcribe_cost.jsonl'))
        return transcribe.Transcriber(
            root=self.root, provider=provider,
            budget=transcribe.Budget(max_usd, estimate), cost_log=self.costs,
            workers=workers, sleep=lambda _s: None)

    def read_page(self, page=1, page_dir='pages/abc'):
        with open(os.path.join(self.root, page_dir, f'p{page}.json'), encoding='utf-8') as fh:
            return json.load(fh)


class TranscribeTests(DigitizeBase):
    def test_1_layer_ratio_catches_missing_paragraph(self):
        """Пропущен абзац — layer_ratio < 0,90 и числа не сходятся; полная
        расшифровка — ≥ 0,90 и числа сходятся. Слой не уходит в модель."""
        full = [{'type': 'task', 'number': '1', 'text': '\n\n'.join(PARA)}]
        short = [{'type': 'task', 'number': '1', 'text': '\n\n'.join(PARA[::2])}]
        ok = transcribe.layer_metrics(transcribe.clean_blocks(full), LAYER)
        bad = transcribe.layer_metrics(transcribe.clean_blocks(short), LAYER)
        self.assertGreaterEqual(ok[0], 0.90)
        self.assertTrue(ok[1])
        self.assertLess(bad[0], 0.90)
        self.assertFalse(bad[1])
        self.assertIn('100', bad[2])
        # Расшифровка с пропуском → повтор → вторая попытка полная → ok.
        provider = StubProvider([page_reply(short), page_reply(full)])
        status = self.transcriber(provider).transcribe_page(self.job())
        page = self.read_page()
        self.assertEqual((status, provider.calls, page['retries'], page['numbers_ok']),
                         ('ok', 2, 1, True))
        self.assertEqual(provider.last_images[0][0], 'image/png')

    def test_2_parse_failure_keeps_cost(self):
        """Сбой формата: страница — ошибка (докачка повторит), но расход
        вызова записан в журнал денег."""
        provider = StubProvider(['это не JSON вовсе'])
        status = self.transcriber(provider).transcribe_page(self.job(has_layer=False))
        self.assertEqual(status, 'error')
        with open(self.costs.path, encoding='utf-8') as fh:
            records = [json.loads(line) for line in fh]
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]['parse_error'])
        self.assertGreater(records[0]['cost_usd'], 0)
        self.assertFalse(transcribe.page_done(os.path.join(self.root, 'pages/abc/p1.json')))

    def test_3_max_usd_stops_run(self):
        """Потолок денег: новые страницы не стартуют, если следующая могла
        бы его превысить; прогон останавливается с причиной."""
        full = [{'type': 'task', 'number': '1', 'text': '\n\n'.join(PARA)}]
        provider = StubProvider([page_reply(full)])     # ≈ $0,00115 за вызов
        runner = self.transcriber(provider, max_usd=0.0025, estimate=0.001)
        runner.run([self.job(page=n) for n in range(1, 6)])
        self.assertEqual(provider.calls, 2)
        self.assertIn('потолок', runner.stopped)
        self.assertLessEqual(runner.budget.spent, 0.0025)

    def test_4_resume_skips_done_pages(self):
        """Готовая страница (ok / needs_eyes) модель не вызывает; ошибочная —
        вызывает снова."""
        jobs = [self.job(page=n) for n in (1, 2, 3)]
        for job, status in zip(jobs, ('ok', 'needs_eyes', 'error')):
            transcribe.Transcriber._write(job.out_path(self.root), {'status': status})
        todo = transcribe.todo(jobs, self.root)
        self.assertEqual([j.page for j in todo], [3])

    def test_5_scan_sample_and_judge(self):
        """Скан: выборочная страница — на глаза; страница с таблицей идёт к
        судье, и замечание судьи ставит needs_eyes."""
        blocks = [{'type': 'task', 'number': '2', 'text': '| a | b |\n|---|---|\n| 1 | 2 |'}]
        judge = json.dumps({'ok': False, 'issues': [{'kind': 'искажение', 'where': 'таблица',
                                                     'detail': '2 вместо 3'}]},
                           ensure_ascii=False)
        provider = StubProvider([page_reply(blocks, has_table=True), judge])
        self.transcriber(provider).transcribe_page(self.job(has_layer=False, layer=''))
        page = self.read_page()
        self.assertEqual((page['status'], provider.calls), ('needs_eyes', 2))
        self.assertIn('судья нашёл расхождения', page['needs_eyes_reasons'])

    def test_6_no_db_write_on_provider_failure(self):
        """Отказ поставщика при log=False: без подмены core.run пишет строку
        AiUsageLog (известный дефект), с подменой — нет; прогон `run()`
        включает подмену. Вызов — в главном потоке: строка из рабочего
        потока ушла бы в другое соединение и тест бы её не увидел."""
        from problems.ai import core
        from problems.ai.providers import ProviderError
        from problems.models import AiUsageLog

        class Failing(StubProvider):
            def complete(self, *args, **kwargs):
                self.calls += 1
                raise ProviderError('сеть упала')

        runner = self.transcriber(Failing(['']))
        job = self.job()

        def failing_call():
            with self.assertRaises(core.AiUnavailable):
                runner._call(job, 'система', 'текст', {}, 'page', transcribe.PROFILE)

        before = AiUsageLog.objects.count()
        failing_call()
        self.assertEqual(AiUsageLog.objects.count(), before + 1)   # дефект core.run
        with transcribe.no_db_usage_log():
            failing_call()
        self.assertEqual(AiUsageLog.objects.count(), before + 1)
        with mock.patch.object(transcribe, 'no_db_usage_log',
                               wraps=transcribe.no_db_usage_log) as guard:
            runner.run([job])
        guard.assert_called_once()
        self.assertEqual(runner.stats['error'], 1)


class AssembleTests(DigitizeBase):
    def write_page(self, page_dir, page, blocks, **extra):
        transcribe.Transcriber._write(
            os.path.join(self.root, page_dir, f'p{page}.json'),
            {'status': 'ok', 'blocks': blocks, 'layer_ratio': 0.97, 'numbers_ok': True,
             'retries': 0, 'needs_eyes': False, **extra})

    def event(self, task_pages=2, solution_pages=1):
        return {'event_id': 'mosh-2020-final-9-v1', 'year': 2020, 'stage': 'final',
                'grade': '9',
                'task_files': [{'file': 'raw/pdf/tasks.pdf', 'page_dir': 'pages/t',
                                'pages': task_pages}],
                'solution_files': [{'file': 'raw/pdf/ans.pdf', 'page_dir': 'pages/s',
                                    'pages': solution_pages}]}

    def test_7_continuation_across_pages(self):
        """Продолжение без номера на следующей странице дописывается к
        заданию, с которого страница началась."""
        self.write_page('pages/t', 1, [
            {'type': 'task', 'number': '1', 'title': 'Налоги', 'points': 10, 'text': 'Начало.'},
            {'type': 'task', 'number': '2', 'title': 'Рынок', 'text': 'Условие 2, начало.'}])
        self.write_page('pages/t', 2, [
            {'type': 'footer'}, {'type': 'task_continuation', 'text': 'Условие 2, конец.'}])
        self.write_page('pages/s', 1, [])
        tasks, report, _missing = assemble.build_event(self.root, self.event(), 'figs', crop=False)
        by_no = {t.number: t for t in tasks}
        self.assertEqual(len(tasks), 2)
        self.assertEqual(by_no['2'].statement, ['Условие 2, начало.', 'Условие 2, конец.'])
        self.assertEqual(report['склеено продолжений'], 1)

    def test_8_figure_crop_and_empty_flag(self):
        """Рамка в долях 0..1000 расширяется на 2 % и обрезается по краям
        страницы; пустая (белая) вырезка получает флаг."""
        png = os.path.join(self.root, 'page.png')
        make_png(png, dark_box=(100, 100, 300, 300))
        out = os.path.join(self.root, 'fig.png')
        self.assertEqual(assemble.crop_figure(png, [100, 100, 300, 300], out), '')
        from PIL import Image
        with Image.open(out) as image:
            self.assertEqual(image.size, (240, 240))
        self.assertEqual(assemble.crop_figure(png, [0, 990, 1000, 1000],
                                              os.path.join(self.root, 'edge.png')), 'пустая вырезка')
        self.assertEqual(assemble.crop_figure(png, [600, 600, 900, 900],
                                              os.path.join(self.root, 'w.png')), 'пустая вырезка')
        self.assertEqual(assemble.crop_figure(png, None, out), 'нет рамки')

    def test_9_solution_matched_by_number_and_title(self):
        """Решение с номером ложится на задание с этим номером, без номера
        — по названию (≥ 0,85), неизвестное — в список несопоставленных."""
        self.write_page('pages/t', 1, [
            {'type': 'task', 'number': '1', 'title': 'Налоги на сигареты', 'text': 'У1'},
            {'type': 'task', 'number': '2', 'title': 'Рынок яблок', 'text': 'У2'}])
        self.write_page('pages/t', 2, [])
        self.write_page('pages/s', 1, [
            {'type': 'solution', 'number': 'Задача 2.', 'text': 'Р2', 'answer': 'P = 5'},
            {'type': 'solution', 'title': 'Налоги на сигареты!', 'text': 'Р1'},
            {'type': 'criteria', 'number': '7', 'text': 'К7'}])
        tasks, report, _ = assemble.build_event(self.root, self.event(), 'figs', crop=False)
        by_no = {t.number: t for t in tasks}
        self.assertEqual((by_no['2'].solution, by_no['2'].answer), (['Р2'], 'P = 5'))
        self.assertEqual(by_no['1'].solution, ['Р1'])
        self.assertEqual(report['solution: сопоставлено по номеру'], 1)
        self.assertEqual(report['solution: сопоставлено по названию'], 1)
        self.assertEqual(report['criteria: не сопоставлено'], 1)

    def test_9c_preamble_fragments_subparts_and_solution_figure(self):
        """Безномерной «задание» до первого — вступление комплекта, после —
        кусок текущего задания; «1.1» из файла решений ложится на задание 1;
        рисунок сразу за повторённым условием — рисунок условия задания без
        своих рисунков, внутри решения — рисунок решения."""
        self.write_page('pages/t', 1, [
            {'type': 'task', 'title': 'Время выполнения 90 минут', 'text': 'Правила.'},
            {'type': 'task', 'number': '1', 'text': 'Условие 1.'},
            {'type': 'task', 'number': 'г', 'text': '(г) Ещё вопрос.'}])
        self.write_page('pages/t', 2, [])
        self.write_page('pages/s', 1, [
            {'type': 'task', 'number': '1', 'text': 'Условие 1.'},
            {'type': 'figure', 'number': '1', 'bbox': [0, 0, 500, 500]},
            {'type': 'solution', 'number': '1.1', 'text': 'Решение пункта 1.1'},
            {'type': 'figure', 'bbox': [0, 500, 500, 1000]}])
        event = self.event()
        tasks, report, _ = assemble.build_event(self.root, event, 'figs', crop=False)
        self.assertEqual([t.number for t in tasks], ['1'])
        task = tasks[0]
        self.assertEqual(task.statement, ['Условие 1.', '(г) Ещё вопрос.'])
        self.assertEqual(event['preamble'], ['Правила.'])
        self.assertEqual(task.solution, ['Решение пункта 1.1'])
        self.assertEqual((len(task.figures), len(task.solution_figures)), (1, 1))

    def test_9d_mixed_file_once_and_solution_only_task(self):
        """Смешанный файл (и условия, и решения) читается один раз —
        решение не задваивается; блок «решение» с номером без задания
        заводит задание с пустым условием (на глаза)."""
        self.write_page('pages/t', 1, [
            {'type': 'task', 'number': '1', 'text': 'Условие 1.'},
            {'type': 'solution', 'number': '1', 'text': 'Решение 1.'},
            {'type': 'solution', 'number': '2', 'title': 'Репетиторы', 'text': 'Всё вместе.'}])
        self.write_page('pages/t', 2, [])
        event = self.event()
        event['solution_files'] = event['task_files']
        tasks, _report, _ = assemble.build_event(self.root, event, 'figs', crop=False)
        by_no = {t.number: t for t in tasks}
        self.assertEqual(by_no['1'].solution, ['Решение 1.'])
        self.assertEqual((by_no['2'].statement, by_no['2'].solution, by_no['2'].title),
                         ([], ['Всё вместе.'], 'Репетиторы'))
        record = assemble.task_record(by_no['2'], event, 'm')
        self.assertTrue(record['needs_eyes'])

    def test_9e_shared_answers_file_by_grade(self):
        """Общий файл ответов на 5–6 классы («5.1», «6.1»): в комплекте 5
        класса «5.1» ложится на задачу 1, «6.1» — мимо (другой комплект);
        в своём файле «6.3» — по-прежнему пункт задания 6."""
        self.write_page('pages/t', 1, [{'type': 'task', 'number': '1', 'text': 'У1'}])
        self.write_page('pages/t', 2, [])
        self.write_page('pages/s', 1, [
            {'type': 'solution', 'number': '5.1', 'text': 'Р5.1'},
            {'type': 'solution', 'number': '6.1', 'text': 'Р6.1'}])
        event = dict(self.event(), grade='5')
        tasks, report, _ = assemble.build_event(self.root, event, 'figs', crop=False,
                                                shared={'pages/s'})
        self.assertEqual(tasks[0].solution, ['Р5.1'])
        self.assertEqual(report['номер другого класса общего файла — мимо'], 1)
        block = {'type': 'solution', 'number': '6.3'}
        self.assertEqual(assemble._own_grade_number(block, {10}), None)  # только общий файл
        tasks, report, _ = assemble.build_event(self.root, dict(self.event(), grade='5'),
                                                'figs', crop=False)
        self.assertEqual(report['номер другого класса общего файла — мимо'], 0)

    def test_9f_solutions_only_event(self):
        """Условий у комплекта нет (финал 2017/18): решения с номером
        заводят задания с пустым условием, на глаза."""
        self.write_page('pages/s', 1, [
            {'type': 'solution', 'number': '1', 'title': 'Нефтяная республика', 'text': 'Р1'},
            {'type': 'criteria', 'number': '1', 'text': 'К1'}])
        event = dict(self.event(), task_files=[])
        tasks, _report, _ = assemble.build_event(self.root, event, 'figs', crop=False)
        self.assertEqual([(t.number, t.title, t.solution, t.criteria) for t in tasks],
                         [('1', 'Нефтяная республика', ['Р1'], ['К1'])])
        self.assertTrue(assemble.task_record(tasks[0], event, 'm')['needs_eyes'])

    def test_9b_test_answer_from_answers_file(self):
        """Файл ответов повторяет вопрос теста (блок task) с отмеченным
        ответом: ответ ложится на задание с тем же номером И вариантом."""
        self.write_page('pages/t', 1, [
            {'type': 'task', 'number': '2', 'task_variant': '1', 'text': 'Вопрос, вариант 1'},
            {'type': 'task', 'number': '2', 'task_variant': '3', 'text': 'Вопрос, вариант 3'}])
        self.write_page('pages/t', 2, [])
        self.write_page('pages/s', 1, [
            {'type': 'task', 'number': '2', 'task_variant': '3', 'text': 'Вопрос, вариант 3',
             'answer': '48 рублям'}])
        tasks, _report, _ = assemble.build_event(self.root, self.event(), 'figs', crop=False)
        answers = {(t.number, t.task_variant): t.answer for t in tasks}
        self.assertEqual(answers, {('2', '1'): '', ('2', '3'): '48 рублям'})


class CommandTests(DigitizeBase):
    def test_10_plan_without_yes_makes_no_calls(self):
        """transcribe без --yes — только план, ноль вызовов; без --max-usd и
        без --olympiad — отказ."""
        audit = os.path.join(self.root, 'audit_mosh_20261009', 'digitized')
        os.makedirs(os.path.join(self.root, 'audit_mosh_20261009', 'raw'))
        page_dir = os.path.join(audit, 'pages', 'abc')
        make_png(os.path.join(page_dir, 'p1.png'))
        with open(os.path.join(page_dir, 'p1.txt'), 'w', encoding='utf-8') as fh:
            fh.write(LAYER)
        with open(os.path.join(audit, 'inventory.jsonl'), 'w', encoding='utf-8') as fh:
            fh.write(json.dumps({'file': 'raw/pdf/t.pdf', 'kind': 'tasks', 'digitize': True,
                                 'duplicate_of': '', 'page_dir': 'pages/abc', 'pages': 1,
                                 'event_ids': ['mosh-2020-final-9-v1']}) + '\n')
        provider = StubProvider([page_reply([{'type': 'task', 'number': '1',
                                              'text': '\n\n'.join(PARA)}])])
        with mock.patch.object(transcribe, 'make_provider', return_value=provider):
            out = StringIO()
            call_command('olympiad_digitize', 'transcribe', olympiad='mosh',
                         data_root=self.root, max_usd=1, stdout=out)
            self.assertEqual(provider.calls, 0)
            self.assertIn('ПЛАН', out.getvalue())
            with self.assertRaises(CommandError):
                call_command('olympiad_digitize', 'transcribe', olympiad='mosh',
                             data_root=self.root, yes=True)
            with self.assertRaises(CommandError):
                call_command('olympiad_digitize', 'transcribe', data_root=self.root,
                             max_usd=1, yes=True)
            self.assertEqual(provider.calls, 0)
            call_command('olympiad_digitize', 'transcribe', olympiad='mosh',
                         data_root=self.root, max_usd=1, yes=True, stdout=StringIO())
            self.assertEqual(provider.calls, 1)


class LayerArtifactTests(SimpleTestCase):
    def test_12_footer_with_page_number_and_power(self):
        """Колонтитул с меняющимся номером страницы — колонтитул; степень,
        склеенная в слое с основанием («452» = 45²), — не пропуск, если
        модель записала `45^2`; настоящий пропуск числа ловится."""
        footer = 'Олимпиада «Высшая проба» 2019, 2 этап {}'
        layers = [f'Текст страницы {n}\n' + footer.format(n) for n in (12, 13, 14)]
        footers = transcribe.repeated_lines(layers)
        layer = PARA[0] + '\nБлагосостояние SW = 452 / 2 при цене 17.\n' + footer.format(14)
        good = [{'type': 'solution',
                 'text': PARA[0] + '\nБлагосостояние $SW = 45^2/2$ при цене 17.'}]
        lost = [{'type': 'solution',
                 'text': PARA[0] + '\nБлагосостояние $SW = 45^2/2$ при цене.'}]
        ok = transcribe.layer_metrics(transcribe.clean_blocks(good), layer, footers, 14)
        bad = transcribe.layer_metrics(transcribe.clean_blocks(lost), layer, footers, 14)
        # Шапка задания у верха страницы («Задача 3 (20 баллов)» на каждой
        # странице) — не колонтитул: номера страницы в ней нет.
        heads = [f'Задача {n} (20 баллов)\nТекст {n}' for n in (1, 2, 3)]
        body = transcribe.layer_body(heads[2], transcribe.repeated_lines(heads), page=7)
        self.assertIn('Задача 3 (20 баллов)', body)
        self.assertEqual((ok[1], ok[2]), (True, []))
        self.assertEqual(bad[2], ['17'])


class ParseTests(SimpleTestCase):
    def test_11_tolerant_parse(self):
        """Обрамление ```, массив вместо объекта, мусор — всё без исключений."""
        self.assertEqual(transcribe.tolerant_parse('```json\n{"blocks": []}\n```'),
                         {'blocks': []})
        self.assertEqual(transcribe.tolerant_parse('[{"type": "task"}]')['blocks'][0]['type'],
                         'task')
        self.assertIn('_parse_error', transcribe.tolerant_parse('ничего'))
        self.assertEqual(transcribe.tolerant_parse('Вот ответ: {"blocks": [1]} спасибо')['blocks'],
                         [1])
