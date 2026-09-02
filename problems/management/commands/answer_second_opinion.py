u"""
answer_second_opinion — модель отвечает на тесты ВСЛЕПУЮ, код сравнивает.

Зачем. Выборочная проверка 30 тестов SolveHub нашла ДВА неверных ответа
(#62000 и #61009). Это дефект, который портит игру молча: задача выглядит
безупречно, KaTeX рендерится, шлюз качества доволен — а игрок теряет жизнь
за верный ответ и не понимает, почему.

Как. Модели дают условие и варианты, БЕЗ ответа банка. Она возвращает свой
ответ и уверенность. Сравнение — кодом, тем же `parse_exact_number`, каким
сверяется ввод игрока. Расхождения смотрит человек.

⚠️ В БАНКЕ НИЧЕГО НЕ МЕНЯЕТСЯ. Записывается только AnswerSecondOpinion.
Ответ банка модель не переписывает даже при полной уверенности: это запрет
P0, и он здесь особенно на месте — модель ошибается на олимпиадных задачах
чаще, чем кажется.

Четыре шага, деньги тратит только второй:

    manage.py answer_second_opinion --source solvehub,aa --dry-run
    manage.py answer_second_opinion --source solvehub,aa --submit --max-cost 8
    manage.py answer_second_opinion --collect
    manage.py answer_second_opinion --apply <файл результатов>

Отчёт с расхождениями: reports/game/answer_disputes.html.
Пакет для ревьюера: `answer_dispute_export`.
"""
import io
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from problems.ai.prompts import system_blocks
from problems.models import AnswerSecondOpinion, Problem, Source

MODEL = 'claude-sonnet-5'
IN_RATE_BATCH = 1.00        # Sonnet 5 через Batch API: −50 % от $2 / $10
OUT_RATE_BATCH = 5.00
MAX_TOKENS = 400
BATCH_LIMIT = 10000
CHARS_PER_TOKEN = 2.5       # кириллица; оценка консервативная

REPORT_DIR = os.path.join('reports', 'answers')
IDS_FILE = os.path.join(REPORT_DIR, 'answer_batch_ids.txt')

SOURCE_KEYS = {
    'solvehub': 'SolveHub',
    'aa': 'Сборник тестов АА',
}

SCHEMA_HINT = (
    u'Верни СТРОГО один JSON и ничего больше:\n'
    u'{"answer": "<твой ответ>", "confidence": <0.0-1.0>}')


def user_text(question, options, qtype):
    u"""Что уходит модели: условие, варианты и форма ответа. Без ключа."""
    parts = [SCHEMA_HINT, '']
    if qtype == 'numeric':
        parts.append(u'ФОРМА ОТВЕТА: одно число. Целое («50»), десятичное с '
                     u'запятой («0,5») или дробь («1/3»). Без единиц, без '
                     u'слов, без знака равенства.')
    elif qtype == 'multi':
        parts.append(u'ФОРМА ОТВЕТА: номера ВСЕХ верных вариантов через '
                     u'запятую, нумерация с 1 («1,3»).')
    else:
        parts.append(u'ФОРМА ОТВЕТА: номер одного верного варианта, '
                     u'нумерация с 1 («2»).')
    parts.append('')
    parts.append(u'ВОПРОС:\n%s' % (question or '').strip())
    if options:
        parts.append('')
        parts.append(u'ВАРИАНТЫ:')
        for i, opt in enumerate(options, 1):
            parts.append(u'%d) %s' % (i, opt))
    return u'\n'.join(parts)


def parse_model_answer(raw, qtype, options):
    u"""Ответ модели -> сравнимая форма. None, если разобрать не вышло."""
    text = (raw or '').strip()
    if not text:
        return None
    if qtype == 'numeric':
        from game.views import parse_exact_number
        return parse_exact_number(text)
    nums = []
    for chunk in text.replace(';', ',').split(','):
        chunk = chunk.strip().rstrip(')').strip()
        if chunk.isdigit():
            n = int(chunk)
            if 1 <= n <= len(options or []):
                nums.append(n - 1)
    if not nums:
        return None
    if qtype == 'multi':
        return frozenset(nums)
    return nums[0]


