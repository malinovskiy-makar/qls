# Продолжение после исправлений аудита

Рабочая копия: `/private/tmp/calc2-astra-local-20261102/calc2-astra-work`.
Ветка: `codex/calc2-astra-20261102`; remote отсутствует.
База текущих исправлений: `15bd4a4b6955b3aa59f6abe9f557671e81fac363`.
Точный итоговый HEAD записан в `SHA256_MANIFEST.json` и `RESTORE_VERIFICATION.json`.

Рабочая папка тренажёра `/Users/makarmalinovskiy/Documents/ChatGPT/Weconomics/codex-work`
не менялась. Не переносить туда файлы автоматически. Не использовать backups,
qls, verification-work или codex-restore-check как рабочую копию графиков.

`work.bundle` содержит полную локальную историю и восстанавливается без
предыдущего снимка. Проверенное восстановление выполнено в отдельную папку
`/private/tmp`; адрес и результат fsck указаны в `RESTORE_VERIFICATION.json`.
У восстановленной копии origin удалён. Никаких push или deploy.

Пример ручного восстановления в НОВУЮ пустую папку:

```sh
git clone /полный/путь/к/work.bundle /новая/папка
git -C /новая/папка remote remove origin
```

В комплект не добавлялись реальные .env или базы. Проверки используют только
собственное окружение `claude/calc2_astra_20261102/run_local.py` и отдельный
CI launcher `claude/calc2_astra_20261103_fixes/run_ci.py`. Для обычного сервера
используется синтетическая SQLite и locmem, адрес `http://127.0.0.1:8113/calc2/`.
Сервисы обязательного CI принадлежат этой задаче: PostgreSQL17 на 61383,
Redis на 61384. Не подключаться к системным службам и не останавливать чужие.

Контрольные команды из рабочей копии:

```sh
node calc2/tests/astra_audit_fixes.mjs
python3 claude/calc2_astra_20261102/run_local.py manage test calc2.tests.test_audit_math
python3 claude/calc2_astra_20261103_fixes/run_ci.py calc2
python3 scripts/check_em_dash.py --json
```

Для PDF использована метка `audit-fixes-final-v3-20261103` существующего
`build_all_pdfs.py`. Сборка выполнена после локального коммита. Отпечатки
всех runtime-файлов сверяются с финальным кодом перед сохранением комплекта.

После приёмки расчётов обсуждать внешний вид V01–V05. Макар статус «Готово»
ставит сам; текущий результат только «На проверке».
