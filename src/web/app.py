import json
import os
import yaml
from pathlib import Path

import jinja2
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel

from src.db import init_db, get_connection, save_vacancy, save_company, \
    get_company_by_name, get_vacancies_with_company, log_decision
from src.scanner import run_scan

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="ValueHunt", version="0.2.0")


@app.get("/static/{path:path}")
def serve_static(path: str):
    file_path = STATIC_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    return JSONResponse(status_code=404, content={"error": "not found"})

jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)


def render(template_name: str, **context) -> str:
    tmpl = jinja_env.get_template(template_name)
    return tmpl.render(**context)


class ProfileUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    work_format: str | None = None
    salary_expectation: int | None = None
    hh_resume_id: str | None = None
    telegram_chat_id: str | None = None
    hh_access_token: str | None = None
    auto_respond_below_score: float | None = None
    search_filters: dict | None = None
    resume_profiles: dict | None = None


class MatrixGroupWeight(BaseModel):
    id: str
    weight: int


class MatrixCriterionWeight(BaseModel):
    group_id: str
    criterion_id: str
    weight: int


def load_profile() -> dict:
    path = CONFIG_DIR / "profile.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_profile(data: dict):
    path = CONFIG_DIR / "profile.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_ues_config() -> dict:
    path = CONFIG_DIR / "ues_config.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    from src.ues import DEFAULT_UES_CONFIG
    return DEFAULT_UES_CONFIG


def load_matrix() -> dict:
    path = CONFIG_DIR / "matrix.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {"groups": []}


def save_matrix(data: dict):
    path = CONFIG_DIR / "matrix.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, indent=2, sort_keys=False)


def get_vacancies_from_db() -> list:
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM vacancies ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@app.get("/api/profile")
def api_get_profile():
    return load_profile()


@app.post("/api/profile")
def api_update_profile(data: ProfileUpdate):
    profile = load_profile()
    update_data = data.model_dump(exclude_none=True)
    profile.update(update_data)
    save_profile(profile)
    return {"ok": True, "profile": profile}


@app.get("/api/matrix")
def api_get_matrix():
    return load_matrix()


@app.post("/api/matrix/group-weight")
def api_update_group_weight(data: MatrixGroupWeight):
    matrix = load_matrix()
    for g in matrix.get("groups", []):
        if g["id"] == data.id:
            g["weight"] = data.weight
            save_matrix(matrix)
            return {"ok": True}
    return JSONResponse(status_code=404, content={"ok": False, "error": "group not found"})


@app.post("/api/matrix/criterion-weight")
def api_update_criterion_weight(data: MatrixCriterionWeight):
    matrix = load_matrix()
    for g in matrix.get("groups", []):
        if g["id"] == data.group_id:
            for c in g.get("criteria", []):
                if c["id"] == data.criterion_id:
                    c["weight"] = data.weight
                    save_matrix(matrix)
                    return {"ok": True}
    return JSONResponse(status_code=404, content={"ok": False, "error": "criterion not found"})


@app.get("/api/vacancies")
def api_get_vacancies(status: str | None = None):
    vacancies = get_vacancies_from_db()
    if status:
        vacancies = [v for v in vacancies if v.get("status") == status]
    return {"items": vacancies, "total": len(vacancies)}


@app.get("/api/vacancies/{vacancy_id}")
def api_get_vacancy(vacancy_id: int):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM vacancies WHERE id = ?", (vacancy_id,)
    ).fetchone()
    conn.close()
    if not row:
        return JSONResponse(status_code=404, content={"error": "not found"})
    result = dict(row)
    for f in ["skills_json", "parsed_tasks", "parsed_requirements", "key_words",
              "risks", "gate_a_result", "gate_b_result"]:
        if result.get(f):
            try:
                result[f] = json.loads(result[f])
            except (json.JSONDecodeError, TypeError):
                pass
    if result.get("company"):
        conn = get_connection()
        company = get_company_by_name(conn, result["company"])
        conn.close()
        if company:
            result["company_data"] = dict(company)
    return result


@app.get("/api/stats")
def api_get_stats():
    vacancies = get_vacancies_from_db()
    total = len(vacancies)
    by_status = {}
    for v in vacancies:
        s = v.get("status", "new")
        by_status[s] = by_status.get(s, 0) + 1
    by_category = {}
    for v in vacancies:
        cat = v.get("category", "REJECT")
        if not cat:
            cat = "REJECT"
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total": total,
        "by_status": by_status,
        "by_category": by_category,
    }


@app.post("/api/scan")
def api_run_scan():
    profile = load_profile()
    conn = get_connection()

    results = run_scan(profile)
    if not results:
        conn.close()
        return {"ok": True, "scanned": 0, "total": 0,
                "message": "Вакансий не найдено"}

    scanned = 0
    for item in results:
        save_vacancy(conn, item)
        scanned += 1

        company_name = item.get("company")
        if company_name:
            existing = get_company_by_name(conn, company_name)
            if not existing and item.get("hh_employer_id"):
                from src.collector import collect_all_company_data
                company_data = collect_all_company_data(
                    company_name,
                    hh_employer_id=item.get("hh_employer_id"),
                )
                company_data["name"] = company_name
                save_company(conn, company_data)

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "scanned": scanned,
        "total": len(results),
        "message": f"Найдено {len(results)} вакансий, обработано {scanned}",
    }


@app.post("/api/vacancies/{vacancy_id}/status")
def api_update_vacancy_status(vacancy_id: int, data: dict):
    status = data.get("status")
    if not status:
        return JSONResponse(status_code=400, content={"error": "status required"})
    conn = get_connection()
    conn.execute("UPDATE vacancies SET status = ? WHERE id = ?", (status, vacancy_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/ues-config")
def api_get_ues_config():
    return load_ues_config()


@app.get("/", response_class=HTMLResponse)
def index_page():
    return render("index.html")


@app.get("/profile", response_class=HTMLResponse)
def profile_page():
    return render("profile.html")


@app.get("/matrix", response_class=HTMLResponse)
def matrix_page():
    return render("matrix.html")


@app.get("/vacancies", response_class=HTMLResponse)
def vacancies_page():
    return render("vacancies.html")


@app.get("/vacancies/{vacancy_id}", response_class=HTMLResponse)
def vacancy_detail_page(vacancy_id: int):
    return render("vacancy_detail.html", vacancy_id=vacancy_id)


@app.on_event("startup")
def startup():
    init_db()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100)
