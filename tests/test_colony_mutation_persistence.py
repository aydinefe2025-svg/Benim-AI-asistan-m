"""Behavioral coverage for sidebar mutations and account persistence."""
import json
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.agent_colony import AgentColony
from core.cano_command_center import _snapshot
from core.colony_panel import render_colony_panel
from tests.test_colony_sidebar_cas_guard import PanelFake

class MutationUI(PanelFake):
    def __init__(self, action, accepted=False):
        super().__init__(clicks={action})
        self.action = action
        self.accepted = accepted
        self.successes = []
    def form_submit_button(self, label, **kw):
        return label == self.action
    def text_input(self, label, **kw):
        return 'A valid research role or reference'
    def text_area(self, label, **kw):
        return 'A valid lesson or instruction'
    def checkbox(self, label, **kw):
        return self.accepted
    def file_uploader(self, *args, **kwargs): return None
    def write(self, *args, **kwargs): pass
    def success(self, text):
        self.successes.append(text)

class Remote:
    def __init__(self, snapshot, fail_second=False):
        self.live = copy.deepcopy(snapshot)
        self.calls = 0
        self.fail_second = fail_second
    def verify_schema(self): pass
    def save_versioned_verified(self, owner, payload, *, expected_prior, archive_prior=True):
        self.calls += 1
        if expected_prior != self.live or (self.fail_second and self.calls == 2):
            raise RuntimeError('Synthetic unavailable or stale backup')
        self.live = copy.deepcopy(payload)

class MutationPersistenceTests(unittest.TestCase):
    def exercise(self, action, *, accepted=False, stale=False, fail_second=False):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'colony.sqlite3'
            colony = AgentColony(path)
            if action != 'colony_founder':
                colony.create_founder('research', 'Research carefully')
            calls = []
            research_action = action in ('Taslak → eleştiri → düzeltme çalıştır',
                'read_mission_sources_mission', 'recover_stale_colony_missions')
            if research_action:
                colony.grow_specialists(approved=True, batch_size=3)
                from core.collaborative_mission import CollaborativeMission
                CollaborativeMission(colony)
                stages = [{'role': role, 'output': 'Draft'} for role in
                          ('planner', 'researcher', 'reviewer', 'synthesis')]
                stages[0]['source_leads'] = [{'title': 'Synthetic source', 'url': 'https://doi.org/10.1234/demo'}]
                with colony._db() as db:
                    db.execute('INSERT INTO colony_missions VALUES (?,?,?,?,?)',
                        ('mission', 'Research safely', json.dumps(stages),
                         'running' if action == 'recover_stale_colony_missions' else 'review_pending',
                         '2020-01-01T00:00:00+00:00'))
            before = _snapshot(colony)
            st = MutationUI(action, accepted)
            st.session_state.update(_cano_backup_owner_key='owner-A',
                                    _cano_backup_expected=copy.deepcopy(before))
            if action == 'read_mission_sources_mission':
                st.session_state['colony_last_mission'] = CollaborativeMission(colony).get('mission')
            def answer(prompt):
                calls.append(prompt)
                return 'A synthetic research draft'
            remote = Remote(before, fail_second)
            remote.provider_calls = calls
            if stale:
                remote.live = {'agents': [], 'feedback': [], 'reviews': [], 'missions': [], 'newer': True}
            with patch('core.colony_panel._session_database_path', return_value=path), patch(
                    'core.colony_panel.ColonySnapshotStore', return_value=remote), patch(
                    'core.europepmc_evidence.read_publication_evidence', return_value={
                        'status': 'abstract_excerpt', 'excerpt': 'A synthetic source passage'}):
                render_colony_panel(st, answer=answer if research_action else None,
                                    owner_key='owner-A', database_url='postgresql://synthetic')
            return before, _snapshot(colony), remote, st

    def test_all_sidebar_agent_and_feedback_mutations_are_durable(self):
        for action in ('colony_founder', 'Uzman ajan oluştur', 'colony_grow', 'Dersi kaydet'):
            for accepted in ((False, True) if action == 'Dersi kaydet' else (False,)):
                with self.subTest(action=action, accepted=accepted):
                    before, after, remote, st = self.exercise(action, accepted=accepted)
                    self.assertNotEqual(before, after)
                    self.assertEqual(remote.live, after)
                    self.assertEqual(st.session_state['_cano_backup_expected'], after)
                    self.assertEqual(remote.calls, 2)

    def test_stale_account_baseline_prevents_local_mutation(self):
        for action in ('colony_founder', 'Uzman ajan oluştur', 'colony_grow', 'Dersi kaydet'):
            with self.subTest(action=action):
                before, after, remote, st = self.exercise(action, stale=True)
                self.assertEqual(before, after)
                self.assertFalse(st.successes)

    def test_save_failure_keeps_local_record_and_old_expected_version(self):
        before, after, remote, st = self.exercise('Dersi kaydet', fail_second=True)
        self.assertNotEqual(before, after)
        self.assertEqual(remote.live, before)
        self.assertEqual(st.session_state['_cano_backup_expected'], before)
        self.assertFalse(st.successes)
        self.assertTrue(any('JSON' in text for text in st.messages))

    def test_review_source_read_and_recovery_persist(self):
        for action in ('Taslak → eleştiri → düzeltme çalıştır',
                       'read_mission_sources_mission', 'recover_stale_colony_missions'):
            with self.subTest(action=action):
                before, after, remote, st = self.exercise(action)
                self.assertNotEqual(before, after)
                self.assertEqual(remote.live, after)
                self.assertEqual(remote.calls, 2)
                if action.startswith('Taslak'):
                    self.assertEqual(len(remote.provider_calls), 3)

    def test_stale_review_never_calls_provider(self):
        before, after, remote, st = self.exercise(
            'Taslak → eleştiri → düzeltme çalıştır', stale=True)
        self.assertEqual(before, after)
        self.assertEqual(remote.provider_calls, [])
        self.assertFalse(st.successes)

    def test_review_save_failure_retains_review_without_success_claim(self):
        before, after, remote, st = self.exercise(
            'Taslak → eleştiri → düzeltme çalıştır', fail_second=True)
        self.assertEqual(len(after['reviews']), 1)
        self.assertEqual(remote.live, before)
        self.assertFalse(st.successes)
        self.assertTrue(any('JSON' in text for text in st.messages))
