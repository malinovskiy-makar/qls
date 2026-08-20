# -*- coding: utf-8 -*-
r"""
Фаза 5б: qa_review.html — самодостаточная страница для проверки глазами.

30 задач: 20 случайных (фиксированный seed=42) + до 10 «интересных»
(с таблицей, с картинкой, с падающей формулой). KaTeX и шрифты вшиты
внутрь файла (base64) — открывается двойным кликом, интернет не нужен.

    python make_qa_page.py --katex-dir <папка с npm i katex>
"""
import argparse
import base64
import html
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import PROBLEMS_DIR, IMAGES_DIR, IMAGE_MAP_FILE, DATA_DIR, SITE, read_json, atomic_write_text

QA_PAGE_FILE = DATA_DIR / "qa_review.html"
KATEX_FAILING_IDS_FILE = DATA_DIR / "katex_failing_ids.json"
FIELDS = [
    ("statement_tex", "Условие"),
    ("solution_tex", "Решение"),
    ("answer_tex", "Ответ"),
    ("criteria_tex", "Критерии оценивания"),
]
INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")

FONT_URL_RE = re.compile(r"url\(([^)]+\.woff2)\)")


def build_katex_bundle(katex_dir: Path):
    dist = katex_dir / "node_modules" / "katex" / "dist"
    js = (dist / "katex.min.js").read_text(encoding="utf-8")
    autorender = (dist / "contrib" / "auto-render.min.js").read_text(encoding="utf-8")
    css = (dist / "katex.min.css").read_text(encoding="utf-8")

    def replace_font(m):
        rel = m.group(1)
        font_path = dist / rel
        data = font_path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"url(data:font/woff2;base64,{b64})"

    # оставляем только woff2-источники (все современные браузеры их понимают),
    # чтобы не тащить втрое больше шрифтов ради ttf/woff фоллбеков
    def strip_extra_formats(css_text):
        # каждый @font-face src: url(...) format('woff2'), url(...) format('woff'), ...
        def fix_src(m):
            block = m.group(0)
            woff2 = re.search(r"url\([^)]+\.woff2\)\s*format\(['\"]woff2['\"]\)", block)
            if woff2:
                return f"src: {woff2.group(0)};"
            return block
        return re.sub(r"src:[^;]+;", fix_src, css_text)

    css = strip_extra_formats(css)
    css = FONT_URL_RE.sub(replace_font, css)
    return js, autorender, css


def pick_sample_ids(problems, failing_ids, seed=42, n_random=20, n_interesting=10):
    rng = random.Random(seed)
    all_ids = [p["Id"] for p in problems]
    random_ids = rng.sample(all_ids, min(n_random, len(all_ids)))
    chosen = set(random_ids)

    by_id = {p["Id"]: p for p in problems}

    def has_table(p):
        return any("tabular" in (p.get(f) or "") for f, _ in FIELDS)

    def has_image(p):
        return any("\\includegraphics" in (p.get(f) or "") for f, _ in FIELDS)

    table_ids = [pid for pid in all_ids if pid not in chosen and has_table(by_id[pid])]
    image_ids = [pid for pid in all_ids if pid not in chosen and has_image(by_id[pid])]
    fail_ids = [pid for pid in failing_ids if pid not in chosen]

    # равномерно чередуем категории (round-robin), а не жадно вычерпываем одну —
    # иначе при большом пуле падающих формул все 10 "интересных" оказались бы
    # только ими, без единого примера с таблицей или картинкой.
    interesting = []
    pools = [iter(fail_ids), iter(image_ids), iter(table_ids)]
    while len(interesting) < n_interesting and pools:
        for it in list(pools):
            if len(interesting) >= n_interesting:
                break
            for pid in it:
                if pid not in chosen and pid not in interesting:
                    interesting.append(pid)
                    break
            else:
                pools.remove(it)

    return random_ids, interesting


def render_field_block(problem, field_key, field_label, image_map, used_images):
    text = problem.get(field_key)
    if not text or not text.strip():
        return ""
    escaped = html.escape(text)
    imgs_html = ""
    sids = {
        "statement_tex": problem.get("QuestionTexSessionId"),
        "solution_tex": problem.get("SolutionTexSessionId"),
        "criteria_tex": problem.get("GradeCriteriaTexSessionId"),
        "answer_tex": (problem.get("Answer") or {}).get("TexSessionId"),
    }
    sid = sids.get(field_key)
    if sid:
        for m in INCLUDEGRAPHICS_RE.finditer(text):
            name = m.group(1).strip()
            key = f"{sid}|{name}"
            local_name = image_map.get(key)
            if local_name:
                used_images.add(local_name)
                imgs_html += f'<img class="qa-img" src="cid:{local_name}" alt="{html.escape(name)}">'
    return (
        f'<div class="qa-field">'
        f'<div class="qa-field-label">{html.escape(field_label)}</div>'
        f'<div class="qa-tex">{escaped}</div>'
        f'{imgs_html}'
        f'</div>'
    )


