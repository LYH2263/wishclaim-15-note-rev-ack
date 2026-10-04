from datetime import datetime, timedelta, timezone
from app.engines.ack_gate import (
    ack_allowed,
    edit_mode,
    fulfill_blocked,
    pending_deadline,
    pending_timed_out,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_edit_mode_dispatch():
    assert edit_mode("open")["mode"] == "direct"
    assert edit_mode("released")["mode"] == "direct"
    assert edit_mode("claimed")["mode"] == "pending"
    denied = edit_mode("fulfilled")
    assert denied["mode"] == "deny" and denied["reason"] == "already_fulfilled"


def test_pending_deadline_and_timeout():
    deadline = pending_deadline(NOW, 3600)
    assert deadline == (NOW + timedelta(seconds=3600)).isoformat()
    assert pending_timed_out(1, deadline, NOW) is False
    assert pending_timed_out(1, deadline, NOW + timedelta(seconds=3601)) is True
    assert pending_timed_out(0, deadline, NOW + timedelta(days=1)) is False
    assert pending_timed_out(1, None, NOW) is False


def test_fulfill_blocked_while_awaiting():
    assert fulfill_blocked("claimed", 1) == "awaiting_ack"
    assert fulfill_blocked("claimed", 0) is None
    assert fulfill_blocked("open", 1) is None


def test_ack_allowed_guards():
    assert ack_allowed("claimed", 1, "alice").get("ok") is True
    assert ack_allowed("claimed", 1, "alice", "alice").get("ok") is True
    assert ack_allowed("claimed", 1, "alice", "bob")["reason"] == "not_claimer"
    assert ack_allowed("claimed", 0, "alice")["reason"] == "no_pending_revision"
    assert ack_allowed("open", 1, "alice")["reason"] == "not_claimed"
