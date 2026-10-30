"""Проверки ночи на НАСТОЯЩЕЙ базе ночи `db_screens.sqlite3` — только чтение.

Тестовая база Django пустая, а инварианты плана (30 сезонов ВсОШ, 18 у МОШ)
живут в настоящей. Запуск:

    ./venv313/bin/python manage.py shell \
        --settings=config.settings_olympiads_screens \
        < claude/night_olymp_20261030/tools/real_db_checks.py

Печатает «проверка → прошло/провал» и итог «прошло N / всего M».
"""
from django.db import connection
from django.test.utils import CaptureQueriesContext

from olympiads import navigator as nav
from olympiads.models import Olympiad

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append(bool(ok))
    print('%s %s %s' % ('прошло' if ok else 'ПРОВАЛ', name, detail))


def grid(page, code):
    return [g for g in page['grids'] if g['code'] == code][0]


def row(g, label):
    return [r for r in g['rows'] if r['label'] == label][0]


vs = Olympiad.objects.get(slug='vseros')
with CaptureQueriesContext(connection) as ctx:
    page = nav.olympiad_page(vs)
final, reg = grid(page, 'final'), grid(page, 'reg')
check('Э1 ВсОШ заключительный: 30 сезонов с 1995/96',
      final['seasons'] == 30 and final['first_label'] == '1995/96',
      '%s с %s' % (final['seasons'], final['first_label']))
check('Э1 ВсОШ региональный: 26 сезонов с 1999/2000',
      reg['seasons'] == 26 and reg['first_label'] == '1999/2000',
      '%s с %s' % (reg['seasons'], reg['first_label']))
check('Э1 2019/20 заключительного — пустая строка', row(final, '2019/20')['empty'])
for label in ('2017/18', '2018/19'):
    cells = row(final, label)['cells']
    check('Э1 %s: «9» отдельно, «10–11» одной клеткой' % label,
          [(c['grades'], c['colspan']) for c in cells] == [([9], 1), ([10, 11], 2)])
cells = row(final, '2016/17')['cells']
check('Э1 2016/17: одна клетка на все классы без подписи',
      len(cells) == 1 and cells[0]['colspan'] == len(final['columns'])
      and cells[0]['grades_label'] == '')
cell11 = [c for c in row(final, '2025/26')['cells'] if c['grades'] == [11]][0]
tours = cell11['tours']
check('Э1 2025/26, 11 класс: два тура по 210 мин, максимум 48',
      [t['label'] for t in tours] == ['1 тур', '2 тур']
      and all(t['minutes'] == 210 and t['max_score'] == 48.0 for t in tours),
      str([(t['label'], t['minutes'], t['max_score'], t['tasks']) for t in tours]))
check('Э1 страница ВсОШ ≤ 30 SQL-запросов', len(ctx) <= 30, '%d' % len(ctx))
for slug, seasons in (('mosh', 18), ('vp', 20)):
    facts = nav.olympiad_page(Olympiad.objects.get(slug=slug))['facts']
    check('Э1 %s — %d сезонов' % (slug, seasons), facts['seasons'] == seasons,
          str(facts['seasons']))
spb = nav.olympiad_page(Olympiad.objects.get(slug='spbgu'))
check('Э1 СПбГУ — пустое состояние', spb['grids'] == [] and spb['facts']['problems'] == 0)
rows = nav.home_rows()
same = True
for r in rows:
    facts = nav.olympiad_page(r['olympiad'])['facts']
    same &= (r['seasons'], r['problems']) == (facts['seasons'], facts['problems'])
check('Э1 число на главной = число на странице у каждой олимпиады', same,
      '%d олимпиад' % len(rows))
slugs = {r['olympiad'].slug for r in rows}
check('Э1 скрытые и заглушки не в разделе',
      not slugs & {'vernadsky', 'mosh-entrepreneurship', 'mosh-fingram',
                   'finat', 'skol', 'icef-evening-school'})
not_four = sum(1 for c in final['cells'] for t in c['tours']
               if t['tour'] in ('1', '2') and t['tasks'] != 4)
total = sum(1 for c in final['cells'] for t in c['tours'] if t['tour'] in ('1', '2'))
print('справка: туров «1»/«2» заключительного ВсОШ — %d, из них не по 4 задания — %d'
      % (total, not_four))

# ── Э5: тур 2 2025/26, 11 класс, на время; задача 59997 ─────────────────────
from django.test import Client, override_settings  # noqa: E402

from olympiads.criteria import split_solution  # noqa: E402
from olympiads.models import TrainingAttempt  # noqa: E402
from problems.models import Problem  # noqa: E402

with override_settings(ALLOWED_HOSTS=['*']):
    guest = Client(HTTP_HOST='127.0.0.1')
    base = '/olympiads/vseros/variant/562/'
    guest.post(base + 'start/', {'timer': '1'})
    key = guest.session.session_key
    attempt = TrainingAttempt.objects.filter(session_key=key, user__isnull=True).latest('started_at')
    minutes = (attempt.expires_at - attempt.started_at).total_seconds() / 60
    check('Э5 ВсОШ 2025/26, 11 кл., 2 тур на время: 210 мин', abs(minutes - 210) < 0.02,
          '%.3f' % minutes)
    html = guest.get(base + 'take/').content.decode()
    reference, criteria = split_solution(Problem.objects.get(pk=59997).solution)
    lines = [ln.strip() for ln in (reference + '\n' + criteria).splitlines()
             if len(ln.strip()) > 25]
    leaked = [ln for ln in lines if ln[:50] in html]
    check('Э5 задача 59997 на странице решения', 'В мире существуют две страны' in html)
    check('Э5 до сдачи нет ни строки разбора и критериев 59997', not leaked,
          'проверено строк %d, утекло %d' % (len(lines), len(leaked)))
    attempt.delete()   # гостевая попытка проверки — не оставляем

print('ИТОГО: прошло %d / всего %d' % (sum(RESULTS), len(RESULTS)))
