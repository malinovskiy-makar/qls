#!/bin/zsh
# Конец этапа Г (сессия 6): опись и сверка, Ж в Chromium и WebKit, math_answer_probe, calc2_math, снимки.
cd ~/Downloads/qls_platform
O=claude/panels_s6/probes/G; mkdir -p $O
node claude/mockups/calc2_panels_20261014/tools/panels_inventory.mjs claude/panels_s6/S6_G.json > $O/inventory.log 2>&1
node claude/mockups/calc2_panels_20261014/tools/panels_compare.mjs claude/panels_s6/S6_V.json claude/panels_s6/S6_G.json claude/panels_s6/B_allow.json > claude/panels_s6/S6_G_compare.txt 2>&1
echo "сверка S6_V → S6_G: $(tail -1 claude/panels_s6/S6_G_compare.txt)" > $O/summary.txt
ENGINES=chromium node calc2/tests/redesign/cards_probe.mjs --only Ж > $O/cards_Zh_chromium.log 2>&1; echo "cards Ж chromium: $(tail -1 $O/cards_Zh_chromium.log)" >> $O/summary.txt
ENGINES=webkit node calc2/tests/redesign/cards_probe.mjs --only Ж > $O/cards_Zh_webkit.log 2>&1; echo "cards Ж webkit: $(tail -1 $O/cards_Zh_webkit.log)" >> $O/summary.txt
ENGINES=webkit node calc2/tests/redesign/cards_probe.mjs --only Д > $O/cards_D_webkit.log 2>&1; echo "cards Д webkit: $(tail -1 $O/cards_D_webkit.log)" >> $O/summary.txt
node calc2/tests/math_answer_probe.mjs > $O/math_answer.log 2>&1; echo "math_answer_probe код $?: $(grep -E 'прошло|провал' $O/math_answer.log | tail -1)" >> $O/summary.txt
node calc2/tests/calc2_math.mjs > $O/calc2_math.log 2>&1; echo "calc2_math код $?: $(grep -E 'регрессия' $O/calc2_math.log | tail -1)" >> $O/summary.txt
D=claude/shots/calc2_panels_s6
THEMES="light dark" node claude/panels_s6/shots_left.mjs $D ineq "ineq@document.getElementById('ineq-in-incomes').click()" "ineq@document.getElementById('ineq-in-formula').click();document.getElementById('ineq-redist').click()" "m-graph@setFieldValue(document.querySelector('#graph-rows .grow.sc-gnew input[id]'),'2*x+1')" m-minmax m-tangent m-transform m-optimum m-constraint > $O/shots.log 2>&1
echo ГОТОВО >> $O/summary.txt
