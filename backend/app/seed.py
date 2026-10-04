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
      wish_id INTEGER NOT NULL,
      rev INTEGER NOT NULL,
      note TEXT NOT NULL,
      state TEXT NOT NULL,
      created_at TEXT NOT NULL,
      acked_at TEXT,
      expires_at TEXT,
      UNIQUE(wish_id, rev)
    );
    """)
    # 幂等迁移：旧库补附言修订相关列
    cols = {r["name"] for r in c.execute("PRAGMA table_info(wishes)")}
    for ddl in (
        "ALTER TABLE wishes ADD COLUMN note_rev INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE wishes ADD COLUMN awaiting_ack INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE wishes ADD COLUMN pending_rev INTEGER",
        "ALTER TABLE wishes ADD COLUMN pending_note TEXT",
        "ALTER TABLE wishes ADD COLUMN pending_at TEXT",
        "ALTER TABLE wishes ADD COLUMN pending_expires_at TEXT",
    ):
        col = ddl.split("COLUMN ", 1)[1].split(" ", 1)[0]
        if col not in cols:
            c.execute(ddl)

    if c.execute("SELECT COUNT(*) c FROM wishes").fetchone()["c"] == 0:
        c.executemany(
            "INSERT INTO wishes(title,note,status,claimer,claimed_at,expires_at,data_quality)"
            " VALUES (?,?,?,?,?,?,?)",
            [
                ("机械键盘", "红轴", "open", None, None, None, "clean"),
                ("围巾", "羊毛", "open", None, None, None, "clean"),
                ("脏愿望-空标题", "", "open", None, None, None, "dirty"),
                ("过期锁样例", "应被TTL释放", "claimed", "ghost", "2020-01-01T00:00:00+00:00",
                 "2020-01-01T01:00:00+00:00", "dirty"),
            ],
        )
        for wid, note in ((1, "红轴"), (2, "羊毛"), (3, ""), (4, "应被TTL释放")):
            c.execute(
                "INSERT INTO note_revisions(wish_id,rev,note,state,created_at) VALUES (?,?,?,'current','2026-01-01T00:00:00+00:00')",
                (wid, 1, note),
            )
        c.execute("INSERT INTO settings(key,value) VALUES ('ttl_seconds','86400')")
        c.execute("INSERT INTO settings(key,value) VALUES ('wall_title','暖粉愿望墙')")
        c.commit()
    else:
        # 旧数据回填：每个愿望补一条 rev=1 current 账本
        for r in c.execute("SELECT id, note FROM wishes w WHERE NOT EXISTS "
                           "(SELECT 1 FROM note_revisions n WHERE n.wish_id=w.id)"):
            c.execute(
                "INSERT OR IGNORE INTO note_revisions(wish_id,rev,note,state,created_at)"
                " VALUES (?,1,?,'current','2026-01-01T00:00:00+00:00')",
                (r["id"], r["note"] or ""),
            )
        c.commit()
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('ack_timeout_seconds','86400')")
    c.commit()
    c.close()
