# Ветка выпуска ВП для Андрея

Ветка: `codex/vp-release-20261103`, исходный main: `0ff5c12222d2fa9d4d296d8e2fc52c5f8207e2e9`.

Макар разрешил отправить эту отдельную ветку. Прод с Mac не изменялся.
Старый ZIP vp-launch-20261103-andrey содержит прежние надписи: для выпуска
использовать эту ветку и её data/vp/variants-manifest.json.

В новой папке на Windows получите ветку (занятый qls не переключать):

```powershell
git clone --branch codex/vp-release-20261103 https://github.com/malinovskiy-makar/qls.git qls-vp-release
Set-Location qls-vp-release
git rev-parse HEAD
```

Перед выпуском проверьте CI именно этого SHA и отсутствие более новых
изменений main. Изменения общего раздела «Олимпиады» и текущая работа
над графиками в эту ветку не переносились. Все прежние варианты сохранены:
3 демоверсии и 30 вариантов, номера 1–10 внутри каждого класса.
Демоверсия в списке первая. Slug, структура, баллы и эталоны ответов
последними текстовыми правками не изменены.

Пакет загрузки для серверной инструкции ниже соберите из этой ветки:

```powershell
New-Item -ItemType Directory -Path deploy-payload/variants -ErrorAction Stop
$manifest = Get-Content data/vp/variants-manifest.json -Raw | ConvertFrom-Json
foreach ($row in $manifest) {
  $src = Join-Path data/vp $row.path
  if ((Get-FileHash $src -Algorithm SHA256).Hash.ToLower() -ne $row.sha256) { throw "Hash mismatch: $src" }
  Copy-Item $src deploy-payload/variants/
}
Copy-Item data/vp/variants-manifest.json deploy-payload/variants/
Copy-Item scripts/vp_release/*.py deploy-payload/
$root = (Resolve-Path deploy-payload).Path
$rows = Get-ChildItem deploy-payload -Recurse -File | ForEach-Object {
  @{ path = $_.FullName.Substring($root.Length + 1).Replace('\', '/'); sha256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower() }
}
$rows | ConvertTo-Json | Set-Content deploy-payload/MANIFEST.json -Encoding utf8
```

Ни .env, ни дампы Mac в пакет не включать. Копирование исходников не загружает
варианты в БД: обязательны план, атомарный импорт и проверка из разделов 6–8.
Перед настоящим импортом снимите актуальную серверную базу и проверьте восстановление.

Ниже сохранён подробный операционный порядок. Разделы 1–2 про старый ZIP
заменены инструкцией получения ветки выше; остальные действия выполняются
оператором на Windows/сервере с фиксацией текущего SHA и результатов CI.

## 3. Паспорт допуска к выкатке

Перед любыми серверными изменениями должны быть записаны:
- полный SHA одобренного итогового коммита и SHA предыдущей версии;
- хеш передаваемого payload, перечень33 slug и583 позиций;
- список миграций между версиями, проверка совместимости отката кода;
- CI и результаты локальной репетиции именно итогового коммита; отдельной строкой
  Linux/Docker/nginx, если они не запускались;
- согласованное техническое окно и единственный оператор;
- разрешённые ящик и два Telegram-аккаунта для конечной проверки;
- что было запущено до окна: web,ws,tgbot, таймеры и dev-автовыкатка.

Почта уже работает со слов Макара. Не создавать заново DNS, ключи Postbox,
OAuth и не менять LEGAL_DOCS_DATE просто из-за обновления вариантов.
Unisender не является условием этого запуска. Решение Notion от30.10
`408b11c9-2bc1-81c2-98e6-c06470f68306` отменило ожидание повышения квоты и
прежнее предварительное условие РКН; юридическая задача остаётся отдельной.

## 4. Windows: подключение и доставка

Только после отдельного одобрения выпуска. В PowerShell используется штатный
ключ Андрея. Приватный ключ никуда не копируется:

```powershell
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_weconomics" makar@135.106.181.151
```

