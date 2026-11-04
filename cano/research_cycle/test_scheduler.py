import sqlite3, tempfile, unittest
from pathlib import Path
import scheduler
class SchedulerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.c=scheduler.connect(Path(self.tmp.name)/'s.db')
 def tearDown(self):self.c.close();self.tmp.cleanup()
 def test_first_tick(self):
  calls=[];r=scheduler.tick(self.c,10000,lambda n:calls.append(n) or True)
  self.assertTrue(r['all_completed']);self.assertEqual(calls,list(scheduler.TASKS))
 def test_cooldown(self):
  scheduler.tick(self.c,10000,lambda n:True)
  r=scheduler.tick(self.c,10001,lambda n:self.fail('should not run'))
  self.assertFalse(r['all_completed']);self.assertEqual([x['status'] for x in r['results']],['cooldown']*2)
 def test_retry_after_interval(self):
  scheduler.tick(self.c,10000,lambda n:False)
  self.assertTrue(scheduler.tick(self.c,13600,lambda n:True)['all_completed'])
 def test_exception_is_failure(self):
  def bad(n):raise RuntimeError('test')
  self.assertEqual(scheduler.tick(self.c,10000,bad)['results'][0]['status'],'failed')
 def test_negative_time_rejected(self):
  with self.assertRaises(ValueError):scheduler.tick(self.c,-1,lambda n:True)
 def test_no_unbounded_retries(self):
  calls=[];scheduler.tick(self.c,10000,lambda n:calls.append(n) or False)
  self.assertEqual(len(calls),2)
if __name__=='__main__':unittest.main()