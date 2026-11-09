"""Disposable PostgreSQL 17/18 encrypted source-to-isolated-restore test.

This executable ALWAYS refuses production/external databases. Only a synthetic
localhost CI service with explicit guard is allowed. No user records or API keys.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit, urlunsplit,unquote
from uuid import uuid4
import psycopg
from psycopg import sql
from scripts.cano_encrypted_backup import (make_encrypted_backup,
                                          verify_encrypted_backup,
                                          restore_to_empty_database,
                                          BackupError)

TABLES=(
 'agent_research_drafts','agent_research_task_events','agent_research_tasks',
 'cano_authorized_job_events','cano_authorized_jobs','organism_lab_records',
 'private_colony_snapshot_revisions','private_colony_snapshots','private_memory_entries'
)

def main():
    uri=os.getenv('TEST_DATABASE_URL','')
    p=urlsplit(uri)
    if not (os.getenv('CANO_CI_ALLOW_DISPOSABLE_DB')=='1' and
            p.scheme in ('postgres','postgresql') and
            p.hostname in ('localhost','127.0.0.1') and
            p.username=='ci_user' and p.path=='/ci_persistence'):
        raise RuntimeError('REFUSED: integration drill requires a disposable local CI database')
    major=os.getenv('CANO_CI_PG_MAJOR','17')
    if major not in ('17','18'):raise RuntimeError('Unsupported disposable PG major')
    with psycopg.connect(uri) as db:
        actual=int(db.execute('SHOW server_version_num').fetchone()[0])//10000
    if actual!=int(major):raise RuntimeError('Disposable PostgreSQL server version mismatch')
    suffix=uuid4().hex[:10];source='cano_ci_enc_source_'+suffix;target='cano_restore_'+suffix
    created=[]
    try:
        with psycopg.connect(uri,autocommit=True) as admin:
            for name in [source,target]:
                admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
                created.append(name)
        def conn_uri(db_name):return urlunsplit((p.scheme,p.netloc,'/'+db_name,'',''))
        src=conn_uri(source);dst=conn_uri(target)
        expected={t:[(1,{'owner':'synthetic-A','secret':'fake-only','table':t}),
                     (2,{'owner':'synthetic-B','stage':'offline','table':t})] for t in TABLES}
        with psycopg.connect(src) as db:
            for t in TABLES:
                db.execute(sql.SQL('CREATE TABLE {} (id int PRIMARY KEY, data jsonb NOT NULL)').format(sql.Identifier(t)))
                for id,payload in expected[t]:
                    db.execute(sql.SQL('INSERT INTO {} (id,data) VALUES (%s,%s::jsonb)').format(sql.Identifier(t)),(id,json.dumps(payload)))
        with tempfile.TemporaryDirectory(prefix='cano-encrypted-dr-') as tmp:
            root=Path(tmp)
            # PostgreSQL 18 client binaries are used against both disposable PG17
            # and PG18 servers. Secrets are passed via -e NAME (not argv).
            for binary in ('pg_dump','pg_restore','psql'):
                file=root/('docker-'+binary)
                file.write_text('#!/bin/sh\nset -eu\n'
                      'exec docker run --rm -i --network host '
                      '-e PGHOST -e PGPORT -e PGUSER -e PGPASSWORD -e PGDATABASE '
                      'postgres:'+major+' '+binary+' "$@"\n')
                file.chmod(file.stat().st_mode|stat.S_IXUSR)
            dump_bin=str(root/'docker-pg_dump')
            psql_bin=str(root/'docker-psql')
            restore_bin=str(root/'docker-pg_restore')
            from unittest.mock import patch
            import secrets
            with patch.dict(os.environ,{
                'DATABASE_URL':src,
                'CANO_RESTORE_DATABASE_URL':dst,
                'CANO_BACKUP_KEY_HEX':secrets.token_hex(32),
            }):
                result=make_encrypted_backup(root/'offsite_simulated',dump_bin=dump_bin)
                verified=verify_encrypted_backup(Path(result['receipt']))
                assert verified['authenticated'] is True
                assert result['plaintext_sha256']==verified['plaintext_sha256']
                # This ephemeral CI test uses a local output folder, never a
                # true independent provider. No decrypted file is ever written.
                files=list((root/'offsite_simulated').iterdir())
                assert len(files)==2 and all(x.suffix!='.dump' for x in files)
                result_restored=restore_to_empty_database(Path(result['archive']),
                         confirm=True,psql_bin=psql_bin,restore_bin=restore_bin)
                assert result_restored['restored_to_new_database']
                with psycopg.connect(dst) as db:
                    tables=db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
                    assert [x[0] for x in tables]==sorted(TABLES), tables
                    for t in TABLES:
                        rows=db.execute(sql.SQL('SELECT id,data FROM {} ORDER BY id').format(sql.Identifier(t))).fetchall()
                        assert rows==expected[t], t
                try:
                    restore_to_empty_database(Path(result['archive']),confirm=True,
                        psql_bin=psql_bin,restore_bin=restore_bin)
                except BackupError:
                    pass
                else:raise AssertionError('Restore into nonempty target should refuse')
                # Wrong key must fail verification without querying target.
                with patch.dict(os.environ,{'CANO_BACKUP_KEY_HEX':'aa'*32}):
                    try:verify_encrypted_backup(Path(result['receipt']))
                    except BackupError:pass
                    else:raise AssertionError('Wrong encryption key was accepted')
        print(json.dumps({'status':'PASS','major':major,'synthetic_tables':len(TABLES),
               'synthetic_rows':len(TABLES)*2,'restore_to_distinct_empty_db':True,
               'encrypted_only':True,'wrong_key_rejected':True,
               'nonempty_target_rejected':True,'production_data_used':False,
               'offsite_production_backup_created':False},sort_keys=True))
    finally:
        if created:
            with psycopg.connect(uri,autocommit=True) as admin:
                for dbname in reversed(created):
                    admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(dbname)))

if __name__=='__main__':main()
