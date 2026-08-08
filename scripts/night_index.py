"""
Контактный лист ночной сессии — reports/night/index.html.

Открывается ДВОЙНЫМ КЛИКОМ, без сервера: все пути относительные, картинки
лежат рядом. Порядок намеренный: сначала ключевой экран из стоп-гейта, потом
экраны по фазам, потом сквозной сценарий шаг за шагом.

Запуск из корня проекта:  ./venv/bin/python scripts/night_index.py
"""
import html
import io
import json
import os

ROOT = 'reports/night'

# Порядок и подписи разделов. Ключ — папка внутри reports/night.
SECTIONS = [
    ('01-styleguide', 'Фаза 1. Набор деталей',
     'Кнопки, поля, карточки, пометки состояния, крупный балл, плитки, '
     'разделитель. Из этого собраны все экраны.'),
    ('05-print', 'Фаза 5. Печатный листок',
     'Подпункты буквами, место под решение по весу задачи, шапка в одну '
     'строку, свой подвал, галочка у верного варианта.'),
    ('06-item-card', 'Фаза 6. Карточка позиции задания',
     'Левая рейка с крупным баллом, заголовок задачи, единый блок состояния '
     'проверки вместо бейджа и отдельных кнопок.'),
    ('09-block-a', 'Фаза 9. Проверка блока А', ''),
    ('10-group-overview', 'Фаза 10. Вход в группу — обзор',
     'Вкладок три, статистика стала первой, таблица учеников одна.'),
    ('11-assignments-tab', 'Фаза 11. Вкладка «Задания»',
     'Три группы по состоянию: требуют вас, идут сейчас, завершены.'),
    ('12-submissions-summary', 'Фаза 12. Сводка решений',
     'Карточки по ученикам вместо таблицы из 21 строки. Второй вид — '
     'прежняя таблица.'),
    ('13-review', 'Фаза 13. Проверка работы',
     'Поток по работе одного ученика: ответ и эталон рядом, балл нажатием, '
     'экран завершения с общим комментарием.'),
    ('14-block-b', 'Фаза 14. Проверка блока Б',
     'Все четыре экрана в трёх ширинах и двух темах.'),
    ('15-create-modes', 'Фаза 15. Три способа собрать задание', ''),
    ('16-create-catalog', 'Фаза 16. Режим «Искать самому»', ''),
    ('17-generate-form', 'Фаза 17. Подбор: форма запроса', ''),
    ('18-generate-found', 'Фаза 18. Подбор: что нашлось',
     'ДО и ПОСЛЕ. Два голых числа получили подписи.'),
    ('19-exam-generate', 'Фаза 19. Контрольная по описанию', ''),
]

KEY_SHOT = '06-item-card/КЛЮЧЕВОЙ-ЭКРАН.png'

CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; font: 15px/1.6 -apple-system, BlinkMacSystemFont,
       'Segoe UI', sans-serif; background: #f5f5f3; color: #1a1a1a; }
@media (prefers-color-scheme: dark) {
  body { background: #10141c; color: #e7e9ef; }
  .card, .key { background: #161b25; border-color: rgba(255,255,255,.13); }
  a { color: #FF4D94; }
  .cap, .sub { color: #a7aebc; }
}
.wrap { max-width: 1100px; margin: 0 auto; padding: 32px 20px 80px; }
h1 { font-size: 26px; margin: 0 0 6px; }
.sub { color: #5b6472; font-size: 14px; margin-bottom: 26px; }
h2 { font-size: 18px; margin: 34px 0 4px; }
.cap { color: #5b6472; font-size: 13px; margin-bottom: 12px; }
.grid { display: grid; gap: 14px;
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); }
.card, .key { background: #fff; border: 1px solid rgba(22,26,38,.12);
              border-radius: 10px; overflow: hidden; }
.key { border-color: #BE185D; border-width: 2px; margin-bottom: 10px; }
.card img, .key img { width: 100%; display: block; }
.name { font-size: 12px; padding: 8px 10px; color: #5b6472;
        overflow-wrap: anywhere; }
a { color: #BE185D; }
.step { display: flex; gap: 16px; align-items: flex-start; margin-bottom: 18px;
        flex-wrap: wrap; }
.step .card { flex: 1 1 460px; }
.step p { flex: 1 1 240px; margin: 0; font-size: 14px; }
"""


def images(folder):
    path = os.path.join(ROOT, folder)
    if not os.path.isdir(path):
        return []
    return sorted(f for f in os.listdir(path) if f.endswith('.png'))


def card(src, name):
    return (
        '<a class="card" href="%s" style="text-decoration:none;display:block">'
        '<img src="%s" alt="%s" loading="lazy">'
        '<div class="name">%s</div></a>'
        % (src, src, html.escape(name), html.escape(name)))


def main():
    out = ['<!doctype html><meta charset="utf-8">',
           '<title>Ночная сессия: кабинет преподавателя</title>',
           '<style>%s</style>' % CSS, '<div class="wrap">',
           '<h1>Ночная сессия: кабинет преподавателя</h1>',
           '<p class="sub">Контактный лист. Снимок открывается по клику. '
           'Порядок: сначала ключевой экран, потом экраны по фазам, '
           'потом сквозной сценарий.</p>']

    # Ключевой экран — первым и крупно.
    if os.path.exists(os.path.join(ROOT, KEY_SHOT)):
        out.append('<h2>🛑 Ключевой экран — карточка позиции задания</h2>')
        out.append('<p class="cap">От неё зависят фазы 10–13 и 15–19. '
                   'Светлая и тёмная тема рядом. Если этот экран не '
                   'понравится, откатывать надо именно его коммит.</p>')
        out.append('<div class="key"><img src="%s" alt="ключевой экран"></div>'
                   % KEY_SHOT)

    for folder, title, caption in SECTIONS:
        files = images(folder)
        if not files:
            continue
        out.append('<h2>%s</h2>' % html.escape(title))
        if caption:
            out.append('<p class="cap">%s</p>' % html.escape(caption))
        out.append('<div class="grid">')
        for name in files:
            out.append(card('%s/%s' % (folder, name), name))
        out.append('</div>')

    # Сквозной сценарий — шаг за шагом, с подписями из самого прогона.
    steps_file = os.path.join(ROOT, '20-end-to-end', 'steps.json')
    if os.path.exists(steps_file):
        steps = json.load(io.open(steps_file, encoding='utf-8'))
        out.append('<h2>Фаза 20. Сквозной сценарий</h2>')
        out.append('<p class="cap">Собрать работу подбором → раздать группе → '
                   'сдать за ученика → проверить. Шаг за шагом.</p>')
        for step in steps:
            out.append('<div class="step">')
            out.append(card('20-end-to-end/%s' % step['file'], step['file']))
            out.append('<p>%s</p>' % html.escape(step['caption']))
            out.append('</div>')

    out.append('</div>')
    io.open(os.path.join(ROOT, 'index.html'), 'w',
            encoding='utf-8').write('\n'.join(out))
    print('готово: %s/index.html' % ROOT)


if __name__ == '__main__':
    main()
