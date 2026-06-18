import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "valuehunt.db"

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
    salary_currency TEXT DEFAULT 'RUB',
    description TEXT,
    skills_json TEXT,
    work_format TEXT,
    location TEXT,
    experience TEXT,
    parsed_tasks TEXT,
    parsed_requirements TEXT,
    key_words TEXT,
    score REAL,
    category TEXT,
    gate_a_result TEXT,
    gate_b_result TEXT,
    override_applied INTEGER DEFAULT 0,
    risks TEXT,
    cover_letter TEXT,
    resume_archetype TEXT,
    llm_analysis TEXT,
    status TEXT DEFAULT 'new',
    created_at TEXT DEFAULT (datetime('now')),
    responded_at TEXT,
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,
    hh_employer_id TEXT,
    website TEXT,
    hh_rating REAL,
    hh_recommend_pct INTEGER,
    hh_reviews_count INTEGER,
    hh_top_rank TEXT,
    dreamjob_summary TEXT,
    habr_summary TEXT,
    tadviser_profile TEXT,
    revenue TEXT,
    employees INTEGER,
    culture_tags TEXT,
    stack_tags TEXT,
    legal_status TEXT,
    overall_score REAL,
    data_confidence TEXT DEFAULT 'not_found',
    last_updated TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scoring_configs (
    id INTEGER PRIMARY KEY,
    profile_name TEXT,
    criteria TEXT,
    gates TEXT,
    is_active INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY,
    name TEXT,
    archetype TEXT,
    body_template TEXT,
    format_block TEXT,
    salary_block TEXT,
    is_default INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY,
    vacancy_id INTEGER,
    score REAL,
    category TEXT,
    gate_a_result TEXT,
    gate_b_result TEXT,
    override_applied INTEGER DEFAULT 0,
    decision TEXT,
    cover_letter TEXT,
    resume_used TEXT,
    applied_at TEXT,
    response_at TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (vacancy_id) REFERENCES vacancies(id)
);
"""

SCHEMA_MIGRATIONS = [
    "ALTER TABLE vacancies ADD COLUMN salary_currency TEXT DEFAULT 'RUB'",
    "ALTER TABLE vacancies ADD COLUMN work_format TEXT",
    "ALTER TABLE vacancies ADD COLUMN location TEXT",
    "ALTER TABLE vacancies ADD COLUMN experience TEXT",
    "ALTER TABLE vacancies ADD COLUMN parsed_tasks TEXT",
    "ALTER TABLE vacancies ADD COLUMN parsed_requirements TEXT",
    "ALTER TABLE vacancies ADD COLUMN key_words TEXT",
    "ALTER TABLE vacancies ADD COLUMN gate_a_result TEXT",
    "ALTER TABLE vacancies ADD COLUMN gate_b_result TEXT",
    "ALTER TABLE vacancies ADD COLUMN override_applied INTEGER DEFAULT 0",
    "ALTER TABLE vacancies ADD COLUMN risks TEXT",
    "ALTER TABLE vacancies ADD COLUMN cover_letter TEXT",
    "ALTER TABLE vacancies ADD COLUMN resume_archetype TEXT",
]


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
    # Run migrations (ignore errors if column already exists)
    for sql in SCHEMA_MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def save_vacancy(conn: sqlite3.Connection, vacancy: dict) -> int:
    cursor = conn.execute("""
        INSERT OR REPLACE INTO vacancies
            (hh_id, title, company, url, salary_from, salary_to,
             salary_currency, description, skills_json, work_format,
             location, experience, parsed_tasks, parsed_requirements,
             key_words, score, category, gate_a_result, gate_b_result,
             override_applied, risks, cover_letter, resume_archetype,
             llm_analysis, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        vacancy["hh_id"],
        vacancy.get("title"),
        vacancy.get("company"),
        vacancy.get("url"),
        vacancy.get("salary_from"),
        vacancy.get("salary_to"),
        vacancy.get("salary_currency", "RUB"),
        vacancy.get("description"),
        json.dumps(vacancy.get("skills", []), ensure_ascii=False),
        vacancy.get("work_format"),
        vacancy.get("location"),
        vacancy.get("experience"),
        json.dumps(vacancy.get("parsed_tasks", []), ensure_ascii=False),
        json.dumps(vacancy.get("parsed_requirements", []), ensure_ascii=False),
        json.dumps(vacancy.get("key_words", []), ensure_ascii=False),
        vacancy.get("score"),
        vacancy.get("category"),
        json.dumps(vacancy.get("gate_a_result", {}), ensure_ascii=False),
        json.dumps(vacancy.get("gate_b_result", {}), ensure_ascii=False),
        1 if vacancy.get("override_applied") else 0,
        json.dumps(vacancy.get("risks", []), ensure_ascii=False),
        vacancy.get("cover_letter"),
        vacancy.get("resume_archetype"),
        vacancy.get("llm_analysis"),
        vacancy.get("status", "new"),
    ))
    return cursor.lastrowid


