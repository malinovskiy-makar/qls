# -*- coding: utf-8 -*-
"""Фаза 2 разведки дедупа — источники и сигналы полноты. Только чтение."""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

from django.db.models import Count  # noqa: E402
from problems.models import Problem  # noqa: E402

OUT = pathlib.Path('reports/dedup_recon_20260911')
OUT.mkdir(parents=True, exist_ok=True)
lines = []


def p(s=''):
    lines.append(str(s))


def pct(num, den):
    return 0.0 if not den else 100.0 * num / den


# Источник задачи — ПЕРВАЯ привязка SourceReference по id.
first_src = {}
for pid, sname in (Problem.objects.filter(source_references__isnull=False)
                   .values_list('id', 'source_references__source__name')
                   .order_by('id', 'source_references__id')):
    first_src.setdefault(pid, sname)

fields = ('id', 'status', 'human_review', 'hidden_pending_review', 'content_status',
          'solution', 'content_format', 'answer_consistency', 'answer', 'text_quality')
rows = []
for r in Problem.objects.values(*fields).iterator(chunk_size=5000):
    r['source'] = first_src.get(r['id'], '(без источника)')
    rows.append(r)

with_parts = dict(Problem.objects.annotate(n=Count('parts')).filter(n__gt=0)
                  .values_list('id', 'n'))
with_files = set(Problem.objects.filter(files__isnull=False)
                 .values_list('id', flat=True).distinct())
with_figs = set(Problem.objects.filter(figures__isnull=False)
                .values_list('id', flat=True).distinct())
with_topics = set(Problem.objects.filter(topics__isnull=False)
                  .values_list('id', flat=True).distinct())
with_tags = set(Problem.objects.filter(tags__isnull=False)
                .values_list('id', flat=True).distinct())
with_feat = set(Problem.objects.filter(features_rel__isnull=False)
                .values_list('id', flat=True).distinct())
with_conc = set(Problem.objects.filter(econ_concepts__isnull=False)
                .values_list('id', flat=True).distinct())

by_src = {}
for r in rows:
    by_src.setdefault(r['source'], []).append(r)
order = sorted(by_src.items(), key=lambda kv: -len(kv[1]))

p('# Фаза 2 — источники: объём, ревью, видимость')
p()
p('Источник задачи = ПЕРВАЯ привязка SourceReference (по id). Задачи с')
p('несколькими привязками к разным источникам это огрубляет.')
p()
hdr = ('%-42s %6s %6s %6s %6s %6s %6s | %9s %7s %7s | %9s' %
       ('источник', 'всего', 'publ', 'dup', 'draft', 'hidd', 'arch',
        'approved', 'defect', 'не см.', 'скрыт*'))
p(hdr)
p('-' * len(hdr))
for name, rs in order:
    n = len(rs)
    st = {}
    for r in rs:
        st[r['status']] = st.get(r['status'], 0) + 1
    ap = sum(1 for r in rs if r['human_review'] == 'approved')
    de = sum(1 for r in rs if r['human_review'] == 'defect')
    hp = sum(1 for r in rs if r['hidden_pending_review'])
    p('%-42.42s %6d %6d %6d %6d %6d %6d | %5d %3.0f%% %7d %7d | %5d %3.0f%%' % (
        name, n, st.get('published', 0), st.get('duplicate', 0), st.get('draft', 0),
        st.get('hidden', 0), st.get('archived', 0),
        ap, pct(ap, n), de, n - ap - de, hp, pct(hp, n)))
p()
p('* скрыт = hidden_pending_review=True (человек ещё не смотрел)')

p()
p('# Фаза 2.3 — сигналы полноты по источникам (доли в процентах)')
p()
hdr2 = ('%-42s %6s %7s %7s %7s %7s %7s %7s %7s %7s' %
        ('источник', 'всего', 'solut.', 'ответ', 'части', 'картин', 'темы',
         'теги', 'особ.', 'понят.'))
