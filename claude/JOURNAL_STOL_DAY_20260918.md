# Журнал дневной сессии «Стол» — 18.09.2026

- Ветка: `feat/catalog-stol` (поверх `feat/beta-prep`, та поверх `main` = `origin/main` = `83fdd67`)
- `main..feat/beta-prep` — 19 коммитов; `feat/beta-prep..feat/catalog-stol` — 26 коммитов ночи
- Промпта в репозитории не было — создан первым коммитом `70369dfc`
- Окружение: Docker — `qls_postgres_dev` (55432), `qls_redis_dev` (56379) подняты; `manage.py check` — 0;
  Playwright (node) есть; порты 8000 и 8611 свободны
- Рабочая локальная база — SQLite `db.sqlite3` (как ночью: `DATABASE_URL` не задан); PostgreSQL в
  Docker — для тестов. Каталог видит 14 082 задачи; `tutor@test.local`, `student1@test.local` есть
- Notion прочитан: «Задачи» (В работе — «Стол» 81b3; Надо — 38 карточек, из них по теме:
  баг «+ В домашку» 81ce, PDF/TeX 8154, числа карты 818d, копия решения 817a, фильтр тем
  конструктора 819e), «Решения» — все 11 решений от 17.09 «Действует», 81b9 «Пересмотрено»
- Базовый прогон `manage.py test catalog teacher` (PostgreSQL): **567 тестов, OK, 3,3 мин**, красных нет
  (ночной журнал называл 568; красного нет, разница в один тест не мешает — записано)
- Ответы владельца: `feat/beta-prep` — пуш и слияние позже, в отчёте S8; сервер на 8000 — да, в фоне

Куда продолжать: S1.1 · новый `stol.html`, `problem_list` рендерит его с `view='entry'`

## Чек-лист

- [x] −1 Сверка, инвентарь, базовый прогон, вопросы владельцу
- [ ] S1.1 Шаблон `stol.html` и адрес `/catalog/`
- [ ] S1.2 Карточка поиска и заголовок
- [ ] S1.3 Чипы и выпадашки (одно состояние с окном «Все фильтры»)
- [ ] S1.4 Лента входа широкими строками, «Продолжить», «Случайная задача»
- [ ] S1.5 Карта-фон (`topic_map_preview.js` с параметрами и выделением)
- [ ] S1.6 Убрать галерею, модалку «Условие», процент близости
- [ ] S1.7 Тесты `test_stol_entry.py`, переписанные старые, снимки → остановка
- [ ] S2.1 Панель задачи одним ответом `?pane=1`
- [ ] S2.2 Вид «стол» в том же шаблоне, `stol_task.js` с `init(root)`
- [ ] S2.3 Переключение видов и адреса без перезагрузки
- [ ] S2.4 Лента у задачи: Выдача / Похожие / Мои, «Дальше», соседи
- [ ] S2.5 Ширины и панели
- [ ] S2.6 Тесты `test_stol_pane.py`, `test_stol_browser.py`, снимки, видео → остановка
- [ ] S3.1 Центр задачи
- [ ] S3.2 Лестница и лента помощи
- [ ] S3.3 Попытка из панели помощи
- [ ] S3.4 Тест (README §5)
- [ ] S3.5 Тесты, снимки → остановка
- [ ] S4.1 Монтируемый движок карты
- [ ] S4.2 Переход вход ↔ карта
- [ ] S4.3 Выбор = фильтры
- [ ] S4.4 Тесты, видео, снимки → остановка
- [ ] S5.1 Корзина учителя в интерфейсе
- [ ] S5.2 «В домашку», «PDF или TeX», «Новая домашка»
- [ ] S5.3 Баг одиночной «+ В домашку» (81ce)
- [ ] S5.4 Тесты, снимки → остановка
- [ ] S6.1 Телефон: вход, шторки, задача, помощь, карта, тест
- [ ] S6.2 Тесты, снимки → остановка
- [ ] S7.1 Стоп-гейт удаления → удаление
- [ ] S7.2 Сторожа
- [ ] S7.3 Документы и ADR
- [ ] S7.4 Notion
- [ ] S8.1 Полный прогон
- [ ] S8.2 Пять джобов CI
- [ ] S8.3 Полный набор снимков, таблица README → доказательство
- [ ] S8.4 Приёмка владельца
- [ ] S8.5 Отчёт

## Инвентарь ночной работы (файл → что в нём → раздел README)

С `feat/beta-prep` (часть A):
| Файл | Что | README |
|---|---|---|
| `catalog/search_log.py`, `SearchLog` (0070), `templates/_search_rating.html` | журнал поиска, `log=1`, `data-search-log`, плашка оценки | §2 (поиск) |
| `templates/_corner_stack.html`, `_pulse.html`, `_feedback.html` | стек плашек угла `#corner-stack` | §7, §8 (над полосами) |
| `catalog/chat.py`, `catalog/chat_files.py`, `ChatTurn.attachments` (0072) | чат с TeX, история `api_chat_history`, `quote`, до трёх файлов, вьюха вложения | §4 |
| `problems/ai/prompts.py` | промпт чата: TeX, «деньги словами» | §4 |
| `scripts/beta_shots.mjs` | снимки Playwright по наборам | S1–S8 снимки |
| `problems/tests/test_beta_smoke.py` | смок | – |

С `feat/catalog-stol` (часть B, ночь):
| Файл | Что | README |
|---|---|---|
| `catalog/preview.py` (+55) | `solution_is_statement_copy`, `strip_statement_retell`, `strip_score_tails` | §4, §5 |
| `catalog/progress.py`, `ProblemProgress` (0073), `POST /catalog/api/progress/<id>/` | статусы, «Как прошло?», подсказки/решение для восстановления, `continue_for`, `statuses_for` | §2 статусы, §3, §4, §5 |
| `catalog/map_numbers.py` | `db` у узлов и живое `c` | §6 |
| `catalog/views.py` (+124) | `api_rail_similar`, `api_rail_saved`, `api_progress`, контекст «Стола» в `problem_detail`, «Продолжить» в `problem_list` | §2, §3 |
| `catalog/templates/catalog/stol/_rail_row.html` | общий партиал строки ленты | §2, §3 |
| `catalog/templates/catalog/stol/_stol_css.html` | стили «Стола» (сетка, полоски, фокус, телефонная панель) | §1, §3, §8 |
| `catalog/static/catalog/js/stol.js` (170) | панели, `localStorage`, «Фокус», клавиши | §1 |
| `catalog/templates/catalog/problem_detail.html` (+70) | разметка «Стола» поверх старой страницы | §3 |
| `catalog/templates/catalog/problem_list.html` (+16) | «Продолжить» | §2 |
| `catalog/templates/catalog/_problem_test.html` | «Дальше ›» главной, клавиши скрыты на телефоне | §5 |
| `catalog/static/catalog/js/topic_map.js` (+22) | «Показать задачи» → `topic`/`tag` | §6 |
| `catalog/static/catalog/js/problem_page.js` (+23) | история разговора при загрузке | §4 |
| `teacher/views.py` (+50), `teacher/urls.py` | `POST /teacher/api/assignment/<pk>/add_problems/` | §7 |
| `docs/adr/0119`, `0120` | прогресс; «Стол» первым шагом | – |
| тесты: `test_stol_api.py` (369 строк), `test_preview.py`, `teacher/tests/test_basket_add.py`, `test_chat_beta.py` | | |

Расхождений журнала ночи с репозиторием нет.

## Решил сам

## Смотрел глазами

## Переписанные и удалённые старые тесты
