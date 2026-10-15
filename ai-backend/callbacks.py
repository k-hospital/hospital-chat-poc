"""
상담원 콜백 요청 — 운영시간 외·상담원 부재 시 전화번호를 받아 상담원이 다시 전화한다.

저장: SQLite (config.CALLBACK_DB). 전화번호·희망 시간·요청 내용만 저장하고,
상담원이 '처리 완료'를 누르면 즉시 삭제, 처리하지 않아도 CALLBACK_RETENTION_DAYS가 지나면 자동 삭제.
"""

from __future__ import annotations

import re
import sqlite3
import time

import config as C

_PHONE_RE = re.compile(r"^0\d{1,2}-?\d{3,4}-?\d{4}$")


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(C.CALLBACK_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS callbacks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created REAL NOT NULL,
        phone TEXT NOT NULL,
        preferred_time TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT ''
    )""")
    return con


def valid_phone(phone: str) -> bool:
    return bool(_PHONE_RE.match(phone.strip()))


def purge_old() -> int:
    limit = time.time() - C.CALLBACK_RETENTION_DAYS * 86400
    with _db() as con:
        return con.execute("DELETE FROM callbacks WHERE created < ?", (limit,)).rowcount


def add(phone: str, preferred_time: str, note: str) -> int:
    purge_old()
    with _db() as con:
        cur = con.execute("INSERT INTO callbacks (created, phone, preferred_time, note) VALUES (?, ?, ?, ?)",
                          (time.time(), phone.strip(), preferred_time.strip(), note.strip()))
        return int(cur.lastrowid)


def list_all() -> list[dict]:
    purge_old()
    with _db() as con:
        rows = con.execute("SELECT id, created, phone, preferred_time, note FROM callbacks ORDER BY created").fetchall()
    return [{"id": r[0], "created": r[1], "phone": r[2], "preferred_time": r[3], "note": r[4]} for r in rows]


def done(callback_id: int) -> bool:
    with _db() as con:
        return con.execute("DELETE FROM callbacks WHERE id = ?", (callback_id,)).rowcount > 0
