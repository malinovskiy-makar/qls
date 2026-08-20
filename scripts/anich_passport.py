import sqlite3, sys
db = sys.argv[1] if len(sys.argv) > 1 else 'db.sqlite3'
c = sqlite3.connect(db)
q = lambda s: c.execute(s).fetchall()
one = lambda s: c.execute(s).fetchone()[0]

print("=== ОБЪЁМЫ ===")
print("Problem                ", one("select count(*) from problems_problem"))
print("ProblemPart            ", one("select count(*) from problems_problempart"))
print("ReviewVerdict          ", one("select count(*) from problems_reviewverdict"))

print("\n=== ReviewVerdict: (bundle, category) ===")
for r in q("select bundle, category, count(*) from problems_reviewverdict group by 1,2 order by 1,2"):
    print(f"  {r[0]:<20} {r[1]:<22} {r[2]}")
print("\n=== ReviewVerdict: по пакетам ===")
for r in q("select bundle, count(*) from problems_reviewverdict group by 1 order by 1"):
    print(f"  {r[0]:<20} {r[1]}")
print("\n=== ReviewVerdict: по ревьюерам ===")
for r in q("select reviewer, count(*) from problems_reviewverdict group by 1 order by 2 desc"):
    print(f"  {r[0]!r:<25} {r[1]}")

print("\n=== Problem.status ===")
for r in q("select status, count(*) from problems_problem group by 1 order by 2 desc"):
    print(f"  {r[0]:<12} {r[1]}")

print("\n=== Признаки ===")
print("needs_quality_review=1 ", one("select count(*) from problems_problem where needs_quality_review=1"))
print("solution_needs_review=1", one("select count(*) from problems_problem where solution_needs_review=1"))
print("duplicate_of непусто   ", one("select count(*) from problems_problem where duplicate_of_id is not null"))

print("\n=== Эмбеддинги ===")
print("непустой embedding     ", one("select count(*) from problems_problem where embedding is not null and length(embedding)>0"))
print("null embedding         ", one("select count(*) from problems_problem where embedding is null"))
print("длина=0                ", one("select count(*) from problems_problem where embedding is not null and length(embedding)=0"))
for r in q("select length(embedding), count(*) from problems_problem where embedding is not null group by 1 order by 2 desc limit 5"):
    print(f"  длина {r[0]} байт: {r[1]} задач")

print("\n=== created_at / updated_at (справочно, НЕ доказательство) ===")
print("MAX(created_at)        ", one("select max(created_at) from problems_problem"))
print("MAX(updated_at)        ", one("select max(updated_at) from problems_problem"))
print("MAX(id)                ", one("select max(id) from problems_problem"))

print("\n=== По источникам (2=ILE, 6=АА, 13=МатЭк) ===")
for sid in (2, 6, 13):
    n = one(f"select count(distinct problem_id) from problems_sourcereference where source_id={sid}")
    hid = one(f"""select count(*) from problems_problem p
                  where p.id in (select problem_id from problems_sourcereference where source_id={sid})
                    and p.status='hidden'""")
    print(f"  source {sid}: задач {n}, status='hidden' {hid}")
c.close()
