# Прогресс сессии: платформа для репетиторов
Ветка: feat/platform-foundation

## Часть A — данные
- [x] Фаза 0. Разведка
- [x] Фаза 1. Профиль и роли — `UserProfile` в `problems/models_platform.py`,
      сигнал в `problems/signals.py`, команда `backfill_profiles`,
      админка `problems/admin_platform.py`
- [x] Фаза 2. Комментарии — `ProblemComment` + `ProblemCommentQuerySet.visible_for()`
- [x] Фаза 3. Свои задачи и тесты — `CustomProblem`, `CustomProblemOption`, `AssignmentItem` (CheckConstraint «ровно одна задача»)
- [x] Фаза 4. Сохранённое и папки — `SavedFolder` (плоские), `SavedProblem`, `SavedGraph`
- [x] Фаза 5. Решалка — поля у `AssignmentItem` + `is_solution_visible_for()`; `Submission.problem_item` (новое поле), `Submission.problem` стал nullable
- [ ] Фаза 6. Контрольные
- [ ] Фаза 7. Логирование событий
- [ ] Фаза 8. Миграция и тесты

## Часть B — группы
- [ ] Фаза 9. Каркас вкладки «Группы»
- [ ] Фаза 10. Страница группы
- [ ] Фаза 11. Просмотр домашки до решений
- [ ] Фаза 12. Комментарии в интерфейсе
- [ ] Фаза 13. Переезд проверки решений
- [ ] Фаза 14. Дашборд входящих
- [ ] Фаза 15. Профиль

## Часть C — редактор
- [ ] Фаза 16. MathLive
- [ ] Фаза 17. Своя задача
- [ ] Фаза 18. Конструктор тестов
- [ ] Фаза 19. Графики в задачи
- [ ] Фаза 20. Решалка в интерфейсе
- [ ] Фаза 21. Финальная проверка и Notion

---

## Найденные имена моделей (Фаза 0, разведка по факту кода)

Все модели живут в ОДНОМ приложении `problems` (`problems/models.py`, 1209 строк).
Приложения `teacher`, `student`, `catalog`, `calc2` СВОИХ моделей не имеют
(`teacher/models.py` и `student/models.py` пустые, миграций нет). Значит новые
модели этой сессии тоже идут в `problems` — иначе миграции разъедутся.

### 1. Задача каталога
`problems.models.Problem`. Поля (используемые нами):
`title` (CharField 300, blank), `statement` (TextField, условие),
`answer` (TextField, blank — ОСНОВНОЕ поле), `solution` (TextField, blank —
необязательное), `problem_type` (CharField 120; тесты — префикс «тест:»),
`difficulty` (PositiveSmallIntegerField 1–5, null), `difficulty_native`,
`status` (draft/needs_review/published/archived/hidden/duplicate),
`owner` (FK User, null), `topics` (M2M Topic), `tags`, `skills`, `mistakes`,
`needs_quality_review`, `solution_needs_review`, `ai_blurb`.
Подпункты — `problems.models.ProblemPart` (`related_name='parts'`).

### 2. Модели цикла ученик↔учитель
- `Lesson` — три M2M к Problem (`main_problems`, `challenge_problems`,
  `homework_problems`).
- **`Assignment`** — `name`, **`problems` = ManyToManyField(Problem)** —
  ⚠️ ПРОСТОЙ M2M, БЕЗ through-модели и БЕЗ порядка; `students` = M2M(User),
  `deadline` (DateTimeField, null), `lesson` (FK, null), `author` (FK User),
  `created_at`. **Поля `group` НЕТ** — домашка не привязана к группе.
- `Submission` — `student` FK, `assignment` FK, **`problem` FK на Problem**,
  `solution_text`, `solution_file`, `submitted_answer`, `opened_hints` M2M,
  `status` (not_started/in_progress/submitted/reviewed), `submitted_at`.
  `unique_together = ('student', 'assignment', 'problem')`.
- `TeacherFeedback` — OneToOne к Submission, `score` (Decimal), `mistakes` M2M,
  `comment`, `reviewed_by`, `reviewed_at`.
- `StudentGroup` — `name`, `teacher` FK(User, limit_choices_to role='teacher'),
  `students` M2M(User, limit_choices_to role='student'), `created_at`.
  **Связи «группа → домашки» нет.**
- `StudentTopicProgress` — `student`, `topic`, `level` 0..100, `updated_at`.

### 3. Пользователь
Кастомный **`problems.User(AbstractUser)`** (`AUTH_USER_MODEL='problems.User'`).
Уже есть поле **`role`** с choices: `teacher`, `student`, `editor`, `viewer`,
`public`. **Ролей `tutor` и `parent` НЕТ.** Отдельного профиля НЕТ.
Различение ролей — декораторами `teacher.views.teacher_required`
(`role=='teacher' or is_staff`) и `student.views.student_required`
(`role=='student' or is_superuser`).