def save_company(conn: sqlite3.Connection, company: dict) -> int:
    cursor = conn.execute("""
        INSERT OR REPLACE INTO companies
            (name, hh_employer_id, website, hh_rating, hh_recommend_pct,
             hh_reviews_count, hh_top_rank, dreamjob_summary, habr_summary,
             tadviser_profile, revenue, employees, culture_tags, stack_tags,
             legal_status, overall_score, data_confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company.get("name"),
        company.get("hh_employer_id"),
        company.get("website"),
        company.get("hh_rating"),
        company.get("hh_recommend_pct"),
        company.get("hh_reviews_count"),
        company.get("hh_top_rank"),
        company.get("dreamjob_summary"),
        company.get("habr_summary"),
        company.get("tadviser_profile"),
        company.get("revenue"),
        company.get("employees"),
        json.dumps(company.get("culture_tags", []), ensure_ascii=False),
        json.dumps(company.get("stack_tags", []), ensure_ascii=False),
        company.get("legal_status"),
        company.get("overall_score"),
        company.get("data_confidence", "not_found"),
    ))
    return cursor.lastrowid


def get_company_by_name(conn: sqlite3.Connection, name: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM companies WHERE name = ?", (name,)
    ).fetchone()
    return dict(row) if row else None


def log_decision(conn: sqlite3.Connection, entry: dict):
    conn.execute("""
        INSERT OR REPLACE INTO logs
            (vacancy_id, score, category, gate_a_result, gate_b_result,
             override_applied, decision, cover_letter, resume_used, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        entry.get("vacancy_id"),
        entry.get("score"),
        entry.get("category"),
        json.dumps(entry.get("gate_a_result", {}), ensure_ascii=False),
        json.dumps(entry.get("gate_b_result", {}), ensure_ascii=False),
        1 if entry.get("override_applied") else 0,
        entry.get("decision"),
        entry.get("cover_letter"),
        entry.get("resume_used"),
        entry.get("notes"),
    ))


def get_vacancies_with_company(conn: sqlite3.Connection) -> list:
    rows = conn.execute("""
        SELECT v.*, c.name AS company_name, c.hh_rating, c.data_confidence
        FROM vacancies v
        LEFT JOIN companies c ON v.company = c.name
        ORDER BY v.created_at DESC
        LIMIT 200
    """).fetchall()
    return [dict(r) for r in rows]


DEFAULT_SCORING_CONFIG = {
    "profile_name": "Active Search",
    "gates": {
        "gate_a": {
            "remote": {"pass": ["remote", "hybrid"], "fail": ["office"]},
            "salary": {"min_net": 200000, "min_net_threshold": 250000},
            "location": {"pass": ["msk", "spb", "remote"], "fail_other": True},
        },
        "gate_b": {
            "archetypes": ["01", "03"],
            "match_required": True,
        },
    },
    "groups": {
        "company": {
            "weight": 35,
            "criteria": {
                "employment_type": {"weight": 9},
                "enterprise_scale": {"weight": 8},
                "culture": {"weight": 7},
                "brand_stability": {"weight": 6},
                "values_alignment": {"weight": 5},
            },
        },
        "vacancy": {
            "weight": 35,
            "criteria": {
                "driver_alignment": {"weight": 10},
                "tech_stack": {"weight": 7},
                "benefits": {"weight": 6},
                "career_path": {"weight": 6},
                "training": {"weight": 6},
            },
        },
        "personal_fit": {
            "weight": 30,
            "criteria": {
                "experience_match": {"weight": 9},
                "domain_match": {"weight": 7},
                "geo_compatibility": {"weight": 7},
                "cultural_compatibility": {"weight": 7},
            },
        },
    },
}
