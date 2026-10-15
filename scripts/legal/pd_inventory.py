# -*- coding: utf-8 -*-
"""Инвентаризация персональных данных и внешних отправок (08.10.2026).

ТОЛЬКО ЧИТАЕТ: ни базы, ни сети, ни файлов проекта не меняет. Базу не
открывает вовсе — модели берутся из реестра Django (`apps.get_models()`),
код — разбором текста и синтаксического дерева Python. Секретов не печатает:
переменные окружения не читает (имена переменных в коде — да, значения — нет).

Отчёт, ради которого скрипт написан: docs/legal/PD_INVENTORY_20261008.md.
Числа инвариантов в отчёте получены этим скриптом.

Запуск из корня проекта (любой интерпретатор, где ставится проект):

    python -X utf8 scripts/legal/pd_inventory.py models     # фаза 1
    python -X utf8 scripts/legal/pd_inventory.py outbound   # фаза 2: места вызова
    python -X utf8 scripts/legal/pd_inventory.py ai         # фаза 2: кто зовёт слой ИИ
    python -X utf8 scripts/legal/pd_inventory.py imports    # фаза 2: сверка по импортам
    python -X utf8 scripts/legal/pd_inventory.py cookies    # фаза 3: куки в коде
    python -X utf8 scripts/legal/pd_inventory.py storage    # фаза 3: localStorage/sessionStorage
    python -X utf8 scripts/legal/pd_inventory.py hosts      # фаза 3: чужие адреса в шаблонах и JS
    python -X utf8 scripts/legal/pd_inventory.py latin      # фаза 5: латиница на экране
    python -X utf8 scripts/legal/pd_inventory.py words      # фаза 5: «курс», «обучение»…
    python -X utf8 scripts/legal/pd_inventory.py all

⚠️ Правила отбора записаны прямо в коде ниже (PATTERNS, PD_FIELD, SKIP_DIRS):
число в отчёте честно ровно настолько, насколько честны эти правила.
"""
import ast
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Каталоги, которые не являются кодом проекта или не идут в счёт.
SKIP_DIRS = {'.git', '.claude', 'node_modules', '__pycache__', 'staticfiles',
             'venv', 'venv311', 'venv312', 'venv313', '.venv', 'media',
             'deploy_fixtures'}


def _rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, '/')


def _walk(exts):
    """Файлы проекта с нужными расширениями, по алфавиту (повторяемый вывод)."""
    found = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS
                         and not d.startswith('venv'))
        for name in sorted(files):
            if name.endswith(exts):
                found.append(os.path.join(base, name))
    return found


def _is_test(rel):
    return ('/tests/' in rel or rel.startswith('tests/')
            or os.path.basename(rel).startswith('test_'))


def _kind_of(rel):
    """Где живёт код: от этого зависит, может ли он сработать на бою."""
    if rel.startswith(('scripts/', 'tools/', 'reports/', 'claude/', 'data/')):
        return 'офлайн-скрипт'
    if rel.startswith('search_service/'):
        return 'сервис поиска (контейнер search)'
    if '/management/commands/' in rel:
        return 'команда manage.py'
    if '/' not in rel:
        return 'файл в корне'
    return 'код сайта'


def _read(path):
    with open(path, encoding='utf-8', errors='replace') as handle:
        return handle.read()


# ─── Фаза 1. Модели ──────────────────────────────────────────────────────

# Поля «без ключа на User», по которым модель всё равно попадает в список
# (задание: ip / user_agent / session / email / phone / name). Совпадение —
# по слову в имени поля через подчёркивание: `session_key`, `region_name`.
PD_FIELD = re.compile(
    r'(^|_)(ip|ip_address|remote_addr|user_agent|session|session_key|email|'
    r'phone|name)($|_)')


def _setup_django():
    sys.path.insert(0, ROOT)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()


def _relation_fields(model):
    """Прямые ссылки модели: FK, OneToOne и явные M2M (без обратных)."""
    out = []
    for field in model._meta.get_fields():
        if not field.is_relation or field.related_model is None:
            continue
        if field.concrete or (field.many_to_many and not field.auto_created):
            out.append(field)
    return out


