from datetime import datetime, timedelta, timezone

from app.db import connect


def init_db():
    c = connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS wishes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, note TEXT, status TEXT,
      claimer TEXT, claimed_at TEXT, expires_at TEXT, data_quality TEXT
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS note_revisions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      wish_id INTEGER NOT NULL, rev INTEGER NOT NULL, body TEXT NOT NULL,
      state TEXT NOT NULL, created_at TEXT, decided_at TEXT
    );
    """)
    _migrate_wish_columns(c)
    if c.execute("SELECT COUNT(*) c FROM wishes").fetchone()["c"] == 0:
        _seed(c)
    _backfill_revisions(c)
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('ack_timeout_seconds','86400')")
    c.commit()
    c.close()


def _migrate_wish_columns(c):
    """Existing DBs gain the note-ack columns; fresh CREATEs get them here too."""
    cols = {r["name"] for r in c.execute("PRAGMA table_info(wishes)")}
    if "note_rev" not in cols:
        c.execute("ALTER TABLE wishes ADD COLUMN note_rev INTEGER NOT NULL DEFAULT 1")
    if "note_state" not in cols:
        c.execute("ALTER TABLE wishes ADD COLUMN note_state TEXT NOT NULL DEFAULT 'none'")
    if "pending_since" not in cols:
        c.execute("ALTER TABLE wishes ADD COLUMN pending_since TEXT")


def _backfill_revisions(c):
    """Every wish without any revision gets its current note as rev 1 (live)."""
    c.execute("""
      INSERT INTO note_revisions(wish_id,rev,body,state,created_at)
      SELECT w.id, 1, COALESCE(w.note,''), 'live',
             COALESCE(w.claimed_at,'2026-01-01T00:00:00+00:00')
      FROM wishes w
      WHERE NOT EXISTS(SELECT 1 FROM note_revisions r WHERE r.wish_id=w.id)
    """)


def _seed(c):
    now = datetime.now(timezone.utc)
    c.executemany(
        "INSERT INTO wishes(title,note,status,claimer,claimed_at,expires_at,data_quality) VALUES (?,?,?,?,?,?,?)",
        [
            ("机械键盘", "红轴", "open", None, None, None, "clean"),
            ("围巾", "羊毛", "open", None, None, None, "clean"),
            ("脏愿望-空标题", "", "open", None, None, None, "dirty"),
            ("过期锁样例", "应被TTL释放", "claimed", "ghost", "2020-01-01T00:00:00+00:00",
             "2020-01-01T01:00:00+00:00", "dirty"),
        ],
    )
    # demo: claimed wish whose note edit awaits claimer ack (rev 2 pending)
    cur = c.execute(
        "INSERT INTO wishes(title,note,status,claimer,claimed_at,expires_at,data_quality,"
        "note_rev,note_state,pending_since) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("拍立得", "改：粉色也可以", "claimed", "alice", now.isoformat(),
         (now + timedelta(days=1)).isoformat(), "clean", 2, "awaiting_ack", now.isoformat()),
    )
    wid = cur.lastrowid
    c.executemany(
        "INSERT INTO note_revisions(wish_id,rev,body,state,created_at) VALUES (?,?,?,?,?)",
        [
            (wid, 1, "想要白色款", "live", now.isoformat()),
            (wid, 2, "改：粉色也可以", "pending", now.isoformat()),
        ],
    )
    c.execute("INSERT INTO settings(key,value) VALUES ('ttl_seconds','86400')")
    c.execute("INSERT INTO settings(key,value) VALUES ('wall_title','暖粉愿望墙')")
