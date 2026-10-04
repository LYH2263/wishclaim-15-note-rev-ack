"""Ack gate for note revisions: edit dispatch, ack/fulfill guards, timeout."""
from datetime import datetime, timedelta

from app.engines.claim_lock import parse_ts


def edit_mode(status: str) -> dict:
    """How a note edit should be handled for the wish's status.

    open/released -> direct (no claimer to confirm with)
    claimed       -> pending (claimer must ack)
    fulfilled     -> deny
    """
    if status in ("open", "released"):
        return {"mode": "direct", "reason": ""}
    if status == "claimed":
        return {"mode": "pending", "reason": ""}
    return {"mode": "deny", "reason": "already_fulfilled"}


def pending_deadline(now: datetime, ack_timeout_seconds: int) -> str:
    return (now + timedelta(seconds=ack_timeout_seconds)).isoformat()


def pending_timed_out(awaiting_ack: int, pending_expires_at: str | None, now: datetime) -> bool:
    return bool(awaiting_ack) and bool(pending_expires_at) and parse_ts(pending_expires_at) <= now


def fulfill_blocked(status: str, awaiting_ack: int) -> str | None:
    """Return the blocking reason while an unacked revision is outstanding."""
    if status == "claimed" and awaiting_ack:
        return "awaiting_ack"
    return None


def ack_allowed(status: str, awaiting_ack: int, row_claimer: str | None,
                body_claimer: str | None = None) -> dict:
    """Only the current claimer can ack, and only while a revision is pending."""
    if status != "claimed":
        return {"ok": False, "reason": "not_claimed"}
    if not awaiting_ack:
        return {"ok": False, "reason": "no_pending_revision"}
    if body_claimer and row_claimer and body_claimer != row_claimer:
        return {"ok": False, "reason": "not_claimer"}
    return {"ok": True, "reason": ""}
