#!/bin/zsh
# Зубастость: временно вернуть дефект, прогнать тест, вернуть файл.
# teeth.sh <файл> <python-выражение замены (old, new)> <лейбл теста>
# Пример: teeth.sh olympiads/navigator.py "('a','b')" olympiads.tests.test_night_E1.GridTests
set -u
FILE=$1; PAIR=$2; LABEL=$3
cd ~/Downloads/qls-screens
./venv313/bin/python - "$FILE" "$PAIR" <<'EOF'
import sys, ast
path, pair = sys.argv[1], ast.literal_eval(sys.argv[2])
text = open(path, encoding='utf-8').read()
old, new = pair
assert text.count(old) == 1, 'образец найден %d раз' % text.count(old)
open(path, 'w', encoding='utf-8').write(text.replace(old, new))
EOF
OUT=$(./venv313/bin/python manage.py test $LABEL --settings=config.settings_olympiads_screens 2>&1)
FAILS=$(echo "$OUT" | grep -cE "^(FAIL|ERROR):")
git checkout -- "$FILE"
AFTER=$(./venv313/bin/python manage.py test $LABEL --settings=config.settings_olympiads_screens 2>&1 | grep -E "^(OK|FAILED)")
echo "провалов с дефектом: $FAILS; после возврата: $AFTER; git status: $(git status --short "$FILE" | wc -l | tr -d ' ') изм."