Далее блоки Bash выполняются **в SSH-окне на Ubuntu**, не в PowerShell.
Все Docker Compose команды — из `/srv/weconomics/app/deploy`.
VPN-проба с Windows не доказывает состояние провайдера: проверки интеграций
выполняются с сервера. Ключ сервера SSH при неожиданной смене не принимать вслепую.

## 5. Сервер: сверка, подготовка образов, фиксация предыдущего состояния

```bash
set -euo pipefail
umask 077
cd /srv/weconomics/app
git status --short
git log -1 --oneline
git fetch origin
read -r -p 'Полный SHA одобренного коммита: ' VP_RELEASE_SHA
[[ "$VP_RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]
test -z "$(git status --porcelain)"
git cat-file -e "$VP_RELEASE_SHA^{commit}"
OLD_SHA=$(git rev-parse HEAD)
git merge-base --is-ancestor "$OLD_SHA" "$VP_RELEASE_SHA"
git diff --name-status "$OLD_SHA" "$VP_RELEASE_SHA" -- '*/migrations/*' deploy Dockerfile
```

Список должен совпасть с паспортом. Неожиданная миграция, чужие локальные
изменения или другой SHA — остановка до сборки/записи. Никаких reset/force.

```bash
STAMP=$(date +%Y%m%d_%H%M%S)
RELEASE_DIR=/srv/weconomics/releases/vp_$STAMP
mkdir -m 700 -p "$RELEASE_DIR/source"
printf 'RELEASE_DIR=%s\n' "$RELEASE_DIR"
cd /srv/weconomics/app/deploy
WEB_CID=$(docker compose ps -q web)
test -n "$WEB_CID"
OLD_IMAGE=$(docker inspect --format '{{.Image}}' "$WEB_CID")
MEDIA_VOL=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/media"}}{{.Name}}{{end}}{{end}}' "$WEB_CID")
test -n "$MEDIA_VOL"
docker compose ps -a > "$RELEASE_DIR/services-before.txt"
systemctl list-timers --all 'weconomics-*' --no-pager > "$RELEASE_DIR/timers-before.txt"
docker image tag "$OLD_IMAGE" "weconomics-web:rollback-$STAMP"
printf 'OLD_SHA=%s\nOLD_IMAGE=%s\nVP_RELEASE_SHA=%s\nSTAMP=%s\nRELEASE_DIR=%s\nMEDIA_VOL=%s\n' \
 "$OLD_SHA" "$OLD_IMAGE" "$VP_RELEASE_SHA" "$STAMP" "$RELEASE_DIR" "$MEDIA_VOL" > "$RELEASE_DIR/passport.env"
sudo cp -p /srv/weconomics/.env "$RELEASE_DIR/before.env"
sudo chmod 600 "$RELEASE_DIR/before.env"
git -C /srv/weconomics/app archive "$VP_RELEASE_SHA" | tar -x -C "$RELEASE_DIR/source"
docker build --build-arg "GIT_SHA=${VP_RELEASE_SHA:0:7}" -t "weconomics-web:vp-$STAMP" "$RELEASE_DIR/source"
docker image save "weconomics-web:rollback-$STAMP" | gzip > "$RELEASE_DIR/rollback-image.tar.gz"
gzip -t "$RELEASE_DIR/rollback-image.tar.gz"
```

Образ собирается из Git-архива одобренного коммита, а не из папки с приватными
снимками. В старом `.dockerignore` нет исключения `.codex-local`: это особенно
важно. Архив образа, `.env` и следующие резервные файлы приватны, не для GitHub/Notion.

Теперь из **второго окна PowerShell** передать только payload в полученный
`RELEASE_DIR`, подставив именно напечатанный сервером путь:

```powershell
$RemoteRelease = Read-Host 'RELEASE_DIR из серверного окна'
if ($RemoteRelease -notmatch '^/srv/weconomics/releases/vp_[0-9]{8}_[0-9]{6}$') { throw 'Unexpected release path' }
scp -i "$env:USERPROFILE\.ssh\id_ed25519_weconomics" -r .\deploy-payload "makar@135.106.181.151:$RemoteRelease/"
```

