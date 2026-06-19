from collections import Counter, defaultdict
from datetime import datetime, timedelta
from .models import get_connection


def funnel():
    conn = get_connection()
    rows = conn.execute("SELECT status FROM applications").fetchall()
    conn.close()
    counts = Counter(r["status"] for r in rows)
    return {
        "viewed": counts.get("viewed", 0),
        "invited": counts.get("invited", 0),
        "interview": counts.get("interview", 0),
        "offer": counts.get("offer", 0),
        "rejected": counts.get("rejected", 0),
        "accepted": counts.get("accepted", 0),
    }


def conversion_rates():
    f = funnel()
    total = f["viewed"] or 1
    return {
        "view_to_invite": round(f["invited"] / total * 100, 1),
        "invite_to_interview": round(f["interview"] / (f["invited"] or 1) * 100, 1),
        "interview_to_offer": round(f["offer"] / (f["interview"] or 1) * 100, 1),
        "offer_to_accept": round(f["accepted"] / (f["offer"] or 1) * 100, 1),
        "overall": round(f["accepted"] / total * 100, 1),
    }


def applications_by_day(days: int = 30) -> list[dict]:
    conn = get_connection()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT applied_at, COUNT(*) as cnt FROM applications WHERE applied_at >= ? GROUP BY applied_at ORDER BY applied_at",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [{"date": r["applied_at"], "count": r["cnt"]} for r in rows]


def applications_by_week(days: int = 90) -> list[dict]:
    conn = get_connection()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT substr(applied_at, 1, 7) as week, COUNT(*) as cnt
           FROM applications WHERE applied_at >= ?
           GROUP BY week ORDER BY week""",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [{"week": r["week"], "count": r["cnt"]} for r in rows]


def score_distribution(buckets: int = 5) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT score FROM applications WHERE score IS NOT NULL").fetchall()
    conn.close()
    scores = [r["score"] for r in rows]
    if not scores:
        return []
    dist = Counter(min(int(s / 10 * buckets), buckets - 1) for s in scores)
    return [{"bucket": f"{i * 10 / buckets:.0f}-{(i + 1) * 10 / buckets:.0f}", "count": dist.get(i, 0)} for i in range(buckets)]


def top_companies(limit: int = 10) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT company_name, COUNT(*) as cnt FROM applications GROUP BY company_name ORDER BY cnt DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [{"name": r["company_name"], "count": r["cnt"]} for r in rows]


def top_industries(limit: int = 10) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT industry, COUNT(*) as cnt FROM applications WHERE industry IS NOT NULL AND industry != '' GROUP BY industry ORDER BY cnt DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [{"name": r["industry"], "count": r["cnt"]} for r in rows]


def avg_response_time() -> float:
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.applied_at, min(ac.activity_date) as first_reply
           FROM applications a
           JOIN activities ac ON ac.application_id = a.id AND ac.activity_type IN ('invite','interview')
           GROUP BY a.id HAVING first_reply IS NOT NULL"""
    ).fetchall()
    conn.close()
    if not rows:
        return 0.0
    deltas = []
    for r in rows:
        try:
            applied = datetime.fromisoformat(r["applied_at"])
            replied = datetime.fromisoformat(r["first_reply"])
            deltas.append((replied - applied).days)
        except (ValueError, TypeError):
            pass
    return round(sum(deltas) / len(deltas), 1) if deltas else 0.0


def total_stats() -> dict:
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) as c FROM applications").fetchone()["c"]
    companies = conn.execute("SELECT COUNT(DISTINCT company_name) as c FROM applications").fetchone()["c"]
    avg_score = conn.execute("SELECT AVG(score) as a FROM applications WHERE score IS NOT NULL").fetchone()["a"]
    conn.close()
    return {
        "total_applications": total,
        "total_companies": companies,
        "avg_score": round(avg_score, 2) if avg_score else 0.0,
    }
