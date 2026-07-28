"""Категории вердиктов ручного ревью внешнего вида задач.

ЕДИНСТВЕННАЯ точка правды для списка категорий. Отсюда читают:
- модель ReviewVerdict (choices),
- экспортёр export_review_bundle (кладёт список в manifest.json/manifest.js,
  оболочка reviewer.html строит кнопки и горячие клавиши ИЗ манифеста),
- импортёр import_review_verdicts (валидация категории при импорте).

Ничего не хардкодить в reviewer.html или командах — только этот список.
Менять ключи (key) после начала ревью нельзя: они уже лежат в вердиктах.
"""

# kind: 'ok' — задача идеальна; 'defect' — категория дефекта; 'disputed' — спорно;
#       'trash' — задачу выбрасываем целиком.
#
# Взаимоисключающие виды ('ok' и 'trash') — вердикт из одного нажатия: он
# отменяет всё выбранное и сразу уводит к следующей задаче. Остальные виды
# (дефекты и «Спорно») выбираются ПАЧКОЙ: нажатие переключает, Enter
# подтверждает. Перечислять дефекты у выброшенной задачи бессмысленно, а
# «идеально и сломанная формула» — противоречие, поэтому они и исключающие.
EXCLUSIVE_KINDS = ('ok', 'trash')

REVIEW_CATEGORIES = [
    {'key': 'perfect',          'hotkey': '1', 'kind': 'ok',
     'label': 'Идеально'},
    {'key': 'broken_formula',   'hotkey': '2', 'kind': 'defect',
     'label': 'Сломанная формула'},
    {'key': 'bare_math',        'hotkey': '3', 'kind': 'defect',
     'label': 'Голая математика / $'},
    {'key': 'merged_structure', 'hotkey': '4', 'kind': 'defect',
     'label': 'Слипшийся список или структура'},
    {'key': 'leaked_solution',  'hotkey': '5', 'kind': 'defect',
     'label': 'Утёкшее «Решение:/Ответ:»'},
    {'key': 'junk',             'hotkey': '6', 'kind': 'defect',
     'label': 'Мусор (колонтитулы, номера страниц, обрубки)'},
    {'key': 'broken_table',     'hotkey': '7', 'kind': 'defect',
     'label': 'Развалившаяся таблица'},
    {'key': 'other',            'hotkey': '8', 'kind': 'defect',
     'label': 'Прочее (с комментарием)'},
    {'key': 'disputed',         'hotkey': '9', 'kind': 'disputed',
     'label': 'Спорно'},
    # Клавиша «0» — намеренно ДАЛЬНЯЯ от «1»: промах по соседней клавише не
    # должен превращать идеальную задачу в выброшенную и наоборот.
    {'key': 'trash',            'hotkey': '0', 'kind': 'trash',
     'label': 'Гагно', 'hint': 'в мусор целиком'},
]

CATEGORY_KEYS = [c['key'] for c in REVIEW_CATEGORIES]
CATEGORY_CHOICES = [(c['key'], c['label']) for c in REVIEW_CATEGORIES]
CATEGORY_LABELS = {c['key']: c['label'] for c in REVIEW_CATEGORIES}
EXCLUSIVE_KEYS = [c['key'] for c in REVIEW_CATEGORIES if c['kind'] in EXCLUSIVE_KINDS]

# Версии форматов файлов — сверяются при импорте, чтобы не съесть чужой JSON.
BUNDLE_FORMAT = 'qls-review-bundle-v1'
# v1: у вердикта одна category (строка). v2: список categories.
# Импорт понимает ОБА — 2 401 вердикт по ILE лежат в v1 и переводу не подлежат.
VERDICTS_FORMAT_V1 = 'qls-review-verdicts-v1'
VERDICTS_FORMAT = 'qls-review-verdicts-v2'
VERDICTS_FORMATS = (VERDICTS_FORMAT_V1, VERDICTS_FORMAT)
