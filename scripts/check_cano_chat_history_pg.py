"""Isolated PostgreSQL 17/18 acceptance for CANO chat-history RLS.

ONLY disposable CI database; never run against production or user's data.
The exact migration is exercised before owner A/B and fresh-session checks.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg

from core.cano_chat_history import ChatHistoryConflict, ChatHistoryStore

OWNER_A = "oidc_" + "a" * 64
OWNER_B = "oidc_" + "b" * 64
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations/20261117_cano_neon_chat_histories.sql"
)


def disposable_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "")
    parsed = urlparse(url)
    if (
        os.environ.get("CANO_CI_ALLOW_DISPOSABLE_DB") != "1"
        or parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or parsed.port != 5432
        or parsed.path != "/ci_persistence"
        or parsed.username != "ci_user"
    ):
        raise RuntimeError("Refusing chat migration test outside disposable CI")
    return url


def restricted_connect(dsn):
    """An actual non-superuser app role, never a privileged CI connection."""
    conn = psycopg.connect(dsn, connect_timeout=8)
    conn.execute("SET ROLE memory_runtime_app")
    conn.commit()  # Preserve session role while ChatHistoryStore opens tx scopes.
    role = conn.execute("SELECT current_user").fetchone()[0]
    if role != "memory_runtime_app":
        conn.close()
        raise AssertionError("The app's least-privilege role is not active")
    return conn



def reject_preexisting_table_before_migration(conn):
    """An additive migration must not repurpose an already-existing owner table.

    Runs only on the disposable ci_persistence database after strict URL checks.
    Its synthetic sentinel must survive a refused migration unchanged.
    """
    conn.execute(
        "CREATE TABLE public.cano_chat_histories("
        "owner_key text PRIMARY KEY, payload jsonb NOT NULL DEFAULT '[]'::jsonb,"
        "updated_at timestamptz NOT NULL DEFAULT now())"
    )
    marker = '[{"role":"user","content":"synthetic-ci-sentinel"}]'
    conn.execute(
        "INSERT INTO public.cano_chat_histories(owner_key,payload)"
        " VALUES(%s,%s::jsonb)", (OWNER_A, marker)
    )
    try:
        try:
            conn.execute(MIGRATION.read_text(encoding="utf-8"))
        except psycopg.Error as exc:
            # Any accidental SQL error is not evidence of a deliberate guard.
            conn.execute("ROLLBACK")
            if "CANO_CHAT_MIGRATION_PREEXISTING_TABLE" not in str(exc):
                raise AssertionError(
                    "Migration must explicitly refuse an existing chat table"
                ) from exc
        else:
            raise AssertionError(
                "Migration silently modified a pre-existing chat table"
            )
        if conn.execute(
            "SELECT payload::text FROM public.cano_chat_histories"
            " WHERE owner_key=%s", (OWNER_A,)
        ).fetchone()[0] != marker.replace(" ", ""):
            raise AssertionError("Rejected migration changed the synthetic row")
        rls = conn.execute(
            "SELECT relrowsecurity,relforcerowsecurity FROM pg_class "
            "WHERE oid='public.cano_chat_histories'::regclass"
        ).fetchone()
        if rls != (False, False):
            raise AssertionError("Rejected migration altered owner-table RLS")
    finally:
        conn.execute("ROLLBACK")
        conn.execute("DROP TABLE IF EXISTS public.cano_chat_histories")



def bootstrap_disposable_db(dsn):
    with psycopg.connect(dsn, autocommit=True) as conn:
        if conn.execute("SELECT current_user").fetchone()[0] != "ci_user":
            raise AssertionError("Must be synthetic PostgreSQL CI owner")
        if conn.execute(
            "SELECT to_regclass('public.cano_chat_histories')"
        ).fetchone()[0] is not None:
            raise AssertionError("CI chat table unexpectedly pre-exists")
        if not conn.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_roles "
            "WHERE rolname='memory_runtime_app')"
        ).fetchone()[0]:
            conn.execute("CREATE ROLE memory_runtime_app NOLOGIN NOBYPASSRLS")
        flags = conn.execute(
            "SELECT rolsuper,rolbypassrls FROM pg_roles "
            "WHERE rolname='memory_runtime_app'"
        ).fetchone()
        if flags != (False, False):
            raise AssertionError("Unsafe CI app role privileges")
        reject_preexisting_table_before_migration(conn)
        conn.execute(MIGRATION.read_text(encoding="utf-8"))
        relation = conn.execute(
            "SELECT relrowsecurity,relforcerowsecurity "
            "FROM pg_class WHERE oid='public.cano_chat_histories'::regclass"
        ).fetchone()
        if relation != (True, True):
            raise AssertionError("Migration did not enable forced RLS")


def test_owner_sessions(dsn):
    a = ChatHistoryStore(dsn, OWNER_A, connect=restricted_connect)
    b = ChatHistoryStore(dsn, OWNER_B, connect=restricted_connect)
    a.verify_schema()
    b.verify_schema()
    expected_a = [
        {"role": "user", "content": "Synthetic CANO greeting"},
        {"role": "assistant", "content": "Synthetic persisted answer"},
    ]
    if a.load() != [] or b.load() != []:
        raise AssertionError("Isolated test owner began with existing records")
    if a.save(expected_a) != 2:
        raise AssertionError("Owner A chat save rejected")

    # Loading through a brand-new independent PostgreSQL session.
    anew = ChatHistoryStore(dsn, OWNER_A, connect=restricted_connect)
    if anew.load() != expected_a or b.load() != []:
        raise AssertionError("Owner A save/read or owner B isolation failed")

    # Owner B cannot read A, but can save a distinct conversation.
    expected_b = [{"role": "user", "content": "Different owner"}]
    if b.save(expected_b) != 1:
        raise AssertionError("Owner B save rejected")
    if anew.load() != expected_a or b.load() != expected_b:
        raise AssertionError("Owner B overwrote A or failed separate readback")

    # No owner scope: default role sees zero rows despite two stored owners.
    with restricted_connect(dsn) as conn:
        if conn.execute(
            "SELECT count(*) FROM public.cano_chat_histories"
        ).fetchone()[0] != 0:
            raise AssertionError("Unscoped app role can see private chat")

    # An owner B scope must not update A, even when owner A key is known.
    with restricted_connect(dsn) as conn:
        conn.execute(
            "SELECT set_config('cano.owner_key', %s, true)", (OWNER_B,)
        )
        update = conn.execute(
            "UPDATE public.cano_chat_histories SET payload='[]'::jsonb "
            "WHERE owner_key=%s", (OWNER_A,)
        )
        if update.rowcount != 0:
            raise AssertionError("RLS permitted cross-owner update")

    # An explicit cross-tenant insert must fail at the database layer.
    try:
        with restricted_connect(dsn) as conn:
            conn.execute(
                "SELECT set_config('cano.owner_key', %s, true)", (OWNER_B,)
            )
            conn.execute(
                "INSERT INTO public.cano_chat_histories(owner_key,payload) "
                "VALUES(%s,'[]'::jsonb) ON CONFLICT(owner_key) DO UPDATE "
                "SET payload=excluded.payload", (OWNER_A,)
            )
        raise AssertionError("RLS accepted cross-owner INSERT/UPSERT")
    except psycopg.errors.InsufficientPrivilege:
        pass

    if anew.load() != expected_a or b.load() != expected_b:
        raise AssertionError("Cross-owner rejection damaged saved messages")


def test_stale_device_never_overwrites(dsn):
    # Real independent PostgreSQL connections using the same OIDC owner.
    a = ChatHistoryStore(dsn, OWNER_A, connect=restricted_connect)
    b = ChatHistoryStore(dsn, OWNER_A, connect=restricted_connect)
    prior = a.load()
    if prior != b.load() or not prior:
        raise AssertionError("Test sessions did not read the same baseline")

    update_a = prior + [{"role": "user", "content": "Device A newest"}]
    update_b = prior + [{"role": "user", "content": "Device B stale"}]
    if a.save(update_a) != len(update_a):
        raise AssertionError("First device write failed")
    try:
        b.save(update_b)
    except ChatHistoryConflict:
        pass
    else:
        raise AssertionError("Device B silently overwrote Device A's chat")

    latest = ChatHistoryStore(dsn, OWNER_A, connect=restricted_connect)
    if latest.load() != update_a:
        raise AssertionError("Rejected stale save corrupted Device A messages")

    # A newly constructed store may NOT blindly overwrite an existing row.
    uninitialized = ChatHistoryStore(dsn, OWNER_A, connect=restricted_connect)
    try:
        uninitialized.save([{"role": "user", "content": "Unloaded tab"}])
    except ChatHistoryConflict:
        pass
    else:
        raise AssertionError("Unloaded tab replaced existing chat history")

    # After explicit reload, both devices' new messages can be retained.
    if b.load() != update_a:
        raise AssertionError("Stale device could not refresh")
    merged = update_a + [{"role": "user", "content": "Device B retried"}]
    if b.save(merged) != len(merged) or latest.load() != merged:
        raise AssertionError("Refreshed device could not append safely")


def main():
    dsn = disposable_url()
    bootstrap_disposable_db(dsn)
    test_owner_sessions(dsn)
    test_stale_device_never_overwrites(dsn)
    print("PASS: synthetic PostgreSQL chat migration + owner A/B RLS "
          "+ fresh-session persistence + stale-device CAS protection, "
          "no production data accessed")


if __name__ == "__main__":
    main()
