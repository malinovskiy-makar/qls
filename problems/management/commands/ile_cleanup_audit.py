"""ile_cleanup_audit — две проверки верности ИИ-чистки ILE. ТОЛЬКО ЧТЕНИЕ.

1. Не потерялись ли вырезанные ответы. Из условия и подпунктов местами
   вырезали хвост вида «а) P1 = 100, P2 = 60 b) P = 125» — это утёкшие
   ответы. Вопрос: переехали они в поля ответа или просто удалены.

2. Насколько модель переписывала АВТОРСКИЙ ТЕКСТ. Правило чистки было
   «только структура и мусор, слова автора не трогать». Считаем, где слова
   всё-таки менялись.

⚠️ Сравнение идёт по ВИДИМОМУ тексту: разметка формул снимается с обеих
сторон. Иначе добавление `$…$` и `P_1` вместо `P1` считалось бы правкой
авторского текста, хотя это ровно то, ради чего чистку и затевали.

⚠️ Ответ «сохранён/пропал» проверяется по БАЗЕ, а не только по патчу: патч
это намерение, а база — то, что реально применилось.

Запуск:
    venv\\Scripts\\python manage.py ile_cleanup_audit
"""

import difflib
import io
import json
import os
import re
from collections import Counter

from django.core.management.base import BaseCommand

from problems.models import Problem

# Какие патчи считать — правило одно с прошлыми сессиями, второй копией
# оно разъехалось бы при первой же правке форматов.
from problems.management.commands.verdicts_vs_cleanup import Command as VvcCommand

CLEANUP_DIR = 'reports/ai_cleanup_ile'
OUT_DIR = 'reports/ile_cleanup_audit'

# ── распознавание «похоже на ответ» ─────────────────────────────────────────
ANSWER_WORD_RE = re.compile(r'\bОтвет[ыа]?\b', re.IGNORECASE)
# «а) P1 = 100, P2 = 60 b) P = 125», «Q = 50», «х=2,5»
ASSIGN_RE = re.compile(r'[A-Za-zА-Яа-я][A-Za-z0-9А-Яа-я_^{}]{0,12}\s*=\s*-?\d')
ITEM_MARK_RE = re.compile(r'(?:^|\s)[аабвгдabcde]\s*[\)\.]', re.IGNORECASE)

CYR_WORD_RE = re.compile(r'[А-Яа-яЁё]{2,}')
NUM_RE = re.compile(r'\d+(?:[.,]\d+)?')

SHRINK_LIMIT = 0.10   # порог «текст усох больше чем на 10%»
MAX_ANSWER_FRAGMENT = 300


def strip_math(text):
    """Снять разметку формул, оставив видимый текст.

    Нужно, чтобы «$Q = 140 - P$» и «Q = 140 - P» считались одним и тем же:
    иначе вся чистка выглядела бы как переписывание авторского текста.
    """
    t = text or ''
    # ⚠️ LaTeX-скобка десятичной запятой: «0{,}5» это то же число, что «0,5».
    # Без этой нормализации каждая такая запятая ловилась бы как пропавшее
    # число — урок свипа Батча 2, наступать на него второй раз не будем.
    t = re.sub(r'\{\s*([.,])\s*\}', r'\1', t)
    t = re.sub(r'\\text\s*\{([^{}]*)\}', r'\1', t)
    t = re.sub(r'\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}', r'\1/\2', t)
    t = t.replace('\\cdot', ' ').replace('\\ldots', '...').replace('\\dots', '...')
    t = re.sub(r'\\[a-zA-Z]+', ' ', t)      # прочие команды
    t = t.replace('$', '')
    t = re.sub(r'[_^]\s*\{([^{}]*)\}', r'\1', t)
    t = re.sub(r'[_^]', '', t)
    t = t.replace('{', ' ').replace('}', ' ')
    t = t.replace('—', '-').replace('–', '-')
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def nums(text):
    """Числовые токены в каноничном виде.

    Десятичный разделитель приводится к точке: модель нередко меняет «0.05»
    на «0,05», и без нормализации это выглядело бы как пропавшее число.
    """
    return [m.replace(',', '.') for m in NUM_RE.findall(text or '')]

