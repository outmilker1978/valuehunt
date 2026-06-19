from datetime import date, datetime
from typing import Optional
from .models import get_connection


def add_application(
    company_name: str,
    position: str,
    applied_at: str = None,
    industry: str = None,
    source: str = "hh",
    url: str = None,
    score: float = None,
    notes: str = None,
) -> int:
    conn = get_connection()
    cur = conn.execute("SELECT id FROM companies WHERE name = ?", (company_name,))
    row = cur.fetchone()
    if row:
        company_id = row["id"]
    else:
        c2 = conn.execute("INSERT INTO companies (name, industry) VALUES (?, ?)", (company_name, industry or ""))
        company_id = c2.lastrowid

    cursor = conn.execute(
        """INSERT INTO applications
           (company_id, company_name, position, industry, source, url, status, score, applied_at, notes)
           VALUES (?, ?, ?, ?, ?, ?, 'viewed', ?, ?, ?)""",
        (company_id, company_name, position, industry, source, url, score, applied_at or date.today().isoformat(), notes),
    )
    app_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return app_id


STATUS_TO_ACTIVITY = {
    "invited": "invite",
    "interview": "interview",
    "offer": "offer",
    "rejected": "reject",
    "accepted": "accept",
    "viewed": "view",
}

def update_status(app_id: int, new_status: str, activity_date: str = None, description: str = None):
    conn = get_connection()
    conn.execute("UPDATE applications SET status = ? WHERE id = ?", (new_status, app_id))
    act_type = STATUS_TO_ACTIVITY.get(new_status, "note")
    conn.execute(
        """INSERT INTO activities (application_id, activity_type, activity_date, description)
           VALUES (?, ?, ?, ?)""",
        (app_id, act_type, activity_date or date.today().isoformat(), description),
    )
    conn.commit()
    conn.close()


def get_all_applications() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM applications ORDER BY applied_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_application(app_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_activities(app_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM activities WHERE application_id = ? ORDER BY activity_date",
        (app_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_companies() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM companies ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]
