"""End-to-end note-ack flow against a temp DB (endpoint functions called directly)."""
import pytest
from fastapi import HTTPException


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app import seed
    seed.init_db()
    from app import main
    return main


def _wish(rows, wid):
    return [r for r in rows if r["id"] == wid][0]


def test_open_edit_skips_ack(api):
    wid = api.create_wish(api.WishIn(title="t", note="v1"))["id"]
    r = api.edit_note(wid, api.NoteIn(note="v2"))
    assert r["rev"] == 2 and r["note_state"] == "none"
    w = api.get_wish(wid)
    assert w["note"] == "v2" and w["note_rev"] == 2 and w["awaiting_ack"] is False


def test_claimed_edit_blocks_fulfill_until_claimer_acks(api):
    wid = api.create_wish(api.WishIn(title="t", note="v1"))["id"]
    api.claim(wid, api.ClaimIn(claimer="alice"))
    r = api.edit_note(wid, api.NoteIn(note="v2"))
    assert r["note_state"] == "awaiting_ack" and r["rev"] == 2

    with pytest.raises(HTTPException) as e:
        api.fulfill(wid)
    assert e.value.status_code == 409 and e.value.detail == "note_awaiting_ack"

    with pytest.raises(HTTPException) as e:
        api.ack_note(wid, api.AckIn(claimer="bob"))
    assert e.value.detail == "not_claimer"

    # ack 前详情可回看上一版
    w = api.get_wish(wid)
    assert w["previous_note"] == "v1" and w["previous_rev"] == 1

    api.ack_note(wid, api.AckIn(claimer="alice"))
    w = api.get_wish(wid)
    assert w["awaiting_ack"] is False and w["note"] == "v2" and w["note_rev"] == 2
    assert w["previous_note"] is None
    assert api.fulfill(wid)["status"] == "fulfilled"


def test_reedit_while_pending_bumps_rev_and_ack_targets_latest(api):
    """拍板 D1: rev 递增，旧待确认版 superseded，ack 针对最新版。"""
    wid = api.create_wish(api.WishIn(title="t", note="v1"))["id"]
    api.claim(wid, api.ClaimIn(claimer="alice"))
    api.edit_note(wid, api.NoteIn(note="v2"))
    r = api.edit_note(wid, api.NoteIn(note="v3"))
    assert r["rev"] == 3
    revs = {x["rev"]: x for x in api.list_note_revisions(wid)}
    assert revs[1]["state"] == "live"
    assert revs[2]["state"] == "superseded"
    assert revs[3]["state"] == "pending"
    api.ack_note(wid, api.AckIn(claimer="alice"))
    w = api.get_wish(wid)
    assert w["note"] == "v3" and w["note_rev"] == 3
    revs = {x["rev"]: x for x in api.list_note_revisions(wid)}
    assert revs[1]["state"] == "superseded" and revs[3]["state"] == "live"


def test_timeout_auto_rejects_to_previous(api):
    """拍板 D2: 超时未 ack 自动驳回回上一版，fulfill 解禁。"""
    wid = api.create_wish(api.WishIn(title="t", note="v1"))["id"]
    api.claim(wid, api.ClaimIn(claimer="alice"))
    api.edit_note(wid, api.NoteIn(note="v2"))
    from app.db import connect
    c = connect()
    c.execute("UPDATE wishes SET pending_since=? WHERE id=?", ("2020-01-01T00:00:00+00:00", wid))
    c.commit(); c.close()

    w = _wish(api.list_wishes(), wid)  # list triggers the sweep
    assert w["note"] == "v1" and w["note_rev"] == 1 and w["awaiting_ack"] is False
    assert w["fulfill_blocked"] is False
    assert api.fulfill(wid)["status"] == "fulfilled"
    revs = {x["rev"]: x for x in api.list_note_revisions(wid)}
    assert revs[1]["state"] == "live" and revs[2]["state"] == "rejected"


def test_three_views_pin_same_rev_and_body(api):
    wid = api.create_wish(api.WishIn(title="t", note="v1"))["id"]
    api.claim(wid, api.ClaimIn(claimer="alice"))
    api.edit_note(wid, api.NoteIn(note="v2"))
    wall = _wish(api.list_wishes(), wid)
    mine = _wish(api.mine("alice"), wid)
    detail = api.get_wish(wid)
    for view in (wall, mine, detail):
        assert view["note"] == "v2"
        assert view["note_rev"] == 2
        assert view["awaiting_ack"] is True
        assert view["fulfill_blocked"] is True


def test_fulfilled_note_is_frozen(api):
    wid = api.create_wish(api.WishIn(title="t", note="v1"))["id"]
    api.claim(wid, api.ClaimIn(claimer="alice"))
    api.fulfill(wid)
    with pytest.raises(HTTPException) as e:
        api.edit_note(wid, api.NoteIn(note="v2"))
    assert e.value.status_code == 400 and e.value.detail == "already_fulfilled"