На сервере проверить манифест payload по выданным SHA-256:

```bash
python3 - "$RELEASE_DIR/deploy-payload" <<'PYVERIFY'
from pathlib import Path
import hashlib, json, sys
root = Path(sys.argv[1]).resolve()
rows = json.loads((root / 'MANIFEST.json').read_text(encoding='utf-8-sig'))
for row in rows:
    path = (root / row['path']).resolve()
    if not path.is_relative_to(root):
        raise SystemExit('Unexpected payload path')
    if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
        raise SystemExit('Payload hash mismatch: ' + row['path'])
print('Payload hashes verified:', len(rows))
PYVERIFY
```

Не передавать ни Mac-дампы, ни весь каталог backups, ни локальные .env.

## 6. Техническое окно и согласованный снимок

Этот порядок предусматривает закрытие входящего трафика на время миграций и
импорта. Общий nginx обслуживает и dev: dev тоже будет недоступен в это окно.
Заранее согласовать окно. Остановка nginx не является восстановлением данных.

По `timers-before.txt` остановить только фактически включённые таймеры записи
в эту базу и dev-автовыкатку, дождаться завершения соответствующих service.
Не прерывать активный backup/импорт/обслуживание посреди записи. Записать точные
имена остановленного, чтобы потом вернуть лишь то, что было включено.

```bash
cd /srv/weconomics/app/deploy
docker compose stop nginx
docker compose stop tgbot ws web
DB=$(docker compose exec -T postgres printenv POSTGRES_DB | tr -d '\r')
[[ "$DB" =~ ^[a-z_][a-z0-9_]*$ ]]
printf 'DB=%s\n' "$DB" >> "$RELEASE_DIR/passport.env"
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "SELECT datname,application_name,state FROM pg_stat_activity WHERE backend_type='"'"'client backend'"'"';"'
```

Если остался неизвестный клиент, пишущий в боевую базу, сначала выяснить кто это.
Дамп согласован сам по себе, но сверка двух отдельных снимков требует отсутствия
записей между ними. Дальнейшие helper-контейнеры запускают только указанную
Python-команду; entrypoint с миграциями у них не запускается.

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$RELEASE_DIR/before.dump"
test -s "$RELEASE_DIR/before.dump"
docker compose cp "$RELEASE_DIR/before.dump" postgres:/tmp/vp-before.dump
docker compose exec -T postgres pg_restore --list /tmp/vp-before.dump > "$RELEASE_DIR/backup-list.txt"
docker run --rm --network weconomics_backend --env-file "$RELEASE_DIR/before.env" \
 -v "$RELEASE_DIR/deploy-payload:/release:ro" --entrypoint python "$OLD_IMAGE" \
 /release/database_fingerprint.py --database "$DB" > "$RELEASE_DIR/before-fingerprint.json"
PROBE_DB=vp_restore_$STAMP
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$PROBE_DB"
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" --exit-on-error -d "$1" /tmp/vp-before.dump' sh "$PROBE_DB"
docker run --rm --network weconomics_backend --env-file "$RELEASE_DIR/before.env" \
 -v "$RELEASE_DIR/deploy-payload:/release:ro" --entrypoint python "$OLD_IMAGE" \
 /release/database_fingerprint.py --database "$PROBE_DB" > "$RELEASE_DIR/restored-fingerprint.json"
cmp "$RELEASE_DIR/before-fingerprint.json" "$RELEASE_DIR/restored-fingerprint.json"
docker run --rm -v "$MEDIA_VOL:/media:ro" -v "$RELEASE_DIR:/backup" alpine:3.20 \
 sh -c 'tar -czf /backup/media.tar.gz -C /media .'