def embed_images_as_data_uri(html_text, used_images):
    ext_to_mime = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml", ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp",
    }
    for local_name in used_images:
        path = IMAGES_DIR / local_name
        if not path.exists():
            continue
        ext = path.suffix.lower()
        mime = ext_to_mime.get(ext, "application/octet-stream")
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        html_text = html_text.replace(f"cid:{local_name}", f"data:{mime};base64,{b64}")
    return html_text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--katex-dir", required=True)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    problems = [read_json(p) for p in sorted(PROBLEMS_DIR.glob("*.json"))]
    image_map = read_json(IMAGE_MAP_FILE, default={})
    failing_ids = read_json(KATEX_FAILING_IDS_FILE, default=[])

    random_ids, interesting_ids = pick_sample_ids(problems, failing_ids, seed=args.seed)
    by_id = {p["Id"]: p for p in problems}

    print(f"Случайных (seed={args.seed}): {len(random_ids)}")
    print(f"Интересных: {len(interesting_ids)} (из них с падающей формулой: "
          f"{sum(1 for i in interesting_ids if i in set(failing_ids))})")

    js, autorender, css = build_katex_bundle(Path(args.katex_dir))

    used_images = set()
    cards = []

    def render_card(pid, tag):
        p = by_id[pid]
        memberships = p.get("theme_memberships") or []
        theme_txt = "; ".join(
            f"{m.get('parentThemeName') or '?'} → {m.get('themeName') or '?'}" for m in memberships
        ) or "—"
        first_theme = memberships[0]["themeId"] if memberships else None
        url = f"{SITE}/catalog/{first_theme}/{pid}" if first_theme else f"{SITE}/catalog/{pid}"
        is_failing = pid in set(failing_ids)
        badge = f'<span class="qa-badge qa-badge-{tag}">{tag}</span>'
        if is_failing:
            badge += '<span class="qa-badge qa-badge-fail">падающая формула</span>'

        blocks = "".join(
            render_field_block(p, key, label, image_map, used_images) for key, label in FIELDS
        )
        return f"""
<section class="qa-card">
  <div class="qa-card-head">
    <h2>#{pid} — {html.escape(p.get('Name') or '')}</h2>
    {badge}
  </div>
  <div class="qa-meta">
    Тема: {html.escape(theme_txt)} · AnswerTypeId: {p.get('AnswerTypeId')} ·
    <a href="{url}" target="_blank" rel="noopener">оригинал на сайте</a>
  </div>
  {blocks}
</section>
"""

    for pid in random_ids:
        cards.append(render_card(pid, "random"))
    for pid in interesting_ids:
        cards.append(render_card(pid, "interesting"))

    body_html = "\n".join(cards)
    body_html = embed_images_as_data_uri(body_html, used_images)

    page = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>QA-обзор: выгрузка Школково</title>
<style>
{css}
body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 24px; line-height: 1.5; color: #1a1a1a; }}
.qa-banner {{ background: #fff3cd; border: 1px solid #ffe08a; padding: 12px 16px; border-radius: 6px; margin-bottom: 24px; }}
.qa-card {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px 20px; margin-bottom: 28px; }}
.qa-card-head {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
.qa-card-head h2 {{ font-size: 18px; margin: 0; }}
.qa-badge {{ font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #eee; color: #555; }}
.qa-badge-fail {{ background: #ffd6d6; color: #a30000; }}
.qa-meta {{ color: #666; font-size: 13px; margin: 6px 0 14px; }}
.qa-field {{ margin-bottom: 14px; }}
.qa-field-label {{ font-weight: 600; font-size: 13px; text-transform: uppercase; color: #888; margin-bottom: 4px; }}
.qa-tex {{ white-space: pre-wrap; font-size: 15px; background: #fafafa; padding: 10px 12px; border-radius: 4px; }}
.qa-img {{ max-width: 100%; margin-top: 8px; border: 1px solid #eee; }}
</style>
</head>
<body>
<h1>QA-обзор выгрузки Школково</h1>
<div class="qa-banner">
  <strong>Важно:</strong> математика (между $, $$, \\[...\\], \\(...\\), в окружениях
  equation/align/gather/cases) отрендерена настоящим KaTeX — тем же движком, что на сайте.
  Всё остальное (\\textbf, tabular, itemize и т.п.) показано КАК ЕСТЬ, сырым LaTeX-текстом —
  конвертер в читаемый вид будет отдельной сессией. Это не поломка разметки, так и задумано
  для этой страницы.
</div>
{body_html}
<script>{js}</script>
<script>{autorender}</script>
<script>
document.querySelectorAll('.qa-tex').forEach(function(el) {{
  renderMathInElement(el, {{
    delimiters: [
      {{left: '$$', right: '$$', display: true}},
      {{left: '\\\\[', right: '\\\\]', display: true}},
      {{left: '\\\\(', right: '\\\\)', display: false}},
      {{left: '$', right: '$', display: false}}
    ],
    throwOnError: false
  }});
}});
</script>
</body>
</html>
"""
    atomic_write_text(QA_PAGE_FILE, page)
    size_mb = QA_PAGE_FILE.stat().st_size / 1024 / 1024
    print(f"Записано: {QA_PAGE_FILE} ({size_mb:.1f} МиБ, картинок вшито: {len(used_images)})")


if __name__ == "__main__":
    main()
