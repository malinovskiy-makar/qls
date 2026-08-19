> **Владелец:** Claude Code
> **Обновлён:** 2026-08-19
> **Статус:** актуален

# Карта маршрутов и границ доступа

Что здесь: **все** маршруты проекта — путь, обработчик, нужен ли вход, какая
роль, какие объекты трогает, что принимает от клиента. Это заготовка для
аудита границ доступа: следующая сессия начинается прямо отсюда.

⚠️ **Этот документ ничего не чинит и не утверждает, что дыр нет.** Он
описывает, как есть. Столбец «владелец» отмечает места, где владелец объекта
берётся **не** из `request.user`, — это кандидаты на разбор, а не доказанные
дыры.

Снято автоматически с резолвера Django (`get_resolver()`), не глазами по
`urls.py`: маршрут, не попавший в резолвер, не существует, а попавший, но
забытый в документации, — самая опасная разновидность.

**Цифры:** 353 маршрута всего, из них **252 — автоген админки** (`/admin/`),
**101 — проектный**. Ниже описаны все 101 плюс раздел про админку.

---

## Как читать столбцы

| Столбец | Что значит |
|---|---|
| **Вход** | `—` открыт всем · `да` нужен вход · `токен` вместо входа знание секретной строки |
| **Роль** | какой декоратор стоит и что он проверяет |
| **Клиент** | что приходит от клиента: `pk` из адреса, `GET`, `POST`, тело JSON |
| **Владелец** | ✅ владелец берётся из `request.user` · ⚠️ берётся иначе — разбирать |

---

## Четыре разных способа проверить роль — и они не совпадают

Это первое, что должен знать аудит: в проекте **не одна** проверка роли, а
четыре, и они дают разные ответы на одного и того же человека.

| Декоратор | Где объявлен | Что проверяет |
|---|---|---|
| `login_required` | Django | только факт входа, роль **не** смотрит |
| `student_required` | [student/views.py:224](../student/views.py) | `user.role == 'student'` **или** `is_superuser` |
| `tutor_required` | [teacher/access.py:41](../teacher/access.py) | `is_staff` **или** `profile.role == 'tutor'` **или** `user.role == 'teacher'` |
| `teacher_required` | [teacher/views.py:27](../teacher/views.py) | `user.role == 'teacher'` **или** `is_staff` |

✅ **ЗАКРЫТО 2026-08-19 (сессия 3А).** Таблица выше описывает состояние на
момент съёмки карты. Тогда `teacher_required` имел собственную реализацию и
знал только старое поле `User.role`, а `tutor_required` — обе системы;
репетитор из профиля проходил на 95 маршрутов и получал 403 на шести.
Нашлось и третье место с той же болезнью — `calendar_stub` (в `_visible_qs`,
`event_create` и `_format_event`).

Теперь реализация **одна**: `teacher.access.is_tutor` / `is_student`.
`teacher_required` оставлен алиасом `tutor_required` — имя стоит в двенадцати
местах, а второй реализации больше нет. Держится тестом
`RoleSystemsAgreeTests`: репетитор, заведённый любым из трёх способов
(только старое поле, только профиль, оба), получает одинаковый доступ.

