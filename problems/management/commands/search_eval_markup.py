# -*- coding: utf-8 -*-
"""`search_eval_markup` — страница разметки топ-20 для владельца (С14).

ТОЛЬКО ЧИТАЕТ БАЗУ. Результат — самодостаточный HTML-файл, который
открывается двойным щелчком, без сервера и без интернета.

## Зачем

Набор C сейчас знает про каждый запрос ровно один правильный ответ — ту
задачу, которую владелец указал ссылкой. Этого хватает для recall@K и MRR@10,
но nDCG@10 при этом ЗАНИЖЕН: задача, которая преподавателя вполне устроила
бы, но не является исходной, засчитывается промахом.

Полная методология требует разметить топ-20 на «подходит / сойдёт / мимо».
Это 2–3 часа времени владельца, и делать их прямо сейчас необязательно —
но инструмент должен лежать готовым, иначе разметка не случится никогда.
Двадцать минут на десять запросов, можно в несколько заходов.

## Как пользоваться

1. `manage.py search_eval_markup --set C`
2. Открыть полученный файл в браузере, размечать переключателями.
   Выбор сохраняется в браузере сам — вкладку можно закрыть и вернуться.
3. Кнопка «Показать разметку» внизу выводит готовый JSON: скопировать его
   в файл и передать в работу.

Запуск:
    manage.py search_eval_markup --set C
    manage.py search_eval_markup --set C --top 20 --out путь.html
"""
import html
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from django.core.management.base import BaseCommand, CommandError

from problems.eval_sets import DATA_DIR, load_eval_set
from problems.management.commands.search_eval import (
    _кодировщик_модели,
    _нормализовать,
    построить_индекс,
)
from problems.models import Problem

ШАБЛОН = """<!doctype html>
<meta charset="utf-8">
<title>Разметка поиска — набор {имя}</title>
<style>
 body{{font:16px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;max-width:60rem;
      margin:0 auto;padding:2rem 1.25rem;color:#1a1a1a;background:#fbfbfa}}
 h1{{font-size:1.5rem;margin:0 0 .25rem}}
 .lead{{color:#555;margin:0 0 2rem}}
 .q{{background:#fff;border:1px solid #e3e3e0;border-radius:.5rem;
     padding:1.25rem;margin:0 0 1.5rem}}
 .qt{{font-weight:600;font-size:1.05rem;margin:0 0 .25rem}}
 .qm{{color:#777;font-size:.85rem;margin:0 0 1rem}}
 .hit{{border-top:1px solid #eee;padding:.7rem 0;display:grid;
       grid-template-columns:3.5rem 1fr 13rem;gap:.75rem;align-items:start}}
 .rank{{color:#999;font-variant-numeric:tabular-nums;font-size:.85rem}}
 .txt{{font-size:.9rem;color:#333}}
 .txt a{{color:#1a5fb4;text-decoration:none;font-weight:600}}
 .target{{background:#eefaf0}}
 .badge{{background:#2e7d32;color:#fff;border-radius:.25rem;padding:0 .35rem;
         font-size:.7rem;vertical-align:.1rem}}
 label{{font-size:.8rem;margin-right:.5rem;white-space:nowrap;cursor:pointer}}
 #out{{width:100%;height:14rem;font-family:ui-monospace,monospace;font-size:.75rem}}
 button{{font-size:1rem;padding:.5rem 1rem;border-radius:.4rem;
         border:1px solid #bbb;background:#fff;cursor:pointer}}
</style>
<h1>Разметка выдачи поиска — набор {имя}</h1>
<p class="lead">{запросов} запросов, топ-{топ} по каждому. Срез: <b>{срез}</b>
 ({индекс} задач). Зелёным отмечена задача, которую вы указали ссылкой.<br>
 Отмечайте: <b>подходит</b> — дал бы ученику; <b>сойдёт</b> — про то же, но
 не то, что искал; <b>мимо</b> — не по теме. Выбор сохраняется сам.</p>
{тело}
<p><button onclick="показать()">Показать разметку</button></p>
<textarea id="out" placeholder="Здесь появится JSON с вашей разметкой"></textarea>
<script>
const КЛЮЧ = 'search_eval_markup_{имя}';
const состояние = JSON.parse(localStorage.getItem(КЛЮЧ) || '{{}}');
document.querySelectorAll('input[type=radio]').forEach(r => {{
  if (состояние[r.name] === r.value) r.checked = true;
  r.addEventListener('change', () => {{
    состояние[r.name] = r.value;
    localStorage.setItem(КЛЮЧ, JSON.stringify(состояние));
  }});
}});
function показать() {{
  document.getElementById('out').value = JSON.stringify(состояние, null, 1);
}}
</script>
"""


