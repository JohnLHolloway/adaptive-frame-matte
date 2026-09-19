"""Small transactional SQLite document store; all values remain local."""

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path


def now():
    return datetime.now(UTC).isoformat()


class Persistence:
    def __init__(self, directory: Path):
        self.directory = directory
        self.lock = threading.RLock()
        directory.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(directory / "frame.sqlite3", check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS records (
          category TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
          PRIMARY KEY(category,key));
        CREATE TABLE IF NOT EXISTS history (
          id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, value TEXT NOT NULL);
        PRAGMA user_version=1;
        """)

    def get(self, category, key, default=None):
        with self.lock:
            row = self.connection.execute(
                "SELECT value FROM records WHERE category=? AND key=?", (category, key)
            ).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, category, key, value):
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO records VALUES(?,?,?) ON CONFLICT(category,key) "
                "DO UPDATE SET value=excluded.value",
                (category, key, json.dumps(value)),
            )

    def all(self, category):
        with self.lock:
            return {
                k: json.loads(v)
                for k, v in self.connection.execute(
                    "SELECT key,value FROM records WHERE category=?", (category,)
                )
            }

    def history(self, value=None):
        if value is not None:
            with self.lock, self.connection:
                self.connection.execute(
                    "INSERT INTO history(timestamp,value) VALUES(?,?)", (now(), json.dumps(value))
                )
        with self.lock:
            return [
                {"timestamp": t, **json.loads(v)}
                for t, v in self.connection.execute(
                    "SELECT timestamp,value FROM history ORDER BY id DESC LIMIT 250"
                )
            ]

    def artwork_page(self, query, behavior, page, size):
        # Filter/count in SQLite; dashboard payloads never contain the full library.
        join = "FROM records a LEFT JOIN records o ON o.category='overrides' AND o.key=a.key "
        where = "WHERE a.category='artwork' AND instr(lower(a.key), lower(?)) > 0 "
        params = [query]
        if behavior != "all":
            where += "AND coalesce(json_extract(o.value, '$.mode'),'automatic')=? "
            params.append(behavior)
        with self.lock:
            total = self.connection.execute("SELECT count(*) " + join + where, params).fetchone()[0]
            pages = max(1, (total + size - 1) // size)
            page = min(page, pages)
            rows = self.connection.execute(
                "SELECT a.value,o.value "
                + join
                + where
                + "ORDER BY json_extract(a.value,'$.last_seen') DESC,a.key LIMIT ? OFFSET ?",
                [*params, size, (page - 1) * size],
            ).fetchall()
        return {
            "items": [
                {**json.loads(a), "override": json.loads(o) if o else {"mode": "automatic"}}
                for a, o in rows
            ],
            "total": total,
            "page": page,
            "pages": pages,
            "size": size,
        }

    def close(self):
        self.connection.close()