def question_text(task):
    """Весь текст, который читает ученик как ВОПРОС: условие + подпункты."""
    if not task:
        return ''
    chunks = [task.get('statement') or '']
    for p in task.get('parts') or []:
        if isinstance(p, dict):
            chunks.append(p.get('statement') or '')
    return '\n'.join(c for c in chunks if c)


def answer_text(task):
    """Весь текст полей ОТВЕТА: Problem.answer + ответы подпунктов."""
    if not task:
        return ''
    chunks = [task.get('answer') or '']
    for p in task.get('parts') or []:
        if isinstance(p, dict):
            chunks.append(p.get('answer') or '')
    return ' '.join(c for c in chunks if c).strip()


def looks_like_answer(fragment):
    """Похож ли вырезанный кусок на утёкший ответ."""
    f = (fragment or '').strip()
    if len(f) < 3 or len(f) > MAX_ANSWER_FRAGMENT:
        return False
    if ANSWER_WORD_RE.search(f):
        return True
    # присваивания с числом: «P1 = 100». Одного мало — в условии таких полно,
    # поэтому либо два и больше, либо одно рядом с меткой пункта.
    hits = ASSIGN_RE.findall(f)
    if len(hits) >= 2:
        return True
    if hits and ITEM_MARK_RE.search(f):
        return True
    return False


