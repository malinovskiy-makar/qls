#!/bin/zsh
# А2: инварианты правки подписей осей — прибор, контрольные числа, .tex стартов, кривые мышью, паритет.
cd ~/Downloads/qls_platform
O=claude/panels_s7/probes/A; mkdir -p $O
ENGINES=chromium node calc2/tests/redesign/axis_labels_probe.mjs > $O/axis_after.log 2>&1; echo "axis: $? $(tail -1 $O/axis_after.log)"
node calc2/tests/control_numbers.mjs > $O/cn_A2.log 2>&1; echo "cn: $? $(tail -1 $O/cn_A2.log)"
node calc2/tests/tex/ci_quick.mjs > $O/ciq_A2.log 2>&1; echo "ci_quick: $? $(tail -2 $O/ciq_A2.log | tr '\n' ' ')"
node scripts/calc2_nodrag_probe.js 8099 $O/nodrag_A2.json > $O/nodrag_A2.log 2>&1; echo "nodrag: $? $(tail -1 $O/nodrag_A2.log)"
node calc2/tests/redesign/parity_quick.mjs > $O/parity_A2.log 2>&1; echo "parity: $? $(tail -1 $O/parity_A2.log)"
CALC2_BASE_URL=http://127.0.0.1:8099 node calc2/tests/canon_checks.mjs > $O/canon_A2.log 2>&1; echo "canon: $? $(grep -E 'label_shake|ИТОГ|FAIL' $O/canon_A2.log | tail -4 | tr '\n' ' ')"
