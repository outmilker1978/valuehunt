import sqlite3
import json
import sys
from datetime import date, timedelta
from pathlib import Path

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "data" / "valuehunt.db"

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
    published_at TEXT,
    hr_contacts TEXT,
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
    status TEXT DEFAULT 'new'
        CHECK(status IN ('new','applied','invited','in_progress','offer','rejected','archived','closed','trash')),
    llm_generated INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    responded_at TEXT,
    archived_at TEXT,
    deleted_at TEXT,
    delete_reason TEXT
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
    address TEXT,
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

CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    hh_resume_id TEXT,
    resume_name TEXT,
    resume_data TEXT,
    search_filters TEXT,
    matrix_data TEXT,
    archetype TEXT DEFAULT '01',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vacancy_profiles (
    vacancy_id INTEGER NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    PRIMARY KEY (vacancy_id, profile_id)
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    role TEXT,
    source TEXT NOT NULL DEFAULT 'other',
    priority TEXT DEFAULT 'B'
        CHECK(priority IN ('S','A','B','C')),
    telegram TEXT,
    email TEXT,
    phone TEXT,
    vk TEXT,
    linkedin TEXT,
    extra_contacts TEXT,
    extra_phones TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);
CREATE INDEX IF NOT EXISTS idx_contacts_priority ON contacts(priority);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    vacancy_id INTEGER REFERENCES vacancies(id) ON DELETE SET NULL,
    type TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('outbound','inbound')),
    summary TEXT,
    outcome TEXT CHECK(outcome IN ('pending','working','on_hold','positive','negative')),
    next_action_date TEXT,
    next_action_time TEXT,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_interactions_contact ON interactions(contact_id);