p(hdr2)
p('-' * len(hdr2))
for name, rs in order:
    n = len(rs)
    ids = [r['id'] for r in rs]
    sol = sum(1 for r in rs if (r['solution'] or '').strip())
    ans = sum(1 for r in rs if (r['answer'] or '').strip())
    par = sum(1 for i in ids if i in with_parts)
    pic = sum(1 for i in ids if i in with_files or i in with_figs)
    top = sum(1 for i in ids if i in with_topics)
    tag = sum(1 for i in ids if i in with_tags)
    fea = sum(1 for i in ids if i in with_feat)
    con = sum(1 for i in ids if i in with_conc)
    p('%-42.42s %6d %6.0f%% %6.0f%% %6.0f%% %6.0f%% %6.0f%% %6.0f%% %6.0f%% %6.0f%%' % (
        name, n, pct(sol, n), pct(ans, n), pct(par, n), pct(pic, n),
        pct(top, n), pct(tag, n), pct(fea, n), pct(con, n)))
p()
p('задач с подпунктами всего: %d; среднее число частей у них: %.2f'
  % (len(with_parts), (sum(with_parts.values()) / len(with_parts)) if with_parts else 0))

p()
p('# Фаза 2.4 — состояние текста, формат, согласованность ответа')
p()
hdr3 = ('%-42s %6s %6s %7s %6s | %-26s | %-26s' %
        ('источник', 'всего', 'ok', 'needfix', 'junk', 'content_format',
         'answer_consistency'))
p(hdr3)
p('-' * len(hdr3))
for name, rs in order:
    n = len(rs)
    cs = {}
    fmt = {}
    ac = {}
    for r in rs:
        cs[r['content_status']] = cs.get(r['content_status'], 0) + 1
        k = r['content_format'] or '-'
        fmt[k] = fmt.get(k, 0) + 1
        k2 = r['answer_consistency'] or '-'
        ac[k2] = ac.get(k2, 0) + 1
    fmt_s = ' '.join('%s:%d' % kv for kv in sorted(fmt.items(), key=lambda kv: -kv[1])[:3])
    ac_s = ' '.join('%s:%d' % kv for kv in sorted(ac.items(), key=lambda kv: -kv[1])[:3])
    p('%-42.42s %6d %5.0f%% %6.0f%% %5.0f%% | %-26.26s | %-26.26s' % (
        name, n, pct(cs.get('ok', 0), n), pct(cs.get('needs_fix', 0), n),
        pct(cs.get('junk', 0), n), fmt_s, ac_s))

p()
p('# Фаза 2.5 — сводная «источник x approved x полнота»')
p()
p('Балл полноты = среднее пяти долей: solution, ответ, темы, теги, понятия.')
p('Отсортировано по доле approved, затем по полноте.')
p()
hdr4 = '%-42s %6s %10s %9s %9s %10s' % ('источник', 'всего', 'approved%',
                                        'defect%', 'полнота', 'ok-текст%')
p(hdr4)
p('-' * len(hdr4))
summary = []
for name, rs in order:
    n = len(rs)
    ids = [r['id'] for r in rs]
    sol = pct(sum(1 for r in rs if (r['solution'] or '').strip()), n)
    ans = pct(sum(1 for r in rs if (r['answer'] or '').strip()), n)
    top = pct(sum(1 for i in ids if i in with_topics), n)
    tag = pct(sum(1 for i in ids if i in with_tags), n)
    con = pct(sum(1 for i in ids if i in with_conc), n)
    ap = pct(sum(1 for r in rs if r['human_review'] == 'approved'), n)
    de = pct(sum(1 for r in rs if r['human_review'] == 'defect'), n)
    okt = pct(sum(1 for r in rs if r['content_status'] == 'ok'), n)
    summary.append((name, n, ap, de, (sol + ans + top + tag + con) / 5, okt))
for name, n, ap, de, full, okt in sorted(summary, key=lambda t: (-t[2], -t[4])):
    p('%-42.42s %6d %9.1f%% %8.1f%% %9.1f %9.1f%%' % (name, n, ap, de, full, okt))

path = OUT / 'phase2_sources.md'
path.write_text('\n'.join(lines), encoding='utf-8')
print('written: %s' % path)