class Command(BaseCommand):
    help = ('Собрать HTML-страницу для ручной разметки топ-20 выдачи поиска '
            '(read-only).')

    def add_arguments(self, parser):
        parser.add_argument('--set', default='C',
                            help='Буква набора или путь к JSON.')
        parser.add_argument('--top', type=int, default=20,
                            help='Сколько результатов показывать (по умолч. 20).')
        parser.add_argument('--scope', default='prod', choices=['prod', 'all'],
                            help='Срез индекса (по умолчанию prod — как на сайте).')
        parser.add_argument('--out', default=None, help='Куда записать HTML.')

    def handle(self, *args, **options):
        путь_набора = (DATA_DIR / f'eval_set_{options["set"].lower()}.json'
                       if len(options['set']) == 1 else Path(options['set']))
        if not путь_набора.exists():
            raise CommandError(f'Набор не найден: {путь_набора}')
        мета, случаи = load_eval_set(путь_набора)
        if мета.get('mode') != 'text':
            raise CommandError(
                'Размечать имеет смысл только текстовые наборы (B и C): у '
                'набора A запрос — это задача, а не формулировка человека.')

        топ = options['top']
        matrix, ids = построить_индекс(options['scope'])
        self.stdout.write(f'Индекс среза «{options["scope"]}»: {len(ids)} задач.')
        self.stdout.write('Загружаем модель для кодирования запросов...')
        кодировать = _кодировщик_модели()

        q = _нормализовать(np.asarray(кодировать([c.query for c in случаи]),
                                      dtype=np.float32))
        оценки = matrix @ q.T

        нужные = set()
        выдачи = []
        for столбец in range(len(случаи)):
            s = оценки[:, столбец]
            k = min(топ, s.shape[0])
            верх = np.argpartition(s, -k)[-k:]
            верх = верх[np.argsort(s[верх])[::-1]]
            выдача = [(ids[i], float(s[i])) for i in верх]
            выдачи.append(выдача)
            нужные.update(pid for pid, _ in выдача)

        тексты = dict(Problem.objects.filter(pk__in=нужные)
                      .values_list('id', 'statement'))
        заголовки = dict(Problem.objects.filter(pk__in=нужные)
                         .values_list('id', 'title'))

        блоки = []
        for н, (случай, выдача) in enumerate(zip(случаи, выдачи), start=1):
            эталон = set(случай.relevant_ids)
            строки = []
            for место, (pid, оценка) in enumerate(выдача, start=1):
                свой = ' target' if pid in эталон else ''
                метка = ' <span class="badge">ваша</span>' if pid in эталон else ''
                кусок = (тексты.get(pid) or '').strip().replace('\n', ' ')[:230]
                имя = f'q{н}_{pid}'
                переключатели = ''.join(
                    f'<label><input type="radio" name="{имя}" value="{v}"> '
                    f'{п}</label>'
                    for v, п in (('relevant', 'подходит'),
                                 ('acceptable', 'сойдёт'),
                                 ('irrelevant', 'мимо')))
                строки.append(
                    f'<div class="hit{свой}">'
                    f'<div class="rank">{место}<br>{оценка:.3f}</div>'
                    f'<div class="txt"><a href="https://weconomics.site'
                    f'/catalog/problem/{pid}/" target="_blank">#{pid}</a>{метка} '
                    f'{html.escape(заголовки.get(pid) or "")}<br>'
                    f'{html.escape(кусок)}…</div>'
                    f'<div>{переключатели}</div></div>')
            блоки.append(
                f'<div class="q"><p class="qt">{н}. '
                f'{html.escape(случай.query)}</p>'
                f'<p class="qm">вы указали: #{sorted(эталон)[0]}</p>'
                f'{"".join(строки)}</div>')

        имя_набора = мета.get('name', '?')
        страница = ШАБЛОН.format(
            имя=имя_набора, запросов=len(случаи), топ=топ,
            срез=options['scope'], индекс=len(ids), тело=''.join(блоки))

        куда = Path(options['out'] or (
            Path('reports') / 'embeddings_scaleup' /
            f'markup_set_{имя_набора.lower()}_'
            f'{datetime.now(timezone.utc):%Y%m%d}.html'))
        куда.parent.mkdir(parents=True, exist_ok=True)
        куда.write_text(страница, encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(
            f'Страница разметки готова: {куда}\n'
            f'Откройте её двойным щелчком. Разметка сохраняется в браузере, '
            f'кнопка внизу выводит JSON.'))
