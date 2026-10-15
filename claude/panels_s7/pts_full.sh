#!/bin/zsh
# pts_probe целиком (Б и В; Chromium и WebKit, 1 440 и 1 280) на сервере 8099 — без параллельной нагрузки.
cd ~/Downloads/qls_platform
O=claude/panels_s7/probes/pts_full; mkdir -p $O; : > $O/summary.txt
for e in chromium webkit; do
  ENGINES=$e node calc2/tests/redesign/pts_probe.mjs > $O/pts_$e.log 2>&1; echo "pts_probe $e код $?: $(grep ИТОГ $O/pts_$e.log)" >> $O/summary.txt
done
echo ГОТОВО >> $O/summary.txt