CREATE INDEX IF NOT EXISTS idx_interactions_vacancy ON interactions(vacancy_id);
CREATE INDEX IF NOT EXISTS idx_interactions_next_action ON interactions(next_action_date);
"""

SCHEMA_MIGRATIONS = [
    "ALTER TABLE vacancies ADD COLUMN salary_currency TEXT DEFAULT 'RUB'",
    "ALTER TABLE vacancies ADD COLUMN work_format TEXT",
    "ALTER TABLE vacancies ADD COLUMN location TEXT",
    "ALTER TABLE vacancies ADD COLUMN experience TEXT",
    "ALTER TABLE vacancies ADD COLUMN published_at TEXT",
    "ALTER TABLE vacancies ADD COLUMN hr_contacts TEXT",
    "ALTER TABLE vacancies ADD COLUMN parsed_tasks TEXT",
    "ALTER TABLE vacancies ADD COLUMN parsed_requirements TEXT",
    "ALTER TABLE vacancies ADD COLUMN key_words TEXT",
    "ALTER TABLE vacancies ADD COLUMN gate_a_result TEXT",
    "ALTER TABLE vacancies ADD COLUMN gate_b_result TEXT",
    "ALTER TABLE vacancies ADD COLUMN override_applied INTEGER DEFAULT 0",
    "ALTER TABLE vacancies ADD COLUMN risks TEXT",
    "ALTER TABLE vacancies ADD COLUMN cover_letter TEXT",
    "ALTER TABLE vacancies ADD COLUMN resume_archetype TEXT",
    "ALTER TABLE vacancies ADD COLUMN llm_generated INTEGER DEFAULT 0",
    "ALTER TABLE vacancies ADD COLUMN notes TEXT",
    "ALTER TABLE contacts ADD COLUMN extra_contacts TEXT",
    "ALTER TABLE contacts ADD COLUMN extra_phones TEXT",
    "ALTER TABLE companies ADD COLUMN address TEXT",
    "ALTER TABLE profiles ADD COLUMN archetype TEXT DEFAULT '01'",
    "ALTER TABLE profiles ADD COLUMN keywords_config TEXT",
    "ALTER TABLE interactions ADD COLUMN next_action_time TEXT",
    # v2.1: Normalize vacancies.company → company_id
    "ALTER TABLE vacancies ADD COLUMN company_id INTEGER REFERENCES companies(id)",
    # v2.2: Interaction completed_at for marking actions done
    "ALTER TABLE interactions ADD COLUMN completed_at TEXT",
    # v2.3: Migrate old vacancy statuses to new simplified set
    "UPDATE vacancies SET status = 'new' WHERE status IN ('follow_up', 'call', 'hh_found')",
    # v2.4: Rename interaction type 'applied' → 'communication'
    "UPDATE interactions SET type = 'communication' WHERE type = 'applied'",
]

# Complex migrations that need multiple statements
COMPLEX_MIGRATIONS = [
    # v2.0: Remove CHECK constraint from interactions.type to allow new funnel types
    """CREATE TABLE IF NOT EXISTS interactions_v2 (
        id INTEGER PRIMARY KEY,
        contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
        vacancy_id INTEGER REFERENCES vacancies(id) ON DELETE SET NULL,
        type TEXT NOT NULL,
        direction TEXT NOT NULL CHECK(direction IN ('outbound','inbound')),
        summary TEXT,
        outcome TEXT CHECK(outcome IN ('pending','working','on_hold','positive','negative')),
        next_action_date TEXT,
        next_action_time TEXT,
        completed_at TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
]


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
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
    # Complex migration: recreate interactions table without CHECK constraint on type
    try:
        conn.execute("SELECT COUNT(*) FROM interactions_v2")
    except sqlite3.OperationalError:
        # interactions_v2 doesn't exist, table still has old CHECK constraint
        conn.executescript("""
            CREATE TABLE interactions_v2 (
                id INTEGER PRIMARY KEY,
                contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
                vacancy_id INTEGER REFERENCES vacancies(id) ON DELETE SET NULL,
                type TEXT NOT NULL,
                direction TEXT NOT NULL CHECK(direction IN ('outbound','inbound')),
                summary TEXT,
                outcome TEXT CHECK(outcome IN ('pending','working','on_hold','positive','negative')),
                next_action_date TEXT,
                next_action_time TEXT,
                completed_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            INSERT INTO interactions_v2 (id,contact_id,vacancy_id,type,direction,summary,outcome,next_action_date,next_action_time,completed_at,created_at)
                SELECT id,contact_id,vacancy_id,type,direction,summary,outcome,next_action_date,next_action_time,completed_at,created_at FROM interactions;
            DROP TABLE interactions;
            ALTER TABLE interactions_v2 RENAME TO interactions;
            CREATE INDEX IF NOT EXISTS idx_interactions_contact ON interactions(contact_id);
            CREATE INDEX IF NOT EXISTS idx_interactions_vacancy ON interactions(vacancy_id);
            CREATE INDEX IF NOT EXISTS idx_interactions_next_action ON interactions(next_action_date);
        """)
    conn.commit()
    # Status CHECK trigger for existing rows (new tables get it from CREATE TABLE)
    try:
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_vacancies_status_check
            BEFORE INSERT ON vacancies
            BEGIN
                SELECT CASE
                    WHEN NEW.status NOT IN ('new','applied','invited','in_progress','offer','rejected','archived','closed')
                    THEN RAISE(ABORT, 'Invalid vacancy status: ' || NEW.status)
                END;
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_vacancies_status_update
            BEFORE UPDATE OF status ON vacancies
            BEGIN
                SELECT CASE
                    WHEN NEW.status NOT IN ('new','applied','invited','in_progress','offer','rejected','archived','closed')
                    THEN RAISE(ABORT, 'Invalid vacancy status: ' || NEW.status)
                END;
            END;
        """)
        conn.commit()
    except sqlite3.OperationalError:
        pass
    # Migration: drop source CHECK constraint on contacts
    try:
        conn.executescript("""
            PRAGMA foreign_keys=OFF;
            CREATE TABLE IF NOT EXISTS contacts_new (
                id INTEGER PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
                name TEXT NOT NULL,
                role TEXT,
                source TEXT NOT NULL DEFAULT 'other',
                priority TEXT DEFAULT 'B'
                    CHECK(priority IN ('S','A','B','C')),
                telegram TEXT,
                email TEXT,
                phone TEXT,
                vk TEXT,
                linkedin TEXT,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            INSERT INTO contacts_new SELECT * FROM contacts;
            DROP TABLE contacts;
            ALTER TABLE contacts_new RENAME TO contacts;
            PRAGMA foreign_keys=ON;
        """)
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    # Data migration: link existing vacancies to companies
    _migrate_vacancy_company_ids(conn)
    conn.close()


def _migrate_vacancy_company_ids(conn: sqlite3.Connection):
    """Match existing vacancies.company text to companies.id and set company_id."""
    rows = conn.execute(
        "SELECT id, company FROM vacancies WHERE company IS NOT NULL AND company != '' AND company_id IS NULL AND deleted_at IS NULL"
    ).fetchall()
    for row in rows:
        vid, company_name = row["id"], row["company"]
        # Try exact match first
        c = conn.execute("SELECT id FROM companies WHERE name = ?", (company_name,)).fetchone()
        if c:
            conn.execute("UPDATE vacancies SET company_id = ? WHERE id = ?", (c["id"], vid))
            continue
        # Try case-insensitive match
        c = conn.execute("SELECT id FROM companies WHERE LOWER(name) = LOWER(?)", (company_name,)).fetchone()
        if c:
            conn.execute("UPDATE vacancies SET company_id = ? WHERE id = ?", (c["id"], vid))
            continue
        # Try normalized match (strip common prefixes)
        normalized = _normalize_company_name(company_name)
        c = conn.execute("SELECT id FROM companies WHERE LOWER(name) = LOWER(?)", (normalized,)).fetchone()
        if c:
            conn.execute("UPDATE vacancies SET company_id = ? WHERE id = ?", (c["id"], vid))
            continue
        # Try matching stored hh_employer_id — vacancies don't have it, skip
        # No match found: create new company
        c = conn.execute("INSERT OR IGNORE INTO companies (name) VALUES (?)", (company_name,))
        if c.lastrowid:
            conn.execute("UPDATE vacancies SET company_id = ? WHERE id = ?", (c.lastrowid, vid))
        else:
            # Name already exists (race/ignore) — fetch again
            c2 = conn.execute("SELECT id FROM companies WHERE name = ?", (company_name,)).fetchone()
            if c2:
                conn.execute("UPDATE vacancies SET company_id = ? WHERE id = ?", (c2["id"], vid))
    conn.commit()


def _normalize_company_name(name: str) -> str:
    """Strip common legal prefixes and parenthesized suffixes for fuzzy matching."""
    import re
    n = name.strip()
    # Remove legal form prefixes (with or without space after)
    n = re.sub(r'^(?:ООО|АО|ЗАО|ОАО|ПАО|ИП|НКО|ЧУ)\s*', '', n, count=1).strip()
    # Remove quotes
    n = re.sub(r'^\s*"|"\s*$', '', n).strip()
    # Remove parenthesized suffixes: (ООО ...), (ЗАО ...), etc.
    n = re.sub(r'\s*\((?:ООО|АО|ЗАО|ОАО|ПАО|ИП|НКО|ЧУ)[^)]*\)\s*$', '', n).strip()
    return n


def save_vacancy(conn: sqlite3.Connection, vacancy: dict) -> dict:
    """Returns {'inserted': bool, 'id': int}.
    Automatically resolves company text to company_id."""
    # Resolve company_name → company_id
    company_name = vacancy.get("company")
    company_id = vacancy.get("company_id")
    if company_name and not company_id:
        company_id = _resolve_company_id(conn, company_name)
    elif not company_id and not company_name:
        company_id = None

    hh_id = vacancy.get("hh_id")
    if not hh_id:
        # Manual vacancy — simple insert, no dedup by hh_id
        cursor = conn.execute("""
            INSERT INTO vacancies
                (hh_id, title, company, company_id, url, salary_from, salary_to,
                 salary_currency, description, skills_json, work_format,
                 location, experience, published_at, hr_contacts,
                 parsed_tasks, parsed_requirements,
                 key_words, score, category, gate_a_result, gate_b_result,
                 override_applied, risks, cover_letter, resume_archetype,
                 llm_analysis, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            None,
            vacancy.get("title"),
            company_name,
            company_id,
            vacancy.get("url"),
            vacancy.get("salary_from"),
            vacancy.get("salary_to"),
            vacancy.get("salary_currency", "RUB"),
            vacancy.get("description"),
            json.dumps(vacancy.get("skills", []), ensure_ascii=False),
            vacancy.get("work_format"),
            vacancy.get("location"),
            vacancy.get("experience"),
            vacancy.get("published_at"),
            vacancy.get("hr_contacts"),
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
        return {"inserted": True, "id": cursor.lastrowid}

    cursor = conn.execute("""
        INSERT OR IGNORE INTO vacancies
            (hh_id, title, company, company_id, url, salary_from, salary_to,
             salary_currency, description, skills_json, work_format,
             location, experience, published_at, hr_contacts,
             parsed_tasks, parsed_requirements,
             key_words, score, category, gate_a_result, gate_b_result,
             override_applied, risks, cover_letter, resume_archetype,
             llm_analysis, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        hh_id,
        vacancy.get("title"),
        company_name,
        company_id,
        vacancy.get("url"),
        vacancy.get("salary_from"),
        vacancy.get("salary_to"),
        vacancy.get("salary_currency", "RUB"),
        vacancy.get("description"),
        json.dumps(vacancy.get("skills", []), ensure_ascii=False),
        vacancy.get("work_format"),
        vacancy.get("location"),
        vacancy.get("experience"),
        vacancy.get("published_at"),
        vacancy.get("hr_contacts"),
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
    inserted = cursor.lastrowid is not None and cursor.lastrowid > 0
    if not inserted:
        cursor2 = conn.execute("SELECT id, company_id, deleted_at FROM vacancies WHERE hh_id = ?", (hh_id,))
        row = cursor2.fetchone()
        vid = row["id"] if row else None
        if vid:
            # Update company_id if missing
            if company_id and not row["company_id"]:
                conn.execute("UPDATE vacancies SET company_id = ? WHERE id = ?", (company_id, vid))
            # Previously deleted — update fields but keep deleted (don't restore)
            if row["deleted_at"]:
                conn.execute("""
                    UPDATE vacancies SET
                        title = ?, url = ?, salary_from = ?, salary_to = ?,
                        description = ?, skills_json = ?, work_format = ?,
                        location = ?, experience = ?, published_at = ?,
                        hr_contacts = ?, parsed_tasks = ?, parsed_requirements = ?,
                        key_words = ?, score = ?, category = ?,
                        gate_a_result = ?, gate_b_result = ?, override_applied = ?,
                        risks = ?, llm_analysis = ?
                    WHERE id = ?
                """, (
                    vacancy.get("title"), vacancy.get("url"),
                    vacancy.get("salary_from"), vacancy.get("salary_to"),
                    vacancy.get("description"),
                    json.dumps(vacancy.get("skills", []), ensure_ascii=False),
                    vacancy.get("work_format"), vacancy.get("location"),
                    vacancy.get("experience"), vacancy.get("published_at"),
                    vacancy.get("hr_contacts"),
                    json.dumps(vacancy.get("parsed_tasks", []), ensure_ascii=False),
                    json.dumps(vacancy.get("parsed_requirements", []), ensure_ascii=False),
                    json.dumps(vacancy.get("key_words", []), ensure_ascii=False),
                    vacancy.get("score"), vacancy.get("category"),
                    json.dumps(vacancy.get("gate_a_result", {}), ensure_ascii=False),
                    json.dumps(vacancy.get("gate_b_result", {}), ensure_ascii=False),
                    1 if vacancy.get("override_applied") else 0,
                    json.dumps(vacancy.get("risks", []), ensure_ascii=False),
                    vacancy.get("llm_analysis"),
                    vid,
                ))
                # NOT inserted — deleted stays, status unchanged
    else:
        vid = cursor.lastrowid
    return {"inserted": inserted, "id": vid}


def _resolve_company_id(conn: sqlite3.Connection, company_name: str) -> int | None:
    """Find or create a company by name, return its id."""
    if not company_name:
        return None
    import re
    # Exact match
    c = conn.execute("SELECT id FROM companies WHERE name = ?", (company_name,)).fetchone()
    if c:
        return c["id"]
    # Case-insensitive
    c = conn.execute("SELECT id FROM companies WHERE LOWER(name) = LOWER(?)", (company_name,)).fetchone()
    if c:
        return c["id"]
    # Normalized (incoming vs all stored)
    normalized = _normalize_company_name(company_name)
    if normalized:
        for try_name in (normalized,):
            c = conn.execute("SELECT id FROM companies WHERE LOWER(name) = LOWER(?)", (try_name,)).fetchone()
            if c:
                return c["id"]
    # Token-based fuzzy: match by significant words
    words = [w.strip().lower() for w in re.split(r'[\s\(\)"\-]+', company_name) if len(w.strip()) > 2]
    if words:
        all_rows = conn.execute("SELECT id, name FROM companies").fetchall()
        scored = []
        for r in all_rows:
            cn_lower = r["name"].lower()
            match_cnt = sum(1 for w in words if w in cn_lower)
            if match_cnt >= max(2, len(words) // 2):
                scored.append((match_cnt, r["id"]))
        if scored:
            scored.sort(key=lambda x: -x[0])
            return scored[0][1]
    # Create new
    c = conn.execute("INSERT OR IGNORE INTO companies (name) VALUES (?)", (company_name,))
    if c.lastrowid:
        return c.lastrowid
    c2 = conn.execute("SELECT id FROM companies WHERE name = ?", (company_name,)).fetchone()
    return c2["id"] if c2 else None


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
    if not name:
        return None
    import re
    def _to_dict(row):
        if row is None:
            return None
        return dict(row) if isinstance(row, (sqlite3.Row, dict)) else {"id": row[0], "name": row[1], **{f"col{i}": row[i] for i in range(2, len(row))}}
    row = conn.execute(
        "SELECT * FROM companies WHERE name = ?", (name,)
    ).fetchone()
    if row:
        return _to_dict(row)
    # Fuzzy fallback: try to match by significant words (Unicode-safe)
    words = [w.strip().lower() for w in re.split(r'[\s\(\)"\-]+', name) if len(w.strip()) > 2]
    if words:
        all_rows = conn.execute("SELECT * FROM companies").fetchall()
        scored = []
        for r in all_rows:
            cn_lower = (r["name"] if isinstance(r, (sqlite3.Row, dict)) else r[1]).lower()
            match_cnt = sum(1 for w in words if w in cn_lower)
            if match_cnt > 0:
                scored.append((match_cnt, -len(cn_lower), _to_dict(r)))
        if scored:
            scored.sort(key=lambda x: (-x[0], x[1]))
            return scored[0][2]
    return None


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
        LEFT JOIN companies c ON v.company_id = c.id
        WHERE v.deleted_at IS NULL
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


# ─── Profiles CRUD ───────────────────────────────────────────────

def get_all_profiles(conn: sqlite3.Connection | None = None) -> list[dict]:
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    rows = conn.execute("SELECT * FROM profiles ORDER BY created_at").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        for f in ['resume_data', 'search_filters', 'matrix_data', 'keywords_config']:
            if d.get(f):
                try: d[f] = json.loads(d[f])
                except: pass
        result.append(d)
    if own_conn:
        conn.close()
    return result


def get_profile(conn: sqlite3.Connection | None, profile_id: int) -> dict | None:
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    if own_conn:
        conn.close()
    if not row:
        return None
    d = dict(row)
    for f in ['resume_data', 'search_filters', 'matrix_data', 'keywords_config']:
        if d.get(f):
            try: d[f] = json.loads(d[f])
            except: pass
    return d


def save_profile(conn: sqlite3.Connection | None, data: dict) -> dict:
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    profile_id = data.get("id")
    fields = {
        "name": data.get("name"),
        "hh_resume_id": data.get("hh_resume_id"),
        "resume_name": data.get("resume_name"),
        "resume_data": json.dumps(data.get("resume_data", {}), ensure_ascii=False),
        "search_filters": json.dumps(data.get("search_filters", {}), ensure_ascii=False),
        "matrix_data": json.dumps(data.get("matrix_data", {}), ensure_ascii=False),
        "archetype": data.get("archetype", "01"),
        "keywords_config": json.dumps(data.get("keywords_config", {}), ensure_ascii=False),
    }
    if profile_id:
        sets = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [profile_id]
        conn.execute(f"UPDATE profiles SET {sets} WHERE id=?", vals)
    else:
        cur = conn.execute(
            "INSERT INTO profiles (name, hh_resume_id, resume_name, resume_data, search_filters, matrix_data, archetype, keywords_config) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            list(fields.values())
        )
        profile_id = cur.lastrowid
    conn.commit()
    if own_conn:
        conn.close()
    return get_profile(None, profile_id)


def delete_profile(conn: sqlite3.Connection | None, profile_id: int):
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    conn.execute("DELETE FROM vacancy_profiles WHERE profile_id=?", (profile_id,))
    conn.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
    if own_conn:
        conn.commit()
        conn.close()


def link_vacancy_to_profile(conn: sqlite3.Connection, vacancy_id: int, profile_id: int):
    conn.execute(
        "INSERT OR IGNORE INTO vacancy_profiles (vacancy_id, profile_id) VALUES (?, ?)",
        (vacancy_id, profile_id)
    )


# ─── Contacts CRUD ────────────────────────────────────────────

def save_contact(conn: sqlite3.Connection | None, data: dict) -> dict:
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    contact_id = data.get("id")
    extra = data.get("extra_contacts")
    extra_json = json.dumps(extra, ensure_ascii=False) if extra else None
    extra_phones = data.get("extra_phones")
    extra_phones_json = json.dumps(extra_phones, ensure_ascii=False) if extra_phones else None
    if contact_id:
        conn.execute("""
            UPDATE contacts SET company_id=?, name=?, role=?, source=?, priority=?,
                telegram=?, email=?, phone=?, vk=?, linkedin=?, extra_contacts=?, extra_phones=?, notes=?
            WHERE id=?
        """, (
            data.get("company_id"), data["name"], data.get("role"),
            data.get("source", "other"), data.get("priority", "B"),
            data.get("telegram"), data.get("email"), data.get("phone"),
            data.get("vk"), data.get("linkedin"), extra_json, extra_phones_json, data.get("notes"),
            contact_id,
        ))
    else:
        cur = conn.execute("""
            INSERT INTO contacts (company_id, name, role, source, priority,
                telegram, email, phone, vk, linkedin, extra_contacts, extra_phones, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("company_id"), data["name"], data.get("role"),
            data.get("source", "other"), data.get("priority", "B"),
            data.get("telegram"), data.get("email"), data.get("phone"),
            data.get("vk"), data.get("linkedin"), extra_json, extra_phones_json, data.get("notes"),
        ))
        contact_id = cur.lastrowid
    if own_conn:
        conn.commit()
        conn.close()
    return get_contact(None, contact_id)


def get_contact(conn: sqlite3.Connection | None, contact_id: int) -> dict | None:
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    row = conn.execute("""
        SELECT c.*, cp.name AS company_name
        FROM contacts c
        LEFT JOIN companies cp ON c.company_id = cp.id
        WHERE c.id=?
    """, (contact_id,)).fetchone()
    if own_conn:
        conn.close()
    if row:
        d = dict(row)
        for f in ['extra_contacts', 'extra_phones']:
            if d.get(f):
                try:
                    d[f] = json.loads(d[f])
                except (json.JSONDecodeError, TypeError):
                    d[f] = []
            else:
                d[f] = []
        return d
    return None


def get_contacts(conn: sqlite3.Connection | None, company_id: int | None = None,
                 priority: str | None = None, source: str | None = None) -> list[dict]:
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    query = """SELECT c.*, cp.name AS company_name, last_i.next_action_date, last_i.next_action_time, last_i.id AS interaction_id
               FROM contacts c
               LEFT JOIN companies cp ON c.company_id = cp.id
               LEFT JOIN (
                   SELECT contact_id, next_action_date, next_action_time, id FROM interactions
                   WHERE id IN (SELECT MAX(id) FROM interactions WHERE next_action_date IS NOT NULL AND completed_at IS NULL GROUP BY contact_id)
               ) last_i ON last_i.contact_id = c.id
               WHERE 1=1"""
    params = []
    if company_id:
        query += " AND c.company_id=?"
        params.append(company_id)
    if priority:
        query += " AND c.priority=?"
        params.append(priority)
    if source:
        query += " AND c.source=?"
        params.append(source)
    query += " ORDER BY c.priority, c.name"
    rows = conn.execute(query, params).fetchall()
    if own_conn:
        conn.close()
    return [dict(r) for r in rows]


def delete_all_vacancies(conn: sqlite3.Connection | None):
    """Delete ALL vacancies (cascades to vacancy_profiles). Contacts/companies untouched."""
    if conn is None:
        conn = get_connection()
        should_close = True
    else:
        should_close = False
    conn.execute("DELETE FROM vacancies")
    if should_close:
        conn.commit()
        conn.close()


def trash_vacancy(conn: sqlite3.Connection | None, vacancy_id: int, reasons: list[str]):
    """Soft-delete: set deleted_at and reasons (JSON array)."""
    own = conn is None
    if own:
        conn = get_connection()
    import json
    conn.execute("UPDATE vacancies SET deleted_at=datetime('now'), delete_reason=? WHERE id=?", (json.dumps(reasons, ensure_ascii=False), vacancy_id))
    if own:
        conn.commit()
        conn.close()


def restore_vacancy(conn: sqlite3.Connection | None, vacancy_id: int):
    """Restore from trash."""
    own = conn is None
    if own:
        conn = get_connection()
    conn.execute("UPDATE vacancies SET deleted_at=NULL, delete_reason=NULL, status='new' WHERE id=?", (vacancy_id,))
    if own:
        conn.commit()
        conn.close()


def get_trashed_vacancies(conn: sqlite3.Connection | None) -> list:
    """Return list of soft-deleted vacancies."""
    own = conn is None
    if own:
        conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM vacancies WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC"
    ).fetchall()
    columns = [d[1] for d in conn.execute("PRAGMA table_info(vacancies)").fetchall()]
    if own:
        conn.close()
    return [dict(zip(columns, r)) for r in rows]


def hard_delete_vacancy(conn: sqlite3.Connection | None, vacancy_id: int):
    """Permanent delete (only from trash)."""
    own = conn is None
    if own:
        conn = get_connection()
    conn.execute("DELETE FROM vacancies WHERE id=? AND deleted_at IS NOT NULL", (vacancy_id,))
    if own:
        conn.commit()
        conn.close()


def delete_contact(conn: sqlite3.Connection | None, contact_id: int):
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    conn.execute("DELETE FROM contacts WHERE id=?", (contact_id,))
    if own_conn:
        conn.commit()
        conn.close()


# ─── Interactions CRUD ───────────────────────────────────────

def save_interaction(conn: sqlite3.Connection | None, data: dict) -> dict:
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    interaction_id = data.get("id")
    if interaction_id:
        conn.execute("""
            UPDATE interactions SET contact_id=?, vacancy_id=?, type=?, direction=?,
                summary=?, outcome=?, next_action_date=?, next_action_time=?, completed_at=?
            WHERE id=?
        """, (
            data.get("contact_id"), data.get("vacancy_id"),
            data["type"], data["direction"],
            data.get("summary"), data.get("outcome"),
            data.get("next_action_date"), data.get("next_action_time"),
            data.get("completed_at"), interaction_id,
        ))
    else:
        cur = conn.execute("""
            INSERT INTO interactions (contact_id, vacancy_id, type, direction,
                summary, outcome, next_action_date, next_action_time, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("contact_id"), data.get("vacancy_id"),
            data["type"], data["direction"],
            data.get("summary"), data.get("outcome"),
            data.get("next_action_date"), data.get("next_action_time"),
            data.get("completed_at"),
        ))
        interaction_id = cur.lastrowid
    if own_conn:
        conn.commit()
        conn.close()
    return get_interaction(None, interaction_id)


def get_interaction(conn: sqlite3.Connection | None, interaction_id: int) -> dict | None:
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    row = conn.execute("SELECT * FROM interactions WHERE id=?", (interaction_id,)).fetchone()
    if own_conn:
        conn.close()
    return dict(row) if row else None


def get_interactions(conn: sqlite3.Connection | None,
                     contact_id: int | None = None,
                     vacancy_id: int | None = None) -> list[dict]:
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    conditions = []
    params = []
    if contact_id:
        conditions.append("contact_id=?")
        params.append(contact_id)
    if vacancy_id:
        conditions.append("vacancy_id=?")
        params.append(vacancy_id)
    where = " AND ".join(conditions) if conditions else "1"
    rows = conn.execute(
        f"SELECT * FROM interactions WHERE {where} ORDER BY created_at DESC",
        params
    ).fetchall()
    if own_conn:
        conn.close()
    return [dict(r) for r in rows]


def get_contacts_due_for_action(conn: sqlite3.Connection | None, mode: str = 'overdue') -> list[dict]:
    """Return contacts with next_action_date.
    Modes: 'today'     — date = today AND completed_at IS NULL
           'overdue'   — date < today AND completed_at IS NULL
           'tomorrow'  — date = today+1
           'thisweek'  — day after tomorrow to Sunday of current week
           'nextweek'  — next Monday to next Sunday
           'done_today' — completed today
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    if mode == 'today':
        date_filter = "AND date(i.next_action_date) = date('now') AND i.completed_at IS NULL"
    elif mode == 'tomorrow':
        date_filter = "AND date(i.next_action_date) = date('now', '+1 day') AND i.completed_at IS NULL"
    elif mode == 'thisweek':
        today = date.today()
        mon = today - timedelta(days=today.weekday())
        sun = mon + timedelta(days=6)
        start = today + timedelta(days=2)
        if start <= sun:
            date_filter = f"AND date(i.next_action_date) >= '{start.isoformat()}' AND date(i.next_action_date) <= '{sun.isoformat()}' AND i.completed_at IS NULL"
        else:
            date_filter = "AND 1=0"
    elif mode == 'nextweek':
        today = date.today()
        mon = today - timedelta(days=today.weekday())
        next_mon = mon + timedelta(days=7)
        next_sun = next_mon + timedelta(days=6)
        date_filter = f"AND date(i.next_action_date) >= '{next_mon.isoformat()}' AND date(i.next_action_date) <= '{next_sun.isoformat()}' AND i.completed_at IS NULL"
    elif mode == 'overdue':
        date_filter = "AND date(i.next_action_date) < date('now') AND i.completed_at IS NULL"
    elif mode == 'done_today':
        date_filter = "AND i.completed_at IS NOT NULL AND date(i.completed_at) = date('now')"
    else:
        date_filter = ""
    rows = conn.execute(f"""
        SELECT c.*, cp.name AS company_name, i.next_action_date, i.next_action_time,
               i.summary AS last_action,
               i.type AS last_action_type, i.direction AS last_action_direction,
               i.outcome, i.id AS interaction_id, i.completed_at
        FROM interactions i
        JOIN contacts c ON i.contact_id = c.id
        LEFT JOIN companies cp ON c.company_id = cp.id
        WHERE i.next_action_date IS NOT NULL
          {date_filter}
          AND i.id = (
              SELECT MAX(i2.id) FROM interactions i2
              WHERE i2.contact_id = c.id AND i2.next_action_date IS NOT NULL
          )
        ORDER BY i.next_action_date ASC, i.next_action_time ASC
    """).fetchall()
    if own_conn:
        conn.close()
    return [dict(r) for r in rows]


def get_completed_on_date(conn: sqlite3.Connection | None, date_str: str) -> list[dict]:
    """Return contacts with interactions completed on a specific date."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    rows = conn.execute("""
        SELECT c.*, cp.name AS company_name, i.id AS interaction_id, i.completed_at,
               i.next_action_date, i.next_action_time, i.type AS last_action_type,
               i.direction AS last_action_direction, i.outcome
        FROM interactions i
        JOIN contacts c ON i.contact_id = c.id
        LEFT JOIN companies cp ON c.company_id = cp.id
        WHERE date(i.completed_at) = ?
        ORDER BY i.completed_at DESC
    """, (date_str,)).fetchall()
    if own_conn:
        conn.close()
    return [dict(r) for r in rows]


def get_calendar_status(conn: sqlite3.Connection | None) -> dict:
    """Return a dict of date -> {total, completed, pending} for calendar highlighting."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    rows = conn.execute("""
        SELECT date(i.next_action_date) as d,
               COUNT(*) as total,
               SUM(CASE WHEN i.completed_at IS NOT NULL THEN 1 ELSE 0 END) as completed,
               SUM(CASE WHEN i.completed_at IS NULL THEN 1 ELSE 0 END) as pending
        FROM interactions i
        WHERE i.next_action_date IS NOT NULL
        GROUP BY date(i.next_action_date)
    """).fetchall()
    if own_conn:
        conn.close()
    return {r[0]: {"total": r[1], "completed": r[2], "pending": r[3]} for r in rows}
