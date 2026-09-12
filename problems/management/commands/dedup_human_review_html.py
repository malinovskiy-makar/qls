# -*- coding: utf-8 -*-
"""dedup_human_review_html — страница ручной разметки групп копий.

ТОЛЬКО ЧТЕНИЕ. Собирает самодостаточный HTML: стратифицированная выборка
групп `DupMark`, в каждой — все версии задачи, отрисованные РОВНО КАК В
КАТАЛОГЕ (`render_markdown`, картинки из `ProblemFigure`). Человек
выбирает фаворита цифрой, ответы копятся в `localStorage` и выгружаются
одним JSON. Приёмщик — `import_dup_human_choices`.

Паттерн повторяет `repair_review_shell` / `export_review_bundle`, а не
выдуман заново: file:// без сети, KaTeX вшит, горячие клавиши, выгрузка
JSON, отдельная команда-приёмщик. Так работает вся ручная разметка
проекта, и так с ней уже умеет работать ревьюер.

⚠️ РАЗМЕТКА СЛЕПАЯ, И ЭТО СМЫСЛ ЗАТЕИ. На экране НЕ показывается ни
правило алгоритма (`DupMark.rule`), ни его фаворит (`is_best`), ни
`human_review`, ни балл полноты, ни источник — всё это входит в
закодированное правило приоритета, и, увидев его, человек размечал бы не
задачи, а согласие с машиной. Мера «алгоритм против владельца» тогда
не измеряла бы ничего. Порядок версий внутри группы и порядок самих
групп перемешан тем же seed.

Запуск:
    manage.py dedup_human_review_html                       # 120 групп
    manage.py dedup_human_review_html --count 150 --seed 7
    manage.py dedup_human_review_html --output путь.html
"""
import base64
import io
import json
import os
import random
import re

from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter.tikz_render import MARKER_RE
from problems.dedup import CONFIDENT_RULES, REASON_TAGS
from problems.models import DupMark, Problem, ProblemFigure, ProblemPart
from problems.rendering import render_markdown

#: Слои выборки и сколько групп берём из каждого при `--count 120`.
#: Доли, а не абсолютные числа: `--count` масштабирует их целиком.
#:
#: Зачем именно эти пять. «Уверенные» дают меру согласия алгоритма и
#: человека там, где машина уже решила сама. «На разбор» — там, где
#: сигнал нужнее всего, машина спасовала. Правила картинки и пустого
#: ответа — единственные закодированные исключения из приоритета
#: approved, и их стоит проверить отдельно: совпадает ли интуиция
#: владельца с тем, что уже написано в коде. Группы 3+ участников
#: (607 штук) ведут себя не как пары и в выборку попадают намеренно.
STRATA = (
    ('confident', 'уверенные по алгоритму', 0.33),
    ('needs_review', 'ушли на разбор человеку', 0.37),
    ('picture_rule', 'сработало правило картинки', 0.10),
    ('answer_rule', 'сработало правило пустого ответа', 0.10),
    ('multi', 'группы из трёх и более версий', 0.10),
)

DEFAULT_OUTPUT = os.path.join('reports', 'dedup_human', 'dedup_review.html')

#: KaTeX берём ИЗ САЙТА (`static/vendor/`), а не из пакета ревью.
#: `repair_gate.katex_head()` читает `reports/review_bundles/ile_20260721/…`,
#: которого в репозитории нет, и молча отдаёт пустую строку — формулы тогда
#: остались бы на странице долларами. Заодно версия совпадает с той, что
#: видит ученик.
KATEX_DIR = os.path.join('static', 'vendor', 'katex-0.16.9')


