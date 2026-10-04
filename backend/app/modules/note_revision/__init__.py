"""Note revision ledger.

Revisions of a wish's note form an append-only ledger in note_revisions:

  current     the body currently shown as wishes.note (rev == wishes.note_rev)
  history     superseded current revisions, still browsable on the detail page
  pending     proposed new body waiting for the claimer's ack
  superseded  a pending revision replaced by a newer edit while awaiting ack
  expired     a pending revision auto-rejected after ack timeout (or on release)

wishes keeps the redundant pending_* columns so projections and the sweep can
act without joining the ledger.
"""

STATE_CURRENT, STATE_HISTORY = "current", "history"
STATE_PENDING, STATE_SUPERSEDED, STATE_EXPIRED = "pending", "superseded", "expired"


def _next_rev(c, wish_id: int) -> int:
    r = c.execute("SELECT COALESCE(MAX(rev),0)+1 rev FROM note_revisions WHERE wish_id=?",
                  (wish_id,)).fetchone()
    return r["rev"]


def seed_revision(c, wish_id: int, note: str, now: str) -> None:
    """rev=1 current row for a newly created wish."""
    c.execute(
        "INSERT INTO note_revisions(wish_id,rev,note,state,created_at) VALUES (?,1,?,?,?)",
        (wish_id, note, STATE_CURRENT, now),
    )


def apply_open_edit(c, wish, note: str, now: str) -> int:
    """Unclaimed edit: new revision takes effect immediately, no ack."""
    wid = wish["id"]
    c.execute("UPDATE note_revisions SET state=? WHERE wish_id=? AND state=?",
              (STATE_HISTORY, wid, STATE_CURRENT))
    rev = _next_rev(c, wid)
    c.execute(
        "INSERT INTO note_revisions(wish_id,rev,note,state,created_at) VALUES (?,?,?,?,?)",
        (wid, rev, note, STATE_CURRENT, now),
    )
    c.execute("UPDATE wishes SET note=?, note_rev=? WHERE id=?", (note, rev, wid))
    return rev


def submit_pending(c, wish, note: str, now: str, deadline: str) -> int:
    """Claimed edit: park the revision as pending; the live body stays put.

    A second edit while still awaiting bumps the rev again and supersedes the
    previously outstanding revision.
    """
    wid = wish["id"]
    c.execute("UPDATE note_revisions SET state=? WHERE wish_id=? AND state=?",
              (STATE_SUPERSEDED, wid, STATE_PENDING))
    rev = _next_rev(c, wid)
    c.execute(
        "INSERT INTO note_revisions(wish_id,rev,note,state,created_at,expires_at)"
        " VALUES (?,?,?,?,?,?)",
        (wid, rev, note, STATE_PENDING, now, deadline),
    )
    c.execute(
        "UPDATE wishes SET awaiting_ack=1, pending_rev=?, pending_note=?,"
        " pending_at=?, pending_expires_at=? WHERE id=?",
        (rev, note, now, deadline, wid),
    )
    return rev


def apply_ack(c, wish, now: str) -> int:
    """Claimer accepts the pending revision: it becomes the live body."""
    wid = wish["id"]
    rev = wish["pending_rev"]
    note = wish["pending_note"]
    c.execute("UPDATE note_revisions SET state=? WHERE wish_id=? AND state=?",
              (STATE_HISTORY, wid, STATE_CURRENT))
    c.execute("UPDATE note_revisions SET state=?, acked_at=? WHERE wish_id=? AND rev=?",
              (STATE_CURRENT, now, wid, rev))
    c.execute(
        "UPDATE wishes SET note=?, note_rev=?, awaiting_ack=0,"
        " pending_rev=NULL, pending_note=NULL, pending_at=NULL, pending_expires_at=NULL"
        " WHERE id=?",
        (note, rev, wid),
    )
    return rev


def void_pending(c, wish) -> None:
    """Reject the outstanding revision (timeout / TTL release / manual release).

    The live body stays on the last confirmed revision.
    """
    wid = wish["id"]
    c.execute("UPDATE note_revisions SET state=? WHERE wish_id=? AND state=?",
              (STATE_EXPIRED, wid, STATE_PENDING))
    c.execute(
        "UPDATE wishes SET awaiting_ack=0, pending_rev=NULL, pending_note=NULL,"
        " pending_at=NULL, pending_expires_at=NULL WHERE id=?",
        (wid,),
    )


def history(c, wish_id: int) -> list[dict]:
    return [
        dict(r)
        for r in c.execute(
            "SELECT rev,note,state,created_at,acked_at,expires_at FROM note_revisions"
            " WHERE wish_id=? ORDER BY rev DESC",
            (wish_id,),
        )
    ]
