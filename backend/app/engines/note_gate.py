"""Ack/timeout gates for the note (附言) confirmation flow."""
from datetime import datetime, timedelta

from app.engines.claim_lock import parse_ts

EDIT_DIRECT = "direct"        # unclaimed: edit applies immediately, no ack
EDIT_ACK = "ack"              # claimed: edit goes pending until claimer acks
EDIT_FORBIDDEN = "forbidden"  # fulfilled: note is frozen history


def edit_mode(status: str) -> str:
    if status == "claimed":
        return EDIT_ACK
    if status == "fulfilled":
        return EDIT_FORBIDDEN
    return EDIT_DIRECT


def fulfill_allowed(note_state: str) -> dict:
    """fulfill is blocked while a note revision awaits claimer ack."""
    if note_state == "awaiting_ack":
        return {"ok": False, "reason": "note_awaiting_ack"}
    return {"ok": True, "reason": ""}


def ack_allowed(note_state: str, claimer: str | None, actor: str) -> dict:
    """Only the current claimer may ack, and only while a revision pends."""
    if note_state != "awaiting_ack":
        return {"ok": False, "reason": "nothing_to_ack"}
    if not claimer or actor != claimer:
        return {"ok": False, "reason": "not_claimer"}
    return {"ok": True, "reason": ""}


def timeout_due(note_state: str, pending_since: str | None, now: datetime, timeout_seconds: int) -> bool:
    if note_state != "awaiting_ack" or not pending_since:
        return False
    return parse_ts(pending_since) + timedelta(seconds=timeout_seconds) <= now