def katex_head():
    """KaTeX со шрифтами, вшитый в страницу: file:// и без сети."""
    try:
        css = io.open(os.path.join(KATEX_DIR, 'katex.min.css'),
                      encoding='utf-8').read()
        js = io.open(os.path.join(KATEX_DIR, 'katex.min.js'),
                     encoding='utf-8').read()
        auto = io.open(os.path.join(KATEX_DIR, 'contrib', 'auto-render.min.js'),
                       encoding='utf-8').read()
    except OSError:
        return ''

    def font(match):
        path = os.path.join(KATEX_DIR, 'fonts', match.group(1))
        if not os.path.exists(path):
            return match.group(0)
        data = base64.b64encode(open(path, 'rb').read()).decode('ascii')
        return 'url(data:font/woff2;base64,%s)' % data

    css = re.sub(r'url\(fonts/([A-Za-z0-9_\-]+\.woff2)\)', font, css)
    # Запасные ttf/woff выброшены: браузер их и не спросит, а вес страницы
    # без них втрое меньше.
    css = re.sub(r",\s*url\(fonts/[^)]+\)\s*format\(['\"](?:woff|truetype)['\"]\)",
                 '', css)
    return ('<style>%s</style><script>%s</script><script>%s</script>'
            % (css, js, auto))


# ── Сбор данных ─────────────────────────────────────────────────────────

def _stratum_of(rule, size):
    """Слой группы. Порядок проверок важен: правила картинки и ответа
    специфичнее, чем общее «ушли на разбор», и забирают группу себе."""
    if rule == DupMark.Rule.APPROVED_PICTURE_REVIEW:
        return 'picture_rule'
    if rule == DupMark.Rule.APPROVED_ANSWER_REVIEW:
        return 'answer_rule'
    if size >= 3:
        return 'multi'
    if rule in CONFIDENT_RULES:
        return 'confident'
    return 'needs_review'


def collect_groups():
    """{группа: {'rule': …, 'ids': [id, …]}} по всей таблице DupMark."""
    groups = {}
    for group, rule, pid in (DupMark.objects
                             .order_by('group', 'problem_id')
                             .values_list('group', 'rule', 'problem_id')):
        entry = groups.setdefault(group, {'rule': rule, 'ids': []})
        entry['ids'].append(pid)
    return groups


def sample_groups(groups, count, seed):
    """Стратифицированная выборка. Недобор в слое переливается в следующий:
    пустой слой не должен молча уменьшать общий объём разметки."""
    rng = random.Random(seed)
    pools = {key: [] for key, _label, _share in STRATA}
    for group, entry in groups.items():
        pools[_stratum_of(entry['rule'], len(entry['ids']))].append(group)
    for pool in pools.values():
        pool.sort()
        rng.shuffle(pool)

    chosen, taken, debt = [], {}, 0
    for key, _label, share in STRATA:
        want = int(round(count * share)) + debt
        take = pools[key][:want]
        taken[key] = len(take)
        debt = want - len(take)
        chosen.extend(take)

    # Долив. Слой мог оказаться пустым (или меньше своей доли) — тогда объём
    # разметки добирается из тех слоёв, где ещё есть группы. Без долива
    # `--count 120` на перекошенной таблице молча превращался бы в 80.
    if len(chosen) < count:
        for key, _label, _share in STRATA:
            while len(chosen) < count and taken[key] < len(pools[key]):
                chosen.append(pools[key][taken[key]])
                taken[key] += 1

    rng.shuffle(chosen)
    return chosen


def _figure_src(figure):
    """Картинка как data:-адрес — страница обязана открываться с file://."""
    if figure.svg:
        raw = figure.svg.encode('utf-8')
        return 'data:image/svg+xml;base64,' + base64.b64encode(raw).decode('ascii')
    if figure.image_data:
        kind = figure.content_type or 'image/png'
        raw = bytes(figure.image_data)
        return 'data:%s;base64,%s' % (kind, base64.b64encode(raw).decode('ascii'))
    return ''