def _field_type(field):
    return type(field).__name__.replace('Field', '') or type(field).__name__


def collect_models():
    """Модели, связанные с человеком, по правилам задания. Без записи в базу."""
    from django.apps import apps
    from django.conf import settings

    user_model = apps.get_model(settings.AUTH_USER_MODEL)
    models = apps.get_models()          # без автосозданных M2M-таблиц
    rows = {}

    # 1) сама модель пользователя
    rows[user_model] = {'group': 'пользователь', 'path': '—'}
    # 2) прямой ключ на User
    for model in models:
        hits = [f for f in _relation_fields(model) if f.related_model is user_model]
        if hits and model is not user_model:
            rows[model] = {'group': 'прямой ключ на User',
                           'path': ', '.join(
                               '%s (%s)' % (f.name, _field_type(f)) for f in hits)}
    # 3) транзитивно: ключ на модель, уже попавшую в список
    changed = True
    while changed:
        changed = False
        for model in models:
            if model in rows:
                continue
            for field in _relation_fields(model):
                target = field.related_model
                if target in rows:
                    path = '%s → %s' % (field.name, target._meta.label)
                    rows[model] = {'group': 'транзитивно', 'path': path}
                    changed = True
                    break
    # 4) без ключа на User, но с полем по шаблону
    for model in models:
        if model in rows:
            continue
        hits = [f.name for f in model._meta.get_fields()
                if getattr(f, 'concrete', False) and PD_FIELD.search(f.name)]
        if hits:
            rows[model] = {'group': 'без ключа, поле по шаблону',
                           'path': 'поля: ' + ', '.join(hits)}
    return models, rows, user_model


def _plain_fields(model):
    """Обычные (не связи) поля модели с типами — сырьё для колонки «данные»."""
    out = []
    for field in model._meta.get_fields():
        if not getattr(field, 'concrete', False) or field.is_relation:
            continue
        if field.primary_key:
            continue
        out.append('%s:%s' % (field.name, _field_type(field)))
    return out


def _user_on_delete(model, user_model):
    """Что станет со строкой при удалении человека: CASCADE / SET_NULL / …"""
    out = []
    for field in _relation_fields(model):
        if field.related_model is user_model and not field.many_to_many:
            rule = getattr(field.remote_field, 'on_delete', None)
            out.append('%s=%s' % (field.name, getattr(rule, '__name__', '?')))
    return ', '.join(out) or '—'


def cmd_models():
    _setup_django()
    models, rows, user_model = collect_models()
    order = ['пользователь', 'прямой ключ на User', 'транзитивно',
             'без ключа, поле по шаблону']
    print('Моделей в реестре (без автосозданных M2M-таблиц): %d' % len(models))
    for group in order:
        print('  %-28s %d' % (group, sum(1 for r in rows.values()
                                         if r['group'] == group)))
    print('ИТОГО МОДЕЛЕЙ В ТАБЛИЦЕ: %d' % len(rows))
    print('Не попали (нет ни ключа, ни поля по шаблону): %d' % (len(models) - len(rows)))
    print()
    number = 0
    for group in order:
        for model in sorted((m for m, r in rows.items() if r['group'] == group),
                            key=lambda m: m._meta.label):
            number += 1
            row = rows[model]
            files = [f.name for f in model._meta.get_fields()
                     if getattr(f, 'concrete', False)
                     and type(f).__name__ in ('FileField', 'ImageField')]
            print('%3d. %s  [%s]' % (number, model._meta.label, group))
            print('     связь: %s' % row['path'])
            print('     удаление человека: %s' % _user_on_delete(model, user_model))
            print('     поля: %s' % ', '.join(_plain_fields(model)))
            if files:
                print('     ФАЙЛЫ: %s' % ', '.join(files))
    print()
    print('Не попали в таблицу:')
    for model in sorted(set(models) - set(rows), key=lambda m: m._meta.label):
        print('   - %s' % model._meta.label)


# ─── Фаза 2. Места сетевых вызовов ───────────────────────────────────────

