#!/bin/zsh
# pts_probe Б (Chromium и WebKit, 1 440 и 1 280) — на копии кода этапа Б (сервер 8094, worktree stB), после WebKit этапа А.
SP=/private/tmp/claude-501/-Users-makarmalinovskiy-Downloads-qls-platform/d72d24f3-1a13-45d4-a86a-5f158f12dbbc/scratchpad
O=~/Downloads/qls_platform/claude/panels_s7/probes/B_full; mkdir -p $O; : > $O/summary.txt
until grep -q ГОТОВО ~/Downloads/qls_platform/claude/panels_s7/probes/A_webkit/summary.txt 2>/dev/null; do sleep 20; done
cd $SP/stB
export CALC2_BASE_URL=http://127.0.0.1:8094
for e in chromium webkit; do
  ENGINES=$e node calc2/tests/redesign/pts_probe.mjs > $O/pts_$e.log 2>&1; echo "pts_probe Б $e код $?: $(grep ИТОГ $O/pts_$e.log)" >> $O/summary.txt
done
echo ГОТОВО >> $O/summary.txt
