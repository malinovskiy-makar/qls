"""Замер: у скольких задач ILE в поле solution лежит форумная реплика.

ILE — это форум iloveeconomics.ru, и при импорте в «решение» местами попал не
разбор, а сообщение ученика: «Пыталась решить следующим образом… что делать
дальше?» (эталон — #476). Здесь проверяется, системный ли это класс.

ТОЛЬКО ЗАМЕР, ничего не чинит и не меняет.

Признаки (четыре независимые группы; засчитывается число ЗАДЕЙСТВОВАННЫХ
групп, а не число слов — иначе одно повторяющееся «я» перевесило бы всё):
  1. первое лицо           — «пыталась решить», «у меня получилось», «я думаю»;
  2. обращение к читателю  — «подскажите», «помогите», «заранее спасибо»;
  3. вопрос в конце        — решение кончается вопросительным знаком;
  4. растерянность         — «не понимаю», «что делать дальше», «где ошибка».

Две группы и больше — уверенная находка; ровно одна — на глаза (в списке
помечено отдельно). Сверка с вердиктами ручного ревью — в выводе команды.

    ./venv/bin/python manage.py ile_forum_solutions
    ./venv/bin/python manage.py ile_forum_solutions --source-id 2 --limit 40
"""

import os
import re
from collections import Counter

from django.core.management.base import BaseCommand

from problems.models import Problem, ReviewVerdict
from problems.review_categories import CATEGORY_LABELS

OUT_DIR = "reports/ile_forum"
REPORT = os.path.join(OUT_DIR, "forum_solutions.md")
ILE_SOURCE_ID = 2

# Слабый ярус (ровно одна группа признаков) почти весь — ложные срабатывания:
# «Подсказка…», «Примечание…», редакторские ремарки жюри. Все 90 просмотрены
# глазами 2026-07-28; ниже — те, что действительно оказались репликой ученика.
# Это РУЧНАЯ разметка, а не детектор: держим списком, чтобы цифра отчёта была
# воспроизводима и было видно, откуда она взялась.
HAND_CONFIRMED_WEAK = [
    189, 571, 1289, 1302, 1408, 1533, 1587, 2053, 2885, 2920, 2928,
    3196, 3206, 3219, 3364, 3473, 2791, 2873,
]

# Просмотрены и НЕ засчитаны — спорные, оставлены на глаза Макару:
# #2687/#2814 (голый расчёт, кончается вопросом), #2990 («Начало решения:» —
# похоже на редакторскую подсказку), #2401/#3549 («Уважаемые товарищи
# Решающие!» — обращение автора задачи, а не вопрос ученика).
HAND_DISPUTED_WEAK = [2401, 2687, 2814, 2990, 3549]

# Формы намеренно с учётом рода: на форуме пишут и «пыталась», и «пытался».
FIRST_PERSON = re.compile(
    r'\b(?:я\s+(?:реш|дела|счита|дума|получ|нашл|пробова|попробова|беру|взял)'
    r'|пыта(?:лся|лась|юсь)'
    r'|у\s+меня\s+(?:получ|выход|выш|не\s+сход)'
    r'|мой\s+ответ|мне\s+кажется|по-моему'
    r'|(?:реша|дела|счита|дума|рассужда)ю\s+так'
    r'|получил(?:ось|ась|)\s|вышло\s+что)', re.IGNORECASE)

ADDRESS_READER = re.compile(
    r'\b(?:подскажите|подскажи|помогите|помоги|объясните|объясни'
    r'|заранее\s+спасибо|спасибо\s+заранее'
    r'|правильно\s+ли\s+я|верно\s+ли\s+я|прав(?:ильно)?\s+ли\s+это'
    r'|кто[- ]нибудь|уважаемые)', re.IGNORECASE)

CONFUSION = re.compile(
    r'\b(?:не\s+пон(?:имаю|ял|яла)|не\s+могу\s+(?:пон|реш|разобра|сообраз)'
    r'|что\s+делать\s+дальше|как\s+быть\s+дальше'
    r'|(?:где|в\s+ч[её]м)\s+(?:моя\s+)?ошибка|застрял|туплю'
    r'|не\s+сходится|не\s+получается|дальше\s+не\s+знаю)', re.IGNORECASE)


