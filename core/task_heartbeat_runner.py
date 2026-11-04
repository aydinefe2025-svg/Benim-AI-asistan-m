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
    failures = []

    touch = db_path.touch_running if hasattr(db_path, "touch_running") else lambda task: touch_running(db_path, task)

    def loop():
        while not stop.wait(interval_seconds):
            try:
                if touch(task_id):
                    continue
                # A normal completed/reviewed task no longer needs a heartbeat.
                # Missing, blocked or reassigned tasks must fail closed.
                from core.task_store import TaskStore
                store = db_path if hasattr(db_path, "get") else TaskStore(db_path)
                status = store.get(task_id)["status"]
                if status not in {"review_pending", "done", "verified"}:
                    failures.append(RuntimeError("Running task lost heartbeat ownership"))
                break
            except Exception as exc:
                failure = RuntimeError("Running task heartbeat failed")
                failure.__cause__ = exc
                failures.append(failure)
                break

    if not touch(task_id):
        raise ValueError("Task must be running before heartbeat starts")
    thread = Thread(target=loop, name="research-task-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        # Wait for an in-flight bounded database touch to finish before the
        # caller closes or removes its SQLite file. A short interval-based
        # join can leave the daemon thread using the file during teardown.
        thread.join()
        if failures:
            raise failures[0]
