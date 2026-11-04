"""UI gates for explicit, authenticated, persistent CANO work queue."""
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch

from core.authorized_queue_panel import render_authorized_queue_panel


class FakeStreamlit:
    def __init__(self, *, fields=None, approved=None, submits=None, click=False):
        self.sidebar = self
        self.fields = fields or {}
        self.approved = approved or {}
        self.submits = list(submits or [])
        self.click = click
        self.messages = []
        self.reruns = 0
        self.forms = []

    def expander(self, *a, **kw): return nullcontext()
    def form(self, *a, **kw):
        self.forms.append((a, kw))
        return nullcontext()
    def text_input(self, label, *, key=None, **kw): return self.fields.get(key, "")
    def text_area(self, label, *, key=None, **kw): return self.fields.get(key, "")
    def checkbox(self, label, *, key=None, **kw): return self.approved.get(key, False)
    def selectbox(self, label, options, *, key=None, **kw): return options[0]
    def form_submit_button(self, *a, **kw): return self.submits.pop(0) if self.submits else False
    def button(self, *a, **kw): return self.click
    def caption(self, s): self.messages.append(str(s))
    def warning(self, s): self.messages.append(str(s))
    def error(self, s): self.messages.append(str(s))
    def success(self, s): self.messages.append(str(s))
    def info(self, s): self.messages.append(str(s))
    def rerun(self): self.reruns += 1


class AuthorizedQueuePanelTests(unittest.TestCase):
    def _queue(self):
        queue = Mock()
        queue.list.return_value = []
        queue.enqueue.return_value = {"id": "job-id", "state": "queued"}
        queue.run_once.return_value = {"status": "review_pending", "verified": False}
        return queue

    def test_no_authenticated_owner_or_postgres_never_initializes(self):
        st = FakeStreamlit(submits=[True], click=True)
        with patch("core.authorized_queue_panel.PostgresAuthorizedQueue") as factory:
            render_authorized_queue_panel(st, answer=lambda _: "draft", owner_key=None,
                                          database_url="postgresql://unused")
            render_authorized_queue_panel(st, answer=lambda _: "draft", owner_key="oidc_owner",
                                          database_url=None)
            factory.assert_not_called()

    def test_queue_submission_requires_checkbox_approval(self):
        fields = {"cano_queue_idempotency": "source-1", "cano_queue_goal": "Review sources"}
        queue = self._queue()
        st = FakeStreamlit(fields=fields, submits=[True], click=False)
        with patch("core.authorized_queue_panel.PostgresAuthorizedQueue", return_value=queue):
            render_authorized_queue_panel(st, owner_key="oidc_owner",
                                          database_url="postgresql://unused")
        queue.enqueue.assert_not_called()

        queue = self._queue()
        st = FakeStreamlit(fields=fields, submits=[True],
                           approved={"cano_queue_approve_enqueue": True})
        with patch("core.authorized_queue_panel.PostgresAuthorizedQueue", return_value=queue):
            render_authorized_queue_panel(st, owner_key="oidc_owner",
                                          database_url="postgresql://unused")
        queue.enqueue.assert_called_once_with("source-1", "Review sources",
                                               approved=True, max_calls=1)

    def test_provider_call_requires_separate_click_and_approval(self):
        queue = self._queue()
        st = FakeStreamlit(click=True, submits=[False, True])
        with patch("core.authorized_queue_panel.PostgresAuthorizedQueue", return_value=queue):
            render_authorized_queue_panel(st, answer=lambda _: "draft", owner_key="oidc_owner",
                                          database_url="postgresql://unused")
        queue.run_once.assert_not_called()

        queue = self._queue()
        st = FakeStreamlit(click=True, submits=[False, True],
                           approved={"cano_queue_approve_run": True})
        def answer(goal): return "draft"
        with patch("core.authorized_queue_panel.PostgresAuthorizedQueue", return_value=queue):
            render_authorized_queue_panel(st, answer=answer, owner_key="oidc_owner",
                                          database_url="postgresql://unused")
        self.assertEqual(queue.run_once.call_count, 1)
        self.assertTrue(queue.run_once.call_args.kwargs["approved"])
        self.assertIs(queue.run_once.call_args.args[1], answer)

    def test_each_execution_requires_fresh_cleared_form_consent(self):
        queue = self._queue()
        st = FakeStreamlit(click=True, approved={"cano_queue_approve_run": True})
        with patch("core.authorized_queue_panel.PostgresAuthorizedQueue", return_value=queue):
            render_authorized_queue_panel(st, answer=lambda _: "draft",
                                          owner_key="oidc_owner",
                                          database_url="postgresql://unused")
        self.assertTrue(any(args and args[0] == "cano_queue_run_form"
                            and kw.get("clear_on_submit") is True
                            for args, kw in st.forms),
                        "Execution approval must be cleared after every submit")
        self.assertTrue(any(args and args[0] == "cano_persistent_queue_form"
                            and kw.get("clear_on_submit") is True
                            for args, kw in st.forms),
                        "Enqueue approval must be cleared after every submit")

    def test_provider_missing_never_claims_work(self):
        queue = self._queue()
        st = FakeStreamlit(click=True, approved={"cano_queue_approve_run": True})
        with patch("core.authorized_queue_panel.PostgresAuthorizedQueue", return_value=queue):
            render_authorized_queue_panel(st, answer=None, owner_key="oidc_owner",
                                          database_url="postgresql://unused")
        queue.run_once.assert_not_called()

    def test_database_errors_are_sanitized(self):
        st = FakeStreamlit()
        with patch("core.authorized_queue_panel.PostgresAuthorizedQueue",
                   side_effect=RuntimeError("postgresql://secret-password")):
            render_authorized_queue_panel(st, answer=None, owner_key="oidc_owner",
                                          database_url="postgresql://unused")
        self.assertNotIn("secret-password", " ".join(st.messages))


if __name__ == "__main__":
    unittest.main()
