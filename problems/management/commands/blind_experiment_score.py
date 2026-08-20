"""blind_experiment_score — сверить слепую разметку модели с вердиктами человека.

ТОЛЬКО ЧТЕНИЕ. Ни одной записи в базу.

Запускается ПОСЛЕ того, как разметка завершена и зафиксирована
(reports/blind_experiment/model_verdicts_locked.txt хранит sha256 и время).

Базовая линия известна и равна нулю: обе группы отобраны по признаку «чистка
не трогала», то есть прежний промпт на этих 130 задачах дал 0 находок и
0 ложных срабатываний. Поэтому любая ненулевая чувствительность — прирост.

Запуск:
    venv\\Scripts\\python manage.py blind_experiment_score
"""

import json
import os
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from problems.models import ReviewVerdict
from problems.review_categories import CATEGORY_LABELS

ILE_BUNDLE = 'ile_20260721'
DIR = 'reports/blind_experiment'


class Command(BaseCommand):
    help = 'Сверить слепую разметку модели с вердиктами ревьюера. Только чтение.'

    def handle(self, *args, **options):
        model = {r['id']: r for r in
                 json.load(open(f'{DIR}/verdicts_model.json', encoding='utf-8'))}
        key = json.load(open(f'{DIR}/sample_key.json', encoding='utf-8'))['groups']
        key = {int(k): v for k, v in key.items()}
        contaminated = set(json.load(
            open(f'{DIR}/contaminated_ids.json', encoding='utf-8')))

        # вердикты человека
        human = defaultdict(set)
        for row in (ReviewVerdict.objects.filter(bundle=ILE_BUNDLE,
                                                 problem_id__in=list(model))
                    .values('problem_id', 'category')):
            human[row['problem_id']].add(row['category'])

        L = []
        A = L.append
        A('# Эксперимент: лечится ли слепота ИИ-чистки промптом')
        A('')
        A('Модель не правит тексты — только говорит, есть дефект или нет. '
          'Проверяется зрение, а не руки.')
        A('')
        locked = ''
        if os.path.exists(f'{DIR}/model_verdicts_locked.txt'):
            locked = open(f'{DIR}/model_verdicts_locked.txt',
                          encoding='utf-8').read()
        sha = next((l.split(': ', 1)[1].strip() for l in locked.splitlines()
                    if l.startswith('sha256')), '—')
        when = next((l.split(': ', 1)[1].strip() for l in locked.splitlines()
                     if l.startswith('записан')), '—')
        A(f'Разметка зафиксирована до открытия ключа: sha256 `{sha}`, '
          f'записана {when}.')
        A('')

        # ── заражение ────────────────────────────────────────────────────
        A('## ⚠️ Оговорка о чистоте эксперимента')
        A('')
        A(f'В контексте этой беседы лежала прошлая сессия, где печатались '
          f'списки id по категориям (broken_table целиком, часть '
          f'leaked_solution, все 42 комментария ревьюера, 20 «идеальных со '
          f'сверь_цифры»). Пересечение этих списков с выборкой — '
          f'**{len(contaminated)} задач из 130**, их вердикт был мне известен '
          f'до разметки.')
        A('')
        A(f'Заражённые id: {sorted(contaminated)}')
        A('')
        A('Поэтому главные числа считаются по **чистым** задачам, а полные '
          'приводятся рядом для сравнения. Разница между ними и показывает, '
          'сколько стоило заражение.')
        A('')

        def stats(ids):
            """Чувствительность/ложные по набору id."""
            a = [i for i in ids if key[i] == 'A']
            b = [i for i in ids if key[i] == 'B']
            a_hit = [i for i in a if model[i]['defect']]
            b_hit = [i for i in b if model[i]['defect']]
            return a, b, a_hit, b_hit

        all_ids = sorted(model)
        clean_ids = [i for i in all_ids if i not in contaminated]

        A('## 1. Чувствительность — главное число сессии')
        A('')
        A('| Набор | Группа А (человек нашёл дефект) | Модель нашла | '
          'Чувствительность |')
        A('|---|---:|---:|---:|')
        for name, ids in (('чистые задачи', clean_ids), ('все 130', all_ids)):
            a, b, a_hit, b_hit = stats(ids)
            A(f'| {name} | {len(a)} | {len(a_hit)} | '
              f'{100.0 * len(a_hit) / len(a):.0f}% |')
        A('')
        a, b, a_hit, b_hit = stats(clean_ids)
        A(f'**Базовая линия — 0%**: обе группы отобраны по признаку «чистка не '
          f'трогала», то есть прежний промпт на этих же задачах не нашёл '
          f'ничего. Чек-лист v2 находит **{100.0 * len(a_hit) / len(a):.0f}%** '
          f'того же материала.')
        A('')
        missed = sorted(i for i in a if not model[i]['defect'])
        A(f'Пропущено моделью: {len(missed)} задач — {missed}')
        A('')

        A('## 2. Ложные срабатывания')
        A('')
        A('| Набор | Группа Б (человек: идеально) | Модель пометила дефектом | '
          'Доля ложных |')
        A('|---|---:|---:|---:|')
        for name, ids in (('чистые задачи', clean_ids), ('все 130', all_ids)):
            a2, b2, a_hit2, b_hit2 = stats(ids)
            A(f'| {name} | {len(b2)} | {len(b_hit2)} | '
              f'{100.0 * len(b_hit2) / len(b2):.0f}% |')
        A('')
        A(f'Ложно помечены: {sorted(b_hit)}')
        A('')
        A('Разбор ложных срабатываний:')
        A('')
        for i in sorted(b_hit):
            m = model[i]
            A(f'- **#{i}** — модель: `{m["category"]}` ({m["confidence"]} '
              f'уверенность). {m["note"]}')
        A('')

        A('## 3. Совпадение категории')
        A('')
        hits = [i for i in a_hit if human.get(i)]
        exact = 0
        matrix = Counter()
        for i in hits:
            h = sorted(c for c in human[i] if c != 'perfect')
            m = model[i]['category']
            matrix[(h[0] if h else '—', m)] += 1
            if m in h:
                exact += 1
        A(f'Из {len(hits)} верно найденных дефектов категория совпала с '
          f'человеком в **{exact}** случаях '
          f'({100.0 * exact / len(hits):.0f}%).')
        A('')
        cats = sorted({k[0] for k in matrix} | {k[1] for k in matrix})
        A('| человек \\ модель | ' + ' | '.join(cats) + ' | всего |')
        A('|---|' + '---:|' * (len(cats) + 1))
        for hc in cats:
            row = [str(matrix.get((hc, mc), 0)) for mc in cats]
            total = sum(matrix.get((hc, mc), 0) for mc in cats)
            if total:
                A(f'| {hc} | ' + ' | '.join(row) + f' | {total} |')
        A('')

        A('## 4. Чувствительность по категориям')
        A('')
        A('| Категория человека | Задач в группе А | Найдено моделью | Доля |')
        A('|---|---:|---:|---:|')
        by_cat = defaultdict(list)
        for i in a:
            for c in human.get(i, set()):
                if c != 'perfect':
                    by_cat[c].append(i)
        for c in sorted(by_cat, key=lambda x: -len(by_cat[x])):
            ids = by_cat[c]
            found = [i for i in ids if model[i]['defect']]
            A(f'| {c} ({CATEGORY_LABELS.get(c, c)}) | {len(ids)} | '
              f'{len(found)} | {100.0 * len(found) / len(ids):.0f}% |')
        A('')

        A('## 5. Связь с уверенностью')
        A('')
        A('| Уверенность | Помечено дефектом | Из них верно (группа А) | '
          'Точность |')
        A('|---|---:|---:|---:|')
        for conf in ('высокая', 'средняя', 'низкая'):
            flagged = [i for i in clean_ids
                       if model[i]['defect'] and model[i]['confidence'] == conf]
            right = [i for i in flagged if key[i] == 'A']
            if flagged:
                A(f'| {conf} | {len(flagged)} | {len(right)} | '
                  f'{100.0 * len(right) / len(flagged):.0f}% |')
        A('')
        hi = [i for i in clean_ids
              if model[i]['defect'] and model[i]['confidence'] == 'высокая']
        hi_ok = [i for i in hi if key[i] == 'A']
        lo = [i for i in clean_ids
              if model[i]['defect'] and model[i]['confidence'] != 'высокая']
        lo_ok = [i for i in lo if key[i] == 'A']
        A(f'Точность на «высокой» — {100.0 * len(hi_ok) / len(hi):.0f}%, '
          f'на «средней и низкой» — {100.0 * len(lo_ok) / len(lo):.0f}%.')
        A('')
        A(f'**Уверенность работает как фильтр.** Если действовать только по '
          f'«высокой», получаем {len(hi_ok)} верных находок при '
          f'{len(hi) - len(hi_ok)} ложной на {len(hi)} помеченных: '
          f'чувствительность падает до '
          f'{100.0 * len(hi_ok) / len(a):.0f}%, зато доля ложных — '
          f'{100.0 * (len(hi) - len(hi_ok)) / len(b):.0f}% группы Б '
          f'вместо {100.0 * len(b_hit) / len(b):.0f}%.')
        A('')

        # ── что измерить не удалось ──────────────────────────────────────
        A('## 6. Чего измерить не удалось')
        A('')
        bt_all = [i for i in all_ids
                  if key[i] == 'A' and 'broken_table' in human.get(i, set())]
        bt_clean = [i for i in bt_all if i not in contaminated]
        bt_found = [i for i in bt_all if model[i]['defect']]
        A(f'**`broken_table` на чистых данных не измерена.** Все '
          f'{len(bt_all)} задач этой категории в выборке '
          f'({sorted(bt_all)}) попали в число заражённых, чистых не осталось '
          f'({len(bt_clean)}). На полном наборе модель нашла '
          f'{len(bt_found)} из {len(bt_all)}, но это число не доказательство.')
        A('')
        A('**`bare_math` человек не поставил ни разу** в этой выборке, хотя '
          'модель использовала эту категорию 20 раз. Отдельной '
          'чувствительности по ней нет по построению.')
        A('')

        # ── смета ────────────────────────────────────────────────────────
        A('## 7. Сколько это стоит')
        A('')
        chars = 0
        blind = json.load(open(f'{DIR}/sample_blind.json', encoding='utf-8'))
        for r in blind:
            chars += len(r['statement']) + len(r['solution']) + len(r['answer'])
            for p in r['parts']:
                chars += len(p['statement']) + len(p['answer'])
        checklist = os.path.getsize(f'{DIR}/checklist_v2.md')
        # русский текст: примерно 2,5 символа на токен
        CPT = 2.5
        in_tok = chars / CPT + (checklist / CPT) * 6   # чек-лист в каждой из 6 партий
        out_tok = 130 * 90                             # ~90 токенов на вердикт
        A(f'- текстов задач: {chars} символов ≈ {chars / CPT:,.0f} токенов')
        A(f'- чек-лист ({checklist} символов) подавался 6 раз ≈ '
          f'{(checklist / CPT) * 6:,.0f} токенов')
        A(f'- вход всего ≈ **{in_tok:,.0f}** токенов, выход ≈ '
          f'**{out_tok:,.0f}** токенов')
        A('')
        per_problem_in = in_tok / 130
        per_problem_out = out_tok / 130
        # Sonnet: $3 / $15 за млн
        cost130 = per_problem_in * 130 / 1e6 * 3 + per_problem_out * 130 / 1e6 * 15
        cost18k = per_problem_in * 18000 / 1e6 * 3 + per_problem_out * 18000 / 1e6 * 15
        A(f'На 130 задач ≈ **${cost130:.2f}**. В пересчёте на 18 000 задач '
          f'каталога ≈ **${cost18k:.0f}** по обычной цене Sonnet '
          f'($3/$15 за млн токенов).')
        A('')
        A(f'⚠️ Это стоимость ОДНОГО ПРОХОДА-ДИАГНОСТИКИ, который только '
          f'называет дефект. Починка — отдельные деньги: там в выход уходит '
          f'весь исправленный текст задачи, а не строка вердикта, то есть '
          f'выходных токенов станет примерно в двадцать раз больше. Batch API '
          f'даёт вдвое дешевле, при пакетной подаче чек-лист кэшируется и его '
          f'вклад падает почти до нуля.')
        A('')
        A(f'⚠️ Считать по этой смете весь каталог нельзя без оговорки: '
          f'выборка целиком из ILE, а средняя задача ILE — {chars // 130} '
          f'символов. У источников с более длинными условиями цена вырастет '
          f'пропорционально.')
        A('')

        # ── ручная сверка расхождений ────────────────────────────────────
        A('## 8. Три расхождения, разобранные вручную')
        A('')
        A('Проверено по снимкам самого пакета ревью '
          '(`reports/review_bundles/ile_20260721/snapshots/`), то есть по '
          'тому, что ревьюер видел на экране. Картинок в снимках нет ни у '
          'одной из трёх — значит человек читал ровно тот же текст, что и '
          'модель.')
        A('')
        A('**#481 — человек «идеально», модель «сломанная формула» '
          '(высокая уверенность).** В условии `$pi=8Q-Q^2-4$`. Без обратного '
          'слэша KaTeX рисует не π, а произведение двух курсивных букв p и i. '
          'Наблюдение модели фактически верно, но ревьюер такое пропустил.')
        A('')
        A('**#2371 — человек «сломанная формула», модель «чисто».** '
          'Единственная особенность разметки: `TC= 24` внутри `$…$` рисуется '
          'курсивным произведением T·C — **ровно тот же класс, что `pi` в '
          '#481**. Два почти одинаковых случая человек рассудил '
          'противоположно.')
        A('')
        A('Вывод по паре: это не промах модели и не промах человека, а '
          '**несогласованность самого эталона на мелких дефектах разметки**. '
          'Она ставит потолок достижимому совпадению: часть «ложных '
          'срабатываний» — это места, где модель применила заявленные правила '
          'последовательнее, чем человек.')
        A('')
        A('**#2036 — человек «идеально», модель «прочее».** Условие говорит '
          '«на приведённых ниже графиках», графиков нет ни в тексте, ни в '
          'снимке; задача нерешаема. Человек всё равно поставил «идеально». '
          'Причина видна в справочнике: **среди семи категорий нет «потерян '
          'рисунок»**, и ревьюеру было некуда это положить. Мой чек-лист '
          'отправлял такие случаи в `other` — расхождение возникло по '
          'построению, а не по зрению.')
        A('')

        # ── вывод ────────────────────────────────────────────────────────
        A('## 9. Вывод')
        A('')
        A('**ЧАСТИЧНО.**')
        A('')
        A(f'Слепота лечится промптом как таковая: там, где прежняя чистка не '
          f'нашла ничего (базовая линия 0 из {len(a)}), чек-лист v2 находит '
          f'{len(a_hit)} из {len(a)} — **{100.0 * len(a_hit) / len(a):.0f}%**. '
          f'Значит дефекты в тексте видны, и прежний промпт их не видел не '
          f'потому, что их нельзя увидеть.')
        A('')
        A('Но пускать это в дело как есть нельзя: треть идеальных задач '
          'получает ложную метку. Поэтому применимость разная по частям.')
        A('')
        A('**Где ИИ применим:**')
        A('')
        A('- `leaked_solution` — 6 из 6. Утёкший «Ответ:» в конце условия '
          'узнаётся дословно и почти без риска.')
        A('- `broken_formula` — 32 из 35. Оторванные индексы, `\\TC`, '
          'двойной индекс, непарные скобки — всё это видно в сыром тексте.')
        A('- `junk` — 4 из 5. Хвост «Все задачи автора», обрубки, реплики '
          'с форума.')
        A('- **Как детектор с порогом уверенности.** На «высокой» точность '
          '97% (33 верных, 1 ложная). Это рабочий режим: отбирать задачи в '
          'очередь на починку, а не чинить подряд.')
        A('')
        A('**Где ИИ не применим:**')
        A('')
        A('- **Как классификатор категорий.** Совпадение 38%. Главная путаница '
          'системная: то, что человек зовёт `broken_formula`, модель '
          '19 раз назвала `bare_math`. Граница «голая математика против '
          'сломанной разметки» у людей и у модели проходит в разных местах, '
          'и на неё нельзя вешать маршрутизацию починки.')
        A('- **`merged_structure` — 72%**, и это самая частая категория. '
          'Каждая четвёртая слипшаяся структура не видна: без исходника '
          'нельзя понять, был ли абзац когда-то списком.')
        A('- **`broken_table`** — не измерена, чистых случаев в выборке не '
          'осталось.')
        A('- **Автоматическая починка без человека** — при 33% ложных это '
          'ровно тот риск переписывания хороших задач, от которого разгребали '
          'Батч 2.')
        A('')

        with open(f'{DIR}/results.md', 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(L) + '\n')

        for line in L[:0] or []:
            pass
        summary = (f'чувствительность(чистые) {len(a_hit)}/{len(a)}; '
                   f'ложных {len(b_hit)}/{len(b)}; '
                   f'категория совпала {exact}/{len(hits)}')
        try:
            self.stdout.write(summary)
        except UnicodeEncodeError:
            self.stdout.write(summary.encode('ascii', 'replace').decode())
