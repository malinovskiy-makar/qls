#!/bin/zsh
# Финал сессии 7: всё последовательно, без параллельной нагрузки (сервер 8099). Итоги — probes/FINAL*/summary.txt.
cd ~/Downloads/qls_platform
claude/panels_s5/run_probes.sh claude/panels_s7/probes/FINAL
X=claude/panels_s7/probes/FINAL_extra; mkdir -p $X; : > $X/summary.txt
ENGINES=chromium node calc2/tests/redesign/cards_probe.mjs > $X/cards_chromium.log 2>&1; echo "cards chromium код $?: $(grep ИТОГ $X/cards_chromium.log | tail -1)" >> $X/summary.txt
for p in calc2/tests/redesign/modes_probe.mjs calc2/tests/calc2_ui.mjs calc2/tests/calc2_blocks.mjs calc2/tests/panels_probe.mjs \
         calc2/tests/phase5_vertex_snap_probe.mjs calc2/tests/phase5_coord_prefix_probe.mjs calc2/tests/self_probe.mjs \
         calc2/tests/mc_drag_probe.mjs calc2/tests/memory_probe.mjs calc2/tests/final_fn_probe.mjs calc2/tests/priyomka_probe.mjs \
         calc2/tests/math_answer_probe.mjs calc2/tests/webkit_probe.mjs; do
  n=${p:t:r}; t0=$(date +%s)
  node $p > $X/$n.log 2>&1; c=$?
  echo "$n код $c $(( $(date +%s) - t0 ))с: $(grep -cE 'FAIL|✗' $X/$n.log) FAIL/✗; $(tail -1 $X/$n.log | cut -c1-200)" >> $X/summary.txt
done
node calc2/tests/from_problem_probe.mjs http://127.0.0.1:8099 > $X/from_problem.log 2>&1; echo "from_problem_probe код $?: $(tail -1 $X/from_problem.log | cut -c1-200)" >> $X/summary.txt
node claude/panels_s5/razbor_check.mjs > $X/razbor.log 2>&1; echo "razbor_check код $?: $(tail -1 $X/razbor.log)" >> $X/summary.txt
node calc2/tests/input_probe.mjs Ш > $X/input_sh.log 2>&1; echo "input_probe Ш код $?: $(tail -2 $X/input_sh.log | tr '\n' ' ')" >> $X/summary.txt
node calc2/tests/tex/sites.mjs > $X/sites.log 2>&1; echo "tex/sites код $?: $(tail -1 $X/sites.log)" >> $X/summary.txt
node claude/panels_s7/tpl_escapes.mjs > $X/tpl.log 2>&1; echo "tpl_escapes код $?: $(tail -1 $X/tpl.log)" >> $X/summary.txt
python3 scripts/check_em_dash.py > $X/em_dash.log 2>&1; echo "check_em_dash код $?: $(tail -1 $X/em_dash.log)" >> $X/summary.txt
for e in chromium webkit; do
  ENGINES=$e node calc2/tests/redesign/axis_labels_probe.mjs > $X/axis_$e.log 2>&1; echo "axis_labels $e код $?: $(grep ИТОГ $X/axis_$e.log)" >> $X/summary.txt
  ENGINES=$e node calc2/tests/redesign/answer_panel_probe.mjs --only З,И > $X/ans_ZI_$e.log 2>&1; echo "answer_panel З,И $e код $?: $(grep ИТОГ $X/ans_ZI_$e.log)" >> $X/summary.txt
done
ENGINES=webkit node calc2/tests/redesign/cards_probe.mjs --only И,Л > $X/cards_IL_webkit.log 2>&1; echo "cards И,Л webkit код $?: $(grep ИТОГ $X/cards_IL_webkit.log)" >> $X/summary.txt
node claude/mockups/calc2_panels_20261014/tools/panels_inventory.mjs claude/panels_s7/S7_G.json > $X/inventory.log 2>&1
node claude/mockups/calc2_panels_20261014/tools/panels_compare.mjs claude/panels_s7/S7_V.json claude/panels_s7/S7_G.json claude/panels_s5/none.json > claude/panels_s7/S7_G_compare.txt 2>&1
echo "сверка S7_V → S7_G: $(tail -1 claude/panels_s7/S7_G_compare.txt)" >> $X/summary.txt
node claude/mockups/calc2_panels_20261014/tools/panels_compare.mjs claude/panels_s7/S7_before.json claude/panels_s7/S7_G.json claude/panels_s7/ALL_allow.json > claude/panels_s7/S7_all_compare.txt 2>&1
echo "сверка S7_before → S7_G (ALL_allow): $(tail -1 claude/panels_s7/S7_all_compare.txt)" >> $X/summary.txt
echo ГОТОВО >> $X/summary.txt
