"""Display projection for the note flow.

Wall card / mine / detail all render through project() so the three views
pin the same rev + body and the same button gates from one source.
"""
from app.engines.note_gate import fulfill_allowed


def project(row: dict) -> dict:
    d = dict(row)
    d["awaiting_ack"] = row.get("note_state") == "awaiting_ack"
    d["fulfill_blocked"] = not fulfill_allowed(row.get("note_state") or "none")["ok"]
    return d


def project_detail(row: dict, live_revision: dict | None) -> dict:
    """Detail additionally exposes the last confirmed revision so the
    claimer can 回看上一版 before acking."""
    d = project(row)
    if d["awaiting_ack"] and live_revision:
        d["previous_rev"] = live_revision["rev"]
        d["previous_note"] = live_revision["body"]
    else:
        d["previous_rev"] = None
        d["previous_note"] = None
    return d
