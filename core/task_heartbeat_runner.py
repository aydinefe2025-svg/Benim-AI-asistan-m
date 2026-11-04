"""Heartbeat a running research task while a blocking provider call executes.

The daemon thread is bounded by a stop event and never runs a provider call.
"""
from contextlib import contextmanager
from threading import Event, Thread
import sqlite3
from contextlib import closing

from core.task_heartbeat import touch_running


@contextmanager
def running_heartbeat(db_path, task_id, *, interval_seconds=30):
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    stop = Event()
    failures = []

    def loop():
        while not stop.wait(interval_seconds):
            try:
                if not touch_running(db_path, task_id):
                    with closing(sqlite3.connect(str(db_path), timeout=15)) as conn:
                        row = conn.execute('SELECT status FROM tasks WHERE id=?', (task_id,)).fetchone()
                    if row is None or row[0] not in ('review_pending', 'done', 'verified'):
                        failures.append(RuntimeError('Running task lost heartbeat ownership'))
                    break
            except Exception as exc:
                failures.append(RuntimeError('Running task heartbeat failed'))
                failures[-1].__cause__ = exc
                break

    if not touch_running(db_path, task_id):
        raise ValueError("Task must be running before heartbeat starts")
    thread = Thread(target=loop, name="research-task-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=min(interval_seconds, 5))
        if failures:
            raise failures[0]
