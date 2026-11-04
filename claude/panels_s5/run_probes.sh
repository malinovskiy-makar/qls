#!/bin/zsh
# Прогон приборов сессии 5 последовательно: лог каждого в папку, сводка (код, время, хвост) в summary.txt.
#   claude/panels_s5/run_probes.sh <папка> [прибор ...]   (без списка — список фазы −1)
# Окружение: сервер 8099 (--settings=config.settings_check). ENGINES для новых приборов — по умолчанию chromium.
cd ~/Downloads/qls_platform
OUT=$1; shift
mkdir -p "$OUT"
LIST=("$@")
if [ ${#LIST} -eq 0 ]; then
  LIST=(calc2/tests/redesign/view_probe.mjs calc2/tests/redesign/answer_panel_probe.mjs calc2/tests/redesign/quiet_probe.mjs
        calc2/tests/redesign/state_probe.mjs calc2/tests/redesign/session_probe.mjs calc2/tests/redesign/parity_quick.mjs
        calc2/tests/redesign/answer_probe.mjs calc2/tests/redesign/answer_rows_probe.mjs calc2/tests/control_numbers.mjs
        calc2/tests/calc2_math.mjs calc2/tests/redesign/layout_probe.mjs calc2/tests/tex/ci_quick.mjs
        scripts/calc2_nodrag_probe.js calc2/tests/check_font_scale.mjs calc2/tests/canon_checks.mjs)
fi
export CALC2_BASE_URL=${CALC2_BASE_URL:-http://127.0.0.1:8099}
export ENGINES=${ENGINES:-chromium}
: > "$OUT/summary.txt"
for p in $LIST; do
  name=${p//\//_}
  t0=$(date +%s)
  if [[ $p == scripts/calc2_nodrag_probe.js ]]; then
    node $p ${CALC2_BASE_URL##*:} "$OUT/nodrag.json" > "$OUT/$name.log" 2>&1
  else
    node $p > "$OUT/$name.log" 2>&1
  fi
  code=$?
  t1=$(date +%s)
  { echo "### $p  код $code  $((t1-t0))с"; grep -E 'FAIL|ПРОВАЛ|ИТОГ|ВСЁ СОШЛОСЬ|ВСЕ |сошлось|Итог|ПАРИТЕТ|регрессия|проверок не прошло|сдвинутых|ЦЕЛА|label_shake|DONE|РАСКЛАДКА|провалов|расхождени' "$OUT/$name.log" | tail -12; echo; } >> "$OUT/summary.txt"
done
echo "ГОТОВО" >> "$OUT/summary.txt"
