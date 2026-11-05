import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from core.task_panel import render_task_panel, _session_database_path
from core.task_store import TaskStore


class FakeStreamlit:
    def __init__(self, inputs=None, submits=None, selections=None):
        self.inputs = inputs or {}
        self.submits = list(submits or [])
        self.selections = selections or {}
        self.sidebar = self
        self.messages = []
        self.session_state = {}
        self.select_options = {}

    def expander(self, *args, **kwargs):
        return nullcontext()

    def form(self, *args, **kwargs):
        return nullcontext()

    def text_input(self, label, key=None, **kwargs):
        return self.inputs.get(key or label, "")

    def text_area(self, label, key=None, **kwargs):
        return self.inputs.get(key or label, "")

    def selectbox(self, label, options, key=None, **kwargs):
        self.select_options[key] = list(options)
        return self.selections.get(key, options[0])

    def form_submit_button(self, label, **kwargs):
        return self.submits.pop(0) if self.submits else False

    def file_uploader(self, *args, **kwargs):
        return None

    def download_button(self, *args, **kwargs):
        return False

    def button(self, *args, **kwargs):
        return False

    def caption(self, value):
        self.messages.append(str(value))

    def text(self, value):
        self.messages.append(str(value))

    def error(self, value):
        self.messages.append(str(value))

    def warning(self, value):
        self.messages.append(str(value))

    def success(self, value):
        self.messages.append(str(value))

    def rerun(self):
        self.messages.append("rerun")


class TaskPanelTests(unittest.TestCase):
    def test_create_task_records_only_manual_form_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "tasks.sqlite3")
            st = FakeStreamlit(
                inputs={"Görev adı": "Kaynağı incele", "Başarı hedefi": "İki kaynak"},
                submits=[True],
            )
            with patch.dict("os.environ", {"AGENT_TASK_DB_PATH": path}):
                render_task_panel(st)
            tasks = TaskStore(_session_database_path(st, path)).list()
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["status"], "planned")
            self.assertNotIn("verified", st.select_options["task_status_" + tasks[0]["id"]])
            self.assertIn("yalnızca kullanıcı düğmeye bastığında çalışır", " ".join(st.messages))

    def test_transition_ui_records_human_note_and_evidence_without_model_call(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "tasks.sqlite3")
            st = FakeStreamlit(submits=[False, True])
            task = TaskStore(_session_database_path(st, path)).create("Kaynağı incele")
            st.inputs.update({
                "task_note_" + task["id"]: "Kaynak kontrol edildi",
                "task_evidence_" + task["id"]: "https://example.org/report",
            })
            st.selections = {"task_status_" + task["id"]: "running"}
            with patch.dict("os.environ", {"AGENT_TASK_DB_PATH": path}):
                render_task_panel(st)
            updated = TaskStore(_session_database_path(st, path)).get(task["id"])
            self.assertEqual(updated["status"], "running")
            self.assertEqual(updated["evidence"], ["https://example.org/report"])
            self.assertIn("Kaynak kontrol edildi", TaskStore(_session_database_path(st, path)).history(task["id"])[-1]["note"])

    def test_review_pending_task_renders_and_can_be_replanned(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "tasks.sqlite3")
            st = FakeStreamlit(submits=[False, False])
            store = TaskStore(_session_database_path(st, path))
            task = store.create("Review draft")
            store.transition(task["id"], "running")
            store.finish_draft(task["id"], "Draft requiring source review")
            with patch.dict("os.environ", {"AGENT_TASK_DB_PATH": path}):
                render_task_panel(st)
            self.assertEqual(st.select_options["task_status_" + task["id"]], ["blocked", "failed", "planned"])
            self.assertEqual(store.get(task["id"])["status"], "review_pending")
            self.assertNotIn("verified", st.select_options["task_status_" + task["id"]])

    def test_each_browser_session_uses_a_distinct_database(self):
        with tempfile.TemporaryDirectory() as folder:
            base = str(Path(folder) / "tasks.sqlite3")
            first = FakeStreamlit()
            second = FakeStreamlit()
            first_db = _session_database_path(first, base)
            second_db = _session_database_path(second, base)
            self.assertNotEqual(first_db, second_db)
            TaskStore(first_db).create("Private first session")
            self.assertEqual(TaskStore(second_db).list(), [])


if __name__ == "__main__":
    unittest.main()

