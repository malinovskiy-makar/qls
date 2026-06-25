#!/bin/zsh
for i in {1..12}; do
  echo "=== Порция $i ($(date +%H:%M:%S)) ==="
  caffeinate -i ./venv/bin/python manage.py build_embeddings --limit 3000 --batch-size 8 --device cpu
  echo "--- осталось со старым вектором (384-мерным): ---"
  sqlite3 db.sqlite3 "SELECT count(*) FROM problems_problem WHERE length(embedding)=1536"
done
echo "=== ГОТОВО ==="
sqlite3 db.sqlite3 "SELECT length(embedding) AS L, count(*) FROM problems_problem WHERE embedding IS NOT NULL GROUP BY L"
