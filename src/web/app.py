import json
import yaml
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.db import init_db, get_connection, get_vacancies_by_status

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="JobMatch", version="0.1.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ─── Pydantic models ──────────────────────────────────────────

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    work_format: Optional[str] = None
    salary_expectation: Optional[int] = None
    hh_resume_id: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    auto_respond_below_score: Optional[float] = None
    search_filters: Optional[dict] = None
    resume_profiles: Optional[dict] = None


class MatrixGroupWeight(BaseModel):
    id: str
    weight: int


class MatrixCriterionWeight(BaseModel):
    group_id: str
    criterion_id: str
    weight: int


# ─── Helpers ──────────────────────────────────────────────────

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


# ─── API Routes ───────────────────────────────────────────────

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
    return {"ok": False, "error": "group not found"}, 404


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
    return {"ok": False, "error": "criterion not found"}, 404


@app.get("/api/vacancies")
def api_get_vacancies(status: Optional[str] = None):
    vacancies = get_vacancies_from_db()
    if status:
        vacancies = [v for v in vacancies if v.get("status") == status]
    return {"items": vacancies, "total": len(vacancies)}


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
        cat = v.get("category", "мимо")
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total": total,
        "by_status": by_status,
        "by_category": by_category,
    }


# ─── Page Routes ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    return templates.TemplateResponse("profile.html", {"request": request})


@app.get("/matrix", response_class=HTMLResponse)
def matrix_page(request: Request):
    return templates.TemplateResponse("matrix.html", {"request": request})


@app.get("/vacancies", response_class=HTMLResponse)
def vacancies_page(request: Request):
    return templates.TemplateResponse("vacancies.html", {"request": request})


# ─── Main ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    init_db()
    uvicorn.run(app, host="127.0.0.1", port=8100)
