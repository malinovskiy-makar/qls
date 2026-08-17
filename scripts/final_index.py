#!/usr/bin/env python3
"""
Контактный лист снимков завершающей сессии ревью 17.08.2026.

Собирает `reports/review/final/*.png` в одну страницу: экран × три режима
(светлая тема, тёмная, узкий 380 px). Владелец смотрит один файл, а не
двадцать семь.

Запуск:  ./venv/bin/python scripts/final_index.py
Выход:   reports/review/index_final.html
"""
import html
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, 'reports', 'review', 'final')
OUT = os.path.join(ROOT, 'reports', 'review', 'index_final.html')

# Экран → что на нём смотреть. Порядок — по фазам задания.
SCREENS = [
    ('solo-overview', 'Индивидуальное занятие, «Обзор»',
     'Фаза 1: заметки об ученике последним блоком, кнопки «Карточка ученика» '
     'нет. Фаза 3.2: пустые темы под строкой «ещё N тем без ответов за '
     'период». Фаза 3.3: зазор у черты в парах чисел. Фаза 3.5: дробная доля '
     'объяснена в подписи блока.'),
    ('student-card', 'Карточка ученика группы',
     'Фаза 1.4: у групп не изменилось ничего — карточка открывается, заметки '
     'на ней. Разметка блоков общая с занятием.'),
    ('students-list', 'Экран «Ученики»',
     'Фаза 2.1: кнопки «Мои задачи» нет. Фаза 2.2: у спокойной карточки одна '
     'фраза вместо двух.'),
    ('group-overview', 'Занятие-группа, «Обзор»',
     'Фаза 2.3: подписи тем в матрице до 22 символов, потолок высоты 170 px.'),
    ('group-assignments', 'Занятие-группа, «Задания»',
     'Фаза 3.6: правая зона карточек одной ширины, у проверенной две строки '
     'вместо трёх. Фаза 3.7: кнопка создания и счётчик на одной горизонтали.'),
    ('group-materials', 'Занятие-группа, «Материалы»',
     'Фаза 4.1: разведка. Вкладка — заглушка, правок не вносилось.'),
    ('work-pick', 'Создание работы, шаг «Что кладём»',
     'Ничего не менялось; снят как соседний экран потока.'),
    ('work-compose', 'Создание работы, шаг «Состав»',
     'Фаза 3.1: стрелки порядка и ручка перетаскивания читаются как органы '
     'управления (замер контраста — в отчёте).'),
    ('student-stats', 'Статистика ученика',
     'Фаза 2.4: верхний блок выровнен влево целиком. Фаза 2.5: ссылка из '
     'промахов в игре ведёт в каталог по теме. Фаза 2.6: блок промахов виден '
     'на демо-данных.'),
]

MODES = [('', 'светлая'), ('-dark', 'тёмная'), ('-380', '380 px')]

CSS = """
body { margin: 0; font: 14px/1.6 -apple-system, BlinkMacSystemFont, 'Segoe UI',
       Roboto, sans-serif; background: #f5f5f3; color: #1a1a1a; }
.wrap { max-width: 1180px; margin: 0 auto; padding: 32px 20px 80px; }
h1 { font-size: 22px; margin: 0 0 6px; }
.lead { color: #5b6472; margin: 0 0 28px; }
.screen { background: #fff; border: 1px solid rgba(22,26,38,.12);
          border-radius: 12px; padding: 18px 20px; margin-bottom: 18px; }
h2 { font-size: 16px; margin: 0 0 4px; }
.what { color: #5b6472; font-size: 13px; margin: 0 0 14px; }
.row { display: grid; gap: 14px;
       grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
figure { margin: 0; }
figcaption { font-size: 12px; color: #687180; margin-bottom: 6px; }
img { width: 100%; border: 1px solid rgba(22,26,38,.12); border-radius: 8px;
      display: block; background: #fff; }
.miss { font-size: 12px; color: #b26b00; }
"""


def main():
    parts = ['<meta charset="utf-8"><title>Ревью 17.08 — завершающая сессия</title>',
             '<style>%s</style>' % CSS, '<div class="wrap">',
             '<h1>Ревью 17.08.2026 — завершающая сессия</h1>',
             '<p class="lead">Фазы 1–3 и разведка фазы 4. Каждый экран — '
             'светлая тема, тёмная и узкий экран 380&nbsp;px.</p>']
    for name, title, what in SCREENS:
        parts.append('<div class="screen"><h2>%s</h2><p class="what">%s</p>'
                     '<div class="row">' % (html.escape(title),
                                            html.escape(what)))
        for suffix, label in MODES:
            rel = 'final/%s%s.png' % (name, suffix)
            if os.path.exists(os.path.join(SHOTS, '%s%s.png' % (name, suffix))):
                parts.append('<figure><figcaption>%s</figcaption>'
                             '<img src="%s" alt="%s, %s"></figure>'
                             % (label, rel, html.escape(title), label))
            else:
                parts.append('<figure><figcaption>%s</figcaption>'
                             '<p class="miss">снимка нет</p></figure>' % label)
        parts.append('</div></div>')
    parts.append('</div>')
    with open(OUT, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(parts))
    print('готово:', os.path.relpath(OUT, ROOT))


if __name__ == '__main__':
    main()
