#!/bin/zsh
# WebKit и razbor_check по этапу А — на копии кода этапа (сервер 8093, worktree stA), после приборов «до».
SP=/private/tmp/claude-501/-Users-makarmalinovskiy-Downloads-qls-platform/d72d24f3-1a13-45d4-a86a-5f158f12dbbc/scratchpad
O=~/Downloads/qls_platform/claude/panels_s7/probes/A_webkit; mkdir -p $O; : > $O/summary.txt
until grep -q ГОТОВО ~/Downloads/qls_platform/claude/panels_s7/probes/before_extra/summary.txt 2>/dev/null; do sleep 20; done
cd $SP/stA
export CALC2_BASE_URL=http://127.0.0.1:8093 BASE=http://127.0.0.1:8093
ENGINES=webkit node calc2/tests/redesign/cards_probe.mjs --only И,Л > $O/cards_IL.log 2>&1; echo "cards И,Л webkit код $?: $(grep ИТОГ $O/cards_IL.log)" >> $O/summary.txt
ENGINES=webkit node calc2/tests/redesign/answer_panel_probe.mjs --only З,И > $O/ans_ZI.log 2>&1; echo "answer_panel З,И webkit код $?: $(grep ИТОГ $O/ans_ZI.log)" >> $O/summary.txt
ENGINES=webkit node calc2/tests/redesign/axis_labels_probe.mjs > $O/axis.log 2>&1; echo "axis_labels webkit код $?: $(grep ИТОГ $O/axis.log)" >> $O/summary.txt
node claude/panels_s5/razbor_check.mjs > $O/razbor.log 2>&1; echo "razbor_check (chromium) код $?: $(tail -1 $O/razbor.log)" >> $O/summary.txt
echo ГОТОВО >> $O/summary.txt