def render_field(text, figures):
    """Поле задачи → HTML ровно как в каталоге, но с вшитыми картинками.

    `render_markdown` тот же самый, что на сайте; отличается только
    последний шаг: вместо адреса `catalog:problem_figure_svg` подставляется
    data:-адрес, иначе на file:// не было бы видно ни одной картинки.
    Поиск ограничен картинками ЭТОЙ задачи — свойство безопасности
    `problems/figures.py` сохранено (см. ADR 0031).
    """
    html = render_markdown(text)
    if not html or '[[FIGURE:' not in html:
        return html or ''

    def repl(match):
        figure = figures.get(match.group(1))
        if figure is None:
            return ''
        src = _figure_src(figure)
        if not src:
            return ''
        return ('<img src="%s" alt="График к задаче" class="qls-figure">' % src)

    return MARKER_RE.sub(repl, html)


def build_version(problem, figures, parts):
    """Одна версия задачи для страницы. Ни одного поля, входящего в
    закодированное правило приоритета: ни `human_review`, ни источника,
    ни балла полноты — см. предупреждение в шапке модуля."""
    return {
        'id': problem.pk,
        'title': render_field(problem.title, figures),
        'statement': render_field(problem.statement, figures),
        'answer': render_field(problem.answer, figures),
        'solution': render_field(problem.solution, figures),
        'parts': [
            {'label': part.label or '',
             'statement': render_field(part.statement, figures),
             'answer': render_field(part.answer, figures)}
            for part in parts
        ],
    }


def build_cards(group_names, groups, rng):
    """Карточки групп. Порядок версий внутри группы перемешан — иначе
    первым всегда стоял бы меньший id, а это сам по себе сигнал."""
    all_ids = sorted({pid for g in group_names for pid in groups[g]['ids']})
    problems = Problem.objects.in_bulk(all_ids)

    figures_by_problem = {}
    for figure in ProblemFigure.objects.filter(problem_id__in=all_ids):
        figures_by_problem.setdefault(figure.problem_id, {})[figure.tikz_hash] = figure

    parts_by_problem = {}
    for part in ProblemPart.objects.filter(problem_id__in=all_ids).order_by('problem_id', 'order'):
        parts_by_problem.setdefault(part.problem_id, []).append(part)

    cards = []
    for group in group_names:
        ids = [pid for pid in groups[group]['ids'] if pid in problems]
        if len(ids) < 2:
            # Группа осталась без пары: задачу удалили после разметки.
            # Выбирать не из чего — на страницу такая группа не идёт.
            continue
        rng.shuffle(ids)
        cards.append({
            'group': group,
            'versions': [build_version(problems[pid],
                                       figures_by_problem.get(pid, {}),
                                       parts_by_problem.get(pid, []))
                         for pid in ids],
        })
    return cards


# ── Страница ────────────────────────────────────────────────────────────

