u"""
assign_topics_by_model — темы для ОСТАТКА игрового пула через Batch API.

Порядок работы, и он не случаен:
  1. `assign_topics_from_source` — темы из разметки самого источника
     (SolveHub). Бесплатно и точнее модели: это не догадка, а факт.
  2. `auto_assign_topics` — kNN по эмбеддингам. Тоже бесплатно, калибровка
     даёт точность 91,5 % при покрытии 31,5 %.
  3. Эта команда — только то, что не закрыли первые две.

⚠️ ПИШЕТ ТОЛЬКО `topics`. Тексты задачи (`statement`, `answer`, `solution`)
не трогаются вовсе — запрет P0 корневого CLAUDE.md.

⚠️ НАРУЖУ УХОДИТ ТОЛЬКО ЗАГОЛОВОК И УСЛОВИЕ ЗАДАЧИ. Ни одного поля профиля
пользователя, ни ответа, ни решения. Ответ и решение не отправляются не
из-за приватности, а по делу: тему видно по условию, а решение — это лишние
токены и лишний соблазн модели решать задачу вместо разметки.

Четыре шага, деньги тратит только второй:

    manage.py assign_topics_by_model --dry-run
        смета по ФАКТИЧЕСКИМ длинам, ни одного обращения к API

    manage.py assign_topics_by_model --submit --max-cost 5.0
        создаёт батчи; выше --max-cost не пойдёт (сравнивает со сметой)

    manage.py assign_topics_by_model --collect
        забирает результаты, считает РЕАЛЬНУЮ стоимость по usage,
        пишет превью reports/game/pool_topics_by_model.html

    manage.py assign_topics_by_model --apply <файл результатов>
        запись в базу + журнал отката
    manage.py assign_topics_by_model --revert <журнал>

Модель — Sonnet (правило проекта), через Batch API: он вдвое дешевле
обычного и на разметке 1 800 задач это разница в разы, а не в проценты.
"""
import io
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.ai.prompts import system_blocks
from problems.models import Problem, Topic
from problems.management.commands.apply_topic_mapping import CANONICAL

MODEL = 'claude-sonnet-5'
# Батч даёт −50 % к обычному тарифу Sonnet 5 ($2 вход / $10 выход за млн).
IN_RATE_BATCH = 1.00
OUT_RATE_BATCH = 5.00
MAX_TOKENS = 300           # ответ короткий: тема, до двух смежных, уверенность
BATCH_LIMIT = 10000        # потолок запросов в одном батче

REPORT_DIR = os.path.join('reports', 'topics')
IDS_FILE = os.path.join(REPORT_DIR, 'topics_batch_ids.txt')

# ⚠️ Оценка длины в ТОКЕНАХ по знакам. Кириллица токенизируется хуже
# латиницы; 2,5 знака на токен — консервативная оценка (то есть смета
# скорее завысит, чем занизит). Точное число приходит с результатами в
# `usage`, и потолок --max-cost проверяется по нему тоже.
CHARS_PER_TOKEN = 2.5

SCHEMA_HINT = (
    u'Верни СТРОГО один JSON и ничего больше:\n'
    u'{"topic_primary": "<одна тема из списка или пустая строка>", '
    u'"topics_secondary": ["<тема>", ...], "confidence": <0.0-1.0>}')


def topic_list_block():
    u"""Закрытый список тем — одинаковый для всех запросов батча."""
    return u'СПИСОК ТЕМ (другие темы не существуют):\n' + u'\n'.join(
        u'- %s' % name for name in CANONICAL)


def user_text(problem):
    u"""Пользовательская часть запроса: только заголовок и условие."""
    head = (problem.title or u'').strip()
    body = (problem.statement or u'').strip()
    parts = [topic_list_block(), '', SCHEMA_HINT, '']
    if head:
        parts.append(u'ЗАГОЛОВОК: %s' % head)
    parts.append(u'УСЛОВИЕ:\n%s' % body)
    return u'\n'.join(parts)


def pool_targets():
    u"""Задачи игрового пула, у которых после первых двух шагов нет темы."""
    from game.models import GameQuestion
    ids = set()
    for pid, topics in (GameQuestion.objects.filter(is_generated=False)
                        .values_list('problem_id', 'topics')):
        if pid and not topics:
            ids.add(pid)
    return (Problem.objects.filter(id__in=ids)
            .prefetch_related('topics').order_by('id'))


