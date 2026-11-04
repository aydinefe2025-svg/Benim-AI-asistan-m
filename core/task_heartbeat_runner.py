"""Heartbeat a running research task while a blocking provider call executes.

The daemon thread is bounded by a stop event and never runs a provider call.
"""
from contextlib import contextmanager
from threading import Event, Thread

from core.task_heartbeat import touch_running


@contextmanager
def running_heartbeat(db_path, task_id, *, interval_seconds=30):
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    stop = Event()

    touch = db_path.touch_running if hasattr(db_path, "touch_running") else lambda task: touch_running(db_path, task)

    def loop():
        while not stop.wait(interval_seconds):
            if not touch(task_id):
                break

    if not touch(task_id):
        raise ValueError("Task must be running before heartbeat starts")
    thread = Thread(target=loop, name="research-task-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=min(interval_seconds, 5))
