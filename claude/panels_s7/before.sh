#!/bin/zsh
# Фаза −1 сессии 7: опись «до» на 8099 (код b4152f73, до первой правки), сверка с S6_D; затем приборы «до» на 8098
# (копия кода старта b4152f73), чтобы правка статики на 8099 не попала в замер «до». Всё последовательно.
cd ~/Downloads/qls_platform
S=claude/panels_s7; O=$S/probes
mkdir -p $O/before_extra
node claude/mockups/calc2_panels_20261014/tools/panels_inventory.mjs $S/S7_before.json > $O/before_extra/inventory.log 2>&1
node claude/mockups/calc2_panels_20261014/tools/panels_compare.mjs claude/panels_s6/S6_D.json $S/S7_before.json claude/panels_s5/none.json > $S/S7_before_vs_S6D.txt 2>&1
echo "сверка S6_D → S7_before: $(tail -1 $S/S7_before_vs_S6D.txt)" > $O/before_extra/summary.txt
echo ОПИСЬ-ГОТОВА >> $O/before_extra/summary.txt
export CALC2_BASE_URL=http://127.0.0.1:8098 BASE=http://127.0.0.1:8098
claude/panels_s5/run_probes.sh $O/before
X=$O/before_extra
ENGINES=chromium BEFORE=http://127.0.0.1:8098 node calc2/tests/redesign/cards_probe.mjs > $X/cards_chromium.log 2>&1; echo "cards chromium код $?: $(grep ИТОГ $X/cards_chromium.log | tail -1)" >> $X/summary.txt
for p in calc2/tests/redesign/modes_probe.mjs calc2/tests/calc2_ui.mjs calc2/tests/calc2_blocks.mjs calc2/tests/panels_probe.mjs \
         calc2/tests/phase5_vertex_snap_probe.mjs calc2/tests/phase5_coord_prefix_probe.mjs calc2/tests/self_probe.mjs \
         calc2/tests/mc_drag_probe.mjs calc2/tests/memory_probe.mjs calc2/tests/final_fn_probe.mjs calc2/tests/priyomka_probe.mjs \
         calc2/tests/math_answer_probe.mjs; do
  n=${p:t:r}; t0=$(date +%s)
  node $p > $X/$n.log 2>&1; c=$?
  echo "$n код $c $(( $(date +%s) - t0 ))с: $(grep -cE 'FAIL|✗' $X/$n.log) FAIL/✗; $(tail -1 $X/$n.log | cut -c1-200)" >> $X/summary.txt
done
node calc2/tests/from_problem_probe.mjs http://127.0.0.1:8098 > $X/from_problem.log 2>&1; echo "from_problem_probe код $?: $(tail -1 $X/from_problem.log | cut -c1-200)" >> $X/summary.txt
echo ГОТОВО >> $X/summary.txt