def forum_signals(text):
    """Список сработавших групп признаков форумной реплики."""
    t = (text or '').strip()
    if not t:
        return []
    hits = []
    if FIRST_PERSON.search(t):
        hits.append('первое лицо')
    if ADDRESS_READER.search(t):
        hits.append('обращение к читателю')
    # Вопрос в самом конце: «…что делать дальше?». Вопросительные знаки в
    # середине бывают и в нормальном разборе, поэтому смотрим только хвост.
    if t.rstrip().endswith('?'):
        hits.append('вопрос в конце')
    if CONFUSION.search(t):
        hits.append('растерянность')
    return hits


class Command(BaseCommand):
    help = 'Замер форумных реплик в поле solution у задач ILE (ничего не меняет).'

    def add_arguments(self, parser):
        parser.add_argument('--source-id', type=int, default=ILE_SOURCE_ID)
        parser.add_argument('--limit', type=int, default=30,
                            help='Сколько примеров показать в консоли.')

    def handle(self, *args, **opts):
        qs = (Problem.objects
              .filter(source_references__source_id=opts['source_id'])
              .exclude(solution='').exclude(solution__isnull=True)
              .distinct())
        total = qs.count()
        self.stdout.write('Задач ILE с непустым solution: {}'.format(total))

        strong, weak = [], []
        for p in qs.only('id', 'title', 'solution', 'status', 'needs_quality_review'):
            hits = forum_signals(p.solution)
            if len(hits) >= 2:
                strong.append((p, hits))
            elif len(hits) == 1:
                weak.append((p, hits))

        # Ручная разметка слабого яруса переезжает к подтверждённым: детектор
        # их не добрал, но глаза увидели ту же самую форумную реплику.
        confirmed_weak = [(p, h) for p, h in weak if p.id in HAND_CONFIRMED_WEAK]
        strong = strong + confirmed_weak
        weak = [(p, h) for p, h in weak if p.id not in HAND_CONFIRMED_WEAK]

        self.stdout.write(self.style.SUCCESS(
            'Подтверждённых находок: {} (детектор 2+ групп: {}, '
            'ручная разметка слабого яруса: {})'
            .format(len(strong), len(strong) - len(confirmed_weak), len(confirmed_weak))))
        self.stdout.write('Осталось слабых (просмотрены, не засчитаны): {}'.format(len(weak)))

        visible = [(p, h) for p, h in strong
                   if p.status == Problem.Status.PUBLISHED and not p.needs_quality_review]
        self.stdout.write('Из подтверждённых видимы в каталоге: {}'.format(len(visible)))

        # ── Сверка с вердиктами ручного ревью ───────────────────────────
        verdicts = {}
        for rv in ReviewVerdict.objects.filter(
                problem_id__in=[p.id for p, _ in strong]):
            verdicts.setdefault(rv.problem_id, []).append(rv.category)

        reviewed = [(p, h) for p, h in strong if p.id in verdicts]
        marked_defect = [(p, h) for p, h in reviewed
                         if any(c != 'perfect' for c in verdicts[p.id])]
        called_perfect = [(p, h) for p, h in reviewed
                          if verdicts[p.id] == ['perfect']]
        cat_counter = Counter(c for p, _ in reviewed for c in verdicts[p.id])

        self.stdout.write('')
        self.stdout.write('Сверка с ручным ревью:')
        self.stdout.write('  из уверенных находок ревьюер видел: {}'.format(len(reviewed)))
        self.stdout.write('  пометил дефектными: {}'.format(len(marked_defect)))
        self.stdout.write('  назвал идеальными: {}'.format(len(called_perfect)))
        for cat, n in cat_counter.most_common():
            self.stdout.write('    {}: {}'.format(CATEGORY_LABELS.get(cat, cat), n))

        self._write_report(total, strong, weak, visible, verdicts,
                           reviewed, marked_defect, called_perfect, cat_counter)
        self.stdout.write(self.style.SUCCESS('Отчёт → {}'.format(REPORT)))

        for p, hits in strong[:opts['limit']]:
            mark = ' [ревью: {}]'.format(', '.join(verdicts[p.id])) if p.id in verdicts else ''
            self.stdout.write('  #{} {} — {}{}'.format(
                p.id, (p.title or '')[:44], ', '.join(hits), mark))

    def _write_report(self, total, strong, weak, visible, verdicts,
                      reviewed, marked_defect, called_perfect, cat_counter):
        os.makedirs(OUT_DIR, exist_ok=True)
        L = []
        L.append('# Форумный текст вместо решения в ILE (Задача 3)\n')
        L.append('ILE — форум iloveeconomics.ru. Проверяем, системный ли класс '
                 '«в поле solution лежит реплика ученика, а не разбор» '
                 '(эталон — #476). Только замер, ничего не чинилось.\n')
        L.append('## Цифры\n')
        L.append('| | Задач |')
        L.append('|---|---:|')
        L.append('| Задач ILE с непустым `solution` | {} |'.format(total))
        L.append('| **Подтверждённых форумных реплик** | **{}** |'.format(len(strong)))
        L.append('| — из них нашёл детектор (2+ групп признаков) | {} |'
                 .format(len(strong) - len(HAND_CONFIRMED_WEAK)))
        L.append('| — из них добавлены ручным просмотром слабого яруса | {} |'
                 .format(len(HAND_CONFIRMED_WEAK)))
        L.append('| из подтверждённых видимы в каталоге | {} |'.format(len(visible)))
        L.append('| Слабых просмотрено и НЕ засчитано | {} |'.format(len(weak)))
        L.append('| — из них спорных, оставлены на глаза | {} |'
                 .format(len(HAND_DISPUTED_WEAK)))
        L.append('')
        L.append('Доля среди решений ILE: **{:.1f}%**.'
                 .format(100.0 * len(strong) / max(1, total)))
        L.append('')
        L.append('**Вывод: класс НЕ системный, а точечный.** Слабый ярус (одна '
                 'группа признаков) почти весь оказался ложным: там «Подсказка…», '
                 '«Примечание…» и ремарки жюри, то есть законная редакторская '
                 'речь, а не вопрос ученика. Это ещё одно подтверждение решения '
                 '«детекторы не годятся для отбора»: автоматический ярус пришлось '
                 'разбирать глазами, иначе цифра завысилась бы в десять раз.')
        L.append('')
        L.append('Заметное попутное наблюдение: находки идут ПАРАМИ с одинаковым '
                 'текстом (#571/#3364, #1289/#3219, #1302/#2873, #1408/#2791, '
                 '#1533/#3206, #1587/#3473, #189/#3196) — одна и та же форумная '
                 'реплика импортирована дважды под разными id. Это материал для '
                 'дедупликации, а не отдельный дефект.')
        L.append('')
        L.append('Спорные, оставлены на глаза Макару: {}.'
                 .format(', '.join('#{}'.format(i) for i in HAND_DISPUTED_WEAK)))
        L.append('')

        L.append('## Сверка с вердиктами ручного ревью\n')
        L.append('Это ещё одна проверка полноты ревью: если ревьюер '
                 'систематически называл такие задачи идеальными, значит класс '
                 'мимо его чек-листа (он смотрел ВНЕШНИЙ ВИД, а не смысл поля).\n')
        L.append('| | Задач |')
        L.append('|---|---:|')
        L.append('| Уверенных находок попало в размеченный пакет | {} |'.format(len(reviewed)))
        L.append('| из них помечено дефектными | {} |'.format(len(marked_defect)))
        L.append('| из них названо идеальными | {} |'.format(len(called_perfect)))
        L.append('')
        if cat_counter:
            L.append('По категориям вердиктов:\n')
            L.append('| Категория | Задач |')
            L.append('|---|---:|')
            for cat, n in cat_counter.most_common():
                L.append('| {} | {} |'.format(CATEGORY_LABELS.get(cat, cat), n))
            L.append('')

        L.append('## Список подтверждённых находок\n')
        L.append('| id | Признаки | Вердикт ревью | Начало solution |')
        L.append('|---|---|---|---|')
        for p, hits in strong:
            v = ', '.join(CATEGORY_LABELS.get(c, c) for c in verdicts.get(p.id, [])) or '—'
            head = re.sub(r'\s+', ' ', (p.solution or ''))[:110].replace('|', '\\|')
            L.append('| #{} | {} | {} | {} |'.format(p.id, ', '.join(hits), v, head))
        L.append('')

        L.append('## Слабый ярус — просмотрен и НЕ засчитан\n')
        L.append('| id | Признак | Начало solution |')
        L.append('|---|---|---|')
        for p, hits in weak:
            head = re.sub(r'\s+', ' ', (p.solution or ''))[:110].replace('|', '\\|')
            L.append('| #{} | {} | {} |'.format(p.id, ', '.join(hits), head))

        with open(REPORT, 'w', encoding='utf-8') as f:
            f.write('\n'.join(L) + '\n')
