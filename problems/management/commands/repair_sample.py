"""repair_sample — выборка и промпты для эксперимента «чинит ли модель по указке».

ТОЛЬКО ЧТЕНИЕ. В базу не пишет ничего.

Зачем: мы знаем, что модель плохо НАХОДИТ дефекты сама (из 482 забракованных
человеком задач чистка не тронула 332, хотя читала каждую). Теперь проверяем
другое — умеет ли она ЧИНИТЬ, когда дефект ей уже показали.

Две группы:
  ПАРНАЯ — задачи с комментарием ревьюера; каждая чинится ДВАЖДЫ:
      способ A — подсказка только категорией,
      способ B — категория плюс дословный комментарий.
  КОНТРОЛЬНАЯ — 20 задач без комментария, только способом A. Нужна, чтобы
      понять, не особенные ли прокомментированные задачи: человек мог
      комментировать именно самые тяжёлые случаи.

⚠️ ИЗОЛЯЦИЯ СПОСОБА A ОБЕСПЕЧЕНА ЗДЕСЬ, В КОДЕ. Промпт способа A собирает
`build_prompt(rec, with_comment=False)`, и комментарий в него физически не
попадает: строка с комментарием добавляется ТОЛЬКО в ветке with_comment.
Проверяется тестом-утверждением в конце сборки: если текст комментария нашёлся
в промпте способа A, команда падает.

Запуск:
    venv\\Scripts\\python manage.py repair_sample
"""

import io
import json
import os
import random
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from problems.models import Problem, ReviewVerdict
from problems.review_categories import CATEGORY_LABELS

ILE_BUNDLE = 'ile_20260721'
OUT_DIR = 'reports/repair_experiment'
PROMPT_DIR = os.path.join(OUT_DIR, 'prompts')
TRIAGE_FILE = 'reports/ile_triage/recheck_ids.txt'

SEED = 20260818
CONTROL_SIZE = 20

# Правила починки. Один текст на оба способа — разница между A и B должна быть
# ровно в наличии комментария, и больше ни в чём.
RULES = """ПРАВИЛА ПОЧИНКИ (нарушать нельзя):
1. Чини ТОЛЬКО тот дефект, на который указал человек. Всё остальное в задаче
   не трогай, даже если видишь, что можно улучшить. Иначе будет невозможно
   понять, что именно оценивает проверяющий.
2. Авторский текст неприкосновенен: слова автора, числа, знаки, единицы
   измерения. Правишь структуру (разбивка на подпункты, списки, таблицы),
   разметку формул и мусор — но не формулировки.
3. Ничего не придумывай. Если данных не хватает (например, потерян рисунок),
   так и напиши, а не восстанавливай по догадке.
4. Если чинить нечего или непонятно, в чём дефект, — так и ответь. Это
   нормальный ответ, он засчитывается.

ФОРМАТ ОТВЕТА — строгий JSON, без markdown-обёртки:
{
  "action": "fixed" | "nothing_to_fix" | "unclear",
  "explain": "<одно-два предложения: что исправлено и почему; либо почему не чинил>",
  "fields": {
     "statement": "<новый текст>",            // только изменённые поля
     "solution": "<новый текст>",
     "answer": "<новый текст>",
     "parts": [{"label": "...", "statement": "...", "answer": "..."}]
  }
}
Неизменённые поля в "fields" НЕ включай. При action != "fixed" оставь
"fields" пустым объектом."""


def read_ids(path):
    out = set()
    if not os.path.exists(path):
        return out
    with io.open(path, encoding='utf-8-sig') as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    out.add(int(line))
                except ValueError:
                    pass
    return out


def task_fields(problem):
    return {
        'statement': problem.statement or '',
        'solution': problem.solution or '',
        'answer': problem.answer or '',
        'parts': [{'label': x.label, 'statement': x.statement or '',
                   'answer': x.answer or ''}
                  for x in problem.parts.order_by('order', 'label')],
    }


def render_task(fields):
    """Текст задачи для промпта — все поля, как они лежат в базе."""
    lines = ['=== УСЛОВИЕ ===', fields['statement'] or '(пусто)']
    if fields['parts']:
        lines.append('=== ПОДПУНКТЫ ===')
        for p in fields['parts']:
            lines.append('[%s] %s' % (p['label'], p['statement'] or '(пусто)'))
            if p['answer']:
                lines.append('    ответ пункта: %s' % p['answer'])
    else:
        lines.append('=== ПОДПУНКТЫ === (нет)')
    lines.append('=== РЕШЕНИЕ ===')
    lines.append(fields['solution'] or '(пусто)')
    lines.append('=== ОТВЕТ ===')
    lines.append(fields['answer'] or '(пусто)')
    return '\n'.join(lines)


def build_prompt(rec, with_comment):
    """Промпт одной починки.

    ⚠️ Комментарий ревьюера добавляется ТОЛЬКО при with_comment=True. В ветке
    способа A его нет физически — это и есть изоляция подсказки.
    """
    cats = ', '.join(CATEGORY_LABELS.get(c, c) for c in rec['categories'])
    head = [
        'Ты чинишь отображение задачи по олимпиадной экономике в банке задач.',
        'Человек-ревьюер посмотрел на эту задачу и отметил дефект.',
        '',
        'ЧЕЛОВЕК ОТМЕТИЛ ДЕФЕКТ: %s' % cats,
    ]
    if with_comment:
        head.append('КОММЕНТАРИЙ РЕВЬЮЕРА: %s' % rec['comment'])
    head += ['', RULES, '', 'ЗАДАЧА #%d' % rec['id'], '',
             render_task(rec['before'])]
    return '\n'.join(head)