sudo tar -czf "$RELEASE_DIR/server-settings.tar.gz" -C /srv/weconomics .env nginx certbot
sudo tar -tzf "$RELEASE_DIR/server-settings.tar.gz" > /dev/null
sudo tar -tzf "$RELEASE_DIR/media.tar.gz" > /dev/null
sha256sum "$RELEASE_DIR/before.dump" > "$RELEASE_DIR/before.dump.sha256"
```

Пустой вывод `cmp` и код0 означают совпадение строк, счётчиков, колонок, индексов
и ограничений. Несовпадение — **не запускать импорт**. Пробная база остаётся
отдельной; действующую базу ради проверки не заменяем. Проверить свободное место
до копирования больших media/образов. Alpine-образ можно заранее загрузить на шаге5.

## 7. Код и миграции, пока доступ закрыт

```bash
cd /srv/weconomics/app
test -z "$(git status --porcelain)"
git merge --ff-only "$VP_RELEASE_SHA"
test "$(git rev-parse HEAD)" = "$VP_RELEASE_SHA"
cd deploy
docker image tag "weconomics-web:vp-$STAMP" weconomics-web:latest
docker compose up -d --no-build --force-recreate web
docker compose ps -a web
docker compose logs --tail=100 web
```

Дождаться healthy; ошибки миграций не обходить `--fake`. Миграции и collectstatic
делает единственный web через штатный entrypoint. Второй web с этим entrypoint
не запускать. nginx,ws,tgbot пока остаются остановленными.

```bash
docker compose exec -T web python manage.py check --deploy --fail-level WARNING
docker compose exec -T web python manage.py migrate --check
docker compose cp "$RELEASE_DIR/deploy-payload" web:/tmp/vp-release
docker compose exec -T web python /tmp/vp-release/release_bundle.py \
 --directory /tmp/vp-release/variants --expect-database "$DB" --mode plan > "$RELEASE_DIR/import-plan.json"
```

План просмотреть полностью:33 варианта/583 позиции; создаются только нужные
slug; старые записи ожидаемо обновляются; нет удаления предметов с попытками.
Если есть несданные попытки на изменяемом варианте, импорт блокируется. Не
завершать их насильно и не обходить защиту: определить допустимое окно/порядок
с владельцем. Пробный импорт откатывает строки, но PostgreSQL может увеличить
счётчики ID; пропуски в ID допустимы и не означают потерю данных.

```bash
PLAN_SHA=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["plan_sha256"])' "$RELEASE_DIR/import-plan.json")
BACKUP_SHA=$(sha256sum "$RELEASE_DIR/before.dump" | cut -d' ' -f1)
docker compose exec -T web python /tmp/vp-release/release_bundle.py \
 --directory /tmp/vp-release/variants --expect-database "$DB" --mode apply \
 --maintenance-confirmed --expected-plan-sha256 "$PLAN_SHA" --backup-sha256 "$BACKUP_SHA" > "$RELEASE_DIR/import-result.json"
docker compose exec -T web python /tmp/vp-release/release_bundle.py \
 --directory /tmp/vp-release/variants --expect-database "$DB" --mode verify > "$RELEASE_DIR/import-verified.json"
