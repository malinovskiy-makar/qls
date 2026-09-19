"""P0: аудит данных для «Стола» (только чтение). Пишет таблицы в markdown на stdout."""
import json
import re
from collections import Counter
from difflib import SequenceMatcher

from django.db.models import Count

from catalog import filters, testplay
from problems.models import Hint, ProblemPart, Tag, Topic

base = filters.base_queryset('catalog')
TOTAL = base.count()
out = []
P = out.append


def norm(s):
    s = (s or '').lower().replace('ё', 'е')
    s = re.sub(r'[‒-―\-–—]', ' ', s)
    s = re.sub(r'[«»"\'“”„]', '', s)
    return ' '.join(s.split())


data = json.load(open('catalog/data/topic_map.json', encoding='utf-8'))
nodes = data['nodes']
themes = [n for n in nodes if n.get('k') == 'theme']
tags = [n for n in nodes if n.get('k') != 'theme']
canon_topics = {norm(t.name): t for t in Topic.objects.filter(is_canonical=True)}
canon_tags = {norm(t.name): t for t in Tag.objects.filter(kind='canonical')}
th_found = [n for n in themes if norm(n['l']) in canon_topics]
tg_found = [n for n in tags if norm(n['l']) in canon_tags]
tg_missing = [n['l'] for n in tags if norm(n['l']) not in canon_tags]

P('## 1. Карта ↔ справочник\n')
P('| Что | На карте | Нашли каноническую | Не нашли |\n|---|---|---|---|')
P('| темы | %d | %d | %d |' % (len(themes), len(th_found), len(themes) - len(th_found)))
P('| теги | %d | %d | %d |' % (len(tags), len(tg_found), len(tg_missing)))
if tg_missing:
    P('\nТеги карты без канонического `Tag` (%d):\n' % len(tg_missing))
    for name in tg_missing:
        P('- %s' % name)

P('\n## 2. Числа карты ↔ фильтр каталога\n')
P('| Тема | Число на карте (`c`) | В фильтре каталога | Разница |\n|---|---|---|---|')
per_topic = dict(base.values('topics').annotate(n=Count('id', distinct=True))
                 .values_list('topics', 'n'))
diffs = 0
for n in themes:
    t = canon_topics.get(norm(n['l']))
    live = per_topic.get(t.id, 0) if t else None
    if live is not None and live != n.get('c'):
        diffs += 1
    P('| %s | %s | %s | %s |' % (n['l'], n.get('c'), '—' if live is None else live,
                                  '' if live is None else (n.get('c') or 0) - live))
P('\nРасходится у %d тем из %d.' % (diffs, len(themes)))

P('\n## 3. Решения\n')
with_sol = base.exclude(solution='').exclude(solution__isnull=True)
copy_ids, retell_ids = [], []
for pk, st, so in with_sol.values_list('id', 'statement', 'solution').iterator(chunk_size=2000):
    st, so = (st or '').strip(), (so or '').strip()
    if not st or not so:
        continue
    sw, tw = set(norm(so).split()), set(norm(st).split())
    share = len(sw & tw) / max(1, len(sw))
    if share >= 0.9 and len(so) <= 1.3 * len(st):
        copy_ids.append(pk)
        continue
    head = SequenceMatcher(None, norm(so)[:200], norm(st)[:200]).ratio()
    if head >= 0.8 and len(so) > len(st):
        retell_ids.append(pk)
P('| Что | Задач |\n|---|---|')
P('| видимых в каталоге | %d |' % TOTAL)
P('| с решением | %d |' % with_sol.count())
P('| решение почти равно условию (слова ≥ 0,9, длина ≤ 1,3) | %d |' % len(copy_ids))
P('| решение начинается с пересказа условия (200 знаков ≥ 0,8) | %d |' % len(retell_ids))
P('\nПервые 50 «решение = копия условия»: %s' % ', '.join(map(str, sorted(copy_ids)[:50])))
P('\nПервые 50 «начинается с пересказа»: %s' % ', '.join(map(str, sorted(retell_ids)[:50])))
P('\n63315 в первом списке: %s; во втором: %s' % (63315 in copy_ids, 63315 in retell_ids))

P('\n## 4. Ответы\n')
ids = list(base.values_list('id', flat=True))
with_answer = base.exclude(answer='').exclude(answer__isnull=True).count()
parts_with_answer = (ProblemPart.objects.filter(problem_id__in=ids).exclude(answer='')
                     .values('problem_id').distinct().count())
P('| Что | Задач |\n|---|---|')
P('| непустой общий ответ | %d |' % with_answer)
P('| хотя бы один подпункт с ответом | %d |' % parts_with_answer)

P('\n## 5. Подсказки\n')
hint_counts = Counter(dict(Hint.objects.filter(problem_id__in=ids).values('problem_id')
                           .annotate(n=Count('id')).values_list('problem_id', 'n')).values())
P('| Подсказок у задачи | Задач |\n|---|---|')
P('| 0 | %d |' % (TOTAL - sum(hint_counts.values())))
for k in sorted(hint_counts):
    P('| %d | %d |' % (k, hint_counts[k]))

P('\n## 6. Тесты\n')
tests = [p for p in base.prefetch_related('parts') if testplay.is_test(p)]
playable = [p for p in tests if testplay.game_of(p) is not None]
why = [p for p in playable if (p.solution or '').strip() and not p.solution_needs_review]
P('| Что | Задач |\n|---|---|')
P('| тестов (`is_test`) | %d |' % len(tests))
P('| играбельных (`testplay.game_of`) | %d |' % len(playable))
P('| из них с «почему так» (решение без флага) | %d |' % len(why))

print('\n'.join(out))
