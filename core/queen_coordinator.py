"""Authorized CANO queen failover using a fenced SQLite lease.

This module coordinates explicitly registered nodes in one shared database.
It does not discover hosts, install software, or replicate across networks.
Distributed production requires a transactional shared store, not SQLite.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class QueenCoordinator:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS queen_nodes (
                    node_id TEXT PRIMARY KEY, authorized INTEGER NOT NULL,
                    healthy INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS queen_lease (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    holder TEXT, expires_at REAL NOT NULL DEFAULT 0,
                    epoch INTEGER NOT NULL DEFAULT 0);
                INSERT OR IGNORE INTO queen_lease(singleton,holder,expires_at,epoch)
                    VALUES(1,NULL,0,0);
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def register(self, node_id, *, authorized=False):
        if not authorized:
            raise PermissionError("Node registration requires authorization")
        if not isinstance(node_id, str) or not 1 <= len(node_id) <= 80:
            raise ValueError("Invalid node ID")
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO queen_nodes(node_id,authorized,healthy) VALUES(?,1,1)",
                       (node_id,))

    def set_health(self, node_id, healthy, *, authorized=False):
        if not authorized:
            raise PermissionError("Health changes require authorization")
        with self._connect() as db:
            cursor = db.execute("UPDATE queen_nodes SET healthy=? WHERE node_id=?",
                                (int(bool(healthy)), node_id))
            if cursor.rowcount != 1:
                raise KeyError(node_id)

    def acquire(self, node_id, *, ttl=30, at=None):
        if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or not 1 <= ttl <= 3600:
            raise ValueError("Invalid lease TTL")
        timestamp = time.time() if at is None else float(at)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            node = db.execute("SELECT authorized,healthy FROM queen_nodes WHERE node_id=?",
                              (node_id,)).fetchone()
            if not node or not node["authorized"] or not node["healthy"]:
                raise PermissionError("Unknown or unhealthy node")
            lease = db.execute("SELECT holder,expires_at,epoch FROM queen_lease WHERE singleton=1").fetchone()
            if lease["holder"] != node_id and lease["expires_at"] > timestamp:
                return None
            if lease["holder"] == node_id and lease["expires_at"] > timestamp:
                epoch = lease["epoch"]
            else:
                epoch = lease["epoch"] + 1
            db.execute("UPDATE queen_lease SET holder=?,expires_at=?,epoch=? WHERE singleton=1",
                       (node_id, timestamp + ttl, epoch))
            return epoch

    def valid(self, node_id, epoch, *, at=None):
        timestamp = time.time() if at is None else float(at)
        with self._connect() as db:
            row = db.execute("""SELECT l.holder,l.epoch,l.expires_at,n.healthy,n.authorized
                FROM queen_lease l LEFT JOIN queen_nodes n ON n.node_id=l.holder
                WHERE l.singleton=1""").fetchone()
        return bool(row and row["holder"] == node_id and row["epoch"] == epoch
                    and row["expires_at"] > timestamp and row["healthy"] and row["authorized"])

    def relinquish(self, node_id, epoch):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE queen_lease SET expires_at=0 WHERE singleton=1 AND holder=? AND epoch=?",
                       (node_id, epoch))