```

Все33 файла — одна транзакция. Изменился план/файл, ошибка посреди импорта —
строки откатываются, весь пакет не объявляется загруженным. Сам параметр
backup-sha256 не проверяет содержимое бэкапа: это уже сделано шагом6.

## 8. Старые попытки и закрытая HTTP-проверка

```bash
RESCORE_ARGS=()
for file in "$RELEASE_DIR"/deploy-payload/variants/*.yaml; do
  RESCORE_ARGS+=(--variant "$(basename "$file" .yaml)")
done
docker compose exec -T web python manage.py rescore_vp "${RESCORE_ARGS[@]}" --dry-run -v 2 > "$RELEASE_DIR/rescore-plan.txt"
```

Проверить, что изменения баллов объясняются утверждёнными исправлениями
эталонов. Неожиданные номера/массовые изменения — остановка до пересчёта.
Решение23.09 допускает пересчёт по новым эталонам в обе стороны, но не оправдывает
ошибку импорта. Если изменений нет, запись пересчёта не требуется. Если всё
соответствует согласованным исправлениям:

```bash
docker compose exec -T web python manage.py rescore_vp "${RESCORE_ARGS[@]}" > "$RELEASE_DIR/rescore-applied.txt"
docker compose exec -T web python manage.py rescore_vp "${RESCORE_ARGS[@]}" --dry-run > "$RELEASE_DIR/rescore-repeat.txt"
docker compose exec -T web python /tmp/vp-release/web_probe.py --variants /tmp/vp-release/variants > "$RELEASE_DIR/http-smoke.json"
docker compose exec -T web python manage.py vp_wall_status
docker compose exec -T web python manage.py tg_setup --ping
docker compose exec -T web python manage.py tg_setup --check
docker compose exec -T web python manage.py tg_setup --info
```

Повтор пересчёта: изменений нет. HTTP:39 страниц и статика успешно. У Telegram
проверяются реальные настройки существующего бота; токен не печатается.
`--delete-webhook` и `tg_poll --force` по старой инструкции не запускать:
сначала определить фактически используемый способ получения обновлений.
Для уже работающего long polling нужен ровно один tgbot, вебхук пустой.

Почту проверить командой `send_test_email` только на согласованный адрес,
введённый оператором. Получатель подтверждает доставку; успех SMTP сам по себе
не подтверждает ящик. Сверить SPF/DKIM/DMARC и доступный остаток квоты Postbox.
Регистрацию/сброс пароля и стену проверяют собственными тестовыми аккаунтами.

## 9. Открытие и конечная приёмка

**С этой точки могут снова поступать реальные записи.** После запуска бота
и открытия nginx автоматический полный откат БД запрещён: он потеряет новые
действия пользователей. Перед началом зафиксировать время открытия.

```bash
date -Is > "$RELEASE_DIR/opened-at.txt"
docker compose up -d --no-build --force-recreate ws
docker compose --profile tgbot up -d --no-build --force-recreate tgbot
docker compose start nginx
docker compose exec -T nginx nginx -t
docker compose restart nginx
docker compose ps -a
```

Вернуть только ранее активные таймеры. Убедиться, что ws и tgbot подняты, а
не просто отсутствуют в `docker compose ps` без `-a`. tgbot не запускать этим
шагом, если сверка показала иной действующий способ доставки — сначала
согласовать переход. nginx перезапускается после смены IP web/ws.

На `https://weconomics.ai`:
1. Варианты:11 на каждый класс; открыть по одному demo/author/archive.
2. Проверить новый почтовый аккаунт и запасной почтовый путь стены.
3. Подписанный Telegram-аккаунт: привязка → анкета/вариант. Неподписанный:
   требование подписки → подписка → «Проверить» → вариант; нет второй сессии сайта
   во встроенном браузере Telegram.
4. Сохранить ответ, обновить, сдать; результат и повтор без таймера; старые
   попытки доступны. Проверить телефон и планшет в обеих темах.
5. `/health/` успешен; нет500,502,409 отбота, потерянной статики, SMTP-ошибок.
6. Повторить наблюдение через15–30минут. Не объявлять релиз принятым по одному200.

## 10. Откат до открытия: код + база

Применим, пока nginx/ws/tgbot и остальные писатели ещё остановлены и
`opened-at.txt` не создан. Если реальный трафик уже допускался — раздел11.
При неудаче импортёр сам откатывает свою транзакцию; полноценное восстановление
нужно, если уже прошли миграции/успешный импорт/пересчёт, которые требуется отменить.

1. Сохранить логи и текущий неудачный дамп отдельно, ничего не перезаписывать.
2. Остановить новый web. Проверить отсутствие неожиданных клиентов к БД.
3. Переименовать неудачную базу, создать пустую с прежним именем, восстановить
   before.dump. Исходную не удалять. Команды ниже запускаются только оператором
   после проверки переменных из паспортного файла, в прежнем SSH-окне.

```bash
cd /srv/weconomics/app/deploy
docker compose stop nginx tgbot ws web
FAILED_DB=vp_failed_$STAMP
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$RELEASE_DIR/failed-state.dump"
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -v db="$POSTGRES_DB" -v failed="$1"' sh "$FAILED_DB" <<'SQL'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'db' AND pid <> pg_backend_pid();
ALTER DATABASE :"db" RENAME TO :"failed";
SQL
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" --exit-on-error -d "$POSTGRES_DB" /tmp/vp-before.dump'
docker run --rm --network weconomics_backend --env-file "$RELEASE_DIR/before.env" \
 -v "$RELEASE_DIR/deploy-payload:/release:ro" --entrypoint python "$OLD_IMAGE" \
 /release/database_fingerprint.py --database "$DB" > "$RELEASE_DIR/rollback-fingerprint.json"
cmp "$RELEASE_DIR/before-fingerprint.json" "$RELEASE_DIR/rollback-fingerprint.json"
cd /srv/weconomics/app
test -z "$(git status --porcelain)"
git switch --detach "$OLD_SHA"
sudo cp -p "$RELEASE_DIR/before.env" /srv/weconomics/.env
docker image tag "$OLD_IMAGE" weconomics-web:latest
cd deploy
docker compose up -d --no-build --force-recreate web
```

Сверка должна пройти до открытия. Старый entrypoint повторно соберёт его
статические файлы. Восстанавливать media не требуется, если выпуск их не менял:
пакет ВП содержит код/статику и YAML, а не пользовательские загрузки.
Если media всё же менялись, остановиться и восстановить отдельный том из
media.tar.gz с проверкой содержимого, не распаковывать поверх чужих новых загрузок.

После восстановления очистить кэш именно боевых `default` и `sessions` через
старое приложение: это завершит пользовательские сессии, но не удалит аккаунты
или попытки. Убедиться по настройкам, что оба Redis-алиаса относятся к бою,
а не общей сторонней базе:

```bash
docker compose exec -T web python manage.py shell -c "from django.core.cache import caches; caches['default'].clear(); caches['sessions'].clear()"
```

Затем проверить старый web, вернуть прежние ws/tgbot,
запустить и перезапустить nginx, вернуть прежние таймеры. Если прежняя версия
тоже не поднимается — сохранять закрытое окно и диагностировать, не удалять БД.

## 11. Проблема после открытия

Остановить новый входящий трафик и фоновые записи; снять **новый** аварийный дамп.
Не применять before.dump вслепую: между снимком и инцидентом могли появиться
регистрации, ответы, сданные попытки, Telegram-привязки и пользовательские файлы.

При совместимой схеме — вернуть сохранённый старый образ/код, **оставив текущую
базу**, затем проверить. Совместимость определяется сравнением конкретных
миграций, а не утверждением «добавляющие миграции всегда безопасны» из старого
промпта: новые NOT NULL-поля без DB-default тоже способны сломать старый код.
Если откат кода несовместим или повреждены данные — чинить вперёд либо отдельно
подготовить перенос новых записей в восстановленную базу с ручной сверкой.

Отказ Telegram не требует отката базы: по существующему порядку можно отключить
только Telegram-путь и оставить почту, сохранив текущий .env перед изменением.
Техническое отключение почты лишает регистрации/сброса пароля, поэтому не
выключать её автоматически из-за одной ошибки или вместо проверки квоты.

## 12. Что сохранить по окончании

Паспорт SHA/образов/миграций, закрытие и открытие окна, checksum и результаты
восстановления, plan/apply/verify, dry-run пересчёта, конечную проверку доставки,
журналы ошибок. Приватные снимки остаются на сервере/разрешённом носителе.
В существующую задачу Notion — только краткий результат и место доказательств,
без токенов, .env, персональных ответов учеников и дампов. Статус «Готово» ставит Макар.
