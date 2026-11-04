import unittest
from core.colony_postgres import ColonySnapshotStore


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
            return (True, True, True)
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



    def test_initialize_only_verifies_preprovisioned_schema(self):
        state = {"rows": {}, "queries": []}
        class PrivilegeCursor(Cursor):
            def fetchone(self):
                return (True, True, True)
        class PrivilegeConnection(Connection):
            def cursor(self):
                return PrivilegeCursor(self.state)
        store = ColonySnapshotStore(
            "postgresql://unused",
            connect=lambda *a, **k: PrivilegeConnection(state))
        store.initialize()
        statements = [sql.lstrip().upper() for sql, _ in state["queries"]]
        self.assertEqual(len(statements), 3)
        self.assertTrue(all(sql.startswith("SELECT") for sql in statements))
        self.assertIn("HAS_SEQUENCE_PRIVILEGE", statements[-1])


if __name__ == "__main__":
    unittest.main()
