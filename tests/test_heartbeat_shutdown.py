"""Regression: heartbeat context must not return with a live worker."""
import unittest
from threading import Event, Timer

from core.task_heartbeat_runner import running_heartbeat


class HeartbeatShutdownTests(unittest.TestCase):
    def test_exit_joins_inflight_worker_even_with_short_interval(self):
        active, release, finished = Event(), Event(), Event()

        class FakeStore:
            calls = 0

            def touch_running(self, task_id):
                self.calls += 1
                if self.calls == 1:
                    return True  # initial synchronous heartbeat
                active.set()
                release.wait(timeout=1.0)
                finished.set()
                return True

        with running_heartbeat(FakeStore(), "task-1", interval_seconds=0.001):
            self.assertTrue(active.wait(timeout=1.0))
            timer = Timer(0.06, release.set)
            timer.start()
        timer.join(timeout=1.0)
        self.assertTrue(finished.is_set())


if __name__ == "__main__":
    unittest.main()
