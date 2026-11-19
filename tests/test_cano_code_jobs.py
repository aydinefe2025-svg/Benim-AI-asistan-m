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
                 "Update limited fixture","https://github.com/example/pr/1","","","")]


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

    def test_concurrent_unique_conflict_returns_existing_receipt_as_duplicate(self):
        # A separate writer may commit the same owner/hash after our initial
        # lookup but before INSERT ... ON CONFLICT DO NOTHING. The fallback
        # read must not tell CANO that it enqueued a NEW job.
        class ConflictAfterPrecheck(FakeCursor):
            inserted = False

            def execute(self, sql, params=None):
                super().execute(sql, params)
                if "INSERT INTO public.cano_code_jobs" in sql:
                    self.inserted = True

            def fetchone(self):
                if "ON CONFLICT" in self.last:
                    return None
                if "SELECT id::text,status" in self.last:
                    return ("previous-committed-id", "pr_open") if self.inserted else None
                return super().fetchone()

        cur = ConflictAfterPrecheck()
        receipt = self.store(cur).enqueue("Düzeltmeyi test et")
        self.assertTrue(cur.inserted)
        self.assertEqual(receipt["id"], "previous-committed-id")
        self.assertEqual(receipt["status"], "pr_open")
        self.assertTrue(receipt["duplicate"])

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



class LifecycleCursor(FakeCursor):
    def __init__(self, latest=None):
        super().__init__(prior=None)
        self.latest = latest

    def fetchone(self):
        if "SELECT id::text,status,goal,created_at,finished_at" in self.last:
            return self.latest
        return super().fetchone()


class RepeatingSelfDevelopmentTests(unittest.TestCase):
    def setUp(self):
        from core.cano_solution_dispatch import infer_code_goal
        self.goal = infer_code_goal("Kendini geliştir cano", [])
        self.assertIsInstance(self.goal, str)

    def store(self, cursor):
        return CodeJobStore(DB_URL, OWNER, connect=lambda _: FakeConnection(cursor))

    def old(self, status, *, age_minutes=120, goal=None,
            created_minutes=180, finished=True):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        return ("prior-job-id", status, self.goal if goal is None else goal,
                now - timedelta(minutes=created_minutes),
                now - timedelta(minutes=age_minutes) if finished else None)

    def test_deployed_self_development_can_start_a_new_bounded_cycle(self):
        cur = LifecycleCursor(latest=self.old("deployed"))
        receipt = self.store(cur).enqueue(self.goal)
        self.assertFalse(receipt["duplicate"])
        insert = next((params for sql, params in cur.queries
                       if "INSERT INTO public.cano_code_jobs" in sql), None)
        self.assertIsNotNone(insert)
        self.assertIn("Döngü 2:", insert[2])
        self.assertIn("önceki", insert[2].casefold())
        self.assertNotEqual(self.goal, insert[2])
        self.assertLessEqual(len(insert[2]), 1200)

    def test_rapid_repeat_of_completed_cycle_is_not_requeued(self):
        cur = LifecycleCursor(latest=self.old("deployed", age_minutes=1))
        receipt = self.store(cur).enqueue(self.goal)
        self.assertTrue(receipt["duplicate"])
        self.assertEqual(receipt["status"], "deployed")
        self.assertFalse(any("INSERT INTO" in sql for sql, _ in cur.queries))

    def test_recent_completion_blocks_even_if_job_created_hours_ago(self):
        # A two-hour build that finished a minute ago must not restart.
        cur = LifecycleCursor(latest=self.old(
            "deployed", age_minutes=1, created_minutes=180))
        receipt = self.store(cur).enqueue(self.goal)
        self.assertTrue(receipt["duplicate"])
        self.assertFalse(any("INSERT INTO" in sql for sql, _ in cur.queries))

    def test_missing_finished_at_rejects_next_cycle(self):
        # Never infer deployment completion from created_at.
        cur = LifecycleCursor(latest=self.old(
            "deployed", age_minutes=240, finished=False))
        receipt = self.store(cur).enqueue(self.goal)
        self.assertTrue(receipt["duplicate"])
        self.assertFalse(any("INSERT INTO" in sql for sql, _ in cur.queries))

    def test_active_and_blocked_prior_cycles_do_not_autoretry(self):
        for state in ("queued", "running", "pr_open", "ci_verified", "blocked"):
            with self.subTest(state=state):
                cur = LifecycleCursor(latest=self.old(state, age_minutes=120))
                receipt = self.store(cur).enqueue(self.goal)
                self.assertTrue(receipt["duplicate"])
                self.assertEqual(receipt["status"], state)
                self.assertFalse(any("INSERT INTO" in sql for sql, _ in cur.queries))

    def test_second_completed_cycle_advances_to_third_not_repeat(self):
        old_goal = self.goal + (
            "\nDöngü 2: Önceki tamamlanan düzeltmeyi tekrarlama; "
            "yeni doğrulanabilir hata ve bağımsız test seç."
        )
        cur = LifecycleCursor(latest=self.old("deployed", goal=old_goal))
        receipt = self.store(cur).enqueue(self.goal)
        self.assertFalse(receipt["duplicate"])
        insert = next(params for sql, params in cur.queries if "INSERT INTO" in sql)
        self.assertIn("Döngü 3:", insert[2])

    def test_manual_explicit_code_goal_still_uses_original_deduplication(self):
        cur = LifecycleCursor(latest=self.old("deployed"))
        receipt = self.store(cur).enqueue("CANO rapor ekranındaki hatayı düzelt")
        self.assertFalse(receipt["duplicate"])
        self.assertFalse(any("SELECT id::text,status,goal,created_at" in sql
                             for sql, _ in cur.queries))


if __name__=="__main__":
    unittest.main()