### 4. Темы
`problems.models.Topic` (`name`, `slug`, `description`, `order`) + `Subtopic`.
В базе **849 тем**, а не 21: 21 каноническая — это подмножество, приведённое
командой `apply_topic_mapping`; остальные — исторические/импортные.

### 5. Результаты партий Econ Rush
`game.models.GameResult` — `code` (Crockford base32), `mode`, `score`,
`correct_count`, `total_count`, `max_combo`, `ended_reason`,
`topic_breakdown`/`difficulty_breakdown`/`score_curve` (JSON), `created_at`.
Создаётся во вьюхе `game/views.py` (в районе строки 719), в функции завершения
забега. Игра работает БЕЗ логина — привязки к User у результата нет.

### 6. Базовый layout и навигация
Общих токенов — `templates/_tokens.html` (подключается первым в `<head>`),
навигация — `templates/_nav.html`. Свои базы у каждого приложения:
`catalog/templates/catalog/base.html`, `student/templates/student/base.html`,
`teacher/templates/teacher/base.html`. У `/calc2/` свой изолированный мир
токенов — не трогаем.

### 7. Что уже есть в приложении teacher
`teacher/urls.py` (app_name='teacher'), views в `teacher/views.py` (591 строка):
`dashboard` (`/teacher/`), `assignment_detail` (`/teacher/assignment/<pk>/` —
таблица решений), `review_submission` (`/teacher/submission/<pk>/review/`),
`groups_list` (`/teacher/groups/`), `group_create`, `group_detail`
(`/teacher/groups/<pk>/`), `student_progress`, `assignment_create`
(конструктор домашек), `api_problem_detail`, `api_assignment_add_problem`.
Шаблоны — `teacher/templates/teacher/*.html` (9 файлов).
Автопроверка тестов — `student/views.py::auto_check_submission`
(работает по `problem_type.startswith('тест')` и сравнению строк).

---

## РАСХОЖДЕНИЯ с промптом (Фаза 0) и как адаптировано

1. **Ветка создана не от `main`, а от `feat/batch2-sweep`.**
   Причина: `git log HEAD..main` пуст, `main..HEAD` = 165 коммитов, то есть
   `feat/batch2-sweep` СОДЕРЖИТ весь `main` и идёт впереди. Главное — миграции:
   в локальной базе применены `problems` 0018–0022, а на `main` файлов
   0018–0022 НЕТ. От `main` новая миграция получила бы номер 0018 и столкнулась
   бы с уже применённой `0018_batch1_ai_fields`. Ветвление от текущей вершины
   даёт согласованную историю: новая миграция будет 0023.
2. **Роли.** В `User.role` уже есть `teacher`/`student`, нет `tutor`/`parent`.
   Заводить вторую систему ролей нельзя (разъедется с
   `teacher_required`/`student_required` и `limit_choices_to` у StudentGroup).
   Решение: `UserProfile.role` = `tutor|student|parent` (как в промпте), плюс
   двусторонняя синхронизация с `User.role` (`tutor` ↔ `teacher`), чтобы старые
   декораторы и админка продолжали работать.
3. **`Assignment.problems` — простой M2M без порядка.** Промпт (3.3) требует
   промежуточную модель позиции. Переводить существующий M2M в `through=`
   нельзя без потери данных, поэтому `AssignmentItem` добавляется РЯДОМ,
   а старый M2M остаётся для обратной совместимости; предусмотрен бэкфилл
   позиций из M2M.
4. **`Assignment` не привязана к группе.** Для вкладки «Группы» (фазы 10–14)
   нужна связь: добавляется `Assignment.group` (FK на StudentGroup, nullable).
5. **`Submission.problem` — FK только на Problem каталога.** Чтобы ученик мог
   сдавать и свои задачи репетитора, добавляется nullable
   `Submission.problem_item` (FK на AssignmentItem); `problem` становится
   nullable. Старый `unique_together` сохраняется.
6. **Тем в базе 849, а не 21.** Ничего не ломает, но выпадающий список тем
   в редакторе задач фильтруется по каноническому набору.

## Заметки для следующего запуска
- Все новые модели — в `problems/models.py`, одна миграция `problems/0023_*`.
- НЕ запускать `makemigrations game` (миграции game 0007–0012 применены
  в базе, файлов на этой ветке нет — сочинит конфликтующую 0007).
- Python 3.9: никаких `int | None`, только `Optional[int]`.
- Команды — через `./venv/bin/python manage.py …`.