# Вызов считается сетевым, если его полное имя совпадает с одним из шаблонов.
# Ищется ВЫЗОВ в синтаксическом дереве, а не строка текста: упоминание в
# докстринге или комментарии в счёт не идёт.
PATTERNS = [
    (r'(^|\.)messages\.(create|stream)$', 'SDK Anthropic: messages'),
    (r'(^|\.)messages\.batches\.(create|retrieve|results|list|cancel)$',
     'SDK Anthropic: Batch API'),
    (r'(^|\.)responses\.create$', 'SDK OpenAI: Responses API'),
    (r'(^|\.)chat\.completions\.create$', 'SDK openai: chat.completions'),
    (r'(^|\.)(?<!messages\.)batches\.(create|retrieve|list|cancel)$',
     'SDK OpenAI: Batch API'),
    (r'(^|\.)files\.(create|content|retrieve)$', 'SDK OpenAI: файлы'),
    (r'(^|\.)embeddings\.create$', 'SDK: embeddings'),
    (r'(^|\.)(urlopen|urlretrieve)$', 'urllib'),
    (r'^requests\.(get|post|put|patch|delete|head|request|Session)$', 'requests'),
    (r'^httpx\.(get|post|put|patch|delete|request|stream|Client|AsyncClient)$',
     'httpx'),
    (r'^aiohttp\.ClientSession$', 'aiohttp'),
    (r'(^|\.)HTTPS?Connection$', 'http.client'),
    (r'^smtplib\.SMTP(_SSL)?$', 'почта: smtplib'),
    (r'(^|\.)(send_mail|send_mass_mail|mail_admins|mail_managers)$',
     'почта: Django'),
    (r'(^|\.)(EmailMessage|EmailMultiAlternatives)$', 'почта: Django'),
    (r'(^|\.)SentenceTransformer$', 'загрузка модели (Hugging Face)'),
    (r'(^|\.)(snapshot_download|hf_hub_download|from_pretrained)$',
     'загрузка модели (Hugging Face)'),
    (r'^socket\.create_connection$', 'socket'),
    # Запрос к DNS тоже уходит наружу — к резолверу сервера, а обратный
    # (PTR) несёт сам адрес посетителя.
    (r'^socket\.(gethostbyaddr|getaddrinfo|gethostbyname(_ex)?)$', 'DNS'),
]
_COMPILED = [(re.compile(p), label) for p, label in PATTERNS]
_SUBPROCESS_NET = ('curl', 'wget')


def _dotted(node):
    """Полное имя вызываемого: `client.chat.completions.create`."""
    parts = []
    while True:
        if isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Subscript):
            parts.append('[]')
            node = node.value
        elif isinstance(node, ast.Call):
            parts.append('()')
            node = node.func
        elif isinstance(node, ast.Name):
            parts.append(node.id)
            break
        else:
            parts.append('?')
            break
    return '.'.join(reversed(parts)).replace('.[]', '[]').replace('.()', '()')