class Command(BaseCommand):
    help = u'Темы для остатка игрового пула через Batch API (Sonnet).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--submit', action='store_true')
        parser.add_argument('--collect', action='store_true')
        parser.add_argument('--apply', default='')
        parser.add_argument('--revert', default='')
        parser.add_argument('--max-cost', type=float, default=0.0,
                            help=u'потолок в долларах; без него --submit не '
                                 u'запускается')
        parser.add_argument('--limit', type=int, default=0,
                            help=u'взять только первые N задач (пилот)')
        parser.add_argument('--min-confidence', type=float, default=0.6,
                            help=u'ниже этой уверенности тему не ставим')
        parser.add_argument('--examples', type=int, default=40)

    # -- вход -------------------------------------------------------------
    def handle(self, *args, **options):
        if options['revert']:
            return self.do_revert(options['revert'])
        if options['apply']:
            return self.do_apply(options['apply'], options['min_confidence'],
                                 options['examples'])
        if options['collect']:
            return self.do_collect()
        if options['submit']:
            return self.do_submit(options)
        return self.do_estimate(options)

    # -- смета ------------------------------------------------------------
    def build_requests(self, limit):
        system = system_blocks('topic_tagging')
        rows = list(pool_targets())
        if limit:
            rows = rows[:limit]
        out = []
        for problem in rows:
            out.append((problem.id, user_text(problem)))
        return system, out

    def estimate(self, system, rows):
        sys_chars = sum(len(block) for block in system)
        in_tokens = 0
        for _pid, text in rows:
            in_tokens += (sys_chars + len(text)) / CHARS_PER_TOKEN
        out_tokens = len(rows) * 90      # ответ короткий и однотипный
        cost = (in_tokens / 1e6 * IN_RATE_BATCH
                + out_tokens / 1e6 * OUT_RATE_BATCH)
        return in_tokens, out_tokens, cost

    def do_estimate(self, options):
        system, rows = self.build_requests(options['limit'])
        in_t, out_t, cost = self.estimate(system, rows)
        self.stdout.write(u'СМЕТА (ни одного обращения к API)')
        self.stdout.write(u'  задач без темы в пуле: %d' % len(rows))
        self.stdout.write(u'  модель: %s, Batch API (−50 %%)' % MODEL)
        self.stdout.write(u'  вход  ≈ %s токенов' % '{:,}'.format(int(in_t)))
        self.stdout.write(u'  выход ≈ %s токенов' % '{:,}'.format(int(out_t)))
        self.stdout.write(self.style.WARNING(
            u'  ИТОГО ≈ $%.2f (вход $%.2f + выход $%.2f)'
            % (cost, in_t / 1e6 * IN_RATE_BATCH,
               out_t / 1e6 * OUT_RATE_BATCH)))
        sys_tokens = sum(len(b) for b in system) / CHARS_PER_TOKEN
        cached_in = (in_t - sys_tokens * (len(rows) - 1)
                     + sys_tokens * (len(rows) - 1) * 0.1)
        cached = (cached_in / 1e6 * IN_RATE_BATCH
                  + out_t / 1e6 * OUT_RATE_BATCH)
        self.stdout.write(
            u'  системная часть одна на все запросы (%d знаков ≈ %d токенов) '
            u'и стоит первой — это кэшируемый префикс'
            % (sum(len(b) for b in system), sys_tokens))
        self.stdout.write(
            u'  при попадании в кэш вышло бы ≈ $%.2f; смета выше '
            u'КОНСЕРВАТИВНА и кэш не учитывает' % cached)
        self.stdout.write(u'Ничего не отправлено. Для запуска: --submit '
                          u'--max-cost <доллары>.')

    # -- отправка ---------------------------------------------------------
    def do_submit(self, options):
        system, rows = self.build_requests(options['limit'])
        _in_t, _out_t, cost = self.estimate(system, rows)
        ceiling = options['max_cost']
        if ceiling <= 0:
            raise CommandError(
                u'--submit без --max-cost запрещён: потолок расхода задаёт '
                u'человек, а не команда.')
        if cost > ceiling:
            raise CommandError(
                u'смета $%.2f выше потолка $%.2f — не отправляю'
                % (cost, ceiling))

        import anthropic
        client = anthropic.Anthropic()
        os.makedirs(REPORT_DIR, exist_ok=True)

        ids = []
        for start in range(0, len(rows), BATCH_LIMIT):
            chunk = rows[start:start + BATCH_LIMIT]
            requests = [{
                'custom_id': 'p%d' % pid,
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
            } for pid, text in chunk]
            batch = client.messages.batches.create(requests=requests)
            ids.append(batch.id)
            with io.open(IDS_FILE, 'a', encoding='utf-8') as fh:
                fh.write(batch.id + '\n')
            self.stdout.write(u'  батч %s: %d запросов'
                              % (batch.id, len(chunk)))
        self.stdout.write(self.style.SUCCESS(
            u'Отправлено батчей: %d. Забрать: --collect' % len(ids)))

    # -- сбор -------------------------------------------------------------
    def do_collect(self):
        import anthropic
        client = anthropic.Anthropic()
        if not os.path.exists(IDS_FILE):
            raise CommandError(u'нет файла с id батчей: %s' % IDS_FILE)
        with io.open(IDS_FILE, encoding='utf-8') as fh:
            batch_ids = [line.strip() for line in fh if line.strip()]

        got, in_tok, out_tok, failed = {}, 0, 0, 0
        for bid in batch_ids:
            info = client.messages.batches.retrieve(bid)
            if info.processing_status != 'ended':
                self.stdout.write(u'  батч %s ещё идёт (%s)'
                                  % (bid, info.processing_status))
                continue
            for item in client.messages.batches.results(bid):
                if item.result.type != 'succeeded':
                    failed += 1
                    continue
                msg = item.result.message
                in_tok += getattr(msg.usage, 'input_tokens', 0)
                out_tok += getattr(msg.usage, 'output_tokens', 0)
                text = ''.join(b.text for b in msg.content
                               if b.type == 'text')
                try:
                    got[int(item.custom_id[1:])] = json.loads(text)
                except (ValueError, TypeError):
                    failed += 1

        cost = in_tok / 1e6 * IN_RATE_BATCH + out_tok / 1e6 * OUT_RATE_BATCH
        os.makedirs(REPORT_DIR, exist_ok=True)
        path = os.path.join(REPORT_DIR, 'topics_model_results.json')
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps({'results': {str(k): v
                                             for k, v in got.items()},
                                 'usage': {'in': in_tok, 'out': out_tok,
                                           'cost': cost}},
                                ensure_ascii=False))
        self.stdout.write(u'  разобрано: %d, не удалось: %d' % (len(got),
                                                                failed))
        self.stdout.write(self.style.SUCCESS(
            u'ФАКТИЧЕСКИЙ расход: $%.2f (вход %s, выход %s токенов)'
            % (cost, '{:,}'.format(in_tok), '{:,}'.format(out_tok))))
        self.stdout.write(u'Результаты: %s' % path)

    # -- запись -----------------------------------------------------------
    def do_apply(self, path, min_conf, examples):
        with io.open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        results = data['results']
        canon = set(CANONICAL)
        plan, low, bad = {}, 0, 0
        for pid, rec in results.items():
            conf = float(rec.get('confidence') or 0)
            names = []
            primary = (rec.get('topic_primary') or '').strip()
            if primary:
                names.append(primary)
            for extra in (rec.get('topics_secondary') or [])[:2]:
                extra = (extra or '').strip()
                if extra and extra not in names:
                    names.append(extra)
            names = [n for n in names if n in canon]
            if len(names) != len([n for n in ([primary] + list(
                    rec.get('topics_secondary') or [])[:2]) if n]):
                bad += 1
            if not names:
                continue
            if conf < min_conf:
                low += 1
                continue
            plan[int(pid)] = names

        self.stdout.write(u'  ответов: %d' % len(results))
        self.stdout.write(u'  ниже порога уверенности %.2f: %d'
                          % (min_conf, low))
        self.stdout.write(u'  тем вне канона отброшено у задач: %d' % bad)
        self.stdout.write(u'  получат тему: %d' % len(plan))

        topics = {t.name: t for t in Topic.objects.filter(
            name__in={n for names in plan.values() for n in names})}
        missing = sorted({n for names in plan.values() for n in names}
                         - set(topics))
        if missing:
            raise CommandError(u'нет таких тем в базе: %s' % missing)

        added = 0
        with transaction.atomic():
            for pid, names in plan.items():
                problem = Problem.objects.filter(pk=pid).first()
                if not problem:
                    continue
                have = {t.name for t in problem.topics.all()}
                for name in names:
                    if name in have:
                        continue
                    problem.topics.add(topics[name])
                    added += 1
        os.makedirs(REPORT_DIR, exist_ok=True)
        log_path = os.path.join(REPORT_DIR, 'applied_model_%d.json' % added)
        with io.open(log_path, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps({'added': {str(k): v
                                           for k, v in plan.items()}},
                                ensure_ascii=False))
        self.stdout.write(self.style.SUCCESS(
            u'Записано связей: %d. Журнал отката: %s' % (added, log_path)))

    def do_revert(self, path):
        with io.open(path, encoding='utf-8') as fh:
            log = json.load(fh)
        names = {n for pairs in log['added'].values() for n in pairs}
        topics = {t.name: t for t in Topic.objects.filter(name__in=names)}
        undone = 0
        with transaction.atomic():
            for pid, pairs in log['added'].items():
                problem = Problem.objects.filter(pk=int(pid)).first()
                if not problem:
                    continue
                for name in pairs:
                    topic = topics.get(name)
                    if topic:
                        problem.topics.remove(topic)
                        undone += 1
        self.stdout.write(self.style.SUCCESS(
            u'Откат: снято связей %d' % undone))
