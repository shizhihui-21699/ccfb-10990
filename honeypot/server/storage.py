"""SQLite 存储:所有会话、认证尝试、事件按时间落盘。

低交互蜜罐流量很小,直接用同步 sqlite3 + 一把锁即可,
所有 SQL 全部参数化(事件内容来自攻击者,绝不拼接)。
"""
import json
import os
import sqlite3
import threading
import time

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    protocol   TEXT NOT NULL,              -- 'ssh' | 'http'
    src_ip     TEXT NOT NULL,
    src_port   INTEGER,
    dst_port   INTEGER,
    start_ts   REAL NOT NULL,              -- epoch 秒
    end_ts     REAL,
    meta       TEXT NOT NULL DEFAULT '{}'  -- JSON: 客户端版本/UA 等
);
CREATE TABLE IF NOT EXISTS auth_attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    ts         REAL NOT NULL,
    username   TEXT,
    password   TEXT,
    success    INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    t_ms       INTEGER NOT NULL,           -- 相对会话开始的毫秒偏移,回放用
    type       TEXT NOT NULL,              -- 'in' | 'out' | 'http'
    data       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, t_ms);
CREATE INDEX IF NOT EXISTS idx_auth_session  ON auth_attempts(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_ip   ON sessions(src_ip);
CREATE INDEX IF NOT EXISTS idx_sessions_ts   ON sessions(start_ts);
"""


class Storage:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # ---------- 写入 ----------

    def open_session(self, protocol: str, src_ip: str, src_port: int,
                     dst_port: int, meta: dict | None = None) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO sessions(protocol, src_ip, src_port, dst_port, start_ts, meta)"
                " VALUES (?,?,?,?,?,?)",
                (protocol, src_ip, src_port, dst_port, time.time(),
                 json.dumps(meta or {}, ensure_ascii=False)))
            self._db.commit()
            return cur.lastrowid

    def close_session(self, session_id: int):
        with self._lock:
            self._db.execute("UPDATE sessions SET end_ts=? WHERE id=?",
                             (time.time(), session_id))
            self._db.commit()

    def log_auth(self, session_id: int, username: str, password: str, success: bool):
        with self._lock:
            self._db.execute(
                "INSERT INTO auth_attempts(session_id, ts, username, password, success)"
                " VALUES (?,?,?,?,?)",
                (session_id, time.time(), username, password, int(success)))
            self._db.commit()

    def log_event(self, session_id: int, session_start: float, etype: str, data: str):
        t_ms = int((time.time() - session_start) * 1000)
        with self._lock:
            self._db.execute(
                "INSERT INTO events(session_id, t_ms, type, data) VALUES (?,?,?,?)",
                (session_id, t_ms, etype, data))
            self._db.commit()

    # ---------- 查询(给 API 用) ----------

    def list_sessions(self, limit: int = 200, offset: int = 0) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT s.*,
                          (SELECT COUNT(*) FROM events e WHERE e.session_id = s.id) AS event_count,
                          (SELECT COUNT(*) FROM auth_attempts a WHERE a.session_id = s.id) AS auth_count
                   FROM sessions s ORDER BY s.id DESC LIMIT ? OFFSET ?""",
                (limit, offset)).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: int) -> dict | None:
        with self._lock:
            s = self._db.execute("SELECT * FROM sessions WHERE id=?",
                                 (session_id,)).fetchone()
            if not s:
                return None
            events = self._db.execute(
                "SELECT t_ms, type, data FROM events WHERE session_id=? ORDER BY t_ms, id",
                (session_id,)).fetchall()
            auths = self._db.execute(
                "SELECT ts, username, password, success FROM auth_attempts"
                " WHERE session_id=? ORDER BY ts", (session_id,)).fetchall()
        return {
            "session": dict(s),
            "events": [dict(e) for e in events],
            "auth_attempts": [dict(a) for a in auths],
        }

    def stats(self) -> dict:
        with self._lock:
            q = lambda sql: [dict(r) for r in self._db.execute(sql).fetchall()]
            one = lambda sql: self._db.execute(sql).fetchone()[0]
            return {
                "totals": {
                    "sessions": one("SELECT COUNT(*) FROM sessions"),
                    "ssh_sessions": one("SELECT COUNT(*) FROM sessions WHERE protocol='ssh'"),
                    "http_sessions": one("SELECT COUNT(*) FROM sessions WHERE protocol='http'"),
                    "auth_attempts": one("SELECT COUNT(*) FROM auth_attempts"),
                    "unique_ips": one("SELECT COUNT(DISTINCT src_ip) FROM sessions"),
                },
                "top_ips": q("SELECT src_ip AS ip, COUNT(*) AS n, "
                             "SUM(protocol='ssh') AS ssh, SUM(protocol='http') AS http "
                             "FROM sessions GROUP BY src_ip ORDER BY n DESC LIMIT 20"),
                "top_passwords": q("SELECT password, COUNT(*) AS n FROM auth_attempts "
                                   "WHERE password IS NOT NULL AND password != '' "
                                   "GROUP BY password ORDER BY n DESC LIMIT 20"),
                "top_usernames": q("SELECT username, COUNT(*) AS n FROM auth_attempts "
                                   "WHERE username IS NOT NULL AND username != '' "
                                   "GROUP BY username ORDER BY n DESC LIMIT 20"),
                "top_http_paths": q(
                    "SELECT json_extract(e.data, '$.path') AS path, COUNT(*) AS n "
                    "FROM events e WHERE e.type='http' "
                    "GROUP BY path ORDER BY n DESC LIMIT 20"),
            }
