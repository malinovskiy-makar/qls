#!/bin/zsh
# Конец этапа Д (сессия 6): опись и сверка, З в Chromium и WebKit, снимки рядом с макетами.
cd ~/Downloads/qls_platform
O=claude/panels_s6/probes/D; mkdir -p $O
node claude/mockups/calc2_panels_20261014/tools/panels_inventory.mjs claude/panels_s6/S6_D.json > $O/inventory.log 2>&1
node claude/mockups/calc2_panels_20261014/tools/panels_compare.mjs claude/panels_s6/S6_G.json claude/panels_s6/S6_D.json claude/panels_s6/D_allow.json > claude/panels_s6/S6_D_compare.txt 2>&1
echo "сверка S6_G → S6_D: $(tail -1 claude/panels_s6/S6_D_compare.txt)" > $O/summary.txt
ENGINES=chromium node calc2/tests/redesign/cards_probe.mjs --only З > $O/cards_Z_chromium.log 2>&1; echo "cards З chromium: $(tail -1 $O/cards_Z_chromium.log)" >> $O/summary.txt
ENGINES=webkit node calc2/tests/redesign/cards_probe.mjs --only З > $O/cards_Z_webkit.log 2>&1; echo "cards З webkit: $(tail -1 $O/cards_Z_webkit.log)" >> $O/summary.txt
D=claude/shots/calc2_panels_s6
THEMES="light dark" node claude/panels_s6/shots_left.mjs $D/D taxes "taxes@setType('subsidy'); setTaxForm('unit'); setTax(20);" mono sd sdsum ceil quota ext smallopen "smallopen@setOpenPw(30); setOpenTool('quota'); STATE.openQuota = 20;" > $O/shots.log 2>&1
for t in light dark; do
  python3 claude/panels_s6/side_by_side.py $D/D/mono_$t.png claude/mockups/calc2_panels_20261014/reference/05_left_Mono_$t.png $D/D/mono_vs_mockup_$t.png
  python3 claude/panels_s6/side_by_side.py $D/D/taxes_$t.png claude/mockups/calc2_panels_20261014/reference/06_left_taxes_$t.png $D/D/taxes_vs_mockup_$t.png
done
echo ГОТОВО >> $O/summary.txt
