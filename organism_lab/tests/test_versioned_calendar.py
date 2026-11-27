"""Opt-in V2 replay/calendar safety; no live state or network writes."""
import copy
import hashlib
import json
import multiprocessing
import shutil
import tempfile
import unittest
from pathlib import Path

from organism_lab.versioned_calendar import (
    inspect_checkpoint, migrate_checkpoint, advance_checkpoint_v2,
    inspect_day_v2, run_day_v2, _hash, _signed, POLICY, V2,
)
from organism_lab.calendar_cycle import _report_for_day, _day_and_tick

FIX=Path(__file__).parent/'fixtures'
EXPECTED_ANCHOR='c6e81cd608d5f4b5444199212f40e3646d5b1e4f8b3ac1cbd78704205f9ba063'


def _run_worker(directory):
    return run_day_v2(directory, day='2026-11-27',expected_anchor_sha=EXPECTED_ANCHOR)['sha256']


class CalendarMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.state=self.root/'genome-state.json'
        self.day26=self.root/'daily'/'2026-11-26.json';self.day26.parent.mkdir()
        shutil.copy2(FIX/'v1_checkpoint_2026-11-26.json',self.state)
        shutil.copy2(FIX/'v1_calendar_2026-11-26.json',self.day26)
        self.anchor_bytes=self.state.read_bytes();self.day26_bytes=self.day26.read_bytes()

    def test_fixture_is_actual_canonical_v1_and_day(self):
        a=inspect_checkpoint(self.state)
        self.assertEqual(a['sha256'],EXPECTED_ANCHOR)
        self.assertEqual(a['state']['metrics']['tick'],160)
        self.assertEqual(a['state']['metrics']['births'],229)
        self.assertEqual(a['state']['metrics']['deaths'],218)
        self.assertEqual(a['state']['metrics']['unique_genomes'],2)
        self.assertEqual(json.loads(self.day26_bytes),_report_for_day('2026-11-26',160,a['parameters']))

    def test_wrong_expected_anchor_does_not_write(self):
        with self.assertRaises(ValueError):migrate_checkpoint(self.state,expected_anchor_sha='0'*64)
        self.assertEqual(self.state.read_bytes(),self.anchor_bytes)
        with self.assertRaises(ValueError):run_day_v2(self.root,day='2026-11-27',expected_anchor_sha='0'*64)
        self.assertEqual(self.state.read_bytes(),self.anchor_bytes)
        self.assertEqual(self.day26.read_bytes(),self.day26_bytes)

    def test_explicit_transition_is_restartable_and_history_immutable(self):
        m=migrate_checkpoint(self.state,expected_anchor_sha=EXPECTED_ANCHOR)
        self.assertEqual(m['schema'],V2);self.assertEqual(m['anchor'],json.loads(self.anchor_bytes))
        self.assertEqual(m['policy'],POLICY)
        d=run_day_v2(self.root,day='2026-11-27',expected_anchor_sha=EXPECTED_ANCHOR)
        self.assertEqual(d['tick'],168)
        self.assertEqual(d['observed']['population'],12)
        self.assertEqual((d['observed']['births'],d['observed']['deaths']),(229,218))
        self.assertEqual(d['division_disabled_control']['births'],0)
        self.assertEqual(inspect_day_v2(self.root,day='2026-11-27')['status'],'verified')
        self.assertEqual(self.day26.read_bytes(),self.day26_bytes)
        before=self.state.read_bytes();daily=(self.root/'daily'/'2026-11-27.json').read_bytes()
        self.assertEqual(run_day_v2(self.root,day='2026-11-27',expected_anchor_sha=EXPECTED_ANCHOR),d)
        self.assertEqual(self.state.read_bytes(),before)
        self.assertEqual((self.root/'daily'/'2026-11-27.json').read_bytes(),daily)

    def test_advancing_to_tick400_has_no_fake_extra_deaths(self):
        migrate_checkpoint(self.state,expected_anchor_sha=EXPECTED_ANCHOR)
        d=advance_checkpoint_v2(self.state,target_tick=400)
        self.assertEqual(d['state']['metrics']['population'],12)
        self.assertEqual((d['state']['metrics']['births'],d['state']['metrics']['deaths']),(229,218))
        self.assertEqual(inspect_checkpoint(self.state),d)
        old=self.state.read_bytes();self.assertEqual(advance_checkpoint_v2(self.state,target_tick=400),d)
        self.assertEqual(self.state.read_bytes(),old)
        with self.assertRaises(ValueError):advance_checkpoint_v2(self.state,target_tick=399)
        self.assertEqual(self.state.read_bytes(),old)

    def test_tamper_outer_hash_and_ancestor_replay_fail(self):
        migrate_checkpoint(self.state,expected_anchor_sha=EXPECTED_ANCHOR)
        d=advance_checkpoint_v2(self.state,target_tick=168)
        evil=copy.deepcopy(d);evil['state']['organisms'][0]['energy']+=10
        evil['sha256']=_hash({k:v for k,v in evil.items() if k!='sha256'})
        self.state.write_text(json.dumps(evil),encoding='utf-8')
        with self.assertRaises(ValueError):inspect_checkpoint(self.state)
        self.state.write_text(json.dumps(d),encoding='utf-8')
        evil=copy.deepcopy(d);evil['anchor']['state']['metrics']['births']+=1
        evil['anchor']['sha256']=_hash({k:v for k,v in evil['anchor'].items() if k!='sha256'})
        evil['sha256']=_hash({k:v for k,v in evil.items() if k!='sha256'})
        self.state.write_text(json.dumps(evil),encoding='utf-8')
        with self.assertRaises(ValueError):inspect_checkpoint(self.state)

    def test_corrupt_daily_even_rehashed_fails_without_checkpoint_change(self):
        run_day_v2(self.root,day='2026-11-27',expected_anchor_sha=EXPECTED_ANCHOR)
        report=self.root/'daily'/'2026-11-27.json';x=json.loads(report.read_bytes())
        before=self.state.read_bytes()
        x['observed']['births']+=1;x['sha256']=_hash({k:v for k,v in x.items() if k!='sha256'})
        report.write_text(json.dumps(x),encoding='utf-8')
        with self.assertRaises(ValueError):inspect_day_v2(self.root,day='2026-11-27')
        with self.assertRaises(ValueError):run_day_v2(self.root,day='2026-11-27',expected_anchor_sha=EXPECTED_ANCHOR)
        self.assertEqual(before,self.state.read_bytes())

    def test_refuse_historical_v1_rewriting_or_unapproved_day(self):
        with self.assertRaises(ValueError):run_day_v2(self.root,day='2026-11-26',expected_anchor_sha=EXPECTED_ANCHOR)
        self.assertEqual(self.anchor_bytes,self.state.read_bytes())
        with self.assertRaises(ValueError):run_day_v2(self.root,day='2026-11-25',expected_anchor_sha=EXPECTED_ANCHOR)
        self.assertEqual(self.day26_bytes,self.day26.read_bytes())

    def test_same_day_concurrency_two_processes_one_result(self):
        # Windows compatibility: importable top-level function (spawn-safe).
        context=multiprocessing.get_context('spawn')
        with context.Pool(2) as pool:
            results=pool.map(_run_worker,[str(self.root),str(self.root)])
        self.assertEqual(results[0],results[1])
        self.assertEqual(inspect_day_v2(self.root,day='2026-11-27')['status'],'verified')
        self.assertEqual(self.day26.read_bytes(),self.day26_bytes)

    def test_stale_day_watchdog_fails(self):
        run_day_v2(self.root,day='2026-11-27',expected_anchor_sha=EXPECTED_ANCHOR)
        with self.assertRaisesRegex(ValueError,'Stale or future'):
            inspect_day_v2(self.root,day='2026-11-28')

