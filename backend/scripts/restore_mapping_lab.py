"""Restore public application records into a private Docker-only mapping lab.

Never connects to Supabase; leaves source backups and application .env untouched.
Supabase-managed auth/storage schemas are intentionally outside this test scope.
"""
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / 'backups' / '2026-09-17'
CONTAINER = 'intellidocs-mapping-lab'


def docker(*args, input=None):
    result = subprocess.run(['docker', *args], input=input, text=True,
                            encoding='utf-8', capture_output=True)
    if result.returncode:
        # Do not echo SQL, backup records, or container environment secrets.
        raise RuntimeError('Docker operation failed: ' + result.stderr[:500])
    return result.stdout.strip()


def sql(database, command):
    return docker('exec', '-i', CONTAINER, 'psql', '-X', '-U', 'postgres',
                  '-d', database, '-v', 'ON_ERROR_STOP=1', '-At', input=command)


def main():
    names = docker('ps', '-a', '--format', '{{.Names}}').splitlines()
    resume_empty = CONTAINER in names
    if resume_empty:
        if sql('mapping_baseline', "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';") != '0':
            raise RuntimeError('Mapping lab contains records; refusing to overwrite it.')
    schema = (BACKUP / 'schema.sql').read_text(encoding='utf-8-sig')
    data = (BACKUP / 'data.sql').read_text(encoding='utf-8-sig')
    # Explicit application-only statement allowlist; no roles, grants, or vault.
    statements = re.findall(
        r'(?:CREATE TABLE(?: IF NOT EXISTS)?|CREATE SEQUENCE(?: IF NOT EXISTS)?|ALTER SEQUENCE|ALTER TABLE(?: ONLY)?|CREATE (?:UNIQUE )?INDEX)\s+"public"\..*?;',
        schema, flags=re.S)
    # Index names may be unqualified in pg_dump output.
    indexes = re.findall(r'CREATE (?:UNIQUE )?INDEX "[^"\n]+" ON "public"\..*?;', schema, re.S)
    statements = list(dict.fromkeys(statements + indexes))
    foreign_keys = [s for s in statements if 'FOREIGN KEY' in s]
    before_data = [s for s in statements if 'FOREIGN KEY' not in s]
    blocks = re.findall(r'COPY "public"\."([^"\n]+)"[^\n]*\n.*?^\\\.$', data, re.S | re.M)
    copy_sql = re.findall(r'COPY "public"\."[^"\n]+"[^\n]*\n.*?^\\\.$', data, re.S | re.M)
    if len(blocks) != 12 or not foreign_keys:
        raise RuntimeError('Unexpected backup layout; refusing a partial restore.')
    if not resume_empty:
        docker('run', '-d', '--name', CONTAINER,
               '--label', 'intellidocs.purpose=mapping-regression-test',
               '-e', 'POSTGRES_PASSWORD=' + secrets.token_urlsafe(32),
               'pgvector/pgvector:pg17')
    # No published ports: database is reachable only through Docker exec.
    for _ in range(30):
        try:
            sql('postgres', 'SELECT 1;')
            break
        except RuntimeError:
            time.sleep(1)
    else:
        raise RuntimeError('Local database did not become ready.')
    if not resume_empty:
        sql('postgres', 'CREATE DATABASE mapping_baseline;')
    sql('mapping_baseline', 'BEGIN; CREATE EXTENSION vector;\n'
        + '\n'.join(before_data) + '\n' + '\n'.join(copy_sql)
        + '\n' + '\n'.join(foreign_keys) + '\nCOMMIT;')
    sql('postgres', 'CREATE DATABASE mapping_working TEMPLATE mapping_baseline;')
    report = {'container': CONTAINER, 'network': 'Docker only; no published ports',
              'scope': 'public application tables only', 'tables': {},
              'backup_sha256': {name: hashlib.sha256((BACKUP/name).read_bytes()).hexdigest()
                                for name in ('schema.sql', 'data.sql')}}
    for table in blocks:
        counts = [int(sql(db, f'SELECT count(*) FROM public."{table}";'))
                  for db in ('mapping_baseline', 'mapping_working')]
        if counts[0] != counts[1]:
            raise RuntimeError('Cloned database count mismatch.')
        report['tables'][table] = counts[0]
        fingerprints = [sql(db, f'''SELECT md5(coalesce(string_agg(row_value, E'\\n' ORDER BY row_value), ''))
            FROM (SELECT row_to_json(t)::text AS row_value FROM public."{table}" t) rows;''')
            for db in ('mapping_baseline', 'mapping_working')]
        if fingerprints[0] != fingerprints[1]:
            raise RuntimeError('Cloned database value mismatch.')
    report['documents'] = json.loads(sql('mapping_baseline', '''
        SELECT coalesce(json_agg(t), '[]'::json) FROM (
          SELECT original_filename, processing_status,
            (SELECT count(*) FROM document_nodes n WHERE n.document_id=d.id) nodes,
            (SELECT count(*) FROM chunks c WHERE c.document_id=d.id) chunks,
            (SELECT count(*) FROM embeddings e JOIN chunks c ON c.id=e.chunk_id WHERE c.document_id=d.id) chunk_embeddings,
            (SELECT count(*) FROM node_embeddings e JOIN document_nodes n ON n.id=e.node_id WHERE n.document_id=d.id) node_embeddings
          FROM documents d ORDER BY original_filename
        ) t;'''))
    sql('postgres', "ALTER DATABASE mapping_baseline SET default_transaction_read_only=on;")
    (BACKUP / 'mapping-lab-restore-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'tables': report['tables'], 'documents': report['documents'],
                      'baseline': 'read-only by default', 'working': 'separate clone'}, indent=2))


if __name__ == '__main__':
    main()
