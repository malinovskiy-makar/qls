#!/bin/zsh
# Фаза −1 сессии 6: опись «до», сверка с S5_G, приборы «до» — на сервере 8098 (копия кода старта 76c55cfa),
# чтобы правка статики на 8099 не попала в замер «до». Всё последовательно, логи в claude/panels_s6/probes/before*.
cd ~/Downloads/qls_platform
export CALC2_BASE_URL=http://127.0.0.1:8098 BASE=http://127.0.0.1:8098
O=claude/panels_s6/probes
mkdir -p $O/before_extra
node claude/mockups/calc2_panels_20261014/tools/panels_inventory.mjs claude/panels_s6/S6_before.json > $O/before_extra/inventory.log 2>&1
node claude/mockups/calc2_panels_20261014/tools/panels_compare.mjs claude/panels_s5/S5_G.json claude/panels_s6/S6_before.json claude/panels_s5/none.json > claude/panels_s6/S6_before_vs_S5G.txt 2>&1
echo "сверка S5_G → S6_before: $(tail -1 claude/panels_s6/S6_before_vs_S5G.txt)" > $O/before_extra/summary.txt
claude/panels_s5/run_probes.sh $O/before
ENGINES=chromium BEFORE=http://127.0.0.1:8098 node calc2/tests/redesign/cards_probe.mjs > $O/before_extra/cards_chromium.log 2>&1; echo "cards chromium код $?: $(tail -1 $O/before_extra/cards_chromium.log)" >> $O/before_extra/summary.txt
ENGINES=webkit BEFORE=http://127.0.0.1:8098 node calc2/tests/redesign/cards_probe.mjs > $O/before_extra/cards_webkit.log 2>&1; echo "cards webkit код $?: $(tail -1 $O/before_extra/cards_webkit.log)" >> $O/before_extra/summary.txt
node claude/panels_s5/razbor_check.mjs > $O/before_extra/razbor.log 2>&1; echo "razbor_check код $?: $(tail -1 $O/before_extra/razbor.log)" >> $O/before_extra/summary.txt
node calc2/tests/input_probe.mjs Ш > $O/before_extra/input_sh.log 2>&1; echo "input_probe Ш код $?: $(tail -2 $O/before_extra/input_sh.log | tr '\n' ' ')" >> $O/before_extra/summary.txt
node calc2/tests/math_answer_probe.mjs > $O/before_extra/math_answer.log 2>&1; echo "math_answer_probe код $?: $(tail -2 $O/before_extra/math_answer.log | tr '\n' ' ')" >> $O/before_extra/summary.txt
node calc2/tests/webkit_probe.mjs > $O/before_extra/webkit_probe.log 2>&1; echo "webkit_probe код $?: $(tail -2 $O/before_extra/webkit_probe.log | tr '\n' ' ')" >> $O/before_extra/summary.txt
echo ГОТОВО >> $O/before_extra/summary.txt