if __name__=='__main__':unittest.main()

class LegacyDispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.state=self.root/'genome-state.json'
        shutil.copy2(FIX/'v1_checkpoint_2026-11-26.json',self.state)
        (self.root/'daily').mkdir()
        shutil.copy2(FIX/'v1_calendar_2026-11-26.json',self.root/'daily'/'2026-11-26.json')
    def test_v1_existing_day_unchanged_and_v2_autodispatch_only_after_explicit_migration(self):
        from organism_lab.calendar_cycle import run_day
        from organism_lab.calendar_health import inspect_day
        before=self.state.read_bytes()
        report=run_day(self.root,day='2026-11-26')
        self.assertEqual(report['schema'],'cano-calendar-digital-cycle-v1')
        self.assertEqual(inspect_day(self.root,day='2026-11-26')['status'],'verified')
        self.assertEqual(self.state.read_bytes(),before)
        migrate_checkpoint(self.state,expected_anchor_sha=EXPECTED_ANCHOR)
        day=run_day(self.root,day='2026-11-27')
        self.assertEqual(day['schema'],'cano-calendar-digital-cycle-v2')
        self.assertEqual(inspect_day(self.root,day='2026-11-27')['status'],'verified')
        self.assertEqual(day,run_day(self.root,day='2026-11-27'))
        self.assertEqual(self.state.read_bytes(),self.state.read_bytes())

