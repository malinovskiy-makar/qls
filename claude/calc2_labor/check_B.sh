#!/bin/zsh
# После точки переписывания эталонов (конец этапа Б): сторожа на сервере 8099, Chromium, последовательно.
cd ~/Downloads/qls_platform
O=claude/calc2_labor/probes/B; mkdir -p $O
claude/panels_s5/run_probes.sh $O calc2/tests/redesign/session_probe.mjs calc2/tests/redesign/parity_quick.mjs calc2/tests/tex/ci_quick.mjs
X=$O/extra; mkdir -p $X; : > $X/summary.txt
node calc2/tests/redesign/answer_rows_probe.mjs --only П > $X/answer_rows_P.log 2>&1; echo "answer_rows П код $?: $(tail -1 $X/answer_rows_P.log)" >> $X/summary.txt
ENGINES=chromium KEYS="labor labor-mono labor-union labor-bilat isoquant m-graph" node calc2/tests/redesign/cards_probe.mjs --only Г,Л > $X/cards_GL.log 2>&1; echo "cards Г,Л код $?: $(grep ИТОГ $X/cards_GL.log | tail -1)" >> $X/summary.txt
echo ГОТОВО >> $X/summary.txt