Почему объединили, а не выбрали одну систему, — в
[SECURITY.md](SECURITY.md#проверка-роли--одна-на-проект).

---

## Публичные маршруты (вход не нужен)

| Путь | Имя | Роль | Клиент | Владелец | Файл |
|---|---|---|---|---|---|
| `/` | `home` | — | — | — | [catalog/views.py:62](../catalog/views.py) |
| `/login/` | `login` | — | POST: логин/пароль | — | [problems/views_auth.py:8](../problems/views_auth.py) |
| `/logout/` | `logout` | — | — | — | Django |
| `/catalog/` | `catalog:problem_list` | — | 10× GET (фильтры, поиск, страница) | — | [catalog/views.py:85](../catalog/views.py) |
| `/catalog/random/` | `catalog:random_problem` | — | — | — | [catalog/views.py:72](../catalog/views.py) |
| `/catalog/problem/<int:pk>/` | `catalog:problem_detail` | — | `pk` | — | [catalog/views.py:249](../catalog/views.py) |
| `/catalog/api/problem/<int:pk>/` | `catalog:api_problem` | — | `pk` | — | [catalog/views.py:496](../catalog/views.py) |
| `/catalog/collection/new/` | `catalog:collection_new` | — | POST: имя, тип | ⚠️ создаёт ничей объект | [catalog/views.py:300](../catalog/views.py) |
| `/game/` | `game:page` | `ensure_csrf_cookie` | — | — | [game/views.py:98](../game/views.py) |
| `/game/r/<str:code>/` | `game:result` | `require_safe` | `code` | ⚠️ по коду забега | [game/views.py:804](../game/views.py) |
| `/game/api/session/start/` | `game:session_start` | `require_GET` | 2× GET | сессия браузера | [game/views.py:238](../game/views.py) |
| `/game/api/session/start_mistakes/` | `game:session_start_mistakes` | `require_GET` | — | сессия браузера | [game/views.py:632](../game/views.py) |
| `/game/api/question/` | `game:question` | `require_GET` | — | сессия браузера | [game/views.py:261](../game/views.py) |
| `/game/api/answer/` | `game:answer` | `require_POST` | тело JSON | сессия браузера | [game/views.py:433](../game/views.py) |
| `/game/api/session/finish/` | `game:session_finish` | `require_POST` | 2× тело | сессия браузера | [game/views.py:677](../game/views.py) |
| `/media/<path>` | — | — | путь от клиента | ⚠️ отдача файлов | Django `static.serve` |

**Про игру.** Состояние забега живёт в сессии браузера, а не в базе за
пользователем. Это осознанно (игра без логина), но означает: всё, что игрок
может подделать в своей сессии, он подделает. Очки в таблице результатов
доверенными считать нельзя.

**Про `/media/`.** Раздача через Django включена в `config/urls.py`; на проде
статику отдаёт хостинг. Проверить, что маршрут не активен при `DEBUG=False`, —
пункт для аудита.

---

## Подборки по токену — доступ вместо входа

| Путь | Имя | Метод | Клиент | Файл |
|---|---|---|---|---|
| `/catalog/collection/<str:token>/` | `catalog:collection_detail` | GET | `token`, 6× GET | [catalog/views.py:311](../catalog/views.py) |
| `/catalog/collection/<str:token>/add/` | `catalog:collection_add` | POST | `token`, `problem_id` | [catalog/views.py:401](../catalog/views.py) |
| `/catalog/collection/<str:token>/remove/` | `catalog:collection_remove` | POST | `token`, `problem_id` | [catalog/views.py:414](../catalog/views.py) |
| `/catalog/collection/<str:token>/reorder/` | `catalog:collection_reorder` | POST | `token`, тело JSON | [catalog/views.py:425](../catalog/views.py) |
| `/catalog/collection/<str:token>/export/` | `catalog:collection_export` | GET | `token` | [catalog/views.py:441](../catalog/views.py) |
| `/catalog/collection/<str:token>/download/pdf/` | `catalog:collection_download_pdf` | POST | `token`, 2× | [catalog/views.py:460](../catalog/views.py) |
| `/catalog/collection/<str:token>/download/tex/` | `catalog:collection_download_tex` | GET | `token`, 2× | [catalog/views.py:482](../catalog/views.py) |

⚠️ **Все семь — `get_object_or_404(Collection, token=token)` и больше ничего.**
Владельца у подборки нет вовсе: кто знает токен, тот может читать, дополнять,
вычищать и переупорядочивать. Три из семи — **запись** (`add`, `remove`,
`reorder`).

Для «поделился ссылкой с коллегой» это ровно то, что задумано. Для аудита
важно записать честно: **токен — единственный секрет**, отзыва нет, срока
жизни нет, истории правок нет. Пересланная не тому ссылка = отданная подборка.

---

## Кабинет ученика

Все — `student_required` (вход + `role == 'student'` или суперпользователь).

| Путь | Имя | Клиент | Владелец | Файл |
|---|---|---|---|---|
| `/student/` | `student:dashboard` | — | ✅ | [student/views.py:238](../student/views.py) |
| `/student/assignment/<int:pk>/` | `student:assignment_detail` | `pk` | ✅ `students=request.user` | [student/views.py:369](../student/views.py) |
| `/student/assignment/<int:pk>/submit/` | `student:submit_assignment` | `pk`, POST ответы | ✅ | [student/views.py:413](../student/views.py) |
| `/student/submission/<int:pk>/` | `student:submission_detail` | `pk` | ✅ `student=request.user` | [student/views.py:519](../student/views.py) |
| `/student/work/<int:pk>/` | `student:work_review` | `pk` | ✅ `students=request.user` | [student/views.py:533](../student/views.py) |
| `/student/work/<int:pk>/difficulty/` | `student:rate_difficulty` | `pk`, POST | ✅ | [student/views.py:612](../student/views.py) |
| `/student/progress/` | `student:progress` | — | редирект | [student/views.py:645](../student/views.py) |
| `/student/exam/<int:pk>/` | `student:exam_intro` | `pk` | ✅ | [student/views_exam.py:32](../student/views_exam.py) |
| `/student/exam/<int:pk>/start/` | `student:exam_start` | `pk` | ✅ | [student/views_exam.py:65](../student/views_exam.py) |
| `/student/exam/<int:pk>/take/` | `student:exam_take` | `pk` | ✅ | [student/views_exam.py:78](../student/views_exam.py) |
| `/student/exam/<int:pk>/autosave/` | `student:exam_autosave` | `pk`, тело JSON | ✅ | [student/views_exam.py:138](../student/views_exam.py) |
| `/student/exam/<int:pk>/time/` | `student:exam_time` | `pk` | ✅ | [student/views_exam.py:117](../student/views_exam.py) |
| `/student/exam/<int:pk>/finish/` | `student:exam_finish` | `pk` | ✅ | [student/views_exam.py:205](../student/views_exam.py) |
| `/student/exam/<int:pk>/result/` | `student:exam_result` | `pk` | ✅ | [student/views_exam.py:257](../student/views_exam.py) |

Кабинет ученика — самая ровная часть проекта: **везде** объект достаётся
запросом, в который вшит `request.user`, а не проверкой после загрузки.

⚠️ Отдельно для аудита: `student_required` пускает `is_superuser`, но **не**
`is_staff`. У репетитора доступа к экранам ученика нет вовсе — «глазами
ученика» сделано отдельным маршрутом в кабинете репетитора.

---

## Кабинет репетитора

| Путь | Имя | Роль | Клиент | Владелец | Файл |
|---|---|---|---|---|---|
| `/teacher/` | `teacher:dashboard` | `tutor_required` | — | ✅ | [teacher/views_groups.py:796](../teacher/views_groups.py) |
| `/teacher/groups/` | `teacher:groups` | `tutor_required` | — | ✅ | [teacher/views_groups.py:177](../teacher/views_groups.py) |
| `/teacher/groups/create/` | `teacher:group_create` | `tutor_required` | 5× POST | ✅ | [teacher/views_groups.py:263](../teacher/views_groups.py) |
| `/teacher/groups/<int:pk>/` | `teacher:group_detail` | `tutor_required` | `pk`, 3× GET | ✅ `own_group_or_404` | [teacher/views_groups.py:328](../teacher/views_groups.py) |
| `/teacher/groups/<gid>/assignments/<aid>/` | `teacher:group_assignment` | `tutor_required` | 2× pk | ✅ | [teacher/views_groups.py:613](../teacher/views_groups.py) |
| `/teacher/groups/<gid>/assignments/<aid>/submissions/` | `teacher:group_submissions` | `tutor_required` | 2× pk, 3× GET | ✅ | [teacher/views_groups.py:1010](../teacher/views_groups.py) |
| `/teacher/groups/<gid>/submissions/<sid>/` | `teacher:group_review_submission` | `tutor_required` | 2× pk | ✅ | [teacher/views_groups.py:1103](../teacher/views_groups.py) |
| `/teacher/groups/<gid>/assignments/<aid>/students/<sid>/` | `teacher:student_work_review` | `tutor_required` | 3× pk, GET | ✅ | [teacher/views_groups.py:1051](../teacher/views_groups.py) |
| `/teacher/assignments/<aid>/students/<sid>/` | `teacher:student_work_review_plain` | `tutor_required` | 2× pk, GET | ⚠️ **без группы** | [teacher/views_groups.py:1051](../teacher/views_groups.py) |
| `/teacher/groups/<gid>/assignments/<aid>/students/<sid>/done/` | `teacher:work_done` | `tutor_required` | 3× pk, GET | ✅ | [teacher/views_groups.py:1288](../teacher/views_groups.py) |
| `/teacher/groups/<int:pk>/exams/new/` | `teacher:exam_create` | `tutor_required` | `pk`, 5× POST | ✅ | [teacher/views_exams.py:18](../teacher/views_exams.py) |
| `/teacher/groups/<gid>/exams/<eid>/results/` | `teacher:group_exam_results` | `tutor_required` | 2× pk | ✅ | [teacher/views_exams.py:167](../teacher/views_exams.py) |
| `/teacher/groups/<int:pk>/stats/` | `teacher:group_stats` | `tutor_required` | `pk`, GET | ✅ редирект | [teacher/views_stats.py:18](../teacher/views_stats.py) |
| `/teacher/students/<int:pk>/stats/` | `teacher:student_stats` | `tutor_required` | `pk` | ✅ редирект | [teacher/views_stats.py:39](../teacher/views_stats.py) |
| `/teacher/student/<int:pk>/progress/` | `teacher:student_progress` | **`teacher_required`** | `pk`, 2× GET | ✅ | [teacher/views.py:631](../teacher/views.py) |
| `/teacher/styleguide/` | `teacher:styleguide` | `tutor_required` | — | — витрина | [teacher/views.py:1042](../teacher/views.py) |
| `/teacher/problems/` | `teacher:problem_list` | `tutor_required` | — | ✅ `owner` | [teacher/views_problems.py:412](../teacher/views_problems.py) |
| `/teacher/problems/new/` | `teacher:problem_new` | `tutor_required` | **22× POST/GET** | ✅ | [teacher/views_problems.py:174](../teacher/views_problems.py) |
| `/teacher/problems/<int:pk>/edit/` | `teacher:problem_edit` | `tutor_required` | `pk`, **22×** | ✅ `owner` | [teacher/views_problems.py:174](../teacher/views_problems.py) |
| `/teacher/groups/<gid>/assignments/<aid>/print/` | `teacher:assignment_print` | **нет декоратора** | 2× pk, GET | ⚠️ см. ниже | [teacher/views_generate.py:694](../teacher/views_generate.py) |
| `/teacher/work/` | `teacher:work_pick` | `tutor_required` | GET | ✅ | [teacher/views_work.py:126](../teacher/views_work.py) |
| `/teacher/work/start/` | `teacher:work_start` | `tutor_required` | — | — | [teacher/views_work.py:346](../teacher/views_work.py) |
| `/teacher/work/compose/` | `teacher:work_compose` | `tutor_required` | — | — | [teacher/views_work.py:236](../teacher/views_work.py) |
| `/teacher/work/give/` | `teacher:work_give` | `tutor_required` | — | ✅ | [teacher/views_work.py:259](../teacher/views_work.py) |
| `/teacher/assignment/create/` | `teacher:assignment_create` | **`teacher_required`** | 8× POST | ✅ | [teacher/views.py:791](../teacher/views.py) |
| `/teacher/assignment/generate/` | `teacher:assignment_generate` | `tutor_required` | 5× | ✅ | [teacher/views_generate.py:133](../teacher/views_generate.py) |
| `/teacher/assignment/cart/print/` | `teacher:cart_print` | `tutor_required` **×2** | 9× POST | ⚠️ корзина из сессии | [teacher/views_generate.py:636](../teacher/views_generate.py) |
| `/teacher/groups/<gid>/assignments/<aid>/export/` | `teacher:assignment_export` | `tutor_required` | 2× pk, 3× GET | ✅ | [teacher/views_generate.py:571](../teacher/views_generate.py) |

### JSON-эндпоинты кабинета репетитора

| Путь | Имя | Роль | Клиент | Владелец | Файл |
|---|---|---|---|---|---|
| `/teacher/api/comment/create/` | `teacher:api_comment_create` | **только `require_POST`** | тело JSON: `item_id`, `text`, `visibility`, `recipient_id` | ⚠️ проверка внутри | [teacher/views_groups.py:705](../teacher/views_groups.py) |
| `/teacher/api/item/solution/` | `teacher:api_item_solution` | `tutor_required` + POST | тело JSON | ✅ | [teacher/views_groups.py:1241](../teacher/views_groups.py) |
| `/teacher/api/item/answers/` | `teacher:api_item_answers` | `tutor_required` + POST | тело JSON | ✅ | [teacher/views_groups.py:1120](../teacher/views_groups.py) |
| `/teacher/api/item/points/` | `teacher:api_item_points` | `tutor_required` + POST | тело JSON | ✅ | [teacher/views_groups.py:1168](../teacher/views_groups.py) |
| `/teacher/api/grade/` | `teacher:api_grade_submission` | `tutor_required` + POST | 3× тело | ✅ | [teacher/views_groups.py:1380](../teacher/views_groups.py) |
| `/teacher/api/generate/more/` | `teacher:api_more_candidates` | `tutor_required` | 6× GET | — подбор | [teacher/views_generate.py:508](../teacher/views_generate.py) |
| `/teacher/api/cart/rows/` | `teacher:api_cart_rows` | `tutor_required` | 6× GET | ⚠️ корзина из сессии | [teacher/views_generate.py:470](../teacher/views_generate.py) |
| `/teacher/api/problem/<str:key>/` | `teacher:api_problem_detail` | **`teacher_required`** | `key` от клиента | ✅ для `c<id>` | [teacher/views.py:901](../teacher/views.py) |
| `/teacher/api/assignment/<int:pk>/add_problem/` | `teacher:api_assignment_add_problem` | **`teacher_required`** + POST | `pk`, POST | ✅ | [teacher/views.py:988](../teacher/views.py) |
| `/teacher/work/api/full/<str:key>/` | `teacher:api_work_full` | `tutor_required` | `key` от клиента | ✅ через `picker` | [teacher/views_work.py:330](../teacher/views_work.py) |
| `/teacher/work/api/tally/` | `teacher:api_work_tally` | `tutor_required` | 4× GET | ✅ | [teacher/views_work.py:311](../teacher/views_work.py) |

### Что в кабинете репетитора требует разбора

**1. `assignment_print` — единственный маршрут кабинета вообще без декоратора.**
Внутри он зовёт `own_group_or_404(request.user, group_id)`, и для вошедшего
репетитора это правильная проверка. Но `own_group_or_404` устроен как
`get_object_or_404(StudentGroup, pk=group_id, teacher=user)`, а для гостя
`user` — это `AnonymousUser`. Фильтр по полю-внешнему-ключу значением
`AnonymousUser` — это не «не нашлось», это **несравнимый тип**.

**Проверено (2026-08-19):** сборка такого запроса падает ещё до похода в базу —

```
TypeError: Field 'id' expected a number but got
           <django.contrib.auth.models.AnonymousUser object>
```

Значит, гость по этому адресу получает **500, а не 403 и не редирект на вход**.
Данные не утекают (до запроса дело не доходит), но ошибка сервера на месте
проверки прав — это и шум в мониторинге, и подсказка сканеру, что маршрут
живой и обрабатывается иначе остальных. Решить, ставить ли `tutor_required`, —
работа следующей сессии.

**2. `api_comment_create` — роль проверяется руками, а не декоратором.**
Это осознанно и написано в самой вьюхе: эндпоинт один на две роли, «два почти
одинаковых эндпоинта разъехались бы». Внутри стоит `is_authenticated`,
`item.is_tutor_for(request.user)` и проверка членства
`assignment.students.filter(pk=request.user.pk)`. Претензий по существу нет —
но это **единственное место**, где граница держится не декоратором, и аудит
обязан на неё посмотреть отдельно, потому что она не видна снаружи.

**3. `cart_print` украшен `@tutor_required` дважды подряд.** Дублирование
безвредно (вторая проверка повторяет первую), но это след правки вслепую.
[teacher/views_generate.py:636](../teacher/views_generate.py).

**4. Шесть маршрутов на `teacher_required`** вместо `tutor_required` — см.
раздел про четыре проверки роли выше.

**5. `student_work_review_plain`** — тот же обработчик, что и групповой
вариант, но **без** `group_id`. Значит, дорога к чужой работе не перекрыта
принадлежностью к группе, а проверяется чем-то другим внутри. Разобрать, чем
именно.

**6. Корзина конструктора живёт в сессии браузера** (`cart_print`,
`api_cart_rows`). Владельца у неё нет по устройству; ключи корзины —
в [teacher/templates/teacher/_cart_keys.html](../teacher/templates/teacher/_cart_keys.html).

---

## Профиль, статистика, родитель (`problems/`)

| Путь | Имя | Роль | Клиент | Владелец | Файл |
|---|---|---|---|---|---|
| `/profile/` | `profile` | `login_required` | 7× POST/GET | ✅ | [problems/views_platform.py:26](../problems/views_platform.py) |
| `/profile/stats/` | `student_stats` | `login_required` | — | ✅ | [problems/views_stats.py:31](../problems/views_stats.py) |
| `/profile/stats/data/` | `student_stats_json` | `login_required` | — | ✅ | [problems/views_stats.py:38](../problems/views_stats.py) |
| `/profile/stats/goal/` | `set_weekly_goal` | `login_required` + POST | POST | ✅ | [problems/views_stats.py:45](../problems/views_stats.py) |
| `/parent/` | `parent_home` | `login_required` | — | ✅ `parent_links` | [problems/views_parent.py:28](../problems/views_parent.py) |
| `/parent/<int:pk>/` | `parent_student` | `login_required` | `pk`, GET | ✅ 404 на чужого | [problems/views_parent.py:44](../problems/views_parent.py) |
| `/api/saved/problem/` | `api_save_problem` | `login_required` + POST | POST | ✅ | [problems/views_platform.py:94](../problems/views_platform.py) |
| `/api/folders/create/` | `api_folder_create` | `login_required` + POST | POST | ✅ | [problems/views_platform.py:126](../problems/views_platform.py) |
| `/api/folders/rename/` | `api_folder_rename` | `login_required` + POST | POST | ✅ | [problems/views_platform.py:140](../problems/views_platform.py) |
| `/api/saved/move/` | `api_saved_move` | `login_required` + POST | POST | ✅ | [problems/views_platform.py:154](../problems/views_platform.py) |
| `/api/saved/delete/` | `api_saved_delete` | `login_required` + POST | POST | ✅ | [problems/views_platform.py:177](../problems/views_platform.py) |
| `/api/graphs/save/` | `api_graph_save` | `login_required` + POST | POST | ✅ | [problems/views_platform.py:193](../problems/views_platform.py) |
| `/password/change/` | `password_change` | `login_required` | POST | ✅ Django | Django |
| `/password/change/done/` | `password_change_done` | `login_required` | — | — | Django |

⚠️ **Роль на маршрутах `/parent/` не проверяется.** Стоит только
`login_required`. Экран честен: кто не родитель — увидит пустой список, потому
что `_children()` возвращает пустой queryset. Дыры нет, но границу держит
**форма запроса**, а не декоратор, и в аудит это записать надо.

---

## Календарь

Все — `login_required`, роль не проверяется.

| Путь | Имя | Клиент | Владелец | Файл |
|---|---|---|---|---|
| `/calendar/` | `calendar_stub:calendar` | — | ✅ | [calendar_stub/views.py:158](../calendar_stub/views.py) |
| `/calendar/api/events/` | `calendar_stub:events_api` | 2× GET | ✅ `_visible_qs` | [calendar_stub/views.py:193](../calendar_stub/views.py) |
| `/calendar/api/events/create/` | `calendar_stub:event_create` | тело JSON | ✅ автор = `request.user` | [calendar_stub/views.py:223](../calendar_stub/views.py) |
| `/calendar/api/events/<int:pk>/` | `calendar_stub:event_detail` | `pk` | ✅ `_visible_qs` | [calendar_stub/views.py:309](../calendar_stub/views.py) |
| `/calendar/api/events/<int:pk>/update/` | `calendar_stub:event_update` | `pk`, тело | ⚠️ проверка после загрузки | [calendar_stub/views.py:318](../calendar_stub/views.py) |
| `/calendar/api/events/<int:pk>/delete/` | `calendar_stub:event_delete` | `pk`, тело | ⚠️ **массовое удаление** | [calendar_stub/views.py:378](../calendar_stub/views.py) |

⚠️ **`event_update` и `event_delete` грузят объект СНАЧАЛА, проверяют потом:**
`get_object_or_404(CalendarEvent, pk=pk)`, затем
`if not (user.is_superuser or event.author_id == user.pk): 403`. Проверка по
существу верная, но образец другой, чем везде в проекте (там ограничение вшито
в запрос). Разница важна: 403 на чужом `pk` **подтверждает, что такое событие
есть**, тогда как 404 не подтверждал бы ничего.

⚠️ **`event_delete` с `delete_all: true` удаляет всю серию повторов** одним
запросом — единственное массовое удаление среди проектных маршрутов. Право
проверяется на **одном** событии, а удаляется вся цепочка `parent_event`.
Проверить, что все звенья цепочки принадлежат тому же автору, — задача аудита.

---

## Калькулятор

| Путь | Имя | Роль | Клиент | Файл |
|---|---|---|---|---|
| `/calc2/` | `calc2:calculator` | — (TemplateView) | — | [calc2/views.py:113](../calc2/views.py) |
| `/calc2/export/pdf/` | `calc2:export_pdf` | `login_required` + POST | 2× POST | [calc2/views.py:142](../calc2/views.py) |

⚠️ `export_pdf` принимает от клиента текст и **запускает `pdflatex`**. Это
единственный маршрут проекта, где ввод клиента доходит до внешнего процесса.
На проде отключён (нет TeX), но код есть. Первоочередной пункт аудита.

---

## Админка

252 маршрута под `/admin/`, все — автоген Django + зарегистрированные модели.
Границу держит `is_staff` + права модели, отдельного кода доступа нет.

Для аудита существенно, что **регистрация на проде закрыта**, а тестовые
пароли публично известны (`admin12345` и подобные) — перед любым показом
`manage.py lockdown_dev_accounts --apply`. Подробности — в
[SECURITY.md](SECURITY.md).

---

## Сводка: что разбирать в аудите

По убыванию того, насколько неприятен промах.
**Статус обновлён 2026-08-19 по итогам сессии 3А** (ветка
`sec/access-boundaries`).

| # | Место | Почему в списке | Статус |
|---|---|---|---|
| 1 | `calc2:export_pdf` | ввод клиента → внешний процесс `pdflatex` | ⬜ следующая сессия (активный контент) |
| 2 | `teacher:assignment_print` | единственный маршрут кабинета без декоратора; гость даёт не 403, а ошибку | ✅ **закрыто**, `@tutor_required` |
| 3 | `calendar_stub:event_delete` | массовое удаление серии; право проверено на одном звене | ✅ **закрыто**, queryset сужен по автору |
| 4 | Подборки по токену (7 маршрутов) | знание строки = право на запись, отзыва нет | 🟡 **намеренно**, см. ниже |
| 5 | `teacher_required` против `tutor_required` | два источника истины о роли, шесть маршрутов на старом | ✅ **закрыто**, одна проверка |
| 6 | `teacher:api_comment_create` | единственная граница без декоратора | 🟡 разобрано: проверка внутри корректна |
| 7 | `teacher:student_work_review_plain` | тот же обработчик без `group_id` | 🟡 разобрано: права по автору работы, покрыто тестом |
| 8 | `/parent/*` | роль не проверяется, границу держит форма запроса | 🟡 разобрано: `_children()` сужает, дыры нет |
| 9 | `calendar_stub:event_update` | загрузка до проверки: 403 подтверждает существование | ⬜ не закрыто, см. «Осталось» |
| 10 | `/media/<path>` | путь от клиента; проверить, что при `DEBUG=False` маршрута нет | ⬜ не проверено |
| 11 | Очки Econ Rush | состояние в сессии браузера, доверенными не считать | ⬜ по устройству игры |
| 12 | `cart_print` | `@tutor_required` дважды — след правки вслепую | ✅ **закрыто** |

### Что нашлось СВЕРХ этого списка и закрыто

| Место | Что было | Серьёзность |
|---|---|---|
| `api_save_problem` ([problems/views_platform.py](../problems/views_platform.py)) | брал `Problem` без фильтра по статусу: любой вошедший клал себе в «Сохранённое» черновик или забракованную задачу и видел её условие на `/profile/?tab=saved` — в обход шлюза качества | **средняя** |
| `teacher:api_problem_detail` ([teacher/views.py](../teacher/views.py)) | `.get(pk=...)` без фильтра: окно предпросмотра отдавало черновик и забракованную | низкая |
| `calendar_stub:event_create` и `event_update` | брали `Assignment` без проверки владения: номер чужой работы обменивался на `submissions_info` — сколько учеников и сколько сдали | **средняя** |
| `assignment_rows.build_rows` | `solution_text` уезжал в контекст безусловно; прятал решение шаблон, и одного забытого `{% if %}` хватало, чтобы отдать эталон посреди контрольной | **средняя** |
| `calendar_stub` (3 места) | роль проверялась по старому `user.role`: репетитор из профиля не видел своих событий и не мог их создать | низкая |

### Почему подборки по токену оставлены как есть

Правка по токену — **заявленная функция**, а не упущение: конструктор
подборок работает без входа, и это записано в
[ARCHITECTURE.md](ARCHITECTURE.md). Запретить запись значило бы сломать
работающий сценарий. Ограничение остаётся прежним и записано в
[SECURITY.md](SECURITY.md): токен — не защита, персональных данных в
подборках нет и класть их туда нельзя.

### Осталось не закрытым

- **`event_update` грузит объект до проверки.** Проверка по существу верная,
  дыры нет; неприятно лишь то, что 403 на чужом `pk` подтверждает
  существование события. Приведение к queryset-first меняет код ответа с 403
  на 404, а на 403 может опираться фронтенд — правка требует проверки экрана.
- **`/media/<path>` при `DEBUG=False`** — не проверено.
- **Показ уже сохранённого.** Вход закрыт (черновик не сохранить), но задача,
  сохранённая ДО того, как её забраковал шлюз, продолжает показываться в
  «Сохранённом». Это не доступ к чужому, а показ забракованного.

---

## Легаси: двойные реализации и мёртвый код

Найдено обходом всех маршрутов. **Ничего не удалено** — решение владельца от
2026-08-19: «потерять не хочется, а удалить всегда успеем». Карточка со
списком заведена в Notion «Задачи».

### Живые редиректы (адрес работает, экрана за ним нет)

Это **не** мусор: они держат старые закладки и ссылки в переписке. Удалять —
только вместе с решением, что закладки можно ломать.

| Адрес | Куда ведёт | Помечен |
|---|---|---|
| `/teacher/assignment/<pk>/` | `teacher:group_submissions` | «устарело, удалить после сессии 5» |
| `/teacher/submission/<pk>/review/` | `teacher:group_review_submission` | «устарело, удалить после сессии 5» |
| `/teacher/groups/<pk>/stats/` | вкладка «Обзор» группы | «устарело» |
| `/teacher/students/<pk>/stats/` | карточка ученика | «устарело» |
| `/student/submission/<pk>/` | `student:work_review` | «⚠️ УСТАРЕЛА» |
| `/student/progress/` | `/profile/stats/` | «⚠️ УСТАРЕЛА» |
| `/student/exam/<pk>/result/` | `student:work_review` | «⚠️ ПОГЛОЩЁН» |
| `/teacher/assignment/create/` (GET) | `teacher:work_pick` | экрана нет, обработчик создаёт работу |

⚠️ **`/teacher/assignment/create/` — не редирект целиком.** POST на этот адрес
**создаёт работу**, и второй точки создания в проекте нет; редирект отдаётся
только на GET. Удалять нельзя.

### Вьюхи без маршрута (код есть, дороги нет)

| Функция | Файл | Что с ней |
|---|---|---|
| `_student_stats_legacy` | [teacher/views_stats.py:59](../teacher/views_stats.py) | **полностью мёртвая**: не в маршрутах, не вызывается ниоткуда. Единственная ссылка на шаблон `groups/student_stats.html` |
| `dashboard` | [teacher/views.py:104](../teacher/views.py) | помечена «устарело», `/teacher/` ведёт на `views_groups.teacher_home` |
| `assignment_detail` | [teacher/views.py:131](../teacher/views.py) | вызывается только из легаси-редиректа для работ без группы |
| `review_submission` | [teacher/views.py:342](../teacher/views.py) | то же |
| `groups_list`, `group_create`, `group_detail` | [teacher/views.py:518–557](../teacher/views.py) | помечены «устарело», экраны переехали в `views_groups.py` |

### Шаблоны, на которые никто не ссылается

Проверено по всему тексту проекта (115 шаблонов, ссылок нет у 5).

| Шаблон | Размер | Почему осиротел |
|---|---|---|
| `student/submission_detail.html` | 5 842 б | вьюха стала чистым редиректом |
| `student/progress.html` | 7 105 б | то же |
| `student/exam_result.html` | 5 799 б | то же |
| `calendar_stub/calendar_student.html` | 2 728 б | `calendar_stub/views.py` рендерит только `calendar.html` |
| `calendar_stub/calendar_teacher.html` | 2 728 б | то же |

Плюс `teacher/groups/student_stats.html` — формально ссылка есть, но
**единственная**, и она из мёртвой `_student_stats_legacy`. Это та самая
«мёртвая пара» из Notion.

**Ложные срабатывания, которые НЕ трогать:** `404.html`,
`registration/password_change_*.html` (Django находит их по соглашению об
именах) и `problems/review_bundle_assets/reviewer.html` (не шаблон Django, а
файл, который `export_review_bundle` копирует в комплект ревью).

### Ни одна ссылка в интерфейсе не ведёт на 404

Проверено: все восемь легаси-адресов отвечают редиректом, а не ошибкой.
Экранов, ссылающихся на удалённые маршруты, не найдено.
