#!/bin/zsh
# Финал сессии «рынок труда»: всё последовательно, без параллельной нагрузки (сервер 8099). Итоги — probes/FINAL*/summary.txt.
cd ~/Downloads/qls_platform
O=claude/calc2_labor/probes
export OUT=$O/FINAL_tex
claude/panels_s5/run_probes.sh $O/FINAL calc2/tests/control_numbers.mjs calc2/tests/calc2_math.mjs calc2/tests/tex/ci_quick.mjs \
  calc2/tests/redesign/parity_quick.mjs calc2/tests/redesign/session_probe.mjs calc2/tests/redesign/answer_rows_probe.mjs \
  calc2/tests/redesign/modes_probe.mjs calc2/tests/calc2_ui.mjs
unset OUT
X=$O/FINAL_extra; mkdir -p $X; : > $X/summary.txt
L="labor labor-mono labor-union labor-bilat"
node calc2/tests/tex/lint.mjs $O/FINAL_tex > $X/tex_lint.log 2>&1; echo "tex/lint код $?: $(tail -1 $X/tex_lint.log)" >> $X/summary.txt
for e in chromium webkit; do
  ENGINES=$e node calc2/tests/redesign/labor_probe.mjs > $X/labor_$e.log 2>&1; echo "labor_probe $e код $?: $(grep ИТОГ $X/labor_$e.log)" >> $X/summary.txt
  ENGINES=$e KEYS="$L" node calc2/tests/redesign/axis_labels_probe.mjs > $X/axis_$e.log 2>&1; echo "axis_labels $e код $?: $(grep ИТОГ $X/axis_$e.log)" >> $X/summary.txt
done
ENGINES=chromium KEYS="$L" node calc2/tests/redesign/answer_panel_probe.mjs > $X/answer_panel.log 2>&1; echo "answer_panel (труд) код $?: $(grep ИТОГ $X/answer_panel.log)" >> $X/summary.txt
ENGINES=chromium KEYS="$L" node calc2/tests/redesign/cards_probe.mjs > $X/cards.log 2>&1; echo "cards (труд) код $?: $(grep ИТОГ $X/cards.log)" >> $X/summary.txt
node calc2/tests/redesign/state_probe.mjs --base calc2/tests/redesign/baseline --keys labor,labor-mono,labor-union,labor-bilat > $X/state.log 2>&1; echo "state_probe (труд) код $?: $(tail -2 $X/state.log | tr '\n' ' ')" >> $X/summary.txt
for p in calc2/tests/final_fn_probe.mjs calc2/tests/priyomka_probe.mjs calc2/tests/calc2_blocks.mjs calc2/tests/phase5_coord_prefix_probe.mjs; do
  n=${p:t:r}; node $p > $X/$n.log 2>&1; echo "$n код $?: $(grep -cE 'FAIL|✗' $X/$n.log) FAIL/✗; $(tail -1 $X/$n.log | cut -c1-200)" >> $X/summary.txt
done
node claude/panels_s5/razbor_check.mjs > $X/razbor.log 2>&1; echo "razbor_check код $?: $(tail -1 $X/razbor.log)" >> $X/summary.txt
node calc2/tests/check_tex_escapes.mjs > $X/tex_escapes.log 2>&1; echo "check_tex_escapes код $?: $(head -1 $X/tex_escapes.log)" >> $X/summary.txt
node calc2/tests/tex/sites.mjs > $X/sites.log 2>&1; echo "tex/sites код $?: $(tail -1 $X/sites.log)" >> $X/summary.txt
node claude/panels_s7/tpl_escapes.mjs > $X/tpl.log 2>&1; echo "tpl_escapes код $?: $(tail -1 $X/tpl.log)" >> $X/summary.txt
python3 scripts/check_em_dash.py > $X/em_dash.log 2>&1; echo "check_em_dash код $?: $(tail -1 $X/em_dash.log)" >> $X/summary.txt
echo ГОТОВО >> $X/summary.txt