def bank_answer_value(gq):
    u"""Ответ банка в той же сравнимой форме."""
    if gq.question_type == 'numeric':
        from game.views import parse_exact_number
        return parse_exact_number(gq.correct_value)
    if gq.question_type == 'multi':
        return frozenset(gq.correct_indices or [])
    return gq.correct_index


def targets(source_keys, limit=0):
    u"""Вопросы игрового пула выбранных источников (только банк, не генератор)."""
    from game.models import GameQuestion
    names = [SOURCE_KEYS[k] for k in source_keys]
    ids = []
    for name in names:
        src = Source.objects.filter(name__startswith=name).first()
        if src is None:
            raise CommandError(u'источник не найден: %s' % name)
        ids.append(src.id)
    qs = (GameQuestion.objects.filter(is_generated=False, source_id__in=ids)
          .exclude(problem__isnull=True).order_by('id'))
    rows = list(qs)
    return rows[:limit] if limit else rows


class Command(BaseCommand):
    help = u'Слепая перепроверка ответов тестов моделью (Batch API).'

    def add_arguments(self, parser):
        parser.add_argument('--source', default='solvehub,aa',
                            help=u'ключи источников через запятую')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--submit', action='store_true')
        parser.add_argument('--collect', action='store_true')
        parser.add_argument('--apply', default='')
        parser.add_argument('--max-cost', type=float, default=0.0)
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--out', default=os.path.join(
            'reports', 'game', 'answer_disputes.html'))
        parser.add_argument('--examples', type=int, default=40)

    def handle(self, *args, **options):
        if options['apply']:
            return self.do_apply(options)
        if options['collect']:
            return self.do_collect()
        keys = [k.strip() for k in options['source'].split(',') if k.strip()]
        bad = [k for k in keys if k not in SOURCE_KEYS]
        if bad:
            raise CommandError(u'неизвестные источники: %s' % bad)
        if options['submit']:
            return self.do_submit(keys, options)
        return self.do_estimate(keys, options)

    # -- смета ------------------------------------------------------------
    def build(self, keys, limit):
        system = system_blocks('answer_blind')
        rows = targets(keys, limit)
        out = []
        for gq in rows:
            out.append((gq, user_text(gq.question, gq.options,
                                      gq.question_type)))
        return system, out

    def estimate(self, system, rows):
        sys_chars = sum(len(b) for b in system)
        in_t = sum((sys_chars + len(t)) / CHARS_PER_TOKEN for _g, t in rows)
        out_t = len(rows) * 60
        cost = in_t / 1e6 * IN_RATE_BATCH + out_t / 1e6 * OUT_RATE_BATCH
        return in_t, out_t, cost

    def do_estimate(self, keys, options):
        system, rows = self.build(keys, options['limit'])
        in_t, out_t, cost = self.estimate(system, rows)
        by_type = {}
        for gq, _t in rows:
            by_type[gq.question_type] = by_type.get(gq.question_type, 0) + 1
        self.stdout.write(u'СМЕТА (ни одного обращения к API)')
        self.stdout.write(u'  источники: %s' % ', '.join(
            SOURCE_KEYS[k] for k in keys))
        self.stdout.write(u'  вопросов пула: %d' % len(rows))
        for qtype, n in sorted(by_type.items()):
            self.stdout.write(u'     %-8s %5d' % (qtype, n))
        self.stdout.write(u'  модель: %s, Batch API (−50 %%)' % MODEL)
        self.stdout.write(u'  вход  ≈ %s токенов' % '{:,}'.format(int(in_t)))
        self.stdout.write(u'  выход ≈ %s токенов' % '{:,}'.format(int(out_t)))
        self.stdout.write(self.style.WARNING(
            u'  ИТОГО ≈ $%.2f' % cost))
        sys_tokens = sum(len(b) for b in system) / CHARS_PER_TOKEN
        cached_in = in_t - sys_tokens * (len(rows) - 1) * 0.9
        self.stdout.write(
            u'  при попадании в кэш системного префикса ≈ $%.2f'
            % (cached_in / 1e6 * IN_RATE_BATCH
               + out_t / 1e6 * OUT_RATE_BATCH))
        self.stdout.write(u'Ничего не отправлено. Запуск: --submit '
                          u'--max-cost <доллары>.')

    # -- отправка ---------------------------------------------------------
    def do_submit(self, keys, options):
        system, rows = self.build(keys, options['limit'])
        _i, _o, cost = self.estimate(system, rows)
        ceiling = options['max_cost']
        if ceiling <= 0:
            raise CommandError(
                u'--submit без --max-cost запрещён: потолок расхода задаёт '
                u'человек, а не команда.')
        if cost > ceiling:
            raise CommandError(u'смета $%.2f выше потолка $%.2f'
                               % (cost, ceiling))
        import anthropic
        client = anthropic.Anthropic()
        os.makedirs(REPORT_DIR, exist_ok=True)
        for start in range(0, len(rows), BATCH_LIMIT):
            chunk = rows[start:start + BATCH_LIMIT]
            requests = [{
                'custom_id': 'q%d' % gq.id,
                'params': {
                    'model': MODEL,
                    'max_tokens': MAX_TOKENS,
                    'system': [
                        {'type': 'text', 'text': system[0],
                         'cache_control': {'type': 'ephemeral'}},
                        {'type': 'text', 'text': system[1]},
                    ],
                    'messages': [{'role': 'user', 'content': text}],
                },
            } for gq, text in chunk]
            batch = client.messages.batches.create(requests=requests)
            with io.open(IDS_FILE, 'a', encoding='utf-8') as fh:
                fh.write(batch.id + '\n')
            self.stdout.write(u'  батч %s: %d' % (batch.id, len(chunk)))
        self.stdout.write(self.style.SUCCESS(u'Отправлено. Забрать: --collect'))

    # -- сбор -------------------------------------------------------------
    def do_collect(self):
        import anthropic
        client = anthropic.Anthropic()
        if not os.path.exists(IDS_FILE):
            raise CommandError(u'нет файла с id батчей: %s' % IDS_FILE)
        with io.open(IDS_FILE, encoding='utf-8') as fh:
            batch_ids = [ln.strip() for ln in fh if ln.strip()]
        got, in_tok, out_tok, failed = {}, 0, 0, 0
        for bid in batch_ids:
            info = client.messages.batches.retrieve(bid)
            if info.processing_status != 'ended':
                self.stdout.write(u'  батч %s ещё идёт' % bid)
                continue
            for item in client.messages.batches.results(bid):
                if item.result.type != 'succeeded':
                    failed += 1
                    continue
                msg = item.result.message
                in_tok += getattr(msg.usage, 'input_tokens', 0)
                out_tok += getattr(msg.usage, 'output_tokens', 0)
                text = ''.join(b.text for b in msg.content if b.type == 'text')
                try:
                    got[int(item.custom_id[1:])] = json.loads(text)
                except (ValueError, TypeError):
                    failed += 1
        cost = in_tok / 1e6 * IN_RATE_BATCH + out_tok / 1e6 * OUT_RATE_BATCH
        os.makedirs(REPORT_DIR, exist_ok=True)
        path = os.path.join(REPORT_DIR, 'answer_results.json')
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps({'results': {str(k): v
                                             for k, v in got.items()},
                                 'usage': {'in': in_tok, 'out': out_tok,
                                           'cost': cost}},
                                ensure_ascii=False))
        self.stdout.write(u'  разобрано %d, не удалось %d' % (len(got), failed))
        self.stdout.write(self.style.SUCCESS(
            u'ФАКТИЧЕСКИЙ расход: $%.2f' % cost))
        self.stdout.write(u'Результаты: %s' % path)

    # -- запись -----------------------------------------------------------
    def do_apply(self, options):
        from game.models import GameQuestion
        with io.open(options['apply'], encoding='utf-8') as fh:
            data = json.load(fh)
        results = data['results']
        now = timezone.now()
        rows, disputes, unparsed = [], [], 0
        for qid, rec in results.items():
            gq = GameQuestion.objects.filter(pk=int(qid)).first()
            if gq is None or gq.problem_id is None:
                continue
            mine = parse_model_answer(rec.get('answer'), gq.question_type,
                                      gq.options)
            theirs = bank_answer_value(gq)
            if mine is None:
                unparsed += 1
                continue
            agrees = (mine == theirs)
            rows.append(AnswerSecondOpinion(
                problem=gq.problem, provider='anthropic', model=MODEL,
                model_answer=str(rec.get('answer') or ''),
                bank_answer=str(gq.correct_value or gq.correct_index
                                if gq.question_type != 'multi'
                                else gq.correct_indices),
                agrees=agrees,
                confidence=float(rec.get('confidence') or 0),
                created_at=now))
            if not agrees:
                disputes.append((gq, rec))
        with transaction.atomic():
            AnswerSecondOpinion.objects.bulk_create(rows, batch_size=500)

        total = len(rows)
        share = 100.0 * len(disputes) / total if total else 0
        self.stdout.write(u'  записано мнений: %d' % total)
        self.stdout.write(u'  не разобрался ответ модели: %d' % unparsed)
        self.stdout.write(u'  РАСХОЖДЕНИЙ: %d (%.1f %%)'
                          % (len(disputes), share))
        # ⚠️ Инвариант пилота: выше 15 % расхождений — промахивается МОДЕЛЬ,
        # а не банк. Смотреть тогда надо промпт, а не задачи.
        if share > 15.0:
            self.stdout.write(self.style.ERROR(
                u'  доля расхождений выше 15 %: это про промпт, а не про '
                u'банк. Разбирать задачи по такому прогону нельзя.'))
        self.write_report(options['out'], disputes, total, share,
                          options['examples'])
        self.stdout.write(u'Отчёт: %s' % options['out'])

    # -- отчёт ------------------------------------------------------------
    def write_report(self, path, disputes, total, share, examples):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)

        def esc(t):
            return (t or '').replace('&', '&amp;').replace(
                '<', '&lt;').replace('>', '&gt;')

        by_source, by_type = {}, {}
        for gq, _rec in disputes:
            by_source[gq.source_group or '?'] = by_source.get(
                gq.source_group or '?', 0) + 1
            by_type[gq.question_type] = by_type.get(gq.question_type, 0) + 1

        parts = ['<!doctype html><html lang="ru"><meta charset="utf-8">',
                 '<title>Расхождения по ответам</title>',
                 '<style>body{font:15px/1.55 system-ui,sans-serif;max-width:'
                 '980px;margin:0 auto;padding:24px}h1{font-size:23px}'
                 'table{border-collapse:collapse;width:100%;margin:10px 0}'
                 'td,th{border:1px solid #ddd;padding:6px 9px;font-size:14px;'
                 'vertical-align:top}th{background:#f4f4f4;text-align:left}'
                 '.q{color:#333}.a{font-weight:600}</style><main>']
        parts.append(u'<h1>Второе мнение по ответам: расхождения</h1>')
        parts.append(u'<p>Проверено вопросов: <b>%d</b>. Расхождений: '
                     u'<b>%d</b> (%.1f %%).</p>' % (total, len(disputes),
                                                    share))
        parts.append(u'<h2>По источникам</h2><table>')
        for key, n in sorted(by_source.items(), key=lambda kv: -kv[1]):
            parts.append(u'<tr><td>%s</td><td>%d</td></tr>' % (esc(key), n))
        parts.append('</table><h2>По типам</h2><table>')
        for key, n in sorted(by_type.items(), key=lambda kv: -kv[1]):
            parts.append(u'<tr><td>%s</td><td>%d</td></tr>' % (esc(key), n))
        parts.append('</table>')
        parts.append(u'<h2>Примеры (до %d)</h2>' % examples)
        for gq, rec in disputes[:examples]:
            parts.append(u'<table><tr><th colspan="2">#%s · %s</th></tr>'
                         % (gq.problem_id, esc(gq.question_type)))
            parts.append(u'<tr><td colspan="2" class="q">%s</td></tr>'
                         % esc(gq.question))
            if gq.options:
                parts.append(u'<tr><td colspan="2">%s</td></tr>' % esc(
                    ' | '.join('%d) %s' % (i, o)
                               for i, o in enumerate(gq.options, 1))))
            parts.append(u'<tr><td class="a">ответ банка</td><td>%s</td></tr>'
                         % esc(str(gq.correct_value or gq.correct_index)))
            parts.append(u'<tr><td class="a">ответ модели</td>'
                         u'<td>%s (уверенность %.2f)</td></tr>'
                         % (esc(str(rec.get('answer'))),
                            float(rec.get('confidence') or 0)))
            parts.append('</table>')
        parts.append('</main></html>')
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(parts))