class _Scanner(ast.NodeVisitor):
    """Обходит дерево и запоминает, внутри какой функции стоит вызов."""

    def __init__(self, on_call):
        self.stack = []
        self.on_call = on_call

    def _scope(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scope

    def visit_Call(self, node):
        self.on_call(node, '.'.join(self.stack) or '<модуль>')
        self.generic_visit(node)


def _py_files(include_tests=False):
    for path in _walk(('.py',)):
        rel = _rel(path)
        if '/migrations/' in rel:
            continue
        if not include_tests and _is_test(rel):
            continue
        yield path, rel


def _parse(path):
    try:
        return ast.parse(_read(path), filename=path)
    except SyntaxError:
        return None


def collect_outbound():
    found = []
    for path, rel in _py_files():
        tree = _parse(path)
        if tree is None:
            continue

        def on_call(node, scope, rel=rel):
            name = _dotted(node.func)
            label = next((lab for rx, lab in _COMPILED if rx.search(name)), None)
            if label is None and name.startswith('subprocess.') and node.args:
                first = node.args[0]
                if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
                    first = first.elts[0]
                if (isinstance(first, ast.Constant) and isinstance(first.value, str)
                        and first.value.split()[0] in _SUBPROCESS_NET):
                    label = 'subprocess: ' + first.value.split()[0]
            if label:
                found.append((rel, node.lineno, scope, name, label, _kind_of(rel)))

        _Scanner(on_call).visit(tree)
    return found


def cmd_outbound():
    found = collect_outbound()
    by_kind = Counter(row[5] for row in found)
    print('МЕСТ СЕТЕВОГО ВЫЗОВА: %d' % len(found))
    for kind, count in sorted(by_kind.items()):
        print('  %-36s %d' % (kind, count))
    print()
    for number, (rel, line, scope, name, label, kind) in enumerate(found, 1):
        print('%3d. %s:%d  %s  ← %s  [%s; %s]' % (number, rel, line, name,
                                                  scope, label, kind))


AI_CALL = re.compile(
    r'((^|\.)(core|ai)\.run$|(^|\.)record_usage$|(^|\.)(provider|_provider)'
    r'(\(\))?\.complete$|providers\[\]\.complete$|^(ai_)?run_profile$)')


def cmd_ai():
    """Кто отправляет текст через слой ИИ (`problems/ai`): точки входа."""
    rows = []
    for path, rel in _py_files():
        if rel.startswith('problems/ai/'):
            continue
        tree = _parse(path)
        if tree is None:
            continue

        def on_call(node, scope, rel=rel):
            name = _dotted(node.func)
            if AI_CALL.search(name):
                rows.append((rel, node.lineno, scope, name, _kind_of(rel)))

        _Scanner(on_call).visit(tree)
    print('ВЫЗОВОВ СЛОЯ ИИ (вне problems/ai/): %d' % len(rows))
    for kind, count in sorted(Counter(r[4] for r in rows).items()):
        print('  %-36s %d' % (kind, count))
    print()
    for number, (rel, line, scope, name, kind) in enumerate(rows, 1):
        print('%3d. %s:%d  %s  ← %s  [%s]' % (number, rel, line, name, scope, kind))


NET_MODULES = ('requests', 'httpx', 'aiohttp', 'urllib.request', 'urllib3',
               'http.client', 'socket', 'smtplib', 'anthropic', 'openai',
               'zhipuai', 'zai', 'telegram', 'aiogram', 'telebot', 'boto3',
               'botocore', 'sentence_transformers', 'huggingface_hub',
               'transformers', 'websocket', 'websockets', 'sentry_sdk',
               'yandex', 'google', 'paramiko', 'ftplib')


def cmd_imports():
    """Файлы, импортирующие сетевые библиотеки, и сколько в них найдено мест.

    Нужна для сверки полноты: файл с импортом и с нулём найденных вызовов
    разбирается руками (вызов мог уйти через переменную или обёртку).
    """
    calls = Counter(row[0] for row in collect_outbound())
    rows = []
    for path, rel in _py_files():
        tree = _parse(path)
        if tree is None:
            continue
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module] + ['%s.%s' % (node.module, a.name)
                                         for a in node.names]
            else:
                continue
            for name in names:
                for mod in NET_MODULES:
                    if name == mod or name.startswith(mod + '.'):
                        mods.add(mod)
        if mods:
            rows.append((rel, sorted(mods), calls.get(rel, 0), _kind_of(rel)))
    print('ФАЙЛОВ С СЕТЕВЫМИ ИМПОРТАМИ: %d' % len(rows))
    print('из них без найденного места вызова: %d' % sum(1 for r in rows if not r[2]))
    print()
    for rel, mods, count, kind in rows:
        print('%-70s вызовов=%d  %s  [%s]' % (rel, count, ','.join(mods), kind))


# ─── Фаза 3. Куки, хранилище браузера, чужие адреса ──────────────────────

_FRONT_EXT = ('.html', '.js', '.mjs')


def _front_files():
    """Шаблоны и скрипты, которые видит браузер (без офлайн-скриптов и тестов)."""
    for path in _walk(_FRONT_EXT):
        rel = _rel(path)
        if rel.startswith(('scripts/', 'tools/', 'reports/', 'claude/', 'data/',
                           'docs/')) or _is_test(rel) or '/tests/' in rel:
            continue
        yield path, rel


