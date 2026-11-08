"""CANO private PostgreSQL offsite backup: pg_dump stdout -> authenticated encryption.

No plaintext `.dump` file is written during backup. The receiving directory MUST
be persistent, private and independent of the source database provider. The
operator must retain the independently generated 32-byte backup key offline.

Requires cryptography and existing scripts.cano_pg_backup URI validator. No
production connections occur on import; no external upload or cron is implied.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import time
import threading
import queue
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit, unquote

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
try:
    from scripts.cano_pg_backup import _libpq_env_from_uri, BackupError
except ImportError:  # direct CLI from scripts/ and minimal local unit harness
    from cano_pg_backup import _libpq_env_from_uri, BackupError

MAGIC=b'CANOENC1'
NONCE_BYTES=12
TAG_BYTES=16
CHUNK=256*1024

# Never pass the AES backup key, provider tokens, or unrelated env secrets to
# pg_dump, pg_restore, psql or Docker wrappers. Only libpq and minimal OS vars.
_SAFE_OS_ENV = {
    'PATH', 'HOME', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TMPDIR', 'TMP', 'TEMP',
    'SystemRoot', 'SYSTEMROOT', 'WINDIR', 'PATHEXT', 'COMSPEC',
    'SSL_CERT_FILE', 'SSL_CERT_DIR', 'DOCKER_HOST',
}

def _child_env(libpq_env: dict) -> dict:
    return {k:v for k,v in libpq_env.items() if k.startswith('PG') or k in _SAFE_OS_ENV}



def _key(key_env: str='CANO_BACKUP_KEY_HEX') -> bytes:
    raw=os.getenv(key_env, '')
    if len(raw)!=64:
        raise BackupError('Missing or invalid 256-bit backup key (store offline)')
    try:
        key=bytes.fromhex(raw)
    except ValueError:
        raise BackupError('Missing or invalid 256-bit backup key (store offline)') from None
    if len(key)!=32:
        raise BackupError('Backup key must be 256 bits')
    return key


def _sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for x in iter(lambda:f.read(CHUNK),b''): h.update(x)
    return h.hexdigest()


def _private_directory(destination: Path) -> None:
    # No symlink redirection into an untrusted destination.
    if destination.is_symlink():
        raise BackupError('Backup directory must not be a symbolic link')
    destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not destination.is_dir() or destination.is_symlink():
        raise BackupError('Invalid private backup directory')
    if os.name=='posix' and destination.stat().st_mode&0o022:
        raise BackupError('Backup directory must not be group/world writable')


def _private_receipt(path: Path, payload: dict) -> None:
    fd,tmp=tempfile.mkstemp(prefix='.cano-receipt-',dir=str(path.parent))
    try:
        os.chmod(tmp,0o600)
        with os.fdopen(fd,'w',encoding='utf8') as f:
            json.dump(payload,f,indent=2,sort_keys=True)
            f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def make_encrypted_backup(destination: Path, *, database_env: str='DATABASE_URL',
                          key_env: str='CANO_BACKUP_KEY_HEX',
                          dump_bin: str='pg_dump', max_plaintext_bytes:int=2*1024**3,
                          max_seconds:float=1800) -> dict:
    """Stream from pg_dump through AES-256-GCM: no unencrypted archive at rest."""
    key=_key(key_env)
    if not isinstance(max_plaintext_bytes,int) or max_plaintext_bytes<6:
        raise BackupError('Invalid maximum backup size')
    if (isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float))
            or not math.isfinite(max_seconds) or max_seconds<=0 or max_seconds>7200):
        raise BackupError('Invalid wall-clock backup timeout')
    url=os.getenv(database_env,'')
    if not url: raise BackupError('Database URL environment variable is missing')
    env=_child_env(_libpq_env_from_uri(url,os.environ))
    executable=shutil.which(dump_bin)
    if not executable: raise BackupError('Required pg_dump executable not found')
    destination=Path(destination)
    _private_directory(destination)
    name='cano-pg-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(8)
    archive=destination/(name+'.canoenc')
    receipt=destination/(name+'.receipt.json')
    fd,temp=tempfile.mkstemp(prefix='.cano-encrypted-',dir=str(destination))
    process=None
    pump=None
    stop_pump=threading.Event()
    try:
        os.chmod(temp,0o600)
        with os.fdopen(fd,'wb') as out:
            nonce=secrets.token_bytes(NONCE_BYTES)
            header=MAGIC+nonce
            ctx=Cipher(algorithms.AES(key),modes.GCM(nonce)).encryptor()
            ctx.authenticate_additional_data(header)
            out.write(header)
            process=subprocess.Popen(
                [executable,'--no-password','--format=custom','--no-owner','--no-privileges'],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env)
            digest=hashlib.sha256();size=0;first=b''
            assert process.stdout is not None
            # Reading a pipe blocks even when Popen.wait(timeout=...) would not.
            # A bounded reader queue makes the deadline effective on Windows and
            # Unix without buffering the plaintext PostgreSQL dump in memory.
            chunks=queue.Queue(maxsize=4)
            deadline=time.monotonic()+float(max_seconds)

            def pump_stdout():
                try:
                    while not stop_pump.is_set():
                        data=process.stdout.read(CHUNK)
                        while not stop_pump.is_set():
                            try:
                                chunks.put(data,timeout=0.1)
                                break
                            except queue.Full:
                                continue
                        if not data:
                            break
                except (OSError, ValueError):
                    # Non-zero exit/invalid input is handled by the parent.
                    while not stop_pump.is_set():
                        try:
                            chunks.put(None,timeout=0.1)
                            break
                        except queue.Full:
                            continue
                finally:
                    # Closing from the blocked reader thread avoids Windows
                    # ReadFile deadlock when a shell grandchild retains the pipe.
                    process.stdout.close()

            pump=threading.Thread(target=pump_stdout,daemon=True,
                                  name='cano-pgdump-pipe')
            pump.start()
            while True:
                left=deadline-time.monotonic()
                if left<=0:
                    raise BackupError('pg_dump exceeded wall-clock time limit')
                try:
                    data=chunks.get(timeout=min(left,0.25))
                except queue.Empty:
                    continue
                if not data:
                    break
                if len(first)<5:first+=data[:5-len(first)]
                digest.update(data);size+=len(data)
                if size>max_plaintext_bytes:
                    raise BackupError('Encrypted backup exceeded configured size limit')
                out.write(ctx.update(data))
            left=deadline-time.monotonic()
            if left<=0:
                raise BackupError('pg_dump exceeded wall-clock time limit')
            if process.wait(timeout=left)!=0 or first!=b'PGDMP' or size<6:
                raise BackupError('pg_dump did not produce a valid custom-format header')
            out.write(ctx.finalize());out.write(ctx.tag)
            out.flush();os.fsync(out.fileno())
        os.replace(temp,archive)
        payload={
            'format':'cano-aes256gcm-pgdump-v1','archive':archive.name,
            'created_utc':datetime.now(timezone.utc).isoformat(),
            'encrypted':True,'plaintext_size_bytes':size,
            'plaintext_sha256':digest.hexdigest(),
            'archive_size_bytes':archive.stat().st_size,
            'archive_sha256':_sha256(archive),
            'authenticated':True,'production_restore_tested':False,
            'offsite_location_verified':False,
            'note':'Encrypted on local operator destination; external transport and isolated restore require separate proof.',
        }
        _private_receipt(receipt,payload)
        return {'archive':str(archive),'receipt':str(receipt),
                'plaintext_sha256':payload['plaintext_sha256'],
                'archive_sha256':payload['archive_sha256'],
                'size_bytes':payload['archive_size_bytes'],'encrypted':True}
    except (OSError,subprocess.SubprocessError,ValueError) as error:
        raise BackupError('Encrypted PostgreSQL dump failed (details intentionally redacted)') from None
    finally:
        stop_pump.set()
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
        if pump is not None:
            # A Windows .cmd wrapper can leave a child holding stdout after
            # the wrapper exits; do not close while another thread reads.
            pump.join(timeout=0.35)
        if process is not None and process.stdout is not None and (pump is None or not pump.is_alive()):
            process.stdout.close()
        if os.path.exists(temp):os.unlink(temp)
        # If receipt publishing fails, do not leave an untracked encrypted archive.
        if archive.exists() and not receipt.exists():archive.unlink()


def _decrypt_from_file(inp, sink, *, key_env='CANO_BACKUP_KEY_HEX',
                       expected_proof:dict|None=None)->dict:
    """Authenticate an entire ciphertext snapshot before releasing sink bytes.

    GCM update() yields unauthenticated plaintext. If a sink was requested,
    temporarily hold that data as separately AES-GCM-encrypted chunks using a
    fresh process-only key. Authenticate the original archive and the expected
    first-pass proof before opening this staged stream to pg_restore. Each
    staged chunk is AEAD-verified independently before release. Plaintext is
    never written to a temporary disk file or held all at once in memory.
    """
    key=_key(key_env)
    if sink is not None and not callable(sink):
        raise BackupError('Invalid authenticated stream destination')
    # The temporary file is private and automatically disposed; it contains
    # ciphertext only, never a plaintext PostgreSQL dump.
    stage=tempfile.TemporaryFile(mode='w+b') if sink is not None else None
    stage_aead=AESGCM(secrets.token_bytes(32)) if stage is not None else None
    blocks=0
    try:
        inp.seek(0,os.SEEK_END)
        size=inp.tell()
        inp.seek(0)
        if size<len(MAGIC)+NONCE_BYTES+TAG_BYTES+6:
            raise BackupError('Encrypted archive truncated')
        header=inp.read(len(MAGIC)+NONCE_BYTES)
        if header[:len(MAGIC)]!=MAGIC:
            raise BackupError('Unknown encrypted archive format')
        inp.seek(size-TAG_BYTES)
        tag=inp.read(TAG_BYTES)
        inp.seek(len(header))
        dec=Cipher(algorithms.AES(key),modes.GCM(header[len(MAGIC):],tag)).decryptor()
        dec.authenticate_additional_data(header)
        remaining=size-len(header)-TAG_BYTES
        h=hashlib.sha256();n=0;first=b''
        try:
            while remaining:
                chunk=inp.read(min(CHUNK,remaining))
                if not chunk:
                    raise BackupError('Encrypted archive is truncated')
                remaining-=len(chunk)
                plain=dec.update(chunk)
                if len(first)<5:first+=plain[:5-len(first)]
                h.update(plain);n+=len(plain)
                if stage is not None:
                    nonce=blocks.to_bytes(12,'big')
                    sealed=stage_aead.encrypt(nonce,plain,header)
                    stage.write(len(sealed).to_bytes(4,'big'))
                    stage.write(sealed)
                    blocks+=1
            # No sink writes before this tag check completes.
            dec.finalize()
        except (InvalidTag,ValueError):
            raise BackupError('Encrypted archive authentication failed') from None
        if first!=b'PGDMP' or n<6:
            raise BackupError('Decrypted content is not a PostgreSQL archive')
        proof={'authenticated':True,'plaintext_sha256':h.hexdigest(),
               'plaintext_size_bytes':n}
        if expected_proof is not None and (
                not isinstance(expected_proof,dict)
                or proof['plaintext_sha256']!=expected_proof.get('plaintext_sha256')
                or proof['plaintext_size_bytes']!=expected_proof.get('plaintext_size_bytes')):
            # The snapshot may have been altered after its first validation.
            # Refuse mismatched but individually authenticated content before SQL.
            raise BackupError('Archive changed between authentication and restore')
        if stage is not None:
            stage.seek(0)
            try:
                for index in range(blocks):
                    size_raw=stage.read(4)
                    if len(size_raw)!=4:
                        raise BackupError('Authenticated staging data is truncated')
                    size=int.from_bytes(size_raw,'big')
                    if not 16<size<=CHUNK+16:
                        raise BackupError('Authenticated staging chunk is invalid')
                    sealed=stage.read(size)
                    if len(sealed)!=size:
                        raise BackupError('Authenticated staging data is truncated')
                    plain=stage_aead.decrypt(index.to_bytes(12,'big'),sealed,header)
                    sink(plain)
                if stage.read(1):
                    raise BackupError('Authenticated staging contains extra data')
            except (InvalidTag,ValueError):
                raise BackupError('Authenticated staging verification failed') from None
        return proof
    finally:
        if stage is not None:
            stage.close()


def decrypt_to_sink(path:Path,sink,*,key_env='CANO_BACKUP_KEY_HEX')->dict:
    """Authenticate encrypted archive; a sink must not trust bytes before finalize."""
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise BackupError('Refusing symbolic link or missing encrypted archive')
    with path.open('rb') as inp:
        return _decrypt_from_file(inp,sink,key_env=key_env)

def verify_encrypted_backup(receipt_path: Path,*,key_env='CANO_BACKUP_KEY_HEX')->dict:
    receipt_path=Path(receipt_path)
    if receipt_path.is_symlink():raise BackupError('Refusing symlink receipt')
    try: data=json.loads(receipt_path.read_text('utf8'))
    except (OSError,ValueError):raise BackupError('Invalid encrypted backup receipt') from None
    name=data.get('archive')
    if (not isinstance(name,str) or not name.endswith('.canoenc') or
        '/' in name or '\\' in name or name in ('.','..')):
        raise BackupError('Invalid receipt archive name')
    path=receipt_path.parent/name
    if path.is_symlink() or not path.is_file():raise BackupError('Invalid encrypted archive path')
    if (path.stat().st_size!=data.get('archive_size_bytes') or
        _sha256(path)!=data.get('archive_sha256')):
        raise BackupError('Encrypted archive hash or size mismatch')
    proof=decrypt_to_sink(path,None,key_env=key_env)
    if (proof['plaintext_sha256']!=data.get('plaintext_sha256') or
        proof['plaintext_size_bytes']!=data.get('plaintext_size_bytes')):
        raise BackupError('Encrypted backup receipt mismatch')
    return {**proof,'archive_sha256':data['archive_sha256']}


def restore_to_empty_database(path:Path,*,target_db_url_env='CANO_RESTORE_DATABASE_URL',
                              confirm:bool=False,psql_bin='psql',restore_bin='pg_restore') -> dict:
    """Never restore to production: only explicitly named, EMPTY cano_restore_* DB.

    Entire ciphertext is authenticated before any psql or pg_restore is executed.
    Decrypted archive streams to pg_restore stdin; no plaintext dump on disk.
    """
    if not confirm:raise BackupError('Explicit empty isolated restore confirmation required')
    url=os.getenv(target_db_url_env,'')
    try: parts=urlsplit(url)
    except ValueError:raise BackupError('Invalid isolated restore target') from None
    target=unquote(parts.path[1:])
    if not target.startswith('cano_restore_') or not target.replace('_','').isalnum():
        raise BackupError('Target must be a dedicated cano_restore_* database')
    # CANO uses CANO_DATABASE_URL for its owner data, while memory and
    # authorized queue can use separate databases. Protect each live source,
    # not merely the generic DATABASE_URL fallback.
    # Normalize the default PostgreSQL port so :5432 cannot bypass this guard.
    for source_env in ('DATABASE_URL', 'CANO_DATABASE_URL', 'MEMORY_DATABASE_URL', 'AGENT_TASK_DATABASE_URL'):
        source_url=os.getenv(source_env,'')
        if not source_url:
            continue
        try:
            src=urlsplit(source_url)
            same_source=(src.hostname==parts.hostname and
                         (src.port or 5432)==(parts.port or 5432) and
                         unquote(src.path[1:])==target)
        except ValueError:
            raise BackupError('Invalid configured source database URL') from None
        if same_source:
            raise BackupError('Isolated restore target must differ from all active source databases')
    # Capture ciphertext in an OS-managed private temporary file. POSIX unlinks
    # its name immediately; Windows deletes it on close. Never spool plaintext.
    original=Path(path)
    if original.is_symlink() or not original.is_file():
        raise BackupError('Refusing symbolic link or missing encrypted archive')
    with tempfile.TemporaryFile(mode='w+b') as snapshot:
        with original.open('rb') as archive:
            shutil.copyfileobj(archive,snapshot,length=CHUNK)
        snapshot.flush()
        # Verify an anonymous, private *ciphertext* snapshot once; stream that same
        # seekable snapshot later, even if the operator archive is replaced during
        # preflight. No unauthenticated second read from the operator's path.
        proof=_decrypt_from_file(snapshot,None)
        env=_child_env(_libpq_env_from_uri(url,os.environ))
        psql=shutil.which(psql_bin);restore=shutil.which(restore_bin)
        if not psql or not restore:raise BackupError('PostgreSQL restore executables unavailable')
        query=("SELECT count(*) FROM pg_catalog.pg_class c "
               "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
               "WHERE c.relkind IN ('r','p','v','m','f') "
               "AND n.nspname NOT IN ('pg_catalog','information_schema') "
               "AND n.nspname NOT LIKE 'pg_toast%' ")
        try:
            pre=subprocess.run([psql,'-X','--no-password','-At','-c',query],
                               stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL,env=env,check=False,timeout=50)
        except (OSError,subprocess.SubprocessError):raise BackupError('Restore preflight failed') from None
        if pre.returncode!=0 or pre.stdout.strip()!=b'0':
            raise BackupError('Isolated restore database is not empty or inaccessible')
        process=None
        try:
            process=subprocess.Popen([restore,'--no-password','--single-transaction',
                   '--exit-on-error','--no-owner','--no-privileges','--dbname',target],
                   stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
            assert process.stdin is not None
            try:
                second=_decrypt_from_file(snapshot,process.stdin.write,expected_proof=proof)
                if second['plaintext_sha256']!=proof['plaintext_sha256'] or second['plaintext_size_bytes']!=proof['plaintext_size_bytes']:
                    raise BackupError('Archive changed between authentication and restore')
            finally:
                process.stdin.close()
            if process.wait(timeout=900)!=0:raise BackupError('Isolated restore failed')
            return {'restored_to_new_database':True,'authenticated':True,
                    'plaintext_sha256':proof['plaintext_sha256'],
                    'target_database_name':target,
                    'note':'Row-level source vs target equality must be tested separately.'}
        except (OSError,subprocess.SubprocessError, BrokenPipeError):
            raise BackupError('Isolated restore failed (details redacted)') from None
        finally:
            if process is not None and process.poll() is None:
                process.kill();process.wait()

def main():
    p=argparse.ArgumentParser(description='CANO: private authenticated PostgreSQL export and isolated recovery')
    sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('backup');b.add_argument('destination',type=Path)
    b.add_argument('--database-env',default='DATABASE_URL')
    v=sub.add_parser('verify');v.add_argument('receipt',type=Path)
    t=sub.add_parser('restore-isolated');t.add_argument('archive',type=Path)
    t.add_argument('--target-database-env',default='CANO_RESTORE_DATABASE_URL')
    t.add_argument('--confirm-empty-isolated-target',action='store_true')
    a=p.parse_args()
    try:
        if a.command=='backup':r=make_encrypted_backup(a.destination,database_env=a.database_env)
        elif a.command=='verify':r=verify_encrypted_backup(a.receipt)
        else:r=restore_to_empty_database(a.archive,target_db_url_env=a.target_database_env,confirm=a.confirm_empty_isolated_target)
    except (BackupError,OSError,ValueError):
        print('ERROR: encrypted backup or isolated recovery failed; no secrets printed')
        return 1
    print(json.dumps(r,indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
