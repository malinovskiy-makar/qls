"""repair_wave1_input — вход первой волны починки (Сборник АА). ТОЛЬКО ЧТЕНИЕ.

Схема волны: человек пометил дефект -> модель чинит -> человек смотрит
результат и говорит, получилось или нет. Здесь готовится ВХОД: 131 задача
пакета `aa_20260728`, у которых `human_review = defect`.

Формат `sample.json` намеренно совпадает с форматом эксперимента
(reports/repair_experiment/sample.json): его читают repair_gate и оболочка
разбора, второй структуры под то же самое не заводим.

⚠️ Комментарий ревьюера идёт в подсказку ВСЕГДА. Эксперимент 18.08 сравнивал
подсказку с комментарием и без него; здесь сравнивать нечего — это боевой
прогон, и всё, что человек написал, обязано дойти до модели.

Запуск:
    venv\\Scripts\\python manage.py repair_wave1_input
    venv\\Scripts\\python manage.py repair_wave1_input --batch-size 25
"""

import io
import json
import os
from collections import Counter

from django.core.management.base import BaseCommand

from problems.models import Problem, ReviewVerdict
from problems.review_categories import CATEGORY_LABELS

BUNDLE = 'aa_20260728'
OUT_DIR = os.path.join('reports', 'repair_wave1')
BATCH_DIR = os.path.join(OUT_DIR, 'batches')

# Правила починки. Ровно те же, что в эксперименте 18.08 (repair_sample.RULES),
# плюс требование объяснить правку словами: по объяснению владелец видит,
# поняла модель задачу или нет, и оно попадает к нему на экран.
RULES = """ПРАВИЛА ПОЧИНКИ (нарушать нельзя):
1. Чини ТОЛЬКО тот дефект, на который указал человек. Всё остальное в задаче
   не трогай, даже если видишь, что можно улучшить. Иначе будет невозможно
   понять, что именно оценивает проверяющий.
2. Авторский текст неприкосновенен: слова автора, числа, знаки, единицы
   измерения. Правишь структуру (разбивка на подпункты, списки, таблицы),
   разметку формул и мусор — но не формулировки.
3. Ничего не придумывай. Если данных не хватает (например, потерян рисунок
   или в базе нет вариантов ответа), так и напиши, а не восстанавливай по
   догадке.
4. Если чинить нечего или непонятно, в чём дефект, — так и ответь. Это
   нормальный ответ, он засчитывается и считается отдельно.
5. Объяснение обязательно и всегда своими словами: что именно ты нашла,
   что исправила и почему. Его читает человек, а не машина.

ФОРМАТ ОТВЕТА — строгий JSON, без markdown-обёртки:
{
  "id": <номер задачи>,
  "method": "W1",
  "action": "fixed" | "nothing_to_fix" | "unclear",
  "explain": "<что нашла, что исправила и почему; либо почему не чинила>",
  "fields": {
     "statement": "<новый текст>",            // только изменённые поля
     "solution": "<новый текст>",
     "answer": "<новый текст>",
     "parts": [{"label": "...", "statement": "...", "answer": "..."}]
  }
}
Неизменённые поля в "fields" НЕ включай. При action != "fixed" оставь
"fields" пустым объектом. Список "parts" при правке подпунктов отдавай
ЦЕЛИКОМ (все подпункты задачи, а не только тронутые) — он замещает прежний."""


def task_fields(problem, parts):
    return {
        'statement': problem.statement or '',
        'solution': problem.solution or '',
        'answer': problem.answer or '',
        'parts': [{'label': x.label, 'statement': x.statement or '',
                   'answer': x.answer or ''} for x in parts],
    }


class Command(BaseCommand):
    help = ('Готовит вход первой волны починки по Сборнику АА '
            '(reports/repair_wave1). Только чтение.')

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=25)

    def say(self, line):
        try:
            self.stdout.write(line)
        except UnicodeEncodeError:
            self.stdout.write(line.encode('ascii', 'replace').decode())

    def handle(self, *args, **opts):
        os.makedirs(BATCH_DIR, exist_ok=True)

        verdicts = {}
        for row in (ReviewVerdict.objects.filter(bundle=BUNDLE)
                    .order_by('problem_id', 'category')
                    .values('problem_id', 'category', 'comment')):
            rec = verdicts.setdefault(row['problem_id'],
                                      {'categories': set(), 'comment': ''})
            rec['categories'].add(row['category'])
            if row['comment'] and not rec['comment']:
                rec['comment'] = row['comment']

        # Берём ровно то, что человек забраковал, и сверяемся с меткой в базе:
        # human_review проставлен по тем же вердиктам, расхождение означало бы
        # рассинхрон и должно быть названо вслух, а не проглочено.
        by_verdict = {pid for pid, v in verdicts.items()
                      if any(c != 'perfect' for c in v['categories'])}
        by_mark = set(Problem.objects
                      .filter(id__in=list(verdicts),
                              human_review=Problem.HumanReview.DEFECT)
                      .values_list('id', flat=True))
        if by_verdict != by_mark:
            self.say('⚠️ Вердикты и метка human_review расходятся: '
                     'только в вердиктах %d, только в метке %d'
                     % (len(by_verdict - by_mark), len(by_mark - by_verdict)))
        ids = sorted(by_verdict & by_mark)

        problems = {p.id: p for p in Problem.objects.filter(id__in=ids)
                    .prefetch_related('parts')}

        sample = []
        for pid in ids:
            p = problems.get(pid)
            if p is None:
                continue
            parts = sorted(p.parts.all(), key=lambda x: (x.order, x.pk))
            v = verdicts[pid]
            cats = sorted(c for c in v['categories'] if c != 'perfect')
            sample.append({
                'id': pid,
                'categories': cats,
                'category_labels': [CATEGORY_LABELS.get(c, c) for c in cats],
                'comment': v['comment'],
                'problem_type': p.problem_type or '',
                'before': task_fields(p, parts),
            })

        with io.open(os.path.join(OUT_DIR, 'sample.json'), 'w',
                     encoding='utf-8') as fh:
            json.dump(sample, fh, ensure_ascii=False, indent=1)

        size = opts['batch_size']
        batches = [sample[i:i + size] for i in range(0, len(sample), size)]
        for n, part in enumerate(batches, 1):
            doc = {
                'batch': n,
                'of': len(batches),
                'rules': RULES,
                'tasks': part,
            }
            with io.open(os.path.join(BATCH_DIR, 'batch_%d.json' % n), 'w',
                         encoding='utf-8') as fh:
                json.dump(doc, fh, ensure_ascii=False, indent=1)

        chars = sum(len(r['before']['statement']) + len(r['before']['solution'])
                    + len(r['before']['answer'])
                    + sum(len(x['statement']) + len(x['answer'])
                          for x in r['before']['parts'])
                    for r in sample)

        self.say('=== ВХОД ПЕРВОЙ ВОЛНЫ (%s) ===' % BUNDLE)
        self.say('задач с браком: %d' % len(sample))
        self.say('из них с комментарием человека: %d'
                 % sum(1 for r in sample if r['comment']))
        self.say('подпунктов: %d'
                 % sum(len(r['before']['parts']) for r in sample))
        self.say('символов во всех полях: %d' % chars)
        self.say('')
        self.say('категории (по задачам, комбинациями):')
        for combo, n in Counter(tuple(r['categories'])
                                for r in sample).most_common():
            self.say('  %-40s %d' % (' + '.join(combo), n))
        self.say('')
        self.say('партий: %d по %d -> %s' % (len(batches), size, BATCH_DIR))
