#!/bin/zsh
# Финал сессии 6: всё последовательно, без параллельной нагрузки. Итоги — claude/panels_s6/probes/FINAL*/summary.txt.
cd ~/Downloads/qls_platform
F=claude/panels_s6/probes/FINAL_new; mkdir -p $F
: > $F/summary.txt
for e in chromium webkit; do
  for p in cards_probe view_probe answer_panel_probe quiet_probe; do
    t0=$(date +%s)
    ENGINES=$e node calc2/tests/redesign/$p.mjs > $F/${p}_$e.log 2>&1; c=$?
    echo "$p [$e] код $c $(( $(date +%s) - t0 ))с: $(grep -E 'ИТОГ' $F/${p}_$e.log | tail -1)" >> $F/summary.txt
  done
done
echo ГОТОВО >> $F/summary.txt
claude/panels_s5/run_probes.sh claude/panels_s6/probes/FINAL
X=claude/panels_s6/probes/FINAL_extra; mkdir -p $X; : > $X/summary.txt
node claude/panels_s5/razbor_check.mjs > $X/razbor.log 2>&1; echo "razbor_check код $?: $(tail -1 $X/razbor.log)" >> $X/summary.txt
node calc2/tests/input_probe.mjs Ш > $X/input_sh.log 2>&1; echo "input_probe Ш код $?: $(tail -2 $X/input_sh.log | tr '\n' ' ')" >> $X/summary.txt
node calc2/tests/math_answer_probe.mjs > $X/math_answer.log 2>&1; echo "math_answer_probe код $?: $(grep -E 'прошло' $X/math_answer.log | tail -1)" >> $X/summary.txt
node calc2/tests/webkit_probe.mjs > $X/webkit_probe.log 2>&1; echo "webkit_probe код $?: $(tail -2 $X/webkit_probe.log | tr '\n' ' ')" >> $X/summary.txt
node calc2/tests/final_fn_probe.mjs > $X/final_fn.log 2>&1; echo "final_fn_probe код $?: $(grep -cE 'FAIL|✗' $X/final_fn.log) провалов; $(tail -1 $X/final_fn.log)" >> $X/summary.txt
node calc2/tests/priyomka_probe.mjs > $X/priyomka.log 2>&1; echo "priyomka_probe код $?: $(grep -cE 'FAIL|✗' $X/priyomka.log) провалов; $(tail -1 $X/priyomka.log)" >> $X/summary.txt
CALC2_BASE_URL=http://127.0.0.1:8098 node calc2/tests/final_fn_probe.mjs > $X/final_fn_before.log 2>&1; echo "final_fn_probe ДО (8098) код $?: $(grep -cE 'FAIL|✗' $X/final_fn_before.log) провалов" >> $X/summary.txt
CALC2_BASE_URL=http://127.0.0.1:8098 node calc2/tests/priyomka_probe.mjs > $X/priyomka_before.log 2>&1; echo "priyomka_probe ДО (8098) код $?: $(grep -cE 'FAIL|✗' $X/priyomka_before.log) провалов" >> $X/summary.txt
node calc2/tests/calc2_ui.mjs > $X/calc2_ui.log 2>&1; echo "calc2_ui код $?: $(tail -1 $X/calc2_ui.log)" >> $X/summary.txt
node calc2/tests/redesign/modes_probe.mjs > $X/modes.log 2>&1; echo "modes_probe код $?: $(tail -1 $X/modes.log)" >> $X/summary.txt
node calc2/tests/memory_probe.mjs > $X/memory.log 2>&1; echo "memory_probe код $?: $(tail -1 $X/memory.log)" >> $X/summary.txt
echo ГОТОВО >> $X/summary.txt