def cmd_cookies():
    print('— Python: set_cookie / set_signed_cookie / delete_cookie')
    for path, rel in _py_files():
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _dotted(node.func)
                if re.search(r'(^|\.)(set_cookie|set_signed_cookie|delete_cookie|'
                             r'get_signed_cookie)$', name):
                    arg = node.args[0] if node.args else None
                    shown = ast.unparse(arg) if arg is not None else '?'
                    print('  %s:%d  %s(%s)' % (rel, node.lineno, name, shown))
        for line_no, line in enumerate(_read(path).splitlines(), 1):
            if re.search(r'COOKIE_NAME\s*=|COOKIE\s*=\s*[\'"]', line) and not line.strip().startswith('#'):
                print('  %s:%d  %s' % (rel, line_no, line.strip()[:120]))
    print('— шаблоны и JS: document.cookie')
    for path, rel in _front_files():
        for line_no, line in enumerate(_read(path).splitlines(), 1):
            if 'document.cookie' in line:
                print('  %s:%d  %s' % (rel, line_no, line.strip()[:140]))


_STORAGE = re.compile(r'\b(localStorage|sessionStorage)\b')


def cmd_storage():
    total = 0
    for path, rel in _front_files():
        for line_no, line in enumerate(_read(path).splitlines(), 1):
            if _STORAGE.search(line):
                total += 1
                print('  %s:%d  %s' % (rel, line_no, line.strip()[:160]))
    print('СТРОК С localStorage/sessionStorage: %d' % total)


_HOST = re.compile(r'(?:https?:)?//([a-z0-9.-]+\.[a-z]{2,})(?=[/:"\'\s?#)]|$)', re.I)
_OWN = ('weconomics.site', 'weconomics.ai', 'dev.weconomics.ai', 'localhost',
        '127.0.0.1', 'www.w3.org', 'example.com', 'example.org')


def cmd_hosts():
    """Чужие домены в шаблонах и JS: кандидаты на загрузку браузером."""
    hits = defaultdict(set)
    for path, rel in _front_files():
        for line_no, line in enumerate(_read(path).splitlines(), 1):
            for host in _HOST.findall(line):
                host = host.lower()
                if host.endswith(_OWN) or host in _OWN:
                    continue
                hits[host].add('%s:%d' % (rel, line_no))
    print('ЧУЖИХ ДОМЕНОВ В ШАБЛОНАХ И JS: %d' % len(hits))
    for host in sorted(hits):
        places = sorted(hits[host])
        print('  %-36s %3d  %s' % (host, len(places), '; '.join(places[:4])))


# ─── Фаза 5. Латиница и «образовательные» слова ─────────────────────────

_CYR = re.compile('[А-Яа-яЁё]')
_LAT = re.compile('[A-Za-z]')
_TEMPLATE_CODE = re.compile(r'{%.*?%}|{{.*?}}|{#.*?#}', re.S)
_HIDDEN_BLOCKS = re.compile(
    r'<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->|'
    r'{%\s*comment\s*%}.*?{%\s*endcomment\s*%}', re.S | re.I)
_VISIBLE_ATTR = re.compile(
    r'\b(?:alt|title|placeholder|aria-label|data-hint|value)\s*=\s*"([^"]*)"', re.I)
_TAG = re.compile(r'<[^>]+>')
_BRANDS = re.compile(r'\bWecon(omics)?\b|\bWecon Rush\b', re.I)
# Технические строки, которые на экран не попадают как слова.
_NOT_TEXT = re.compile(r'^[\W\d_]*$|^&\w+;$|^[a-z]+\([^)]*\)$')


def _template_texts(source):
    """(текст, тип) всего, что человек видит в шаблоне: узлы и атрибуты."""
    cleaned = _HIDDEN_BLOCKS.sub(' ', source)
    for value in _VISIBLE_ATTR.findall(cleaned):
        value = _TEMPLATE_CODE.sub(' ', value).strip()
        if value:
            yield value, 'атрибут'
    cleaned = _TEMPLATE_CODE.sub(' ', cleaned)
    for chunk in _TAG.split(cleaned):
        chunk = ' '.join(chunk.split())
        if chunk:
            yield chunk, 'текст'