class RealV1Tick168AnchorCompatibility(unittest.TestCase):
    def test_27_nov_real_v1_digest_to_28_nov_hypothetical_v2(self):
        """Do not call this a real 28-Nov scheduled run: it is local replay."""
        from organism_lab.genome_checkpoint import _replay, _snapshot, _serialize
        from organism_lab.calendar_cycle import _report_for_day
        parameters={"seed":17,"capacity":24,"resources_per_tick":12,
                    "mutation_rate":0.02,"allow_replication":True}
        original={"schema":"genome-replay-checkpoint-v1","parameters":parameters,
                  "ticks":168,"state":_snapshot(_replay(parameters,168))}
        original["sha256"]=_hash(original)
        self.assertEqual(original["sha256"],
             "39ef30ef9ffefec545c9030062c0f994c26e9936ba09981a7aa269bcfac5fc34")
        report27=_report_for_day("2026-11-27",168,parameters)
        self.assertEqual(report27["sha256"],
             "14a2f3bdd6b14843ebc99155d710b7c2b83217c22fca9f54feef724e0530c4de")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"daily").mkdir()
            state=root/"genome-state.json";state.write_bytes(_serialize(original))
            old=root/"daily"/"2026-11-27.json";old.write_bytes(_serialize(report27))
            old_bytes=old.read_bytes()
            report=run_day_v2(root,day="2026-11-28",expected_anchor_sha=original["sha256"])
            self.assertEqual(report["schema"],"cano-calendar-digital-cycle-v2")
            self.assertEqual((report["observed"]["births"],report["observed"]["deaths"],report["observed"]["population"]),(241,230,12))
            self.assertEqual(report["division_disabled_control"]["births"],0)
            self.assertEqual(old.read_bytes(),old_bytes)
            self.assertEqual(inspect_day_v2(root,day="2026-11-28")["status"],"verified")

class AtomicDailyPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.state=self.root/'genome-state.json'
        (self.root/'daily').mkdir()
        shutil.copy2(FIX/'v1_checkpoint_2026-11-26.json',self.state)

    def test_mid_write_failure_retries_without_creating_partial_report(self):
        from unittest.mock import patch
        from organism_lab import versioned_calendar as v
        with patch.object(v,'_atomic_create_report',side_effect=OSError('injected interrupted report write')):
            with self.assertRaises(OSError):
                run_day_v2(self.root,day='2026-11-27',expected_anchor_sha=EXPECTED_ANCHOR)
        self.assertFalse((self.root/'daily'/'2026-11-27.json').exists())
        self.assertEqual(inspect_checkpoint(self.state)['ticks'],168)
        day=run_day_v2(self.root,day='2026-11-27',expected_anchor_sha=EXPECTED_ANCHOR)
        self.assertEqual(day['tick'],168)
        self.assertEqual(inspect_day_v2(self.root,day='2026-11-27')['status'],'verified')

    def test_symlink_report_never_accepted_even_if_contents_are_valid(self):
        from organism_lab.versioned_calendar import _report_v2
        from organism_lab.genome_checkpoint import _serialize
        anchor=inspect_checkpoint(self.state)
        payload=_serialize(_report_v2(anchor,day='2026-11-27'))
        outside=self.root/'outside.json';outside.write_bytes(payload)
        link=self.root/'daily'/'2026-11-27.json'
        try:link.symlink_to(outside)
        except OSError:self.skipTest('symlink not permitted on this OS')
        before=self.state.read_bytes()
        with self.assertRaises(ValueError):run_day_v2(self.root,day='2026-11-27',expected_anchor_sha=EXPECTED_ANCHOR)
        self.assertEqual(self.state.read_bytes(),before)
        self.assertEqual(outside.read_bytes(),payload)

class CalendarDispatchRaceTests(unittest.TestCase):
    setUp = CalendarMigrationTests.setUp
    def test_dispatch_rechecks_schema_after_calendar_lock_acquisition(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        from organism_lab import calendar_cycle as c
        from organism_lab.audit_store import _exclusive_lock as real_lock

        @contextmanager
        def migrate_before_acquiring(path):
            # Model a migration winning the lock just before this scheduled run.
            migrate_checkpoint(self.state, expected_anchor_sha=EXPECTED_ANCHOR)
            with real_lock(path):
                yield

        with patch.object(c, "_exclusive_lock", migrate_before_acquiring):
            report = c.run_day(self.root, day="2026-11-27")
        self.assertEqual(report["schema"], "cano-calendar-digital-cycle-v2")
        self.assertEqual(inspect_day_v2(self.root, day="2026-11-27")["status"], "verified")
        self.assertEqual(self.day26.read_bytes(), self.day26_bytes)

    def test_explicit_migration_serializes_with_calendar_writer(self):
        from unittest.mock import patch
        from organism_lab import versioned_calendar as v
        from organism_lab.audit_store import _exclusive_lock as real_lock
        with patch.object(v, "_exclusive_lock", wraps=real_lock) as observed:
            migrate_checkpoint(self.state, expected_anchor_sha=EXPECTED_ANCHOR)
        paths = [call.args[0] for call in observed.call_args_list]
        self.assertEqual(paths, [self.root / "calendar-cycle", self.state])
