#!/bin/zsh
# Фаза −1 сессии «рынок труда»: сторожа главного инварианта на коде до сессии (сервер 8098, bfb74cc3), Chromium,
# последовательно; затем хвост сессии 7 — cards_probe целиком (тоже сервер 8098: код bfb74cc3, чтобы правки на 8099 его не задели).
cd ~/Downloads/qls_platform
O=claude/calc2_labor/probes
CALC2_BASE_URL=http://127.0.0.1:8098 claude/panels_s5/run_probes.sh $O/before \
  calc2/tests/control_numbers.mjs calc2/tests/calc2_math.mjs calc2/tests/redesign/parity_quick.mjs \
  calc2/tests/redesign/session_probe.mjs calc2/tests/tex/ci_quick.mjs calc2/tests/redesign/answer_rows_probe.mjs
X=$O/before_extra; mkdir -p $X; : > $X/summary.txt
CALC2_BASE_URL=http://127.0.0.1:8098 ENGINES=chromium node calc2/tests/redesign/cards_probe.mjs > $X/cards_chromium.log 2>&1
echo "cards chromium код $?: $(grep ИТОГ $X/cards_chromium.log | tail -1)" >> $X/summary.txt
echo ГОТОВО >> $X/summary.txt
