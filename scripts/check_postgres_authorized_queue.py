"""Real PostgreSQL integration smoke for the authorized CANO task queue.

Runs only with a synthetic TEST_TASK_DATABASE_URL on a disposable CI database.
Never touches Render secrets or user data.
"""
from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

from core.postgres_authorized_queue import PostgresAuthorizedQueue


def provision_synthetic_schema(database_url):
    """Create only the empty tables needed by this disposable CI smoke."""
    import psycopg

    with psycopg.connect(database_url) as db, db.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.cano_authorized_jobs (
                owner_key text NOT NULL,
                id text NOT NULL,
                idem_key text NOT NULL,
                goal text NOT NULL,
                state text NOT NULL,
                max_calls integer NOT NULL,
                attempts integer NOT NULL DEFAULT 0,
                eligible_after double precision NOT NULL DEFAULT 0,
                lease_token text,
                worker_id text,
                lease_until double precision,
                result_digest text,
                draft text,
                created_at double precision NOT NULL,
                PRIMARY KEY (owner_key, id),
                UNIQUE (owner_key, idem_key)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.cano_authorized_job_events (
                event_id bigserial PRIMARY KEY,
                owner_key text NOT NULL,
                job_id text NOT NULL,
                at double precision NOT NULL,
                state text NOT NULL,
                code text NOT NULL,
                FOREIGN KEY (owner_key, job_id)
                    REFERENCES public.cano_authorized_jobs(owner_key, id)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_cano_authorized_jobs_claim
            ON public.cano_authorized_jobs(owner_key, state, eligible_after, created_at, id)
        """)


def run():
    database_url = os.environ["TEST_TASK_DATABASE_URL"]
    owner = "ci-owner-" + uuid.uuid4().hex
    queue = PostgresAuthorizedQueue(database_url, owner_key=owner, max_jobs=5)
    provision_synthetic_schema(database_url)
    queue.verify_schema()

    try:
        queue.enqueue("first", "Source review")
        raise AssertionError("Missing explicit authorization accepted")
    except PermissionError:
        pass

    first = queue.enqueue("first", "Source review", approved=True, max_calls=2)
    assert first["state"] == "queued"
    assert queue.enqueue("first", "Source review", approved=True, max_calls=2)["id"] == first["id"]
    try:
        queue.enqueue("first", "Different goal", approved=True, max_calls=2)
        raise AssertionError("Idempotency key conflict was accepted")
    except ValueError:
        pass

    other = PostgresAuthorizedQueue(database_url, owner_key=owner+"-other", max_jobs=5)
    assert other.list() == []
    assert other.claim("other-worker", approved=True, now=100) is None
    try:
        other.get(first["id"])
        raise AssertionError("Cross-owner task read succeeded")
    except KeyError:
        pass

    lease = queue.claim("worker-one", approved=True, now=100, lease_seconds=30)
    assert lease["id"] == first["id"]
    assert queue.claim("worker-two", approved=True, now=101) is None
    result = queue.complete(first["id"], lease["lease_token"], "Unverified research draft", now=101)
    assert result["status"] == "review_pending" and result["verified"] is False
    assert queue.get(first["id"])["state"] == "review_pending"
    assert [e["state"] for e in queue.events(first["id"])] == ["queued","running","review_pending"]

    retry = queue.enqueue("retry", "Retry task", approved=True, max_calls=2)
    def provider_fails(_):
        raise RuntimeError("simulated sensitive provider detail")
    failure = queue.run_once("worker-1", provider_fails, approved=True, now=200)
    assert failure["status"] == "retry_pending"
    assert queue.run_once("worker-1", provider_fails, approved=True, now=200) is None
    failure = queue.run_once("worker-1", provider_fails, approved=True, now=203)
    assert failure["status"] == "blocked"
    assert queue.get(retry["id"])["attempts"] == 2
    assert "sensitive" not in str(queue.events(retry["id"]))

    expired = queue.enqueue("expired", "Check old lock", approved=True)
    expired_lease = queue.claim("worker-1", approved=True, now=400, lease_seconds=5)
    assert expired_lease["id"] == expired["id"]
    assert queue.recover_expired(now=406) == 1
    assert queue.get(expired["id"])["state"] == "blocked"
    try:
        queue.complete(expired["id"], expired_lease["lease_token"], "Late", now=407)
        raise AssertionError("Expired lease accepted")
    except PermissionError:
        pass

    # Two independent queue clients race the same authorized task.
    # The winning worker commits one draft; a losing or cross-owner worker
    # cannot write a second result. Real row locks and separate connections.
    queued = queue.enqueue("concurrent", "Only one result write", approved=True)
    def worker_claim_and_complete(i):
        independent = PostgresAuthorizedQueue(
            database_url, owner_key=owner, max_jobs=5)
        lease = independent.claim(f"worker-{i}", approved=True, now=500)
        if lease is None:
            return None
        result = independent.complete(
            lease["id"], lease["lease_token"], "Only winner draft", now=501)
        return lease, result

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker_claim_and_complete, (0, 1)))
    winners = [item for item in results if item is not None]
    assert len(winners) == 1, "Multiple workers wrote the same task"
    winner, result = winners[0]
    assert winner["id"] == queued["id"]
    assert result["status"] == "review_pending" and not result["verified"]

    try:
        other.complete(queued["id"], winner["lease_token"],
                       "Cross-owner overwrite", now=501)
        raise AssertionError("Cross-owner completion was accepted")
    except KeyError:
        pass
    try:
        queue.complete(queued["id"], "different-worker-lease-token",
                       "Losing worker overwrite", now=501)
        raise AssertionError("Losing worker completion was accepted")
    except PermissionError:
        pass

    reopened = PostgresAuthorizedQueue(database_url, owner_key=owner, max_jobs=5)
    assert reopened.get(first["id"])["draft"] == "Unverified research draft"
    assert reopened.get(queued["id"])["draft"] == "Only winner draft"
    assert [event["state"] for event in reopened.events(queued["id"])] == [
        "queued", "running", "review_pending"]
    print("PostgreSQL CANO queue integration: authorization/idempotency/owners/"
          "claims/single-writer/retry/expiry/readback OK")
if __name__ == "__main__":
    run()