class Command(BaseCommand):
    help = ('Собрать выборку и промпты для эксперимента о починке по указке. '
            'Только чтение.')

    def say(self, line):
        try:
            self.stdout.write(line)
        except UnicodeEncodeError:
            self.stdout.write(line.encode('ascii', 'replace').decode())

    def handle(self, *args, **options):
        os.makedirs(PROMPT_DIR, exist_ok=True)
        test_ids = read_ids(TRIAGE_FILE)

        verdicts = {}
        for row in (ReviewVerdict.objects.filter(bundle=ILE_BUNDLE)
                    .order_by('problem_id', 'category')
                    .values('problem_id', 'category', 'comment')):
            rec = verdicts.setdefault(row['problem_id'],
                                      {'categories': set(), 'comment': ''})
            rec['categories'].add(row['category'])
            if row['comment'] and not rec['comment']:
                rec['comment'] = row['comment']

        defective = {pid: v for pid, v in verdicts.items()
                     if pid not in test_ids
                     and any(c != 'perfect' for c in v['categories'])}

        with_comment = sorted(pid for pid, v in defective.items() if v['comment'])
        without = sorted(pid for pid, v in defective.items() if not v['comment'])

        # Контрольная группа — по возможности с тем же распределением категорий,
        # что в парной: иначе разница между группами объяснялась бы составом,
        # а не наличием комментария.
        want = Counter()
        for pid in with_comment:
            for c in sorted(defective[pid]['categories']):
                if c != 'perfect':
                    want[c] += 1
                    break
        rnd = random.Random(SEED)
        by_cat = {}
        for pid in without:
            cat = next(c for c in sorted(defective[pid]['categories'])
                       if c != 'perfect')
            by_cat.setdefault(cat, []).append(pid)
        for lst in by_cat.values():
            rnd.shuffle(lst)

        total_want = sum(want.values())
        control = []
        for cat, n in want.most_common():
            take = round(CONTROL_SIZE * n / total_want)
            control += by_cat.get(cat, [])[:take]
        # добор до ровного размера, если округление не дало 20
        pool = [p for p in without if p not in set(control)]
        rnd.shuffle(pool)
        control = sorted(control[:CONTROL_SIZE] + pool[:max(0, CONTROL_SIZE - len(control))])

        ids = sorted(set(with_comment) | set(control))
        problems = {p.id: p for p in Problem.objects.filter(id__in=ids)
                    .prefetch_related('parts')}

        sample = []
        for pid in ids:
            p = problems.get(pid)
            if p is None:
                continue
            v = defective[pid]
            sample.append({
                'id': pid,
                'categories': sorted(c for c in v['categories'] if c != 'perfect'),
                'category_labels': [CATEGORY_LABELS.get(c, c) for c in
                                    sorted(c for c in v['categories'] if c != 'perfect')],
                'comment': v['comment'],
                'group': 'paired' if pid in set(with_comment) else 'control',
                'before': task_fields(p),
            })

        with io.open(f'{OUT_DIR}/sample.json', 'w', encoding='utf-8') as fh:
            json.dump(sample, fh, ensure_ascii=False, indent=1)

        # ── промпты ──────────────────────────────────────────────────────
        written = []
        for rec in sample:
            methods = ['A', 'B'] if rec['group'] == 'paired' else ['A']
            for m in methods:
                text = build_prompt(rec, with_comment=(m == 'B'))
                # ⚠️ Страховка: подсказка-комментарий не имеет права оказаться
                # в способе A. Проверяем СТРУКТУРНО — по метке строки: сам
                # текст комментария сверять бессмысленно, у #94 он равен одной
                # букве «с», которая есть в любом русском тексте.
                if m == 'A':
                    if 'КОММЕНТАРИЙ РЕВЬЮЕРА' in text:
                        raise CommandError(
                            'Метка комментария в промпте способа A у #%d — '
                            'эксперимент недействителен.' % rec['id'])
                    # Дословный текст сверяем только у достаточно длинных
                    # комментариев, где совпадение не может быть случайным.
                    needle = (rec['comment'] or '').strip()
                    if len(needle) >= 12 and needle in text:
                        raise CommandError(
                            'Комментарий ревьюера просочился в промпт способа A '
                            'у #%d — эксперимент недействителен.' % rec['id'])
                path = os.path.join(PROMPT_DIR, '%s_%d.txt' % (m, rec['id']))
                with io.open(path, 'w', encoding='utf-8') as fh:
                    fh.write(text)
                written.append((m, rec['id']))

        paired = [r for r in sample if r['group'] == 'paired']
        ctrl = [r for r in sample if r['group'] == 'control']
        self.say('=== ВЫБОРКА ===')
        self.say('парная (с комментарием): %d' % len(paired))
        self.say('контрольная (без комментария): %d' % len(ctrl))
        # ⚠️ Исключение оставлено ради воспроизводимости уже собранной выборки.
        # Чтение «ревьюер пробовал оболочку» ОШИБОЧНО (исправлено 2026-08-19):
        # «тест» это тип задачи. На состояние задач эти вердикты влияют.
        self.say('исключено вердиктов «тест» (ради воспроизводимости): %d'
                 % len(test_ids))
        self.say('')
        self.say('категории — парная группа:')
        for c, n in Counter(x['categories'][0] for x in paired).most_common():
            self.say('  %-18s %d' % (c, n))
        self.say('категории — контрольная группа:')
        for c, n in Counter(x['categories'][0] for x in ctrl).most_common():
            self.say('  %-18s %d' % (c, n))
        self.say('')
        self.say('промптов записано: %d (A: %d, B: %d)'
                 % (len(written),
                    sum(1 for m, _ in written if m == 'A'),
                    sum(1 for m, _ in written if m == 'B')))
        self.say('Комментарий в промптах способа A не найден ни разу '
                 '(проверено при записи).')