_JS_STRING = re.compile(r"'((?:[^'\\\n]|\\.){2,})'|\"((?:[^\"\\\n]|\\.){2,})\"|"
                        r"`((?:[^`\\]|\\.){2,})`")
# Строка JS выводится на экран, только если рядом стоит одно из этих слов:
# присваивание текста, подписи, всплывающие окна. Иначе это код.
_JS_UI_CONTEXT = re.compile(
    r'(textContent|innerText|innerHTML|insertAdjacentHTML|\.title\b|title\s*:|'
    r'placeholder|aria-label|\balt\b|label\s*:|text\s*:|caption|hint\s*:|'
    r'alert\(|confirm\(|prompt\(|toast|setAttribute\(\s*[\'"](title|aria-label|'
    r'placeholder|alt|data-hint)[\'"])')
# Служебные имена, которые на экран не попадают: клавиши, теги, события.
_JS_NOT_UI = re.compile(
    r'^(use strict|Enter|Escape|Esc|Tab|Space|Backspace|Delete|Home|End|'
    r'Page(Up|Down)|Arrow(Up|Down|Left|Right)|Shift|Control|Alt|Meta|'
    r'INPUT|TEXTAREA|SELECT|BUTTON|SCRIPT|STYLE|DOMContentLoaded|'
    r'XMLHttpRequest|HTTP|NaN|Infinity|[A-Za-z]+Node)$')
_ENTITY = re.compile(r'&#?\w+;')
# Признаки кода внутри строки JS: имя класса через дефис, одиночное
# строчное слово (значение свойства, тег, тип), куски выражений.
_JS_CODE_LIKE = re.compile(
    r'^[a-z][a-z0-9]*(-[a-z0-9]+)+$|^[a-z][a-z0-9]*$|^[a-z]+[A-Z]\w*$|'
    r'^\.|[;{}=#]\s*|\+\s*\w+\(|^[,)\s]|^\w+-[A-Z]{2}$|^[a-z]{2}-[a-z]{2}$')
# Только латиница, цифры, пробелы и знаки: «надпись на латинице».
_LATIN_ONLY = re.compile(r"^[A-Za-z0-9\s.,:;!?'’\"«»()\-–—/+*^=%&|·…]+$")


def _is_latin_text(text):
    text = _ENTITY.sub(' ', text).strip()
    return bool(text and _LAT.search(text) and not _CYR.search(text)
                and _LATIN_ONLY.match(text) and not _NOT_TEXT.match(text))


def _js_sources(rel, source):
    if rel.endswith(('.js', '.mjs')):
        return [source]
    return re.findall(r'<script\b[^>]*>(.*?)</script>', source, re.S | re.I)


def _latin_hits():
    """(файл, вид, текст) — надписи только на латинице, которые видит человек.

    Шаблоны: текст между тегами и видимые атрибуты. JS: строки рядом со
    словами из `_JS_UI_CONTEXT`. Библиотеки `static/vendor/` не считаются —
    это чужой код, его строки видны, только если библиотека их показывает.
    """
    hits = []
    for path, rel in _front_files():
        if rel.startswith('static/vendor/') or 'review_bundle' in rel:
            continue
        source = _read(path)
        if rel.endswith('.html'):
            for text, kind in _template_texts(source):
                if _is_latin_text(text):
                    hits.append((rel, kind, ' '.join(_ENTITY.sub(' ', text).split())))
        for js in _js_sources(rel, source):
            js = re.sub(r'/\*.*?\*/', ' ', js, flags=re.S)
            for line in js.splitlines():
                line = re.sub(r'(^|\s)//.*$', ' ', line)
                if not _JS_UI_CONTEXT.search(line):
                    continue
                for a, b, c in _JS_STRING.findall(line):
                    text = re.sub(r'<[^>]+>|\$\{[^}]*\}', ' ', a or b or c)
                    text = ' '.join(text.split())
                    if (_is_latin_text(text) and not _JS_NOT_UI.match(text)
                            and not _JS_CODE_LIKE.search(text)):
                        hits.append((rel, 'строка JS', text))
    return hits


