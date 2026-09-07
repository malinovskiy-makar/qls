"""Формула отпечатка v2 — порядок блоков из ночного задания §6.3.
Заголовок убран, обрезка statement[:500] снимается (бюджет параметром)."""
from problems.management.commands.build_embeddings import CANONICAL_TAG_NAMES

def problem_to_text_v2(problem, statement_budget=None, part_budget=500):
    """1 Тема, 2 Теги, 3 Понятия, 4 ai_blurb, 5 Найти, 6 Дано,
    7 Условие (бюджет), 8 Подпункты (бюджет на каждый), 9 Навыки.
    Заголовка НЕТ. Решение и ответ по-прежнему не входят."""
    parts = []
    topic_names = [t.name for t in problem.topics.all() if t.name != 'Тест']
    if topic_names:
        parts.append('Темы: ' + ', '.join(topic_names) + '.')
    canonical_tags = sorted(t.name for t in problem.tags.all()
                            if t.name in CANONICAL_TAG_NAMES)
    if canonical_tags:
        parts.append('Теги: ' + ', '.join(canonical_tags) + '.')
    concepts = getattr(problem, '_concepts_cache', None)
    if concepts:
        parts.append('Понятия: ' + ', '.join(concepts) + '.')
    blurb = (problem.ai_blurb or '').strip()
    if blurb:
        parts.append(blurb[:400])
    find = (getattr(problem, 'find', '') or '').strip()
    if find:
        parts.append('Найти: ' + find)
    given = (getattr(problem, 'given', '') or '').strip()
    if given:
        parts.append('Дано: ' + given)
    st = problem.statement or ''
    parts.append(st if statement_budget is None else st[:statement_budget])
    subparts = list(problem.parts.all())
    if subparts:
        for sp in subparts:
            if sp.statement:
                parts.append(sp.statement[:part_budget])
    skill_names = [s.name for s in problem.skills.all()]
    if skill_names:
        parts.append('Навыки: ' + ', '.join(skill_names) + '.')
    return ' '.join(p for p in parts if p)
