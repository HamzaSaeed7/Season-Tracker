import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shows.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            current_season INTEGER DEFAULT 1,
            current_episode INTEGER DEFAULT 1,
            last_watched TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watch_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id INTEGER NOT NULL,
            season INTEGER NOT NULL,
            episode INTEGER NOT NULL,
            watched_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (show_id) REFERENCES shows(id)
        )
    """)
    conn.commit()
    conn.close()


def get_all_shows() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM shows ORDER BY last_watched DESC, name ASC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_show_by_name(name: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM shows WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_show(name: str, season: int, episode: int) -> bool:
    """Insert or update a show. Returns True if the tracked episode changed."""
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing = conn.execute(
        "SELECT * FROM shows WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()

    updated = False
    if existing:
        if existing["current_season"] != season or existing["current_episode"] != episode:
            conn.execute(
                "UPDATE shows SET current_season=?, current_episode=?, last_watched=? WHERE id=?",
                (season, episode, now, existing["id"]),
            )
            conn.execute(
                "INSERT INTO watch_history (show_id, season, episode) VALUES (?, ?, ?)",
                (existing["id"], season, episode),
            )
            updated = True
        else:
            conn.execute(
                "UPDATE shows SET last_watched=? WHERE id=?", (now, existing["id"])
            )
    else:
        conn.execute(
            "INSERT INTO shows (name, current_season, current_episode, last_watched) VALUES (?, ?, ?, ?)",
            (name, season, episode, now),
        )
        show_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO watch_history (show_id, season, episode) VALUES (?, ?, ?)",
            (show_id, season, episode),
        )
        updated = True

    conn.commit()
    conn.close()
    return updated


def update_show_manual(show_id: int, name: str, season: int, episode: int):
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE shows SET name=?, current_season=?, current_episode=?, last_watched=? WHERE id=?",
        (name, season, episode, now, show_id),
    )
    conn.execute(
        "INSERT INTO watch_history (show_id, season, episode) VALUES (?, ?, ?)",
        (show_id, season, episode),
    )
    conn.commit()
    conn.close()


def add_show(name: str, season: int, episode: int):
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT OR IGNORE INTO shows (name, current_season, current_episode, last_watched) VALUES (?, ?, ?, ?)",
        (name, season, episode, now),
    )
    conn.commit()
    conn.close()


def delete_show(show_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM watch_history WHERE show_id=?", (show_id,))
    conn.execute("DELETE FROM shows WHERE id=?", (show_id,))
    conn.commit()
    conn.close()


def get_watch_history(show_id: int) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM watch_history WHERE show_id=? ORDER BY watched_at DESC LIMIT 20",
        (show_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
