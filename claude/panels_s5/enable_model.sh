#!/bin/zsh
# Включить модель в SC_ON, проверить инварианты (model_check.sh) и при зелёном — коммит модели.
#   claude/panels_s5/enable_model.sh <ключ SC_ON> "<ключи описи>" "<ключи cards_probe>" "<сообщение коммита>"
cd ~/Downloads/qls_platform
M=$1; INV=$2; CARDS=$3; MSG=$4
python3 - "$M" <<'PY'
import sys, re
p = 'calc2/static/calc2/92-ui-kit.js'; s = open(p).read()
m = re.search(r"const SC_ON = new Set\(\[(.*?)\]\);", s)
items = [x.strip() for x in m.group(1).split(',') if x.strip()]
if repr(sys.argv[1]) not in items and ("'" + sys.argv[1] + "'") not in items: items.append("'" + sys.argv[1] + "'")
s = s[:m.start()] + "const SC_ON = new Set([" + ', '.join(items) + "]);" + s[m.end():]
open(p, 'w').write(s)
PY
sleep 1
claude/panels_s5/model_check.sh claude/panels_s5/S5_A.json "$INV" "$CARDS"
r=$?
if [ $r -eq 0 ]; then
  git add calc2/static/calc2/92-ui-kit.js calc2/tests/redesign/layer_new.mjs
  git commit -q -m "$MSG

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" && git log --oneline -1
fi
exit $r
