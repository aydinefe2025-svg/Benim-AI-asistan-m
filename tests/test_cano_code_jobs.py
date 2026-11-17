"""Behavior contracts for the CANO web-to-developer worker bridge."""
import unittest
from core.cano_code_jobs import CodeJobStore, parse_code_request


OWNER = "oidc_" + "a"*64
DB_URL = "postgresql://example.invalid/assistant_pg"


class FakeCursor:
    def __init__(self, *, prior=None, active=0):
        self.queries = []
        self.prior = prior
        self.active = active
        self.last = ""
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self, sql, params=None):
        self.queries.append((sql, params))
        self.last = sql
    def fetchone(self):
        if "SELECT COUNT(*)" in self.last: return (self.active,)
        if "ON CONFLICT" in self.last: return ("00000000-0000-4000-8000-000000000001","queued")
        if "SELECT id::text,status" in self.last: return self.prior
        return (None,)
    def fetchall(self):
        return [("00000000-0000-4000-8000-000000000001","queued",
                 "Update limited fixture","https://github.com/example/pr/1","","")]


class FakeConnection:
    def __init__(self,cursor):
        self.cur = cursor
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def cursor(self): return self.cur


class CodeJobsTests(unittest.TestCase):
    def store(self,cur):
        return CodeJobStore(DB_URL, OWNER, connect=lambda db: FakeConnection(cur))

    def test_explicit_web_chat_command_parses_without_swallowing_research(self):
        self.assertEqual("Düzeltmeyi test et",parse_code_request("CANO kod: Düzeltmeyi test et"))
        self.assertEqual("Geliştirme ekibini kur",parse_code_request("CANO geliştir: Geliştirme ekibini kur"))
        self.assertIsNone(parse_code_request("Robotik simülasyonu yap"))
        self.assertIsNone(parse_code_request("CANO görev: Robot araştır"))
        with self.assertRaises(ValueError): parse_code_request("CANO kod: sk-" + "q"*20)

    def test_owner_identity_mandatory_and_not_in_error(self):
        for key in ("anonymous","",None,"oidc_bad"):
            with self.subTest(key=key),self.assertRaises(PermissionError):
                CodeJobStore(DB_URL,key)

    def test_first_submission_is_idempotent_owner_scoped_and_does_not_execute_code(self):
        cur=FakeCursor()
        result=self.store(cur).enqueue("Düzeltmeyi test et")
        self.assertEqual(result["status"],"queued")
        self.assertFalse(result["duplicate"])
        statements=[q[0] for q in cur.queries]
        self.assertEqual("SELECT set_config('cano.owner_key', %s, true)",statements[0])
        self.assertTrue(any("ON CONFLICT" in q for q in statements))
        self.assertTrue(any("pg_advisory_xact_lock" in q for q in statements))
        self.assertTrue(all(not word in " ".join(statements).upper()
                            for word in ("DROP TABLE","DELETE FROM","EXECUTE PROGRAM")))

    def test_duplicate_input_returns_old_id_without_insert(self):
        cur=FakeCursor(prior=("existing-id","pr_open"))
        result=self.store(cur).enqueue("Düzeltmeyi test et")
        self.assertTrue(result["duplicate"])
        self.assertEqual(result["id"],"existing-id")
        self.assertFalse(any("INSERT INTO" in sql for sql,p in cur.queries))

    def test_active_quota_blocks_extra_execution(self):
        cur=FakeCursor(active=3)
        with self.assertRaises(RuntimeError): self.store(cur).enqueue("Düzeltmeyi test et")
        self.assertFalse(any("INSERT INTO" in sql for sql,p in cur.queries))

    def test_status_query_scoped_to_owner(self):
        cur=FakeCursor()
        items=self.store(cur).recent()
        self.assertEqual(items[0]["status"],"queued")
        self.assertIn("WHERE owner_key=%s",cur.queries[-1][0])
        self.assertEqual(OWNER,cur.queries[-1][1][0])


if __name__=="__main__":
    unittest.main()
