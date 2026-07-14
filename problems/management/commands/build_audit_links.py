"""
Кликабельный HTML-индекс дефектных задач (из clean_audit.txt) со ссылками на страницы
этих задач на локальном сайте, сгруппированный по типу дефекта. Только чтение.
"""
import re
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.urls import reverse, NoReverseMatch

BASE = "http://127.0.0.1:8000"
CAT_RU = {
    "missing_figure": "Пропал рисунок/таблица", "ocr_corruption": "OCR-порча текста",
    "broken_latex": "Битая формула", "duplicated": "Задвоение",
    "truncated": "Обрыв текста", "other": "Прочее", "parse_error": "Ответ не разобран",
}


def problem_path(pid: int) -> str:
    return reverse("catalog:problem_detail", args=[pid])


class Command(BaseCommand):
    help = "HTML-индекс дефектных задач со ссылками на локальный сайт. Только чтение."

    def add_arguments(self, parser):
        parser.add_argument("--audit", type=str, default="clean_audit.txt")
        parser.add_argument("--out", type=str, default="audit_links.html")

    def handle(self, *args, **opts):
        pat = re.compile(r"ЗАДАЧА #(\d+)\s*\|\s*(.*?)\s*\|\s*([a-z_]+)/([a-z]+)\s*\|\s*(.*)")
        groups = defaultdict(list)
        with open(opts["audit"], encoding="utf-8") as f:
            for line in f:
                m = pat.search(line)
                if m:
                    groups[m.group(3)].append((int(m.group(1)), m.group(2), m.group(4), m.group(5)))

        total = sum(len(v) for v in groups.values())
        sample_route = problem_path(1).replace("1", "<id>")
        html = ["<html><head><meta charset='utf-8'><title>Аудит дефектных задач</title>",
                "<style>body{font-family:sans-serif;max-width:820px;margin:24px auto;line-height:1.6}"
                "h2{margin-top:28px}a{color:#1a5fb4;text-decoration:none}a:hover{text-decoration:underline}"
                "li{margin:5px 0}.meta{color:#777;font-size:.85em}</style></head><body>",
                f"<h1>Дефектные задачи из аудита ({total})</h1>",
                f"<p><b>Запусти сервер</b> (<code>./venv/bin/python manage.py runserver</code>) и кликай. "
                f"Маршрут страницы задачи: <code>{sample_route}</code></p>"]
        for cat in ["missing_figure", "broken_latex", "ocr_corruption", "duplicated",
                    "truncated", "other", "parse_error"]:
            items = groups.get(cat)
            if not items:
                continue
            html.append(f"<h2>{CAT_RU.get(cat, cat)} — {len(items)}</h2><ul>")
            for pid, src, sev, note in sorted(items):
                html.append(f"<li><a href='{BASE}{problem_path(pid)}' target='_blank'>Задача #{pid}</a>"
                            f" <span class='meta'>[{sev}] {note} — {src}</span></li>")
            html.append("</ul>")
        html.append("</body></html>")
        with open(opts["out"], "w", encoding="utf-8") as f:
            f.write("\n".join(html))
        self.stdout.write(f"Разобрано дефектных задач: {total}")
        self.stdout.write(f"Маршрут страницы задачи: {problem_path(1)}")
        self.stdout.write(f"HTML-индекс записан: {opts['out']} — открой его в браузере при запущенном сервере.")