PAGE_CSS = """
:root{--ink:#2c2925;--muted:#6f675d;--line:#ded7cb;--bg:#f6f3ec;--card:#fffdf8;
--pick:#1f7a6a;--warn:#a8552f;}
*{box-sizing:border-box}
body{margin:0;padding:0 0 120px;background:var(--bg);color:var(--ink);
font:16px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif}
.qls-wrap{max-width:1180px;margin:0 auto;padding:24px 20px}
h1{font-size:22px;margin:0 0 6px}
.qls-lead{color:var(--muted);font-size:14px;margin:0 0 22px;max-width:70ch}
.qls-group{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:18px 18px 14px;margin:0 0 22px}
.qls-group.qls-done{opacity:.55}
.qls-ghead{display:flex;align-items:baseline;gap:12px;margin:0 0 14px;
padding-bottom:10px;border-bottom:1px solid var(--line)}
.qls-gnum{font-weight:600}
.qls-gkey{color:var(--muted);font-size:12px;font-family:ui-monospace,monospace}
.qls-versions{display:grid;gap:14px}
.qls-v{border:1px solid var(--line);border-radius:8px;padding:12px 14px;background:#fff}
.qls-v.qls-picked{border-color:var(--pick);box-shadow:inset 0 0 0 1px var(--pick)}
.qls-vhead{display:flex;align-items:center;gap:10px;margin:0 0 8px}
.qls-key{display:inline-flex;width:26px;height:26px;align-items:center;
justify-content:center;border:1px solid var(--line);border-radius:6px;
font-weight:600;font-size:13px;background:var(--bg)}
.qls-vid{color:var(--muted);font-size:12px;font-family:ui-monospace,monospace}
.qls-title{font-weight:600;margin:0 0 6px}
.qls-lbl{color:var(--muted);font-size:11px;letter-spacing:.06em;
text-transform:uppercase;margin:10px 0 2px}
.qls-part{margin:6px 0 0;padding-left:12px;border-left:2px solid var(--line)}
.qls-figure{max-width:100%;height:auto;display:block;margin:8px 0}
.qls-actions{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 0}
button{font:inherit;padding:6px 12px;border:1px solid var(--line);border-radius:6px;
background:#fff;cursor:pointer}
button:hover{border-color:var(--ink)}
button.qls-on{background:var(--pick);border-color:var(--pick);color:#fff}
button.qls-esc.qls-on{background:var(--warn);border-color:var(--warn)}
.qls-reasons{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 0}
.qls-reasons button{font-size:13px;padding:4px 10px}
.qls-note{width:100%;margin:8px 0 0;padding:6px 8px;border:1px solid var(--line);
border-radius:6px;font:inherit;min-height:32px}
.qls-bar{position:fixed;left:0;right:0;bottom:0;background:var(--card);
border-top:1px solid var(--line);padding:10px 20px;display:flex;gap:14px;
align-items:center;font-size:14px}
.qls-bar .qls-sp{flex:1}
table{border-collapse:collapse}
td,th{border:1px solid var(--line);padding:3px 7px}
"""

