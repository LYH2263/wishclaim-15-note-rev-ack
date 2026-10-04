from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect
from app.engines.claim_lock import claim_allowed, lock_payload, release_if_expired
from app.engines.ack_gate import (
    ack_allowed,
    edit_mode,
    fulfill_blocked,
    pending_deadline,
    pending_timed_out,
)
from app.modules.note_revision import apply_ack, apply_open_edit, seed_revision, submit_pending, void_pending
from app.modules.note_projection import card, detail

app = FastAPI(title="Wishclaim", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

def now(): return datetime.now(timezone.utc)

def ttl():
    c = connect(); row = c.execute("SELECT value FROM settings WHERE key='ttl_seconds'").fetchone(); c.close()
    return int(row["value"] if row else 86400)

def ack_ttl():
    c = connect(); row = c.execute("SELECT value FROM settings WHERE key='ack_timeout_seconds'").fetchone(); c.close()
    return int(row["value"] if row else 86400)

def sweep(c):
    ts = now()
    for r in c.execute("SELECT * FROM wishes WHERE status='claimed'"):
        rel = release_if_expired(r["status"], r["expires_at"], ts)
        if rel:
            c.execute("UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
                      (rel["status"], None, None, None, r["id"]))
            if r["awaiting_ack"]:
                void_pending(c, r)  # 锁没了，待确认修订一并作废
    # 附言修订超时：自动驳回回上一已确认版
    for r in c.execute("SELECT * FROM wishes WHERE awaiting_ack=1"):
        if pending_timed_out(r["awaiting_ack"], r["pending_expires_at"], ts):
            void_pending(c, r)

@app.get("/api/health")
def health(): return {"ok": True, "project": "wishclaim"}

@app.get("/api/wishes")
def list_wishes():
    c = connect(); sweep(c); c.commit()
    rows = [card(r) for r in c.execute("SELECT * FROM wishes ORDER BY id DESC")]; c.close(); return rows

@app.get("/api/wishes/{wid}")
def get_wish(wid: int):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    out = detail(c, r); c.close(); return out

class WishIn(BaseModel):
    title: str
    note: str = ""

@app.post("/api/wishes")
def create_wish(body: WishIn):
    c = connect()
    cur = c.execute("INSERT INTO wishes(title,note,status,data_quality) VALUES (?,?,?,?)",
                    (body.title, body.note, "open", "clean"))
    wid = cur.lastrowid
    seed_revision(c, wid, body.note, now().isoformat())
    c.commit(); c.close(); return {"id": wid}

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
    p = lock_payload(body.claimer, now(), ttl())
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
    if r["awaiting_ack"]:
        void_pending(c, r)
    c.commit(); c.close(); return {"ok": True, "status": "released"}

@app.post("/api/wishes/{wid}/fulfill")
def fulfill(wid: int):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    if r["status"] != "claimed":
        c.close(); raise HTTPException(400, "need_claim")
    blocked = fulfill_blocked(r["status"], r["awaiting_ack"])
    if blocked:
        c.close(); raise HTTPException(409, blocked)
    c.execute("UPDATE wishes SET status='fulfilled' WHERE id=?", (wid,))
    c.commit(); c.close(); return {"ok": True, "status": "fulfilled"}

class NoteIn(BaseModel):
    note: str

@app.patch("/api/wishes/{wid}/note")
def edit_note(wid: int, body: NoteIn):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    mode = edit_mode(r["status"])
    ts = now()
    if mode["mode"] == "deny":
        c.close(); raise HTTPException(409, mode["reason"])
    if mode["mode"] == "direct":
        rev = apply_open_edit(c, r, body.note, ts.isoformat())
        c.commit(); c.close(); return {"ok": True, "mode": "direct", "rev": rev}
    rev = submit_pending(c, r, body.note, ts.isoformat(), pending_deadline(ts, ack_ttl()))
    c.commit(); c.close(); return {"ok": True, "mode": "pending", "rev": rev}

class AckIn(BaseModel):
    claimer: str = ""

@app.post("/api/wishes/{wid}/ack")
def ack(wid: int, body: AckIn):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    allowed = ack_allowed(r["status"], r["awaiting_ack"], r["claimer"], body.claimer or None)
    if not allowed["ok"]:
        c.close(); raise HTTPException(409, allowed["reason"])
    rev = apply_ack(c, r, now().isoformat())
    c.commit(); c.close(); return {"ok": True, "rev": rev}

@app.get("/api/mine")
def mine(claimer: str):
    c = connect(); sweep(c); c.commit()
    rows = [card(r) for r in c.execute("SELECT * FROM wishes WHERE claimer=?", (claimer,))]; c.close(); return rows

@app.get("/api/done")
def done():
    c = connect()
    rows = [card(r) for r in c.execute("SELECT * FROM wishes WHERE status='fulfilled'")]; c.close(); return rows

@app.get("/api/settings")
def settings():
    c = connect(); rows = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; c.close(); return rows

@app.get("/api/rules")
def rules():
    return {
        "mutex": "同一愿望同时只能被一人认领",
        "ttl": "认领超时未核销则自动释放",
        "fulfill": "核销后状态变为 fulfilled",
        "note_ack": "已认领愿望的附言修改需认领人确认后生效，确认期间不可核销",
        "ack_timeout": "超过 ack_timeout_seconds 未确认的修改自动驳回，正文回退到上一版",
    }
