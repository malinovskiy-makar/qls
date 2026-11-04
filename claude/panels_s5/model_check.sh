#!/bin/zsh
# Ключевые инварианты одной модели сессии 5 (предохранитель модели): опись и сверка с базой этапа, паритет,
# состояние, контрольные числа, cards_probe по модели.
#   claude/panels_s5/model_check.sh <база.json> "<ключи описи>" "<ключи cards_probe>"
cd ~/Downloads/qls_platform
BASEINV=$1; INVKEYS=$2; CARDKEYS=$3
OUT=claude/panels_s5/tmp/mc_${${INVKEYS// /_}:0:40}
mkdir -p $OUT
KEYS="$INVKEYS" node claude/mockups/calc2_panels_20261014/tools/panels_inventory.mjs $OUT/inv.json > $OUT/inv.log 2>&1
python3 - "$BASEINV" "$OUT/inv.json" "$OUT/base.json" <<'PY'
import json, sys
b = json.load(open(sys.argv[1])); a = json.load(open(sys.argv[2]))
b['models'] = {k: v for k, v in b['models'].items() if k in a['models']}
json.dump(b, open(sys.argv[3], 'w'), ensure_ascii=False)
PY
r=0
node claude/mockups/calc2_panels_20261014/tools/panels_compare.mjs $OUT/base.json $OUT/inv.json claude/panels_s5/${ALLOW:-none}.json > $OUT/compare.txt 2>&1 || r=1
echo "сверка: $(tail -1 $OUT/compare.txt)"
node calc2/tests/redesign/parity_quick.mjs > $OUT/parity.log 2>&1 || r=1; echo "паритет: $(tail -1 $OUT/parity.log)"
node calc2/tests/redesign/state_probe.mjs > $OUT/state.log 2>&1 || r=1; echo "состояние: $(tail -1 $OUT/state.log)"
node calc2/tests/control_numbers.mjs > $OUT/cn.log 2>&1 || r=1; echo "контрольные числа: $(tail -1 $OUT/cn.log)"
ENGINES=chromium KEYS="$CARDKEYS" node calc2/tests/redesign/cards_probe.mjs > $OUT/cards.log 2>&1 || r=1; echo "cards_probe: $(tail -1 $OUT/cards.log)"
grep -h -E "FAIL|✗" $OUT/*.log $OUT/compare.txt | head -8
echo "КОД $r"
exit $r
