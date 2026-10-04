import pytest
from app.db import connect
from app import seed
from app.modules.note_revision import (
    apply_ack,
    apply_open_edit,
    history,
    seed_revision,
    submit_pending,
    void_pending,
)

NOW = "2026-01-01T12:00:00+00:00"
DEADLINE = "2026-01-02T12:00:00+00:00"


@pytest.fixture()
def c(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    conn = connect()
    yield conn
    conn.close()


def make_wish(c, status="open", claimer=None):
    cur = c.execute(
        "INSERT INTO wishes(title,note,status,claimer,data_quality,note_rev,awaiting_ack)"
        " VALUES ('t','v1',?,?,'clean',1,0)",
        (status, claimer),
    )
    wid = cur.lastrowid
    seed_revision(c, wid, "v1", NOW)
    c.commit()
    return wid


def get_row(c, wid):
    return c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()


def test_pending_edit_then_ack_switches_body(c):
    wid = make_wish(c, "claimed", "alice")
    submit_pending(c, get_row(c, wid), "v2", NOW, DEADLINE)
    r = get_row(c, wid)
    # 待确认期间正文与当前 rev 不动
    assert r["note"] == "v1" and r["note_rev"] == 1
    assert r["awaiting_ack"] == 1 and r["pending_rev"] == 2 and r["pending_note"] == "v2"

    apply_ack(c, r, NOW)
    r = get_row(c, wid)
    assert r["note"] == "v2" and r["note_rev"] == 2 and r["awaiting_ack"] == 0
    assert r["pending_rev"] is None and r["pending_note"] is None
    states = {rv["rev"]: rv["state"] for rv in history(c, wid)}
    assert states == {1: "history", 2: "current"}


def test_second_edit_supersedes_old_pending(c):
    wid = make_wish(c, "claimed", "alice")
    submit_pending(c, get_row(c, wid), "v2", NOW, DEADLINE)
    submit_pending(c, get_row(c, wid), "v3", NOW, DEADLINE)
    r = get_row(c, wid)
    assert r["pending_rev"] == 3 and r["note"] == "v1"
    apply_ack(c, r, NOW)
    states = {rv["rev"]: rv["state"] for rv in history(c, wid)}
    assert states == {1: "history", 2: "superseded", 3: "current"}
    assert get_row(c, wid)["note"] == "v3"


def test_open_edit_takes_effect_immediately(c):
    wid = make_wish(c, "open")
    rev = apply_open_edit(c, get_row(c, wid), "v2", NOW)
    r = get_row(c, wid)
    assert rev == 2 and r["note"] == "v2" and r["note_rev"] == 2 and r["awaiting_ack"] == 0
    states = {rv["rev"]: rv["state"] for rv in history(c, wid)}
    assert states == {1: "history", 2: "current"}


def test_void_pending_keeps_last_confirmed_body(c):
    wid = make_wish(c, "claimed", "alice")
    submit_pending(c, get_row(c, wid), "v2", NOW, DEADLINE)
    void_pending(c, get_row(c, wid))
    r = get_row(c, wid)
    assert r["note"] == "v1" and r["note_rev"] == 1 and r["awaiting_ack"] == 0
    assert r["pending_rev"] is None
    states = {rv["rev"]: rv["state"] for rv in history(c, wid)}
    assert states == {1: "current", 2: "expired"}


def test_seeded_old_db_backfills_rev_one(monkeypatch, tmp_path):
    """旧库迁移：已存在的愿望补 rev=1 current。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()  # 首次：4 条种子
    conn = connect()
    rows = conn.execute(
        "SELECT wish_id, state, rev FROM note_revisions ORDER BY wish_id"
    ).fetchall()
    assert len(rows) == 4 and all(r["rev"] == 1 and r["state"] == "current" for r in rows)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(wishes)")}
    assert {"note_rev", "awaiting_ack", "pending_rev", "pending_expires_at"} <= cols
    assert conn.execute("SELECT value FROM settings WHERE key='ack_timeout_seconds'").fetchone()["value"] == "86400"
    conn.close()
