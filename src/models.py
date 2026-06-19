import sqlite3
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "valuehunt.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            industry    TEXT,
            website     TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS applications (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id      INTEGER REFERENCES companies(id),
            company_name    TEXT NOT NULL,
            position        TEXT NOT NULL,
            industry        TEXT,
            source          TEXT DEFAULT 'hh',
            url             TEXT,
            status          TEXT NOT NULL DEFAULT 'viewed'
                            CHECK(status IN ('viewed','invited','interview','offer','rejected','accepted')),
            score           REAL CHECK(score IS NULL OR (score >= 0 AND score <= 10)),
            applied_at      TEXT NOT NULL,
            notes           TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS activities (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id  INTEGER NOT NULL REFERENCES applications(id),
            activity_type   TEXT NOT NULL CHECK(activity_type IN ('view','invite','interview','offer','reject','accept','note')),
            activity_date   TEXT NOT NULL,
            description     TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
        CREATE INDEX IF NOT EXISTS idx_applications_applied ON applications(applied_at);
        CREATE INDEX IF NOT EXISTS idx_applications_score ON applications(score);
    """)
    conn.commit()
    conn.close()