def _brand_mentions():
    """Упоминания брендов во ВСЁМ видимом тексте шаблонов, с кириллицей тоже."""
    found = Counter()
    for path, rel in _front_files():
        if rel.startswith('static/vendor/') or not rel.endswith('.html'):
            continue
        for text, _kind in _template_texts(_read(path)):
            for match in re.findall(r'Wecon Rush|Weconomics|Wecon', text):
                found[match] += 1
    return found


def cmd_latin():
    hits = _latin_hits()
    brand = [h for h in hits if _BRANDS.search(h[2])]
    other = [h for h in hits if not _BRANDS.search(h[2])]
    print('ВХОЖДЕНИЙ НАДПИСЕЙ ТОЛЬКО НА ЛАТИНИЦЕ: %d' % len(hits))
    print('  из них Weconomics / Wecon Rush: %d' % len(brand))
    print('  прочих: %d (шаблоны: %d, строки JS: %d)' % (
        len(other), sum(1 for h in other if h[1] != 'строка JS'),
        sum(1 for h in other if h[1] == 'строка JS')))
    counts = Counter(h[2] for h in other)
    files = defaultdict(set)
    kinds = defaultdict(set)
    for rel, kind, text in other:
        files[text].add(rel)
        kinds[text].add(kind)
    print('РАЗНЫХ НАДПИСЕЙ (прочих): %d' % len(counts))
    print()
    for text, count in counts.most_common():
        print('%4d  %-40s [%s] %s' % (count, text[:40], ','.join(sorted(kinds[text])),
                                      '; '.join(sorted(files[text])[:3])))
    print()
    print('— бренды отдельной строкой (только латиница):')
    for text, count in Counter(h[2] for h in brand).most_common():
        print('%4d  %s' % (count, text[:80]))
    print('— бренды во всём видимом тексте шаблонов (с кириллицей рядом):')
    for name, count in _brand_mentions().most_common():
        print('%4d  %s' % (count, name))


WORDS = [('курс', re.compile(r'\bкурс(а|у|ом|е|ы|ов|ам|ами|ах)?\b', re.I)),
         ('обучение', re.compile(r'\bобучени[еяюи]м?\b|\bобучению\b', re.I)),
         ('сертификат', re.compile(r'\bсертификат\w*', re.I)),
         ('программа обучения', re.compile(r'программ\w* обучения', re.I))]


def cmd_words():
    for label, rx in WORDS:
        total = 0
        per_file = Counter()
        for path in _walk(('.html',)):
            rel = _rel(path)
            # data/ — скачанные чужие страницы (правила олимпиад, сайты вузов),
            # а не шаблоны сайта: их никто на нашем сайте не видит.
            if rel.startswith(('scripts/', 'reports/', 'claude/', 'docs/', 'tools/',
                               'data/', 'static/vendor/')):
                continue
            source = _read(path)
            count = len(rx.findall(source))
            if count:
                per_file[rel] += count
                total += count
                for line_no, line in enumerate(source.splitlines(), 1):
                    if rx.search(line):
                        print('       %s:%d  %s' % (rel, line_no, line.strip()[:110]))
        print('«%s»: %d вхождений в %d файлах' % (label, total, len(per_file)))
        for rel, count in sorted(per_file.items()):
            print('     %3d  %s' % (count, rel))


COMMANDS = {'models': cmd_models, 'outbound': cmd_outbound, 'ai': cmd_ai,
            'imports': cmd_imports, 'cookies': cmd_cookies,
            'storage': cmd_storage, 'hosts': cmd_hosts, 'latin': cmd_latin,
            'words': cmd_words}


def main(argv):
    wanted = argv[1:] or ['all']
    if wanted == ['all']:
        wanted = list(COMMANDS)
    for name in wanted:
        if name not in COMMANDS:
            print('Неизвестный режим: %s. Есть: %s' % (name, ', '.join(COMMANDS)))
            return 2
        print('=' * 72)
        print('РЕЖИМ %s' % name)
        print('=' * 72)
        COMMANDS[name]()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
