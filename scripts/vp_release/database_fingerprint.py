"""Read-only DB fingerprint. Requires DATABASE_URL; prints hashes/counts, never row values."""
import argparse
import hashlib
import json
import os
import psycopg
from psycopg import sql


def fingerprint(database):
    with psycopg.connect(os.environ['DATABASE_URL'], dbname=database) as con:
        con.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        tables = [r[0] for r in con.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
        result = {}
        for table in tables:
            rows = sorted(r[0] for r in con.execute(sql.SQL('SELECT row_to_json(t)::text FROM {} t').format(sql.Identifier(table))))
            result[table] = {'rows': len(rows), 'sha256': hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
        sequences = {}
        for name, in con.execute("SELECT sequencename FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename"):
            sequences[name] = list(con.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(sql.Identifier(name))).fetchone())
        schema = {
            'columns': con.execute("SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position").fetchall(),
            'indexes': con.execute("SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname").fetchall(),
            'constraints': con.execute("SELECT c.relname,t.conname,pg_get_constraintdef(t.oid) FROM pg_constraint t JOIN pg_class c ON c.oid=t.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.relname,t.conname").fetchall(),
        }
        return {'tables': result, 'sequences': sequences,
                'schema_sha256': hashlib.sha256(json.dumps(schema, sort_keys=True, default=str).encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    result = fingerprint(args.database)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
