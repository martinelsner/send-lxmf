"""Persistent SQLite-backed message queue for LXMF messages."""

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class QueuedMessage:
    id: int
    destinations: list[bytes]
    content: str
    title: str
    fields: dict[str, Any]
    propagation_node: bytes | None
    created_at: float
    attempts: int
    last_attempt: float | None
    status: str


class MessageQueue:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._local = threading.local()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS message_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                destinations BLOB NOT NULL,
                content TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                fields TEXT NOT NULL DEFAULT '{}',
                propagation_node BLOB,
                created_at REAL NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_attempt REAL,
                status TEXT NOT NULL DEFAULT 'pending'
            )
            """
        )
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
        return self._local.conn

    def enqueue(
        self,
        destinations: list[bytes],
        content: str,
        title: str = "",
        fields: dict[str, Any] | None = None,
        propagation_node: bytes | None = None,
    ) -> int:
        destinations_bytes = b",".join(destinations)
        fields_json = json.dumps(fields or {})
        created_at = time.time()
        with self._lock:
            cursor = self._get_conn().execute(
                """
                INSERT INTO message_queue
                (destinations, content, title, fields, propagation_node, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    destinations_bytes,
                    content,
                    title,
                    fields_json,
                    propagation_node,
                    created_at,
                ),
            )
            self._get_conn().commit()
            return cursor.lastrowid

    def get_pending(self, limit: int = 10) -> list[QueuedMessage]:
        with self._lock:
            cursor = self._get_conn().execute(
                """
                SELECT id, destinations, content, title, fields, propagation_node,
                       created_at, attempts, last_attempt, status
                FROM message_queue
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            messages = []
            for row in rows:
                destinations_list = row[1].split(b",") if row[1] else []
                messages.append(
                    QueuedMessage(
                        id=row[0],
                        destinations=destinations_list,
                        content=row[2],
                        title=row[3],
                        fields=json.loads(row[4]),
                        propagation_node=row[5],
                        created_at=row[6],
                        attempts=row[7],
                        last_attempt=row[8],
                        status=row[9],
                    )
                )
            return messages

    def mark_attempt(self, message_id: int) -> None:
        with self._lock:
            self._get_conn().execute(
                """
                UPDATE message_queue
                SET attempts = attempts + 1, last_attempt = ?
                WHERE id = ?
                """,
                (time.time(), message_id),
            )
            self._get_conn().commit()

    def mark_done(self, message_id: int) -> None:
        with self._lock:
            self._get_conn().execute(
                "UPDATE message_queue SET status = 'done' WHERE id = ?",
                (message_id,),
            )
            self._get_conn().commit()

    def mark_failed(self, message_id: int) -> None:
        with self._lock:
            self._get_conn().execute(
                "UPDATE message_queue SET status = 'failed' WHERE id = ?",
                (message_id,),
            )
            self._get_conn().commit()

    def count_pending(self) -> int:
        with self._lock:
            cursor = self._get_conn().execute(
                "SELECT COUNT(*) FROM message_queue WHERE status = 'pending'"
            )
            return cursor.fetchone()[0]
