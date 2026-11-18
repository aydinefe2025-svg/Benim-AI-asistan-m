import json
import unittest

from core.cano_chat_history import ChatHistoryStore


OWNER = "oidc_" + "a" * 64


class FakeCursor:
    def __init__(self, database):
        self.db = database
        self.owner = None
        self.current = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, args=None):
        if "set_config" in statement:
            self.owner = args[0]
        elif "LIMIT 0" in statement:
            self.current = None
        elif "INSERT INTO public.cano_chat_histories" in statement:
            owner, raw, expected = args
            if self.owner != owner:
                raise PermissionError("RLS scope mismatch")
            current = self.db.rows.get(owner)
            # Simulate the atomic PostgreSQL ON CONFLICT ... WHERE ... RETURNING
            # compare-and-swap contract for independent concurrent sessions.
            if current is not None and current != json.loads(expected):
                self.current = None
            else:
                self.db.rows[owner] = json.loads(raw)
                self.current = (self.db.rows[owner],)
        elif "SELECT payload" in statement:
            if self.owner != args[0]:
                raise PermissionError("RLS scope mismatch")
            saved = self.db.rows.get(args[0])
            self.current = (saved,) if saved is not None else None
        else:
            raise AssertionError("Unexpected SQL")

    def fetchone(self):
        return self.current


class FakeDatabase:
    def __init__(self):
        self.rows = {}

    def __call__(self, *_):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return FakeCursor(self)


class CanoChatHistoryTests(unittest.TestCase):
    def test_verified_owner_round_trip_and_new_session(self):
        db = FakeDatabase()
        first = ChatHistoryStore("postgresql://test-host/db", OWNER, connect=db)
        first.verify_schema()
        self.assertEqual(first.load(), [])
        transcript = [
            {"role": "user", "content": "Kendini geliştir cano"},
            {"role": "assistant", "content": "Gerçek iş kuyruğa alındı."},
        ]
        self.assertEqual(first.save(transcript), 2)
        another_session = ChatHistoryStore(
            "postgresql://test-host/db", OWNER, connect=db)
        self.assertEqual(another_session.load(), transcript)

    def test_owner_isolation(self):
        db = FakeDatabase()
        a = ChatHistoryStore("postgresql://test-host/db", OWNER, connect=db)
        b = ChatHistoryStore(
            "postgresql://test-host/db", "oidc_" + "b" * 64, connect=db)
        a.save([{"role": "user", "content": "private"}])
        self.assertEqual(b.load(), [])

    def test_invalid_owner_and_payloads_fail_closed(self):
        with self.assertRaises(PermissionError):
            ChatHistoryStore("postgresql://test-host/db", "unverified")
        store = ChatHistoryStore(
            "postgresql://test-host/db", OWNER, connect=FakeDatabase())
        with self.assertRaises(ValueError):
            store.save([{"role": "system", "content": "unsafe"}])
        with self.assertRaises(ValueError):
            store.save([{"role": "user", "content": "x" * 8001}])


    def test_secondary_chat_routes_persist_messages_before_rerun(self):
        # Streamlit app is not importable without a live session; validate its
        # two actual chat append branches at the source boundary.
        import re
        from pathlib import Path
        app = (Path(__file__).resolve().parents[1] / "app.py").read_text(
            encoding="utf-8")
        self.assertIn('key="cano_code_apply_previous_solution"', app)
        code_action = app.split(
            'key="cano_code_apply_previous_solution"', 1)[1].split(
            "# A team task preview", 1)[0]
        self.assertEqual(code_action.count("st.session_state.messages.append("), 2)
        self.assertRegex(
            code_action,
            r'(?s)"role": "assistant", "content": _result,.*?'
            r'\}\)\s*_save_cano_chat\(\)\s*st\.rerun\(\)',
        )

        approved = app.split("_chat_task_result = asistani_calistir(", 1)[1]
        self.assertRegex(
            approved,
            r'(?s)"role": "assistant", "content": _chat_task_result,.*?'
            r'\}\)\s*_save_cano_chat\(\)',
        )



    def test_two_sessions_must_not_silently_overwrite_newer_messages(self):
        db = FakeDatabase()
        left = ChatHistoryStore("postgresql://test-host/db", OWNER, connect=db)
        right = ChatHistoryStore("postgresql://test-host/db", OWNER, connect=db)
        self.assertEqual(left.load(), [])
        self.assertEqual(right.load(), [])
        newer = [{"role": "user", "content": "Saved from another device"}]
        stale = [{"role": "user", "content": "Written from a stale device"}]
        left.save(newer)
        with self.assertRaisesRegex(RuntimeError, "another session"):
            right.save(stale)
        self.assertEqual(
            ChatHistoryStore("postgresql://test-host/db", OWNER, connect=db).load(),
            newer,
        )
        # The stale session may safely refresh and then add new messages.
        self.assertEqual(right.load(), newer)
        self.assertEqual(right.save(newer + stale), 2)

    def test_session_expected_baseline_survives_streamlit_rerun(self):
        db = FakeDatabase()
        first = ChatHistoryStore("postgresql://test-host/db", OWNER, connect=db)
        initial = [{"role": "user", "content": "Initial message"}]
        self.assertEqual(first.load(), [])
        first.save(initial)
        # Streamlit recreates ChatHistoryStore on every rerun, but the browser
        # session must retain the exact last-acknowledged chat baseline.
        rerun = ChatHistoryStore("postgresql://test-host/db", OWNER, connect=db)
        updated = initial + [{"role": "assistant", "content": "New reply"}]
        self.assertEqual(rerun.save(updated, expected=initial), 2)
        self.assertEqual(rerun.load(), updated)

        older = ChatHistoryStore("postgresql://test-host/db", OWNER, connect=db)
        with self.assertRaisesRegex(RuntimeError, "another session"):
            older.save(initial + [{"role": "user", "content": "Stale"}],
                       expected=initial)
        self.assertEqual(older.load(), updated)

    def test_streamlit_tracks_last_acknowledged_transcript_across_reruns(self):
        from pathlib import Path
        app = (Path(__file__).resolve().parents[1] / "app.py").read_text(
            encoding="utf-8")
        self.assertIn('"_cano_chat_saved"', app)
        self.assertIn("expected=st.session_state", app)
        self.assertIn("Sohbet başka bir oturumda", app)


if __name__ == "__main__":
    unittest.main()
