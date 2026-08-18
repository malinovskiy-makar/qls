#!/usr/bin/env bash
# =============================================================================
# Полный пересчёт эмбеддингов + перестройка кэша похожих задач
# Запуск: caffeinate -i ./run_full_recompute.sh
#
# Устойчивость к перезапуску:
#   Пересчёт идёт через night_embeddings с done-файлом. После каждых 100 задач
#   обработанные id дописываются в DONE_FILE. При повторном запуске команда
#   читает done-файл и пропускает уже сделанное — продолжает с места обрыва.
#   Единственное условие: НЕ удалять DONE_FILE между запусками!
#
#   Если нужно начать СТРОГО С НУЛЯ (не с продолжения):
#     rm reports/recompute_2026-07/embeddings_done_ids.txt
#     ./run_full_recompute.sh
#
# Устройство: строго CPU (MPS зависает на BGE-M3 при 8 ГБ RAM).
# Батч кодирования: 8 (безопасно для 8 ГБ RAM).
# =============================================================================

set -euo pipefail

PYTHON="./venv/bin/python"
MANAGE="$PYTHON manage.py"

LOG_DIR="reports/recompute_2026-07"
LOG_FILE="$LOG_DIR/recompute.log"
ALL_IDS_FILE="$LOG_DIR/all_problem_ids.txt"
DONE_FILE="$LOG_DIR/embeddings_done_ids.txt"
MISSING_FILE="$LOG_DIR/missing_ids.txt"

# ---------- 0. Подготовка ----------
mkdir -p "$LOG_DIR"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

log "=== Старт полного пересчёта эмбеддингов ==="
log "LOG_DIR:      $LOG_DIR"
log "ALL_IDS_FILE: $ALL_IDS_FILE"
log "DONE_FILE:    $DONE_FILE"

# ---------- 1. Экспортируем ВСЕ id задач ----------
# (перегенерируем при каждом старте — быстро, гарантирует актуальность)
log "Экспортируем все id задач..."
$PYTHON -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from problems.models import Problem
ids = list(Problem.objects.values_list('id', flat=True))
with open('$ALL_IDS_FILE', 'w') as f:
    f.write('\n'.join(str(i) for i in ids) + '\n')
print(f'Записано {len(ids)} id в $ALL_IDS_FILE')
"

TOTAL_IDS=$(wc -l < "$ALL_IDS_FILE" | tr -d ' ')
log "Всего задач для пересчёта: $TOTAL_IDS"

# ---------- 2. Пересчёт эмбеддингов ----------
log "Запуск night_embeddings (device=cpu, encode-batch=8)..."
$MANAGE night_embeddings \
    --ids-file "$ALL_IDS_FILE" \
    --done-file "$DONE_FILE" \
    --log-file  "$LOG_FILE" \
    --device cpu \
    --encode-batch 8

log "night_embeddings завершён."

# ---------- 3. Контроль полноты ----------
log "Проверяем полноту пересчёта (размерность 1024 = 4096 байт)..."
$PYTHON -c "
import django, os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from problems.models import Problem
from problems.embedding_config import EMBEDDING_DIM

EMBEDDING_BYTES = EMBEDDING_DIM * 4  # 4096 для BGE-M3

total = Problem.objects.count()

# Задачи с правильной размерностью вектора
ok_ids = set(
    Problem.objects.extra(
        where=['length(embedding) = %s'], params=[EMBEDDING_BYTES]
    ).values_list('id', flat=True)
)

all_ids = set(Problem.objects.values_list('id', flat=True))
missing_ids = sorted(all_ids - ok_ids)

print(f'Всего задач: {total}')
print(f'С правильным вектором ({EMBEDDING_DIM}d): {len(ok_ids)}')
print(f'Без правильного вектора: {len(missing_ids)}')

if missing_ids:
    with open('$MISSING_FILE', 'w') as f:
        f.write('\n'.join(str(i) for i in missing_ids) + '\n')
    print(f'ВНИМАНИЕ: {len(missing_ids)} id записаны в $MISSING_FILE')
    sys.exit(1)
else:
    print('ОК: все задачи имеют актуальный вектор.')
    sys.exit(0)
" && COMPLETENESS_OK=1 || COMPLETENESS_OK=0

# ---------- 4. Перестройка кэша похожих задач ----------
if [ "$COMPLETENESS_OK" -eq 1 ]; then
    log "Пересчёт эмбеддингов полный. Запускаем cache_similar --rebuild..."
    $MANAGE cache_similar --rebuild 2>&1 | tee -a "$LOG_FILE"

    # Итоговая статистика
    SIMILAR_COUNT=$($PYTHON -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from problems.models import Problem
through = Problem.similar_problems.through
print(through.objects.count())
")
    log "=== ИТОГ ==="
    log "Векторов пересчитано: $TOTAL_IDS"
    log "Связей в кэше похожих: $SIMILAR_COUNT"
    log "Пропущено задач: 0"
    log "=== Готово ==="
else
    MISSING_COUNT=$(wc -l < "$MISSING_FILE" | tr -d ' ')
    log "=== ИТОГ (НЕ ПОЛНЫЙ) ==="
    log "Векторов с правильной размерностью: меньше $TOTAL_IDS"
    log "Пропущено задач: $MISSING_COUNT (см. $MISSING_FILE)"
    log "КЭША ПОХОЖИХ НЕ ПЕРЕСТРАИВАЛИ — сначала исправьте пропуски."
    log "Для продолжения запустите скрипт повторно (done-файл сохранён)."
    exit 1
fi
