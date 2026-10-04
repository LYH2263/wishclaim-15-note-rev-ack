from datetime import datetime, timedelta, timezone

from app.engines import note_revision as nrev
from app.engines.note_gate import (
    EDIT_ACK, EDIT_DIRECT, EDIT_FORBIDDEN,
    ack_allowed, edit_mode, fulfill_allowed, timeout_due,
)
from app.engines.note_projection import project, project_detail

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_edit_mode_routes_by_status():
    assert edit_mode("open") == EDIT_DIRECT
    assert edit_mode("released") == EDIT_DIRECT
    assert edit_mode("claimed") == EDIT_ACK
    assert edit_mode("fulfilled") == EDIT_FORBIDDEN


def test_direct_edit_goes_live_and_clears_flags():
    plan = nrev.plan_edit(1, EDIT_DIRECT, 2, "new body", NOW)
    assert plan["insert"]["state"] == nrev.LIVE
    assert plan["wishes"] == {
        "note": "new body", "note_rev": 2, "note_state": "none", "pending_since": None,
    }
    assert set(plan["supersede"]) == {nrev.LIVE, nrev.PENDING}


def test_claimed_edit_goes_pending_and_supersedes_only_pending():
    plan = nrev.plan_edit(1, EDIT_ACK, 3, "v3", NOW)
    assert plan["insert"]["state"] == nrev.PENDING
    assert plan["wishes"]["note_state"] == "awaiting_ack"
    assert plan["wishes"]["pending_since"] == NOW.isoformat()
    # 拍板 D1: rev 递增，旧待确认版被取代，live 版不动
    assert plan["supersede"] == [nrev.PENDING]


def test_ack_plan_clears_flag():
    plan = nrev.plan_ack(NOW)
    assert plan["wishes"] == {"note_state": "none", "pending_since": None}


def test_reject_plan_rolls_back_to_live():
    plan = nrev.plan_reject(2, "old body", NOW)
    assert plan["wishes"]["note"] == "old body"
    assert plan["wishes"]["note_rev"] == 2
    assert plan["wishes"]["note_state"] == "none"
    assert plan["wishes"]["pending_since"] is None


def test_fulfill_blocked_while_awaiting_ack():
    assert fulfill_allowed("awaiting_ack")["reason"] == "note_awaiting_ack"
    assert fulfill_allowed("none")["ok"] is True


def test_ack_only_by_current_claimer():
    assert ack_allowed("awaiting_ack", "alice", "alice")["ok"] is True
    assert ack_allowed("awaiting_ack", "alice", "bob")["reason"] == "not_claimer"
    assert ack_allowed("awaiting_ack", None, "alice")["reason"] == "not_claimer"
    assert ack_allowed("none", "alice", "alice")["reason"] == "nothing_to_ack"


def test_timeout_due_boundary():
    since = NOW.isoformat()
    assert timeout_due("awaiting_ack", since, NOW + timedelta(seconds=99), 100) is False
    assert timeout_due("awaiting_ack", since, NOW + timedelta(seconds=100), 100) is True
    assert timeout_due("none", since, NOW + timedelta(days=9), 100) is False
    assert timeout_due("awaiting_ack", None, NOW, 100) is False


def test_projection_pins_flags():
    d = project({"id": 1, "note": "x", "note_rev": 3, "note_state": "awaiting_ack"})
    assert d["awaiting_ack"] is True and d["fulfill_blocked"] is True
    d = project({"id": 1, "note": "x", "note_rev": 3, "note_state": "none"})
    assert d["awaiting_ack"] is False and d["fulfill_blocked"] is False


def test_detail_projection_exposes_previous_only_while_pending():
    row = {"id": 1, "note": "new", "note_rev": 3, "note_state": "awaiting_ack"}
    d = project_detail(row, {"rev": 2, "body": "old"})
    assert d["previous_rev"] == 2 and d["previous_note"] == "old"
    d = project_detail({**row, "note_state": "none"}, {"rev": 3, "body": "new"})
    assert d["previous_rev"] is None and d["previous_note"] is None
