"""Note (附言) revision transitions. Pure plans; main.py persists them.

拍板 D1: re-editing while awaiting_ack bumps rev again — the older pending
revision is superseded, ack always targets the newest rev, and the ack
timeout restarts from the latest edit.
拍板 D2: ack timeout auto-rejects back to the last live revision.

Invariants: exactly one 'live' revision per wish, at most one 'pending'.
wishes.note / wishes.note_rev always mirror the newest revision, so wall /
mine / detail pin the same rev+body from a single source.
"""
from datetime import datetime

LIVE = "live"            # the last confirmed revision
PENDING = "pending"      # awaiting claimer ack
SUPERSEDED = "superseded"  # replaced by a newer revision
REJECTED = "rejected"    # ack timeout, rolled back


def revision_row(wish_id: int, rev: int, body: str, state: str, now: datetime) -> dict:
    return {
        "wish_id": wish_id,
        "rev": rev,
        "body": body,
        "state": state,
        "created_at": now.isoformat(),
        "decided_at": None,
    }


def plan_edit(wish_id: int, mode: str, new_rev: int, body: str, now: datetime) -> dict:
    """Direct edits go live at once; edits on claimed wishes go pending.

    supersede lists which old revision states the new one retires. In ack
    mode only a previous pending is retired (D1: rev keeps climbing, the
    live revision stays untouched until ack).
    """
    if mode == "ack":
        return {
            "insert": revision_row(wish_id, new_rev, body, PENDING, now),
            "supersede": [PENDING],
            "wishes": {
                "note": body,
                "note_rev": new_rev,
                "note_state": "awaiting_ack",
                "pending_since": now.isoformat(),
            },
        }
    return {
        "insert": revision_row(wish_id, new_rev, body, LIVE, now),
        "supersede": [LIVE, PENDING],
        "wishes": {
            "note": body,
            "note_rev": new_rev,
            "note_state": "none",
            "pending_since": None,
        },
    }


def plan_ack(now: datetime) -> dict:
    """Claimer confirms: pending -> live, old live -> superseded."""
    return {
        "decided_at": now.isoformat(),
        "wishes": {"note_state": "none", "pending_since": None},
    }


def plan_reject(live_rev: int, live_body: str, now: datetime) -> dict:
    """Timeout (D2): pending -> rejected, projection rolls back to live."""
    return {
        "decided_at": now.isoformat(),
        "wishes": {
            "note": live_body,
            "note_rev": live_rev,
            "note_state": "none",
            "pending_since": None,
        },
    }
