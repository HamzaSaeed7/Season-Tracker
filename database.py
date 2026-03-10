import sqlite3
import os
import sys
from datetime import datetime
from typing import Optional, List, Dict


def _data_dir() -> str:
    """Directory for user data (db). Next to the exe when frozen, else script dir."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


DB_PATH = os.path.join(_data_dir(), "shows.db")


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
            type TEXT NOT NULL DEFAULT 'show',
            current_season INTEGER DEFAULT 1,
            current_episode INTEGER DEFAULT 1,
            watch_time_seconds INTEGER DEFAULT 0,
            rating INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            poster_path TEXT DEFAULT '',
            last_watched TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watch_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id INTEGER NOT NULL,
            season INTEGER,
            episode INTEGER,
            watch_time_seconds INTEGER,
            watched_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (show_id) REFERENCES shows(id)
        )
    """)
    # Safe migration for existing databases
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(shows)").fetchall()}
    for col, ddl in [
        ("type",               "ALTER TABLE shows ADD COLUMN type TEXT NOT NULL DEFAULT 'show'"),
        ("watch_time_seconds", "ALTER TABLE shows ADD COLUMN watch_time_seconds INTEGER DEFAULT 0"),
        ("rating",             "ALTER TABLE shows ADD COLUMN rating INTEGER DEFAULT 0"),
        ("description",        "ALTER TABLE shows ADD COLUMN description TEXT DEFAULT ''"),
        ("poster_path",        "ALTER TABLE shows ADD COLUMN poster_path TEXT DEFAULT ''"),
        ("status",             "ALTER TABLE shows ADD COLUMN status TEXT DEFAULT 'watching'"),
    ]:
        if col not in existing_cols:
            conn.execute(ddl)
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
    """Auto-called by VLC monitor for TV episodes. Returns True if episode changed."""
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
            updated = True
        else:
            conn.execute(
                "UPDATE shows SET last_watched=? WHERE id=?", (now, existing["id"])
            )
    else:
        conn.execute(
            "INSERT INTO shows (name, type, current_season, current_episode, last_watched)"
            " VALUES (?, 'show', ?, ?, ?)",
            (name, season, episode, now),
        )
        updated = True
    conn.commit()
    conn.close()
    return updated


def upsert_movie(title: str, position_seconds: int) -> bool:
    """Auto-called by VLC monitor for movies. Returns True if newly added."""
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing = conn.execute(
        "SELECT * FROM shows WHERE LOWER(name) = LOWER(?)", (title,)
    ).fetchone()
    is_new = False
    if existing:
        if existing["type"] == "movie":
            conn.execute(
                "UPDATE shows SET watch_time_seconds=?, last_watched=? WHERE id=?",
                (position_seconds, now, existing["id"]),
            )
        # If tracked as a TV show, don't override it
    else:
        conn.execute(
            "INSERT INTO shows (name, type, watch_time_seconds, last_watched)"
            " VALUES (?, 'movie', ?, ?)",
            (title, position_seconds, now),
        )
        is_new = True
    conn.commit()
    conn.close()
    return is_new


def add_entry(name: str, entry_type: str, season: int = 1, episode: int = 1,
              watch_time_seconds: int = 0, rating: int = 0,
              description: str = "", poster_path: str = "", status: str = "watching"):
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT OR IGNORE INTO shows"
        " (name, type, current_season, current_episode, watch_time_seconds,"
        "  rating, description, poster_path, status, last_watched)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, entry_type, season, episode, watch_time_seconds,
         rating, description, poster_path, status, now),
    )
    conn.commit()
    conn.close()


def update_entry(show_id: int, name: str, entry_type: str, season: int,
                 episode: int, watch_time_seconds: int,
                 rating: int = 0, description: str = "", poster_path: str = "",
                 status: str = "watching"):
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE shows SET name=?, type=?, current_season=?, current_episode=?,"
        " watch_time_seconds=?, rating=?, description=?, poster_path=?, status=?,"
        " last_watched=? WHERE id=?",
        (name, entry_type, season, episode, watch_time_seconds,
         rating, description, poster_path, status, now, show_id),
    )
    conn.commit()
    conn.close()


def update_show_progress(show_id: int, season: int, episode: int):
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE shows SET current_season=?, current_episode=?, last_watched=? WHERE id=?",
        (season, episode, now, show_id),
    )
    conn.commit()
    conn.close()


def update_movie_progress(show_id: int, watch_time_seconds: int):
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE shows SET watch_time_seconds=?, last_watched=? WHERE id=?",
        (watch_time_seconds, now, show_id),
    )
    conn.commit()
    conn.close()


def delete_show(show_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM watch_history WHERE show_id=?", (show_id,))
    conn.execute("DELETE FROM shows WHERE id=?", (show_id,))
    conn.commit()
    conn.close()
