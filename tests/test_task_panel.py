import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from core.task_panel import render_task_panel
from core.task_store import TaskStore


class FakeStreamlit:
    def __init__(self, inputs=None, submits=None, selections=None):
        self.inputs = inputs or {}
        self.submits = list(submits or [])
        self.selections = selections or {}
        self.sidebar = self
        self.messages = []

    def expander(self, *args, **kwargs):
        return nullcontext()

    def form(self, *args, **kwargs):
        return nullcontext()

    def text_input(self, label, key=None, **kwargs):
        return self.inputs.get(key or label, "")

    def text_area(self, label, key=None, **kwargs):
        return self.inputs.get(key or label, "")

    def selectbox(self, label, options, key=None, **kwargs):
        return self.selections.get(key, options[0])

    def form_submit_button(self, label, **kwargs):
        return self.submits.pop(0) if self.submits else False

    def file_uploader(self, *args, **kwargs):
        return None

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
            tasks = TaskStore(path).list()
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["status"], "planned")
            self.assertIn("otomatik çalıştırmaz", " ".join(st.messages))

    def test_transition_ui_records_human_note_and_evidence_without_model_call(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "tasks.sqlite3")
            task = TaskStore(path).create("Kaynağı incele")
            st = FakeStreamlit(
                inputs={
                    "task_note_" + task["id"]: "Kaynak kontrol edildi",
                    "task_evidence_" + task["id"]: "https://example.org/report",
                },
                submits=[False, True],
                selections={"task_status_" + task["id"]: "running"},
            )
            with patch.dict("os.environ", {"AGENT_TASK_DB_PATH": path}):
                render_task_panel(st)
            updated = TaskStore(path).get(task["id"])
            self.assertEqual(updated["status"], "running")
            self.assertEqual(updated["evidence"], ["https://example.org/report"])
            self.assertIn("Kaynak kontrol edildi", TaskStore(path).history(task["id"])[-1]["note"])


if __name__ == "__main__":
    unittest.main()

