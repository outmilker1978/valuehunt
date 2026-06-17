import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobmatch.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY,
    hh_resume_id TEXT,
    telegram_chat_id TEXT,
    auto_respond_below_score REAL DEFAULT 6.9,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS matrix (
    id INTEGER PRIMARY KEY,
    groups_json TEXT,
    version INTEGER,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY,
    hh_id TEXT UNIQUE,
    title TEXT,
    company TEXT,
    url TEXT,
    salary_from INTEGER,
    salary_to INTEGER,
    description TEXT,
    skills_json TEXT,
    score REAL,
    category TEXT,
    llm_analysis TEXT,
    status TEXT DEFAULT 'new',
    created_at TEXT DEFAULT (datetime('now')),
    responded_at TEXT,
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY,
    vacancy_id INTEGER,
    name TEXT,
    role TEXT,
    phone TEXT,
    telegram TEXT,
    linkedin TEXT,
    notes TEXT,
    FOREIGN KEY (vacancy_id) REFERENCES vacancies(id)
);

CREATE TABLE IF NOT EXISTS communications (
    id INTEGER PRIMARY KEY,
    vacancy_id INTEGER,
    contact_id INTEGER,
    type TEXT,
    direction TEXT,
    content TEXT,
    reminder_date TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (vacancy_id) REFERENCES vacancies(id),
    FOREIGN KEY (contact_id) REFERENCES contacts(id)
);

CREATE TABLE IF NOT EXISTS analytics (
    id INTEGER PRIMARY KEY,
    date TEXT UNIQUE,
    new_vacancies INTEGER DEFAULT 0,
    auto_responses INTEGER DEFAULT 0,
    manual_responses INTEGER DEFAULT 0,
    invitations INTEGER DEFAULT 0,
    interviews INTEGER DEFAULT 0,
    offers INTEGER DEFAULT 0,
    rejections INTEGER DEFAULT 0,
    recommendations TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


def save_vacancy(conn: sqlite3.Connection, vacancy: dict) -> int:
    cursor = conn.execute("""
        INSERT OR REPLACE INTO vacancies
            (hh_id, title, company, url, salary_from, salary_to,
             description, skills_json, score, category, llm_analysis, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        vacancy["hh_id"],
        vacancy.get("title"),
        vacancy.get("company"),
        vacancy.get("url"),
        vacancy.get("salary_from"),
        vacancy.get("salary_to"),
        vacancy.get("description"),
        json.dumps(vacancy.get("skills", []), ensure_ascii=False),
        vacancy.get("score"),
        vacancy.get("category"),
        vacancy.get("llm_analysis"),
        vacancy.get("status", "new"),
    ))
    return cursor.lastrowid


def get_vacancies_by_status(conn: sqlite3.Connection, status: str) -> list:
    cursor = conn.execute(
        "SELECT * FROM vacancies WHERE status = ? ORDER BY created_at DESC",
        (status,)
    )
    return [dict(row) for row in cursor.fetchall()]