PAGE_JS = r"""
var KEY = 'qls-dedup-' + WSEED;
var state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { state = {}; }

function save() {
  try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
  refresh();
}

function entry(group) {
  if (!state[group]) state[group] = {verdict: null, chosen: null, reasons: [], note: ''};
  return state[group];
}

function pick(group, pid) {
  var e = entry(group);
  if (e.verdict === 'chosen' && e.chosen === pid) { e.verdict = null; e.chosen = null; }
  else { e.verdict = 'chosen'; e.chosen = pid; }
  paint(group); save();
}

function escape_(group, verdict) {
  var e = entry(group);
  if (e.verdict === verdict) { e.verdict = null; }
  else { e.verdict = verdict; e.chosen = null; }
  paint(group); save();
}

function reason(group, tag) {
  var e = entry(group);
  var i = e.reasons.indexOf(tag);
  if (i < 0) e.reasons.push(tag); else e.reasons.splice(i, 1);
  paint(group); save();
}

function note(group, text) { entry(group).note = text; save(); }

function paint(group) {
  var e = state[group] || {};
  var box = document.querySelector('[data-group="' + group + '"]');
  if (!box) return;
  box.classList.toggle('qls-done', !!e.verdict);
  box.querySelectorAll('[data-pid]').forEach(function (el) {
    el.classList.toggle('qls-picked',
      e.verdict === 'chosen' && String(e.chosen) === el.dataset.pid);
  });
  box.querySelectorAll('[data-verdict]').forEach(function (el) {
    el.classList.toggle('qls-on', e.verdict === el.dataset.verdict);
  });
  box.querySelectorAll('[data-reason]').forEach(function (el) {
    el.classList.toggle('qls-on', (e.reasons || []).indexOf(el.dataset.reason) >= 0);
  });
  var area = box.querySelector('textarea');
  if (area && area.value !== (e.note || '')) area.value = e.note || '';
}

function refresh() {
  var done = 0, chosen = 0, hard = 0, notdup = 0;
  GROUPS.forEach(function (g) {
    var e = state[g];
    if (!e || !e.verdict) return;
    done++;
    if (e.verdict === 'chosen') chosen++;
    else if (e.verdict === 'cannot_decide') hard++;
    else notdup++;
  });
  document.getElementById('qls-count').textContent =
    'размечено ' + done + ' из ' + GROUPS.length +
    '  ·  выбран фаворит ' + chosen + '  ·  не могу решить ' + hard +
    '  ·  не дубли ' + notdup;
}

function download() {
  var rows = [];
  GROUPS.forEach(function (g) {
    var e = state[g];
    if (!e || !e.verdict) return;
    rows.push({group: g, verdict: e.verdict, chosen_problem_id: e.chosen,
               reason_tags: e.reasons || [], note: e.note || ''});
  });
  var blob = new Blob([JSON.stringify({seed: WSEED, rows: rows}, null, 1)],
                      {type: 'application/json'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'dedup_human_' + WSEED + '.json';
  a.click();
}

/* Горячие клавиши работают по группе, ближайшей к середине экрана: так
   «1» означает то, что человек сейчас читает, и рука не уходит с цифр. */
function activeGroup() {
  var best = null, bestDist = 1e9, mid = window.innerHeight / 2;
  document.querySelectorAll('[data-group]').forEach(function (box) {
    var r = box.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight) return;
    var d = Math.abs((r.top + r.bottom) / 2 - mid);
    if (d < bestDist) { bestDist = d; best = box; }
  });
  return best;
}

document.addEventListener('keydown', function (ev) {
  if (ev.target.tagName === 'TEXTAREA' || ev.metaKey || ev.ctrlKey || ev.altKey) return;
  var box = activeGroup();
  if (!box) return;
  var group = box.dataset.group;
  if (ev.key >= '1' && ev.key <= '9') {
    var els = box.querySelectorAll('[data-pid]');
    var idx = parseInt(ev.key, 10) - 1;
    if (idx < els.length) { pick(group, parseInt(els[idx].dataset.pid, 10)); ev.preventDefault(); }
  } else if (ev.key === '0') {
    escape_(group, 'cannot_decide'); ev.preventDefault();
  } else if (ev.key === '-' || ev.key === 'x') {
    escape_(group, 'not_duplicates'); ev.preventDefault();
  }
});

GROUPS.forEach(paint);
refresh();
if (window.renderMathInElement) {
  renderMathInElement(document.body, {delimiters: [
    {left: '$$', right: '$$', display: true},
    {left: '\\[', right: '\\]', display: true},
    {left: '$', right: '$', display: false},
    {left: '\\(', right: '\\)', display: false}], throwOnError: false});
}
"""


def _field_block(label, html):
    if not html:
        return ''
    return '<div class="qls-lbl">%s</div>%s' % (label, html)


def version_html(version, index):
    parts = []
    for part in version['parts']:
        body = _field_block('условие подпункта', part['statement'])
        body += _field_block('ответ подпункта', part['answer'])
        if body:
            label = part['label'] and ('<b>%s</b> ' % part['label']) or ''
            parts.append('<div class="qls-part">%s%s</div>' % (label, body))

    return (
        '<div class="qls-v" data-pid="%(id)s">'
        '<div class="qls-vhead"><span class="qls-key">%(key)s</span>'
        '<span class="qls-vid">#%(id)s</span></div>'
        '%(title)s%(statement)s%(parts)s%(answer)s%(solution)s'
        '</div>'
    ) % {
        'id': version['id'],
        'key': index + 1,
        'title': version['title'] and '<div class="qls-title">%s</div>' % version['title'] or '',
        'statement': _field_block('условие', version['statement']),
        'parts': ''.join(parts),
        'answer': _field_block('ответ', version['answer']),
        'solution': _field_block('решение', version['solution']),
    }


