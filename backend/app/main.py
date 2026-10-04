from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect
from app.engines.claim_lock import claim_allowed, lock_payload, release_if_expired
from app.engines import note_revision as nrev
from app.engines.note_gate import (
    EDIT_FORBIDDEN, ack_allowed, edit_mode, fulfill_allowed, timeout_due,
)
from app.engines.note_projection import project, project_detail

app = FastAPI(title="Wishclaim", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

def now(): return datetime.now(timezone.utc)

def setting(c, key, default):
    row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return int(row["value"] if row else default)

def sweep(c):
    t = now()
    for r in c.execute("SELECT * FROM wishes WHERE status='claimed'"):
        rel = release_if_expired(r["status"], r["expires_at"], t)
        if rel:
            c.execute("UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
                      (rel["status"], None, None, None, r["id"]))
    # ack timeout sweep (拍板 D2): auto-reject back to the last live revision
    timeout = setting(c, "ack_timeout_seconds", 86400)
    for r in c.execute("SELECT id, note_state, pending_since FROM wishes WHERE note_state='awaiting_ack'"):
        if timeout_due(r["note_state"], r["pending_since"], t, timeout):
            live = c.execute(
                "SELECT rev, body FROM note_revisions WHERE wish_id=? AND state='live'", (r["id"],)).fetchone()
            if live:
                plan = nrev.plan_reject(live["rev"], live["body"], t)
                c.execute("UPDATE note_revisions SET state=?, decided_at=? WHERE wish_id=? AND state='pending'",
                          (nrev.REJECTED, plan["decided_at"], r["id"]))
                w = plan["wishes"]
                c.execute("UPDATE wishes SET note=?, note_rev=?, note_state=?, pending_since=? WHERE id=?",
                          (w["note"], w["note_rev"], w["note_state"], w["pending_since"], r["id"]))

@app.get("/api/health")
def health(): return {"ok": True, "project": "wishclaim"}

@app.get("/api/wishes")
def list_wishes():
    c = connect(); sweep(c); c.commit()
    rows = [project(dict(r)) for r in c.execute("SELECT * FROM wishes ORDER BY id DESC")]; c.close(); return rows

@app.get("/api/wishes/{wid}")
def get_wish(wid: int):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    live = c.execute(
        "SELECT rev, body FROM note_revisions WHERE wish_id=? AND state='live'", (wid,)).fetchone()
    out = project_detail(dict(r), dict(live) if live else None); c.close(); return out

class WishIn(BaseModel):
    title: str
    note: str = ""

@app.post("/api/wishes")
def create_wish(body: WishIn):
    c = connect()
    cur = c.execute(
        "INSERT INTO wishes(title,note,status,data_quality,note_rev,note_state) VALUES (?,?,?,?,?,?)",
        (body.title, body.note, "open", "clean", 1, "none"))
    wid = cur.lastrowid
    rev1 = nrev.revision_row(wid, 1, body.note, nrev.LIVE, now())
    c.execute("INSERT INTO note_revisions(wish_id,rev,body,state,created_at) VALUES (?,?,?,?,?)",
              (wid, rev1["rev"], rev1["body"], rev1["state"], rev1["created_at"]))
    c.commit(); c.close(); return {"id": wid}

class NoteIn(BaseModel):
    note: str

@app.post("/api/wishes/{wid}/note")
def edit_note(wid: int, body: NoteIn):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    mode = edit_mode(r["status"])
    if mode == EDIT_FORBIDDEN:
        c.close(); raise HTTPException(400, "already_fulfilled")
    t = now()
    new_rev = c.execute(
        "SELECT COALESCE(MAX(rev),0)+1 n FROM note_revisions WHERE wish_id=?", (wid,)).fetchone()["n"]
    plan = nrev.plan_edit(wid, mode, new_rev, body.note, t)
    for st in plan["supersede"]:
        c.execute("UPDATE note_revisions SET state=?, decided_at=? WHERE wish_id=? AND state=?",
                  (nrev.SUPERSEDED, t.isoformat(), wid, st))
    ins = plan["insert"]
    c.execute("INSERT INTO note_revisions(wish_id,rev,body,state,created_at) VALUES (?,?,?,?,?)",
              (wid, ins["rev"], ins["body"], ins["state"], ins["created_at"]))
    w = plan["wishes"]
    c.execute("UPDATE wishes SET note=?, note_rev=?, note_state=?, pending_since=? WHERE id=?",
              (w["note"], w["note_rev"], w["note_state"], w["pending_since"], wid))
    c.commit(); c.close()
    return {"ok": True, "rev": new_rev, "note_state": w["note_state"]}

class AckIn(BaseModel):
    claimer: str

@app.post("/api/wishes/{wid}/note/ack")
def ack_note(wid: int, body: AckIn):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    chk = ack_allowed(r["note_state"], r["claimer"], body.claimer)
    if not chk["ok"]:
        c.close(); raise HTTPException(409, chk["reason"])
    plan = nrev.plan_ack(now())
    c.execute("UPDATE note_revisions SET state=?, decided_at=? WHERE wish_id=? AND state='live'",
              (nrev.SUPERSEDED, plan["decided_at"], wid))
    c.execute("UPDATE note_revisions SET state=?, decided_at=? WHERE wish_id=? AND state='pending'",
              (nrev.LIVE, plan["decided_at"], wid))
    c.execute("UPDATE wishes SET note_state='none', pending_since=NULL WHERE id=?", (wid,))
    c.commit(); c.close(); return {"ok": True, "note_state": "none"}

@app.get("/api/wishes/{wid}/note/revisions")
def list_note_revisions(wid: int):
    c = connect()
    rows = [dict(r) for r in c.execute(
        "SELECT rev, body, state, created_at, decided_at FROM note_revisions "
        "WHERE wish_id=? ORDER BY rev DESC", (wid,))]
    c.close(); return rows

class ClaimIn(BaseModel):
    claimer: str

@app.post("/api/wishes/{wid}/claim")
def claim(wid: int, body: ClaimIn):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    allowed = claim_allowed(r["status"], r["claimer"], now(), r["expires_at"])
    if not allowed["ok"]:
        c.close(); raise HTTPException(409, allowed["reason"])
    p = lock_payload(body.claimer, now(), setting(c, "ttl_seconds", 86400))
    c.execute("UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
              (p["status"], p["claimer"], p["claimed_at"], p["expires_at"], wid))
    c.commit(); c.close(); return p

@app.post("/api/wishes/{wid}/release")
def release(wid: int):
    c = connect()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    if r["status"] != "claimed":
        c.close(); raise HTTPException(400, "not_claimed")
    c.execute("UPDATE wishes SET status='released', claimer=NULL, claimed_at=NULL, expires_at=NULL WHERE id=?", (wid,))
    c.commit(); c.close(); return {"ok": True, "status": "released"}

@app.post("/api/wishes/{wid}/fulfill")
def fulfill(wid: int):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    if r["status"] != "claimed":
        c.close(); raise HTTPException(400, "need_claim")
    chk = fulfill_allowed(r["note_state"])
    if not chk["ok"]:
        c.close(); raise HTTPException(409, chk["reason"])
    c.execute("UPDATE wishes SET status='fulfilled' WHERE id=?", (wid,))
    c.commit(); c.close(); return {"ok": True, "status": "fulfilled"}

@app.get("/api/mine")
def mine(claimer: str):
    c = connect(); sweep(c); c.commit()
    rows = [project(dict(r)) for r in c.execute("SELECT * FROM wishes WHERE claimer=?", (claimer,))]
    c.close(); return rows

@app.get("/api/done")
def done():
    c = connect()
    rows = [dict(r) for r in c.execute("SELECT * FROM wishes WHERE status='fulfilled'")]; c.close(); return rows

@app.get("/api/settings")
def settings():
    c = connect(); rows = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; c.close(); return rows

@app.get("/api/rules")
def rules():
    return {
        "mutex": "同一愿望同时只能被一人认领",
        "ttl": "认领超时未核销则自动释放",
        "fulfill": "核销后状态变为 fulfilled",
        "note_edit_open": "未认领时修改附言立即生效，无需确认",
        "note_edit_claimed": "已认领时修改附言进入待确认，认领人确认前不可核销",
        "note_reedit": "待确认期间再次修改：rev 递增，确认永远针对最新版",
        "note_ack_timeout": "超过 ack_timeout_seconds 未确认：自动驳回回上一版",
    }
