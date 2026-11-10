import json
import unittest
from core.colony_postgres import (
    ColonySnapshotStore, MAX_ARCHIVED_REVISIONS_PER_OWNER,
)


class Cursor:
    def __init__(self, state):
        self.state = state
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params=None):
        self.state["queries"].append((sql, params))
        if sql.startswith("INSERT"):
            self.state["rows"][params[0]] = params[1]
        if "has_table_privilege" in sql:
            self.state["last"] = "__privileges__"
        elif sql.startswith("SELECT") and params:
            self.state["last"] = params[0]
    def fetchone(self):
        if self.state.get("last") == "__privileges__":
            return (True, True, True, True, True, True)
        value = self.state["rows"].get(self.state["last"])
        return (value,) if value is not None else None


class Connection:
    def __init__(self, state): self.state = state
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return Cursor(self.state)


class ColonySnapshotTests(unittest.TestCase):
    def test_owner_isolation_and_readback(self):
        state = {"rows": {}, "queries": []}
        store = ColonySnapshotStore("postgresql://unused",
                                    connect=lambda *a, **k: Connection(state))
        store.initialize()
        payload = {"agents": [{"id": "a"}], "feedback": [], "reviews": []}
        store.save("owner-a", payload)
        self.assertEqual(store.load("owner-a"), payload)
        self.assertIsNone(store.load("owner-b"))
        with self.assertRaises(ValueError):
            store.save("", payload)
        with self.assertRaises(ValueError):
            store.save("owner-a", {"agents": []})

    def test_save_verified_reads_back_exact_snapshot(self):
        state = {"rows": {}, "queries": []}
        store = ColonySnapshotStore("postgresql://unused",
                                    connect=lambda *a, **k: Connection(state))
        store.initialize()
        payload = {"agents": [{"id": "owner-unit"}], "feedback": [],
                   "reviews": [], "missions": [{"id": "m1", "status": "blocked"}]}
        self.assertTrue(store.save_verified("owner-a", payload))
        self.assertEqual(store.load("owner-a"), payload)
        self.assertIsNone(store.load("owner-b"))

    def test_save_verified_refuses_false_success_if_readback_differs(self):
        state = {"rows": {}, "queries": []}
        store = ColonySnapshotStore("postgresql://unused",
                                    connect=lambda *a, **k: Connection(state))
        store.initialize()
        payload = {"agents": [{"id": "original"}], "feedback": [],
                   "reviews": [], "missions": []}
        store.load = lambda owner: {"agents": [], "feedback": [],
                                    "reviews": [], "missions": []}
        with self.assertRaises(RuntimeError):
            store.save_verified("owner-a", payload)



    def test_verify_schema_only_checks_preprovisioned_schema(self):
        state = {"rows": {}, "queries": []}
        class PrivilegeCursor(Cursor):
            def fetchone(self):
                return (True, True, True, True, True, True)
        class PrivilegeConnection(Connection):
            def cursor(self):
                return PrivilegeCursor(self.state)
        store = ColonySnapshotStore(
            "postgresql://unused",
            connect=lambda *a, **k: PrivilegeConnection(state))
        store.verify_schema()
        statements = [sql.lstrip().upper() for sql, _ in state["queries"]]
        self.assertEqual(len(statements), 3)
        self.assertTrue(all(sql.startswith("SELECT") for sql in statements))
        self.assertIn("HAS_SEQUENCE_PRIVILEGE", statements[-1])


    def test_verify_schema_only_reads_and_checks_runtime_privileges(self):
        state = {"rows": {}, "queries": []}
        class PrivilegeCursor(Cursor):
            def fetchone(self):
                return (True, True, True, True, True, True)
        class PrivilegeConnection(Connection):
            def cursor(self):
                return PrivilegeCursor(self.state)
        store = ColonySnapshotStore(
            "postgresql://unused",
            connect=lambda *a, **k: PrivilegeConnection(state))
        store.verify_schema()
        statements = [sql.lstrip().upper() for sql, _ in state["queries"]]
        self.assertEqual(len(statements), 3)
        self.assertTrue(all(sql.startswith("SELECT") for sql in statements))
        self.assertIn("HAS_SEQUENCE_PRIVILEGE", statements[-1])



    def test_verify_schema_rejects_one_missing_required_privilege(self):
        state = {"rows": {}, "queries": []}
        class MissingPrivilegeCursor(Cursor):
            def fetchone(self):
                return (True, True, False, True, True, True)
        class MissingPrivilegeConnection(Connection):
            def cursor(self):
                return MissingPrivilegeCursor(self.state)
        store = ColonySnapshotStore(
            "postgresql://unused",
            connect=lambda *a, **k: MissingPrivilegeConnection(state))
        with self.assertRaisesRegex(PermissionError, "privileges"):
            store.verify_schema()
        access_sql = state["queries"][-1][0].upper()
        self.assertEqual(access_sql.count("HAS_TABLE_PRIVILEGE"), 5)
        self.assertEqual(access_sql.count("HAS_SEQUENCE_PRIVILEGE"), 1)


    def test_versioned_save_keeps_existing_history_and_allows_growth_past_legacy_limit(self):
        self.assertEqual(MAX_ARCHIVED_REVISIONS_PER_OWNER, 100)
        prior = {"agents": [{"id": "agent"}], "feedback": [], "reviews": [],
                 "missions": [{"id": "mission", "status": "blocked"}]}
        updated = {**prior, "missions": [{"id": "mission", "status": "resumed"}]}
        old_revisions = [{"revision": i} for i in range(20)]
        state = {"snapshots": {"owner-a": prior}, "revisions": list(old_revisions)}

        class VersionedCursor:
            def __init__(self, state):
                self.state, self.result = state, None
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params=None):
                params = params or ()
                normalized = " ".join(sql.split()).upper()
                if normalized.startswith("SELECT PG_ADVISORY_XACT_LOCK"):
                    self.result = None
                elif normalized.startswith("SELECT PAYLOAD FROM PRIVATE_COLONY_SNAPSHOTS"):
                    row = self.state["snapshots"].get(params[0])
                    self.result = (row,) if row is not None else None
                elif normalized.startswith("SELECT COUNT(*) FROM PRIVATE_COLONY_SNAPSHOT_REVISIONS"):
                    self.result = (len(self.state["revisions"]),)
                elif normalized.startswith("INSERT INTO PRIVATE_COLONY_SNAPSHOT_REVISIONS"):
                    self.state["revisions"].append(json.loads(params[1]))
                    self.result = None
                elif normalized.startswith("INSERT INTO PRIVATE_COLONY_SNAPSHOTS"):
                    self.state["snapshots"][params[0]] = json.loads(params[1])
                    self.result = None
                else:
                    raise AssertionError("Unexpected SQL in snapshot test: " + normalized)
            def fetchone(self): return self.result

        class VersionedConnection:
            def __init__(self, state): self.state = state
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def cursor(self): return VersionedCursor(self.state)

        store = ColonySnapshotStore(
            "postgresql://unused",
            connect=lambda *a, **k: VersionedConnection(state))
        self.assertTrue(store.save_versioned_verified(
            "owner-a", updated, expected_prior=prior, archive_prior=True))
        self.assertEqual(state["revisions"][:20], old_revisions)
        self.assertEqual(state["revisions"][20], prior)
        self.assertEqual(store.load("owner-a"), updated)

    def test_versioned_save_fails_closed_at_new_bound_without_deleting_history(self):
        prior = {"agents": [{"id": "agent"}], "feedback": [], "reviews": [],
                 "missions": [{"id": "mission", "status": "blocked"}]}
        updated = {**prior, "missions": [{"id": "mission", "status": "resumed"}]}
        old_revisions = [{"revision": i} for i in range(MAX_ARCHIVED_REVISIONS_PER_OWNER)]
        state = {"snapshots": {"owner-a": prior}, "revisions": list(old_revisions)}

        class VersionedCursor:
            def __init__(self, state):
                self.state, self.result = state, None
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params=None):
                params = params or ()
                normalized = " ".join(sql.split()).upper()
                if normalized.startswith("SELECT PG_ADVISORY_XACT_LOCK"):
                    self.result = None
                elif normalized.startswith("SELECT PAYLOAD FROM PRIVATE_COLONY_SNAPSHOTS"):
                    row = self.state["snapshots"].get(params[0])
                    self.result = (row,) if row is not None else None
                elif normalized.startswith("SELECT COUNT(*) FROM PRIVATE_COLONY_SNAPSHOT_REVISIONS"):
                    self.result = (len(self.state["revisions"]),)
                elif normalized.startswith("INSERT INTO PRIVATE_COLONY_SNAPSHOT_REVISIONS"):
                    self.state["revisions"].append(json.loads(params[1]))
                    self.result = None
                elif normalized.startswith("INSERT INTO PRIVATE_COLONY_SNAPSHOTS"):
                    self.state["snapshots"][params[0]] = json.loads(params[1])
                    self.result = None
                else:
                    raise AssertionError("Unexpected SQL in snapshot test: " + normalized)
            def fetchone(self): return self.result

        class VersionedConnection:
            def __init__(self, state): self.state = state
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def cursor(self): return VersionedCursor(self.state)

        store = ColonySnapshotStore(
            "postgresql://unused",
            connect=lambda *a, **k: VersionedConnection(state))
        with self.assertRaisesRegex(RuntimeError, "revision quota"):
            store.save_versioned_verified(
                "owner-a", updated, expected_prior=prior, archive_prior=True)
        self.assertEqual(state["revisions"], old_revisions)
        self.assertEqual(state["snapshots"]["owner-a"], prior)

if __name__ == "__main__":
    unittest.main()
