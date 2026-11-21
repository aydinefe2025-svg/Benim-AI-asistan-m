"""Isolated real-PostgreSQL owner A/B security test, no production connections.

Run with CANO_RLS_TEST_DB_URL pointing ONLY at a disposable CI database.
The runner uses a fresh postgres service containing synthetic rows.
"""
import json
import os
import unittest
from pathlib import Path

from core.colony_postgres import ColonySnapshotStore


@unittest.skipUnless(os.environ.get("CANO_RLS_TEST_DB_URL"),
                     "Requires disposable PostgreSQL CI environment")
class ColonyRLSPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        cls.url = os.environ["CANO_RLS_TEST_DB_URL"]
        if "localhost" not in cls.url and "127.0.0.1" not in cls.url:
            raise RuntimeError("RLS integration test refuses non-local database")
        with psycopg.connect(cls.url) as db:
            db.execute("CREATE ROLE cano_snapshot_app NOLOGIN")
            db.execute("""CREATE TABLE public.private_colony_snapshots (
                owner_key text primary key, payload jsonb not null,
                updated_at timestamptz not null default now())""")
            db.execute("""CREATE TABLE public.private_colony_snapshot_revisions (
                revision bigserial primary key, owner_key text not null,
                payload jsonb not null, archived_at timestamptz not null default now())""")
            # Seed both synthetic owners before applying RLS. Each test then
            # has deterministic data independent of unittest method ordering.
            db.execute("""INSERT INTO public.private_colony_snapshots (owner_key,payload)
                VALUES (%s,%s::jsonb)""",
                ("tenant-a", json.dumps(
                    {"agents": [{"id": "a"}], "feedback": [], "reviews": []})))
            db.execute("""INSERT INTO public.private_colony_snapshots (owner_key,payload)
                VALUES (%s,%s::jsonb)""",
                ("tenant-b", json.dumps(
                    {"agents": [{"id": "b"}], "feedback": [], "reviews": []})))
            db.execute("""GRANT SELECT, INSERT, UPDATE
                ON public.private_colony_snapshots TO cano_snapshot_app""")
            db.execute("""GRANT SELECT, INSERT
                ON public.private_colony_snapshot_revisions TO cano_snapshot_app""")
            db.execute("""GRANT USAGE ON SEQUENCE
                public.private_colony_snapshot_revisions_revision_seq TO cano_snapshot_app""")
            db.execute(Path("sql/cano_colony_owner_rls_20261111.sql").read_text(),
                       prepare=False)

    @classmethod
    def app_connect(cls, _url, **kwargs):
        conn = cls.psycopg.connect(cls.url, **kwargs)
        conn.execute("SET ROLE cano_snapshot_app")
        return conn

    def test_two_tenants_private_snapshot_and_version_history(self):
        store = ColonySnapshotStore(self.url, connect=self.app_connect)
        a = {"agents": [{"id": "a"}], "feedback": [], "reviews": []}
        b = {"agents": [{"id": "b"}], "feedback": [], "reviews": []}
        store.save("tenant-a", a)
        store.save("tenant-b", b)
        self.assertEqual(store.load("tenant-a"), a)
        self.assertEqual(store.load("tenant-b"), b)
        changed = {**a, "agents": [{"id": "a2"}]}
        self.assertTrue(store.save_versioned_verified("tenant-a", changed,
                         expected_prior=a))
        archived = store.list_archived("tenant-a")
        self.assertEqual(len(archived), 1)
        self.assertEqual(store.load_archived("tenant-a", archived[0]["revision"]), a)
        self.assertEqual(store.list_archived("tenant-b"), [])
        self.assertEqual(store.load("tenant-b"), b)

    def test_policy_denies_unscoped_select_and_cross_tenant_insert(self):
        with self.app_connect(self.url) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM public.private_colony_snapshots").fetchone()[0], 0)
            db.execute("SELECT set_config('cano.owner_key', %s, true)",
                       ("tenant-a",))
            self.assertEqual(db.execute(
                "SELECT count(*) FROM public.private_colony_snapshots").fetchone()[0], 1)
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
            with self.app_connect(self.url) as db:
                db.execute("SELECT set_config('cano.owner_key', %s, true)",
                           ("tenant-a",))
                db.execute("""INSERT INTO public.private_colony_snapshots
                    (owner_key,payload) VALUES ('tenant-b', '{}'::jsonb)""")

    def test_role_is_restricted_without_deletion(self):
        with self.psycopg.connect(self.url) as db:
            row = db.execute("""SELECT c.relrowsecurity,
                pg_has_role('cano_snapshot_app',c.relowner,'USAGE'),
                (SELECT rolbypassrls FROM pg_roles
                 WHERE rolname='cano_snapshot_app'),
                has_table_privilege('cano_snapshot_app', c.oid, 'DELETE')
                FROM pg_class c
                WHERE c.oid='public.private_colony_snapshots'::regclass""").fetchone()
        self.assertEqual(row, (True, False, False, False))


if __name__ == "__main__":
    unittest.main()