def card_html(card, number):
    versions = ''.join(version_html(v, i) for i, v in enumerate(card['versions']))
    keys = ' '.join('<button onclick="pick(\'%s\',%s)">%s — #%s</button>'
                    % (card['group'], v['id'], i + 1, v['id'])
                    for i, v in enumerate(card['versions']))
    reasons = ' '.join(
        '<button data-reason="%s" onclick="reason(\'%s\',\'%s\')">%s</button>'
        % (key, card['group'], key, label) for key, label in REASON_TAGS)
    return (
        '<section class="qls-group" data-group="%(group)s">'
        '<div class="qls-ghead"><span class="qls-gnum">Группа %(num)s</span>'
        '<span class="qls-gkey">%(group)s · версий: %(n)s</span></div>'
        '<div class="qls-versions">%(versions)s</div>'
        '<div class="qls-actions">%(keys)s'
        '<button class="qls-esc" data-verdict="cannot_decide" '
        'onclick="escape_(\'%(group)s\',\'cannot_decide\')">0 — не могу решить</button>'
        '<button class="qls-esc" data-verdict="not_duplicates" '
        'onclick="escape_(\'%(group)s\',\'not_duplicates\')">− — это вообще не дубли</button>'
        '</div>'
        '<div class="qls-reasons">%(reasons)s</div>'
        '<textarea class="qls-note" rows="1" placeholder="заметка, необязательно" '
        'oninput="note(\'%(group)s\',this.value)"></textarea>'
        '</section>'
    ) % {'group': card['group'], 'num': number, 'n': len(card['versions']),
         'versions': versions, 'keys': keys, 'reasons': reasons}


def build_page(cards, seed):
    groups = [c['group'] for c in cards]
    body = ''.join(card_html(c, i + 1) for i, c in enumerate(cards))
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Разметка групп копий</title>'
        + katex_head() +
        '<style>' + PAGE_CSS + '</style></head><body>'
        '<div class="qls-wrap"><h1>Разметка групп копий</h1>'
        '<p class="qls-lead">В каждой группе — версии одной и той же задачи, '
        'отрисованные так, как их увидит ученик. Выберите ту, которая должна '
        'остаться на сайте: цифрой <b>1…9</b> или кнопкой. <b>0</b> — не могу '
        'решить, <b>−</b> — это вообще не дубли. Причины и заметка '
        'необязательны. Прогресс сохраняется сам; в конце нажмите «Скачать '
        'разметку».</p>'
        + body +
        '</div><div class="qls-bar"><span id="qls-count"></span>'
        '<span class="qls-sp"></span>'
        '<button onclick="download()">Скачать разметку (JSON)</button></div>'
        '<script>var WSEED=' + json.dumps(str(seed)) + ';'
        'var GROUPS=' + json.dumps(groups, ensure_ascii=False) + ';'
        + PAGE_JS + '</script></body></html>'
    )


# ── Команда ─────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Собрать HTML ручной разметки групп копий (только чтение).'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=120,
                            help='сколько групп взять в разметку (по умолчанию 120)')
        parser.add_argument('--seed', type=int, default=20260912,
                            help='зерно выборки: тот же seed даёт ту же страницу')
        parser.add_argument('--output', default=DEFAULT_OUTPUT)

    def handle(self, *args, **options):
        count = options['count']
        seed = options['seed']
        if count < 1:
            raise CommandError('--count должен быть положительным')

        groups = collect_groups()
        if not groups:
            raise CommandError('в DupMark нет ни одной группы — '
                               'сначала прогоните dedup_apply --apply')

        names = sample_groups(groups, count, seed)
        cards = build_cards(names, groups, random.Random(seed))
        page = build_page(cards, seed)

        path = options['output']
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with io.open(path, 'w', encoding='utf-8', newline='') as handle:
            handle.write(page)

        counts = {}
        for name in names:
            key = _stratum_of(groups[name]['rule'], len(groups[name]['ids']))
            counts[key] = counts.get(key, 0) + 1

        self.stdout.write('Групп в DupMark: %s, в выборке: %s' % (len(groups), len(cards)))
        for key, label, _share in STRATA:
            self.stdout.write('  %-34s %4d' % (label, counts.get(key, 0)))
        self.stdout.write(self.style.SUCCESS('Страница: %s' % path))
