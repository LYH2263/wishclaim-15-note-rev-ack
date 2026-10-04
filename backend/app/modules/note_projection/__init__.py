"""Read projections for note revisions.

Wall cards and the claimer's list stay pinned to the confirmed body/rev and do
not leak the pending text; the detail view additionally exposes the pending
body and the full revision ledger for looking back at previous versions.
"""
from app.modules.note_revision import history


def card(r) -> dict:
    d = dict(r)
    d["awaiting_ack"] = bool(d.get("awaiting_ack"))
    # pending body stays private to the publisher/claimer detail view
    d.pop("pending_note", None)
    return d


def detail(c, r) -> dict:
    d = card(r)
    d["pending_note"] = r["pending_note"]
    d["revisions"] = history(c, r["id"])
    return d
