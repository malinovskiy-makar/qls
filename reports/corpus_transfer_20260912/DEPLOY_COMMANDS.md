# Перенос отобранного корпуса на прод — план команд

> **Собрано:** Claude Code, сессия «строгий отбор корпуса», 12.09.2026
> **Выполняет:** владелец. Эта сессия на сервере не выполнила НИ ОДНОЙ команды,
> кроме чтения.
> **Ветка:** `feat/corpus-transfer-selection`

## Что везём

| | |
|---|---|
| Сейчас на проде | 5 095 задач |
| Переносим | **3 522** задачи |
| Станет | **8 617** задач |
| Видимыми в каталоге сразу | 3 101 из 3 522 (остальные 421 приедут скрытыми) |
| Дамп | 36 файлов `.json.gz`, **35 МБ** (69,6 МБ до сжатия) |
| Пометки групп копий | 2 строки в 1 группе — см. «Почему так мало» ниже |

Список id — `transfer_new_ids.txt` в этой же папке. Область видимости групп —
`transfer_scope_ids.txt`.

**Что будет с нынешними 5 095.** Ничего. `bulk_load_fixtures` зовёт
`bulk_create(..., ignore_conflicts=True)`: строка с занятым `pk` молча
пропускается. Заливка только ДОБАВЛЯЕТ и никогда не заменяет. Правки в
существующих задачах так на прод не попадают вовсе — для этого есть отдельная
команда `update_prod_problems`. В дамп нынешние 5 095 не включены намеренно:
их подпункты и картинки приехали бы вторыми экземплярами с новыми номерами
(на проде `ProblemPart` до 85 325, локально до 89 378 — диапазоны
пересекаются, но строки разные).

## 0. Бэкап боевой базы — ПЕРВЫМ ШАГОМ, БЕЗ ИСКЛЮЧЕНИЙ

```bash
ssh -i ~/.ssh/id_ed25519_weconomics makar@135.106.181.151
sudo /srv/weconomics/app/deploy/backup.sh
sudo sh -c 'ls -1t /srv/weconomics/backups/*.dump.gz | head -3'
```

Свежая копия обязана появиться сверху списка, с сегодняшней датой. Без неё
дальше не идти: заливка необратима иначе как восстановлением из копии.

## 1. Отправить дамп на сервер (с рабочей машины)

```bash
ssh -i ~/.ssh/id_ed25519_weconomics makar@135.106.181.151 \
    mkdir -p /srv/weconomics/backups/fixtures/transfer_20260912
scp -i ~/.ssh/id_ed25519_weconomics deploy_fixtures_transfer/*.json.gz \
    makar@135.106.181.151:/srv/weconomics/backups/fixtures/transfer_20260912/
```

Отдельная папка, а не общая `fixtures/`: в ней уже лежат файлы прошлой
выкатки, и `--dir` залил бы заодно и их.

## 2. Залить (на сервере, из `/srv/weconomics/app/deploy`)

```bash
ssh -i ~/.ssh/id_ed25519_weconomics makar@135.106.181.151
cd /srv/weconomics/app/deploy

docker compose exec -T web python manage.py shell -c \
  "from problems.models import Problem; print('ДО:', Problem.objects.count())"

docker compose exec -T web mkdir -p /tmp/transfer
docker compose cp /srv/weconomics/backups/fixtures/transfer_20260912/. web:/tmp/transfer
docker compose exec -T web python manage.py bulk_load_fixtures --dir /tmp/transfer
```

`docker compose cp` внутрь контейнера, а не прямой `--dir` на хостовый путь:
у контейнера `web` папка `backups/` не смонтирована.

## 3. Счётчики автоинкремента — обязательный шаг

```bash
docker compose exec -T web python manage.py fix_sequences --apply
docker compose exec -T web python manage.py fix_sequences   # ждём «отставших нет»
docker compose exec -T web rm -rf /tmp/transfer
```

Без этого ломается не заливка, а первое обычное действие человека после неё:
заливка вставляет строки с явными `id`, счётчик таблицы при этом не двигается,
и следующая вставка без `id` получает занятый номер. На SQLite не
воспроизводится, поэтому локально мина не видна.

## 4. Пул игры заново

```bash
docker compose exec -T web python manage.py build_game_pool
```

## 5. Проверить

```bash
docker compose exec -T web python manage.py shell -c "
from problems.models import Problem, DupMark
from catalog.filters import base_queryset
print('Problem      ', Problem.objects.count(), '(ждём 8617)')
print('видно в каталоге', base_queryset('catalog').count())
print('DupMark      ', DupMark.objects.count(), '(ждём 2)')
"
curl -sI https://weconomics.site/catalog/ | head -1
```

## Откат

Заливка только добавляет, поэтому откат — это удаление добавленного:

```bash
docker compose exec -T web python manage.py shell -c "
from problems.models import Problem
ids = [int(x) for x in open('/tmp/transfer_new_ids.txt') if x.strip() and not x.startswith('#')]
print(Problem.objects.filter(pk__in=ids).delete())
"
```

Каскад снимет подпункты, ссылки, картинки и пометки — они все `CASCADE` на
задачу. Если что-то пойдёт не так и до этого, остаётся копия из шага 0.

## Почему пометок групп копий всего 2

Флаг `--with-dupmark` везёт группу, только если ВСЕ её участники будут на
проде. Строгий отбор при этом исключил проигравших уверенных групп (117) и
всех участников групп «на разбор» (747) — то есть у почти каждой группы
партнёр остался дома по построению. Целиком в перенос уложилась одна группа.

Это не ошибка отбора, а его следствие: разметка дедупа считалась против всего
локального банка на 41 307 задач, а на прод едет 8 617. Полноценный дедуп на
проде — отдельная работа после того, как владелец разметит группы вручную
(инструмент — `reports/dedup_human/dedup_review.html`).