def removed_fragments(before, after):
    """Куски, которые были в before и исчезли в after (по видимому тексту)."""
    sm = difflib.SequenceMatcher(None, before, after, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ('delete', 'replace'):
            frag = before[i1:i2].strip()
            if len(frag) >= 3:
                out.append(frag)
    return out


def word_ops(before, after):
    """Пословный разбор по русским словам: что вставлено/заменено/удалено."""
    wb = [w.lower() for w in CYR_WORD_RE.findall(before)]
    wa = [w.lower() for w in CYR_WORD_RE.findall(after)]
    sm = difflib.SequenceMatcher(None, wb, wa, autojunk=False)
    ins = repl = dele = 0
    tail_only = True
    details = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        if tag == 'insert':
            ins += (j2 - j1)
            details.append(('вставлено', '', ' '.join(wa[j1:j2])))
        elif tag == 'replace':
            repl += max(i2 - i1, j2 - j1)
            details.append(('заменено', ' '.join(wb[i1:i2]), ' '.join(wa[j1:j2])))
        elif tag == 'delete':
            dele += (i2 - i1)
            details.append(('удалено', ' '.join(wb[i1:i2]), ''))
            # удаление в СЕРЕДИНЕ текста — это уже не отрезанный хвост
            if i2 < len(wb) - 3 and i1 > 3:
                tail_only = False
    return {'words_before': len(wb), 'words_after': len(wa),
            'inserted': ins, 'replaced': repl, 'deleted': dele,
            'tail_only_deletion': tail_only, 'details': details}


# Вердикты по восьми верхним кандидатам — проставлены вручную, сверкой raw,
# патча и базы. Автоматический детектор их различить не может.
HAND_CHECKED = [
    (632, '**НАСТОЯЩАЯ ПОТЕРЯ УСЛОВИЯ.** Из условия исчезли обе пары функций '
          'спроса и предложения ($x^d_1=100+0.5p_2-p_1$ и далее). Условие '
          'обрывается двоеточием, задача нерешаема. Формулы уцелели только '
          'в решении.'),
    (1573, '**НАСТОЯЩАЯ ПОДМЕНА УСЛОВИЯ.** Модель не вырезала, а переписала '
           'задачу другими числами: спрос второй группы был $q_2=100-p$, стал '
           '$Q_2=30-p_2$; издержки были $C=5000+100x$, стали «равны нулю»; '
           'дисконтирование и бесконечный горизонт удалены целиком. Решение '
           'осталось от исходной задачи и теперь противоречит условию.'),
    (2161, 'Ложное срабатывание: пункты 2.1–2.6 стали подпунктами, суммы '
           'вкладов уехали в них же. Данные на месте.'),
    (2517, 'Ложное срабатывание детектора: таблица нормативов была свалкой из '
           'подчёркиваний, модель собрала её в LaTeX-массив — это починка. '
           'Числа «пропали» из-за того, что подчёркивания склеивали соседние '
           'значения в один токен.'),
    (2599, 'Ложное срабатывание: таблица индексов цен реконструирована в '
           'массив, все пять значений на месте.'),
    (237, 'Ложное срабатывание: тарифная таблица реконструирована.'),
    (2233, 'Удаление правильное: вырезана чужая неверная попытка решения с '
           'форума («Мое решение, но оно неверно»). Условие не пострадало.'),
    (456, 'Удаление правильное: вырезаны реплика с форума и ссылка на '
          'сторонний сайт; ответ при этом сохранён в поле ответа.'),
]


class Command(BaseCommand):
    help = ('Аудит ИИ-чистки ILE: сохранность вырезанных ответов и объём '
            'переписывания авторского текста. Только чтение.')

    def handle(self, *args, **options):
        os.makedirs(OUT_DIR, exist_ok=True)
        helper = VvcCommand()
        patches, _hide, _sver, skipped, used = helper.load_patches()
        raw = helper.load_raw()

        # текущее состояние базы — источник правды о применённом
        ids = sorted(patches)
        db = {}
        db_solution = {}
        for p in (Problem.objects.filter(id__in=ids).prefetch_related('parts')
                  .only('id', 'statement', 'solution', 'answer')):
            db_solution[p.id] = p.solution or ''
            db[p.id] = {
                'answer': p.answer or '',
                'parts': [{'label': x.label, 'statement': x.statement or '',
                           'answer': x.answer or ''}
                          for x in p.parts.order_by('order', 'label')],
                'statement': p.statement or '',
            }

        answer_cases = []
        rewrite_rows = []
        lost_numbers = []

        for pid in ids:
            rawt = raw.get(pid)
            if not rawt:
                continue
            # «после» — сливаем raw с патчем, как это делает apply
            merged = dict(rawt)
            for name, info in sorted(patches[pid]['patches'].items()):
                pass
            patch_fields = {}
            for name in sorted(patches[pid]['patches']):
                with open(os.path.join(CLEANUP_DIR, name), encoding='utf-8') as fh:
                    tasks = json.load(fh)['tasks']
                patch_fields.update(tasks[str(pid)])
            for k in ('statement', 'solution', 'answer', 'parts'):
                if k in patch_fields:
                    merged[k] = patch_fields[k]

            q_before = strip_math(question_text(rawt))
            q_after = strip_math(question_text(merged))
            a_before = strip_math(answer_text(rawt))
            a_after_patch = strip_math(answer_text(merged))
            dbrec = db.get(pid)
            a_after_db = strip_math(answer_text(dbrec)) if dbrec else ''

            # ── задача 1: вырезанные ответы ─────────────────────────────
            frags = [f for f in removed_fragments(q_before, q_after)
                     if looks_like_answer(f)]
            if frags:
                answer_cases.append({
                    'id': pid,
                    'fragments': frags,
                    'answer_before': a_before,
                    'answer_after_patch': a_after_patch,
                    'answer_after_db': a_after_db,
                    'saved': bool(a_after_db.strip()),
                    'patch_files': sorted(patches[pid]['patches']),
                })

            # ── числа, исчезнувшие из ВОПРОСА ───────────────────────────
            # Отдельная проверка, потому что потеря формулы почти не меняет
            # длину текста: #632 потерял функции спроса и предложения, а по
            # усыханию не прошёл вовсе. Ученик читает вопрос, а не решение,
            # поэтому решение в зачёт не идёт — только поля ответа.
            nb = Counter(nums(q_before))
            na = Counter(nums(q_after))
            na.update(nums(a_after_db or a_after_patch))
            gone = nb - na
            # Решающий фильтр: есть ли «пропавшее» число ХОТЬ ГДЕ-ТО в записи
            # базы (включая решение). Если есть — оно не потеряно, а переехало
            # или переформатировано. Если нет нигде — это кандидат в настоящую
            # потерю, и его надо смотреть глазами.
            whole_db = ' '.join([
                (dbrec or {}).get('statement', ''), (dbrec or {}).get('answer', ''),
                ' '.join((x.get('statement', '') + ' ' + x.get('answer', ''))
                         for x in (dbrec or {}).get('parts', [])),
                (db_solution.get(pid) or ''),
            ]) if dbrec else ''
            in_db = Counter(nums(strip_math(whole_db)))
            gone_anywhere = gone - in_db
            if gone:
                lost_numbers.append({
                    'id': pid,
                    'gone': sorted(gone.elements()),
                    'count': sum(gone.values()),
                    'gone_anywhere': sorted(gone_anywhere.elements()),
                    'count_anywhere': sum(gone_anywhere.values()),
                    'answer_after_db': a_after_db,
                    'removed': [f[:200] for f in
                                removed_fragments(q_before, q_after)][:4],
                })

            # ── задача 2: переписывание авторского текста ───────────────
            ops = word_ops(q_before, q_after)
            shrink = ((len(q_before) - len(q_after)) / len(q_before)
                      if q_before else 0.0)
            rewrite_rows.append({
                'id': pid,
                'shrink': shrink,
                'chars_before': len(q_before),
                'chars_after': len(q_after),
                **{k: v for k, v in ops.items() if k != 'details'},
                'details': ops['details'][:6],
            })

        self.write_answers(answer_cases)
        self.write_numbers(lost_numbers)
        self.write_rewrite(rewrite_rows, raw, patches)
        self.say(f'патчей прочитано: {len(used)}; задач с правками: {len(ids)}')
        self.say(f'случаев вырезанного ответа: {len(answer_cases)}; '
                 f'из них сохранено: {sum(1 for c in answer_cases if c["saved"])}')

    def say(self, line):
        try:
            self.stdout.write(line)
        except UnicodeEncodeError:
            self.stdout.write(line.encode('ascii', 'replace').decode())

    # ------------------------------------------------------------------

    def write_answers(self, cases):
        saved = [c for c in cases if c['saved']]
        lost = [c for c in cases if not c['saved']]
        L = ['# Задача 1. Не потерялись ли вырезанные ответы', '',
             'Из условия и подпунктов ИИ-чистка местами вырезала хвост, '
             'похожий на утёкший ответ. Проверено, появилось ли непустое поле '
             'ответа — **в базе**, а не только в патче: патч это намерение, а '
             'база то, что реально применилось.', '',
             f'- случаев вырезанного «ответа»: **{len(cases)}**',
             f'- ответ сохранён в поле ответа: **{len(saved)}**',
             f'- ответ пропал: **{len(lost)}**', '']
        if lost:
            L.append('## Пропавшие — это потеря данных')
            L.append('')
            L.append('| id | вырезано | было в ответе | стало в ответе |')
            L.append('|---|---|---|---|')
            for c in lost:
                frag = '; '.join(c['fragments'])[:160].replace('|', '\\|')
                L.append(f'| #{c["id"]} | {frag} | '
                         f'{(c["answer_before"] or "—")[:60]} | '
                         f'{(c["answer_after_db"] or "—")[:60]} |')
            L.append('')
        else:
            L.append('**Потерь нет: у всех случаев поле ответа в базе непустое.**')
            L.append('')
        L.append('## Сохранённые — примеры')
        L.append('')
        L.append('| id | вырезано из вопроса | стало в поле ответа |')
        L.append('|---|---|---|')
        for c in saved[:25]:
            frag = '; '.join(c['fragments'])[:140].replace('|', '\\|')
            L.append(f'| #{c["id"]} | {frag} | '
                     f'{c["answer_after_db"][:90].replace("|", chr(92) + "|")} |')
        L.append('')

        with io.open(f'{OUT_DIR}/answers_audit.md', 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(L) + '\n')
        with io.open(f'{OUT_DIR}/answers_lost_ids.txt', 'w', encoding='utf-8') as fh:
            fh.write('# Задачи, где вырезанный ответ не попал в поле ответа\n')
            fh.write('# (пусто — значит потерь не найдено)\n')
            for c in lost:
                fh.write(f'{c["id"]}\n')
        with io.open(f'{OUT_DIR}/answers_cases.json', 'w', encoding='utf-8') as fh:
            json.dump(cases, fh, ensure_ascii=False, indent=1)

    def write_numbers(self, cases):
        """Числа, исчезнувшие из ВОПРОСА и не попавшие в поле ответа."""
        cases = sorted(cases, key=lambda c: -c['count'])
        hard = [c for c in cases if c['count_anywhere'] > 0]
        L = ['# Задача 1б. Числа, пропавшие из условия', '',
             'Отдельная проверка, потому что потеря формулы почти не меняет '
             'длину текста и по усыханию не ловится: #632 лишился обеих функций '
             'спроса и предложения, а в список усохших не попал вовсе.', '',
             'Считаются числовые токены в ВОПРОСЕ (условие + подпункты). Число '
             'засчитано сохранённым, если оно уехало в поле ответа.', '',
             f'- задач, где из вопроса пропало хотя бы одно число: '
             f'**{len(cases)}**',
             f'- из них число не находится и в решении: **{len(hard)}**', '',
             '⚠️ **Это список кандидатов, а не подтверждённых потерь.** Числа '
             'законно исчезают вместе с вырезанным мусором (чужая попытка '
             'решения с форума, ссылка с цифрами в адресе, номера пунктов, '
             'ставшие метками подпунктов). Колонка «есть в решении» помогает, '
             'но не решает: у #632 формулы остались в решении, а из условия '
             'пропали — для ученика это потеря, он читает вопрос.', '',
             '| id | пропало из вопроса | нет и в решении | какие | что вырезано |',
             '|---|---:|---:|---|---|']
        for c in cases[:30]:
            gone = ', '.join(c['gone'][:10])
            rem = ' … '.join(c['removed'])[:120].replace('|', '\|')
            L.append(f'| #{c["id"]} | {c["count"]} | {c["count_anywhere"]} | '
                     f'{gone} | {rem} |')
        L.append('')
        L.append('## Проверено глазами — восемь верхних кандидатов')
        L.append('')
        for pid, verdict in HAND_CHECKED:
            L.append(f'- **#{pid}** — {verdict}')
        L.append('')
        with io.open(f'{OUT_DIR}/numbers_audit.md', 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(L) + '\n')
        with io.open(f'{OUT_DIR}/numbers_lost_ids.txt', 'w', encoding='utf-8') as fh:
            fh.write('# Кандидаты: из вопроса пропали числа, в ответ не уехали\n')
            fh.write('# id\tпропало_из_вопроса\tнет_и_в_решении\n')
            for c in cases:
                fh.write('%d\t%d\t%d\n' % (c['id'], c['count'],
                                           c['count_anywhere']))
        with io.open(f'{OUT_DIR}/numbers_cases.json', 'w', encoding='utf-8') as fh:
            json.dump(cases, fh, ensure_ascii=False, indent=1)

    def write_rewrite(self, rows, raw, patches):
        total = len(rows)
        touched = [r for r in rows if r['inserted'] or r['replaced']
                   or (r['deleted'] and not r['tail_only_deletion'])]
        ins_or_repl = [r for r in rows if r['inserted'] or r['replaced']]
        mid_del = [r for r in rows
                   if r['deleted'] and not r['tail_only_deletion']]
        shrunk = [r for r in rows if r['shrink'] > SHRINK_LIMIT]
        clean = [r for r in rows if not (r['inserted'] or r['replaced']
                                         or r['deleted'])]

        L = ['# Задача 2. Насколько модель переписывала авторский текст', '',
             'Правило чистки было: «только структура и мусор, авторский текст '
             'не переписывать». Сравнение идёт по ВИДИМОМУ тексту вопроса '
             '(условие + подпункты): разметка формул снята с обеих сторон, '
             'иначе добавление `$…$` считалось бы переписыванием — а это ровно '
             'то, ради чего чистку затевали.', '',
             'Считаются русские слова. Три разных события:', '',
             '- **вставлено** — модель добавила слова, которых у автора не было;',
             '- **заменено** — слова автора заменены другими;',
             '- **удалено в середине** — вырезан кусок не с краю текста '
             '(вырезанный хвост считается отдельно: это, как правило, мусор '
             'или утёкший ответ, и это чистке разрешено).', '',
             f'Всего задач с правками: **{total}**', '',
             '| Что | Задач | Доля |', '|---|---:|---:|',
             f'| слова не тронуты вовсе | {len(clean)} | '
             f'{100.0 * len(clean) / total:.0f}% |',
             f'| вставлены или заменены слова | {len(ins_or_repl)} | '
             f'{100.0 * len(ins_or_repl) / total:.0f}% |',
             f'| удаление в середине текста | {len(mid_del)} | '
             f'{100.0 * len(mid_del) / total:.0f}% |',
             f'| **любое переписывание** | **{len(touched)}** | '
             f'**{100.0 * len(touched) / total:.0f}%** |',
             f'| текст усох больше чем на {int(SHRINK_LIMIT * 100)}% | '
             f'{len(shrunk)} | {100.0 * len(shrunk) / total:.0f}% |', '']

        L.append('## Вердикт: это системная практика, а не единичные случаи')
        L.append('')
        L.append(f'Слова автора остались нетронутыми у {len(clean)} задач из '
                 f'{total} ({100.0 * len(clean) / total:.0f}%). У остальных '
                 f'{total - len(clean)} модель так или иначе вмешалась в текст, '
                 f'причём у {len(ins_or_repl)} задач '
                 f'({100.0 * len(ins_or_repl) / total:.0f}%) она не просто '
                 f'вырезала лишнее, а ПОДСТАВИЛА свои слова.')
        L.append('')
        L.append('Единичным случаем это назвать нельзя: каждая пятая правка '
                 'содержит подстановку слов. При этом мелкая правка вроде '
                 '«договориться с фирмой А, они сошлись на том, что фирма А '
                 'может» → «договориться с фирмой А: фирма А может» (#859) '
                 'смысла не меняет, а вот верхушка списка — уже переписывание '
                 'сюжета целиком:')
        L.append('')
        L.append('- **#971** — «в высоко в горах Швейцарии над одной живописной '
                 'лощиной стоят два одинаковых очень дорогих отеля…» стало '
                 '«два предпринимателя Рокф и Ротш владеют отелями на берегу '
                 'моря». Сменились и место, и герои.')
        L.append('- **#1674** — «ходят в школу, в качестве домашнего задания им '
                 'задали разбиться на группы из двух человек…» стало «делать '
                 'домашнее задание, решать… читать книги».')
        L.append('- **#1573** — переписан не только сюжет, но и ЧИСЛА условия '
                 '(разобрано в `numbers_audit.md`).')
        L.append('')
        L.append('⚠️ Правку сюжета сама по себе нельзя назвать порчей: задача '
                 'может остаться решаемой и даже читаться лучше. Но правило '
                 'чистки было другим, и проверить 198 переписанных задач на '
                 'сохранность смысла автоматикой нельзя — только глазами.')
        L.append('')
        L.append('## Усохшие больше чем на 10% — где риск потери смысла')
        L.append('')
        L.append('| id | было симв. | стало | усохло | удалено слов | '
                 'удаление только с краю |')
        L.append('|---|---:|---:|---:|---:|---|')
        for r in sorted(shrunk, key=lambda x: -x['shrink'])[:30]:
            L.append(f'| #{r["id"]} | {r["chars_before"]} | {r["chars_after"]} | '
                     f'{100.0 * r["shrink"]:.0f}% | {r["deleted"]} | '
                     f'{"да" if r["tail_only_deletion"] else "НЕТ"} |')
        L.append('')

        L.append('## 20 примеров ДО/ПОСЛЕ')
        L.append('')
        examples = sorted(ins_or_repl, key=lambda x: -(x['inserted'] + x['replaced']))[:20]
        for r in examples:
            L.append(f'### #{r["id"]} — вставлено {r["inserted"]}, '
                     f'заменено {r["replaced"]}, удалено {r["deleted"]}')
            L.append('')
            for kind, before, after in r['details']:
                if kind == 'вставлено':
                    L.append(f'- **вставлено:** «{after[:160]}»')
                elif kind == 'заменено':
                    L.append(f'- **заменено:** «{before[:120]}» → «{after[:120]}»')
                else:
                    L.append(f'- удалено: «{before[:120]}»')
            L.append('')

        with io.open(f'{OUT_DIR}/rewrite_audit.md', 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(L) + '\n')
        with io.open(f'{OUT_DIR}/rewrite_rows.json', 'w', encoding='utf-8') as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
        with io.open(f'{OUT_DIR}/rewrite_shrunk_ids.txt', 'w', encoding='utf-8') as fh:
            fh.write('# Задачи, где видимый текст усох больше чем на 10%\n')
            for r in sorted(shrunk, key=lambda x: -x['shrink']):
                fh.write('%d\n' % r['id'])
