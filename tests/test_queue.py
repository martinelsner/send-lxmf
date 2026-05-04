"""Tests for lxmf_sender.queue."""

import json
import os
import sqlite3
import tempfile

import pytest

from lxmf_sender.queue import MessageQueue, QueuedMessage


VALID_HEX = "b9af7034186731b9f009d06795172a36"


class TestMessageQueue:
    def test_enqueue_returns_id(self, tmp_path):
        q = self._make_queue(tmp_path)
        msg_id = q.enqueue(
            destinations=[bytes.fromhex(VALID_HEX)],
            content="hello",
            title="test",
        )
        assert msg_id == 1

    def test_enqueue_multiple_returns_incrementing_ids(self, tmp_path):
        q = self._make_queue(tmp_path)
        id1 = q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="a")
        id2 = q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="b")
        id3 = q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="c")
        assert id1 < id2 < id3

    def test_get_pending_returns_enqueued_messages(self, tmp_path):
        q = self._make_queue(tmp_path)
        q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="hello", title="t")
        pending = q.get_pending()
        assert len(pending) == 1
        assert pending[0].content == "hello"
        assert pending[0].title == "t"
        assert pending[0].status == "pending"

    def test_get_pending_respects_limit(self, tmp_path):
        q = self._make_queue(tmp_path)
        for i in range(20):
            q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content=f"msg{i}")
        pending = q.get_pending(limit=5)
        assert len(pending) == 5

    def test_get_pending_returns_oldest_first(self, tmp_path):
        q = self._make_queue(tmp_path)
        for i in range(5):
            q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content=f"msg{i}")
        pending = q.get_pending()
        assert [m.content for m in pending] == ["msg0", "msg1", "msg2", "msg3", "msg4"]

    def test_get_pending_excludes_done(self, tmp_path):
        q = self._make_queue(tmp_path)
        id1 = q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="a")
        q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="b")
        q.mark_done(id1)
        pending = q.get_pending()
        assert len(pending) == 1
        assert pending[0].content == "b"

    def test_get_pending_excludes_failed(self, tmp_path):
        q = self._make_queue(tmp_path)
        q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="a")
        id2 = q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="b")
        q.mark_failed(id2)
        pending = q.get_pending()
        assert len(pending) == 1
        assert pending[0].content == "a"

    def test_mark_attempt_increments_attempts(self, tmp_path):
        q = self._make_queue(tmp_path)
        msg_id = q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="test")
        assert q.get_pending()[0].attempts == 0
        q.mark_attempt(msg_id)
        assert q.get_pending()[0].attempts == 1
        q.mark_attempt(msg_id)
        assert q.get_pending()[0].attempts == 2

    def test_mark_attempt_sets_last_attempt(self, tmp_path):
        q = self._make_queue(tmp_path)
        msg_id = q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="test")
        q.mark_attempt(msg_id)
        assert q.get_pending()[0].last_attempt is not None

    def test_mark_done_sets_status_to_done(self, tmp_path):
        q = self._make_queue(tmp_path)
        msg_id = q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="test")
        q.mark_done(msg_id)
        assert q.get_pending() == []

    def test_mark_failed_sets_status_to_failed(self, tmp_path):
        q = self._make_queue(tmp_path)
        msg_id = q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="test")
        q.mark_failed(msg_id)
        assert q.get_pending() == []

    def test_count_pending(self, tmp_path):
        q = self._make_queue(tmp_path)
        assert q.count_pending() == 0
        id1 = q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="a")
        assert q.count_pending() == 1
        id2 = q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="b")
        assert q.count_pending() == 2
        q.mark_done(id1)
        assert q.count_pending() == 1
        q.mark_failed(id2)
        assert q.count_pending() == 0

    def test_multiple_destinations_stored_and_restored(self, tmp_path):
        q = self._make_queue(tmp_path)
        dests = [bytes.fromhex(VALID_HEX), bytes.fromhex("a" * 32)]
        q.enqueue(destinations=dests, content="multi")
        pending = q.get_pending()
        assert len(pending) == 1
        assert pending[0].destinations == dests

    def test_fields_stored_as_json(self, tmp_path):
        q = self._make_queue(tmp_path)
        fields = {"key": "value", "num": 42}
        q.enqueue(
            destinations=[bytes.fromhex(VALID_HEX)], content="test", fields=fields
        )
        pending = q.get_pending()
        assert pending[0].fields == fields

    def test_propagation_node_stored(self, tmp_path):
        q = self._make_queue(tmp_path)
        pn = bytes.fromhex(VALID_HEX)
        q.enqueue(
            destinations=[bytes.fromhex(VALID_HEX)], content="test", propagation_node=pn
        )
        pending = q.get_pending()
        assert pending[0].propagation_node == pn

    def test_created_at_set(self, tmp_path):
        q = self._make_queue(tmp_path)
        q.enqueue(destinations=[bytes.fromhex(VALID_HEX)], content="test")
        pending = q.get_pending()
        assert pending[0].created_at > 0

    def _make_queue(self, tmp_path) -> MessageQueue:
        db_path = str(tmp_path / "queue.db")
        return MessageQueue(db_path)
