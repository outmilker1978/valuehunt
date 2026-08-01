import json
import os
import re
import shutil
import sys
import traceback
import sqlite3
import time
import yaml
from datetime import datetime
from pathlib import Path

import jinja2
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel

from src.db import init_db, get_connection, save_vacancy, save_company, \
    get_company_by_name, get_vacancies_with_company, log_decision, \
    get_all_profiles, get_profile, save_profile, delete_profile, link_vacancy_to_profile, \
    get_contacts, get_contact, save_contact, delete_contact, delete_all_vacancies, \
    get_interactions, get_interaction, save_interaction, get_contacts_due_for_action, \
    get_calendar_status, get_completed_on_date, trash_vacancy, restore_vacancy, get_trashed_vacancies, hard_delete_vacancy
from src.scanner import run_scan, import_vacancy_by_url
from src.retro_import import import_retro
from src.ues import UESCalculator

if getattr(sys, 'frozen', False):
    MEIPASS = Path(sys._MEIPASS)
    EXE_DIR = Path(sys.executable).resolve().parent
    TEMPLATES_DIR = MEIPASS / "src" / "web" / "templates"
    STATIC_DIR = MEIPASS / "src" / "web" / "static"
    CONFIG_DIR = EXE_DIR / "config"
    BASE_DIR = EXE_DIR
    if not CONFIG_DIR.exists():
        import shutil
        src_cfg = MEIPASS / "config"
        if src_cfg.exists():
            shutil.copytree(src_cfg, CONFIG_DIR)
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
    STATIC_DIR = Path(__file__).resolve().parent / "static"
    CONFIG_DIR = BASE_DIR / "config"

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


class ProfileCreate(BaseModel):
    name: str
    hh_resume_id: str | None = None
    resume_name: str | None = None
    resume_data: dict | None = None
    search_filters: dict | None = None
    matrix_data: dict | None = None
    archetype: str | None = None


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
    titles: list[str] | None = None
    keywords: list[str] | None = None
    experience: list[str] | None = None
    employment: list[str] | None = None
    schedule: list[str] | None = None
    professional_roles: list[int] | None = None


class MatrixGroupWeight(BaseModel):
    id: str
    weight: int


class MatrixCriterionWeight(BaseModel):
    group_id: str
    criterion_id: str
    weight: int


class HHImportRequest(BaseModel):
    resume_id: str
    profile_id: int | None = None


class ContactCreate(BaseModel):
    company_id: int | None = None
    name: str
    role: str | None = None
    source: str = "other"
    priority: str = "B"
    telegram: str | None = None
    email: str | None = None
    phone: str | None = None
    vk: str | None = None
    linkedin: str | None = None
    extra_contacts: list[dict] | None = None
    extra_phones: list[str] | None = None
    notes: str | None = None


class ContactUpdate(BaseModel):
    company_id: int | None = None
    name: str | None = None
    role: str | None = None
    source: str | None = None
    priority: str | None = None
    telegram: str | None = None
    email: str | None = None
    phone: str | None = None
    vk: str | None = None
    linkedin: str | None = None
    extra_contacts: list[dict] | None = None
    extra_phones: list[str] | None = None
    notes: str | None = None


class InteractionCreate(BaseModel):
    contact_id: int | None = None
    vacancy_id: int | None = None
    type: str
    direction: str = "outbound"
    summary: str | None = None
    outcome: str | None = None
    next_action_date: str | None = None
    next_action_time: str | None = None
    completed_at: str | None = None


def load_profile() -> dict:
    path = CONFIG_DIR / "profile.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_legacy_profile(data: dict):
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


def get_vacancies_from_db(profile_id: int | None = None, show_deleted: bool = False) -> list:
    try:
        conn = get_connection()
        base_sql = """SELECT v.*, c.name AS company_name
                       FROM vacancies v
                       LEFT JOIN companies c ON v.company_id = c.id"""
        deleted_filter = "" if show_deleted else " AND v.deleted_at IS NULL"
        if profile_id:
            rows = conn.execute(
                base_sql + " WHERE v.id IN (SELECT vacancy_id FROM vacancy_profiles WHERE profile_id = ?)"
                + deleted_filter + " ORDER BY v.created_at DESC LIMIT 500",
                (profile_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                base_sql + " WHERE 1=1" + deleted_filter + " ORDER BY v.created_at DESC LIMIT 500"
            ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("company_name"):
                d["company"] = d["company_name"]
            result.append(d)
        return result
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
    save_legacy_profile(profile)
    return {"ok": True, "profile": profile}


@app.post("/api/profile/import-hh")
def api_import_hh_profile(data: HHImportRequest):
    """Scrape public HH resume page and populate profile fields."""
    try:
        from bs4 import BeautifulSoup
        resume_url = f"https://hh.ru/resume/{data.resume_id}"
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        # First visit main page to get cookies
        for attempt in range(2):
            try:
                session.get("https://hh.ru", timeout=15)
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                if attempt == 0:
                    time.sleep(2)
                else:
                    return JSONResponse(status_code=504, content={"ok": False, "error": "HH.ru не отвечает. Проверьте интернет и VPN."})
        resp = session.get(resume_url, headers={"Referer": "https://hh.ru/"}, timeout=15)
        if resp.status_code != 200:
            return JSONResponse(status_code=400, content={"ok": False,
                                "error": f"HH вернул {resp.status_code}"})
        soup = BeautifulSoup(resp.text, "lxml")
        profile = load_profile()

        # Name from h1
        h1 = soup.find("h1")
        if h1:
            profile["name"] = h1.get_text(strip=True)

        # Desired position / title
        title_block = soup.find("span", attrs={"data-qa": "resume-block-title"})
        if title_block:
            pos = title_block.get_text(strip=True)
            profile["titles"] = [pos]

        # Location
        loc_block = soup.find("span", attrs={"data-qa": "resume-personal-address"})
        if loc_block:
            profile["location"] = loc_block.get_text(strip=True).split(",")[0].strip()

        # Salary
        salary_block = soup.find("span", attrs={"data-qa": "resume-block-salary"})
        if salary_block:
            nums = re.findall(r"\d[\d\s]*\d", salary_block.get_text())
            if nums:
                profile["salary_expectation"] = int(nums[0].replace(" ", "").replace("\u202f", ""))

        # Skills
        skills = []
        for tag in soup.find_all("span", attrs={"data-qa": "resume-block-skills"}):
            skills.append(tag.get_text(strip=True))
        if skills:
            profile["keywords"] = skills

        # Experience from resume
        exp_items = soup.find_all("div", attrs={"data-qa": "resume-block-experience-item"})
        if exp_items:
            years = len(exp_items)
            if years <= 1:
                profile["experience"] = ["between1And3"]
            elif years <= 3:
                profile["experience"] = ["between3And6"]
            else:
                profile["experience"] = ["moreThan6"]

        # Work format
        for tag in soup.find_all(attrs={"data-qa": "resume-block-employment"}):
            t = tag.get_text(strip=True).lower()
            if "удалён" in t:
                profile["work_format"] = "remote"
            elif "гибрид" in t:
                profile["work_format"] = "hybrid"

        save_legacy_profile(profile)
        # Also create/update a profile in multi-profile system
        try:
            conn = get_connection()
            resume_data = {
                "name": profile.get("name"),
                "titles": profile.get("titles", []),
                "location": profile.get("location"),
                "salary_expectation": profile.get("salary_expectation"),
                "keywords": profile.get("keywords", []),
                "experience": profile.get("experience", []),
                "employment": profile.get("employment", []),
                "schedule": profile.get("schedule", []),
            "work_formats": profile.get("work_formats", [profile.get("work_format")] if profile.get("work_format") else []),
                "professional_roles": profile.get("professional_roles", []),
            }
            created_id = None
            if data.profile_id:
                p = get_profile(conn, data.profile_id)
                if p:
                    p["resume_data"] = resume_data
                    p["search_filters"] = p.get("search_filters", profile.get("search_filters", {}))
                    p = save_profile(conn, p)
                    created_id = p["id"]
            if not created_id:
                existing = get_all_profiles(conn)
                if existing:
                    p = existing[0]
                    p["resume_data"] = resume_data
                    p["search_filters"] = profile.get("search_filters", {})
                    save_profile(conn, p)
                else:
                    save_profile(conn, {
                        "name": profile.get("name", "Загруженное резюме"),
                        "resume_data": resume_data,
                        "search_filters": profile.get("search_filters", {}),
                    })
            conn.commit()
            conn.close()
        except Exception:
            pass  # Non-critical: profiles table might not exist yet
        return {"ok": True, "profile": profile}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.post("/api/profile/upload-resume")
async def api_upload_resume(file: UploadFile = File(...), profile_id: int = Form(None)):
    """Parse uploaded resume (HTML or TXT) and save to profile."""
    try:
        content = (await file.read()).decode("utf-8", errors="replace")
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Не удалось прочитать файл"})

    raw = content.strip()

    # HTML (HH.ru export)
    if raw.startswith("<"):
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, "lxml")
            resume_data = _parse_hh_html(soup)
        except Exception:
            return JSONResponse(status_code=500, content={"ok": False, "error": "Ошибка парсинга HTML"})
    else:
        resume_data = {}
        lines = content.splitlines()
        for i, line in enumerate(lines):
            m = re.search(r"Желаемая\s*должность", line)
            if m:
                for j in range(i + 1, min(i + 5, len(lines))):
                    t = lines[j].strip()
                    if t and not t.startswith("Специализации"):
                        resume_data["titles"] = [t]
                        break
            m = re.search(r"(\d[\d\s]+\d)\s*(?:руб|₽)", line)
            if m and "salary_expectation" not in resume_data:
                resume_data["salary_expectation"] = int(m.group(1).replace(" ", "").replace(" ", "").replace(" ", ""))
            m = re.search(r"Проживает[^:]*:\s*(.+)", line, re.IGNORECASE)
            if m and "location" not in resume_data:
                resume_data["location"] = m.group(1).strip()
            m = re.search(r"Формат\s*работы[:\s]*(.+)", line, re.IGNORECASE)
            if m and "work_formats" not in resume_data:
                txt = m.group(1).lower()
                fmts = []
                if "удалён" in txt: fmts.append("remote")
                if "гибрид" in txt: fmts.append("hybrid")
                if fmts: resume_data["work_formats"] = fmts
            m = re.search(r"Тип\s*занятости[:\s]*(.+)", line, re.IGNORECASE)
            if m and "employment" not in resume_data:
                em = m.group(1).lower()
                if "полная" in em: resume_data["employment"] = ["full"]

    # Save to profile
    if not profile_id:
        conn = get_connection()
        existing = get_all_profiles(conn)
        profile_id = existing[0]["id"] if existing else None
        conn.close()
    if not profile_id:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Нет профиля. Создай профиль сначала."})

    conn = get_connection()
    p = get_profile(conn, profile_id)
    if not p:
        conn.close()
        return JSONResponse(status_code=404, content={"ok": False, "error": "Профиль не найден"})

    existing_rd = p.get("resume_data") or {}
    existing_rd.update(resume_data)
    p["resume_data"] = existing_rd
    save_profile(conn, p)
    conn.close()
    return {"ok": True, "profile_id": profile_id, "resume_data": existing_rd}


def _parse_hh_html(soup) -> dict:
    """Extract all resume fields from HH.ru HTML export."""
    data = {}

    el = soup.select_one("p.resume__title")
    if el:
        data["name"] = re.sub(r"\s+", " ", el.get_text(strip=True))

    el = soup.select_one("p.resume__position")
    if el:
        data["titles"] = [el.get_text(strip=True)]

    for p in soup.find_all("p"):
        txt = p.get_text(strip=True)
        m = re.search(r"Проживает[:\s]*(.+)", txt)
        if m:
            data["location"] = m.group(1).strip()
            break

    el = soup.select_one("p.resume__salary")
    if el:
        nums = re.findall(r"\d[\d\s]*\d", el.get_text(strip=True))
        if nums:
            data["salary_expectation"] = int(nums[0].replace(" ", "").replace(" ", "").replace(" ", ""))

    for p in soup.find_all("p"):
        txt = p.get_text(strip=True)
        m = re.search(r"Формат\s*работы[:\s]*(.+)", txt, re.IGNORECASE)
        if m:
            vals = m.group(1).lower()
            fmts = []
            if "удалён" in vals: fmts.append("remote")
            if "гибрид" in vals: fmts.append("hybrid")
            if "офис" in vals: fmts.append("office")
            if fmts: data["work_formats"] = fmts
        m2 = re.search(r"Тип\s*занятости[:\s]*(.+)", txt, re.IGNORECASE)
        if m2:
            em = m2.group(1).lower()
            if "полная" in em: data["employment"] = ["full"]
            elif "частич" in em: data["employment"] = ["part"]
            elif "проект" in em: data["employment"] = ["project"]

    for p in soup.find_all("p", class_="resume__block"):
        txt = p.get_text(strip=True)
        m = re.search(r"Опыт\s*работы\s*[—\-–]\s*(.+)", txt)
        if m:
            nums = re.findall(r"(\d+)\s*(?:лет|год|года)", m.group(1))
            total_years = sum(int(y) for y in nums) if nums else 0
            if total_years >= 6:
                data["experience"] = ["moreThan6"]
            elif total_years >= 3:
                data["experience"] = ["between3And6"]
            elif total_years >= 1:
                data["experience"] = ["between1And3"]
            else:
                data["experience"] = ["noExperience"]
            break

    for li in soup.find_all("li", class_="resume-skils"):
        hint = li.find("span", class_="bloko-form-hint")
        if hint and hint.get_text(strip=True).lower() == "навыки":
            item_p = li.find(["p", "div"], class_="resume-skils__item")
            if item_p:
                raw = item_p.get_text(" ", strip=True)
                parts = re.split(r"\s*;\s*", raw)
                skills = [s.strip() for s in parts if s.strip() and len(s.strip()) > 2]
                data["keywords"] = skills
            break

    prof_role_map = {
        "руководитель проектов": 107, "менеджер продукта": 73,
        "владелец продукта": 73, "delivery manager": 104,
        "program manager": 104, "agile-коуч": 107, "scrum-мастер": 107,
        "cio": 36, "cto": 125, "технический директор": 125,
        "руководитель группы разработки": 104, "руководитель отдела ит": 36,
        "руководитель отдела анализа": 157, "руководитель отдела разработки": 104,
        "бизнес-аналитик": 150, "системный аналитик": 148,
        "head of product": 73, "руководитель отдела маркетинга": 170,
        "руководитель отдела поддержки": 121, "техлид": 104,
        "директор департамента ит": 36,
    }
    roles = soup.select("ul.resume-profession-roles li.resume-profession-role")
    if roles:
        matched = []
        for li in roles:
            txt = li.get_text(strip=True).lower().strip("— ")
            for key, code in prof_role_map.items():
                if key in txt or txt in key:
                    if code not in matched:
                        matched.append(code)
                    break
        if matched:
            data["professional_roles"] = matched

    return data
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


@app.post("/api/matrix/save")
def api_save_matrix(data: dict):
    save_matrix(data)
    return {"ok": True}


@app.post("/api/matrix/save-ui-weights")
def api_save_ui_weights(data: dict):
    """Apply weight changes from UI (groups + criteria weights only)."""
    try:
        matrix = load_matrix()
        ui_groups = {g["id"]: g for g in data.get("groups", [])}
        if not ui_groups:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Нет данных о группах"})
        for g in matrix.get("groups", []):
            if g["id"] in ui_groups:
                ug = ui_groups[g["id"]]
                if ug.get("weight") is not None:
                    g["weight"] = ug["weight"]
                ui_criteria = {c["id"]: c for c in ug.get("criteria", [])}
                for c in g.get("criteria", []):
                    if c["id"] in ui_criteria:
                        uc = ui_criteria[c["id"]]
                        if uc.get("weight") is not None:
                            c["weight"] = uc["weight"]
        save_matrix(matrix)
        return {"ok": True}
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.post("/api/matrix/reevaluate")
def api_reevaluate_matrix():
    conn = get_connection()
    try:
        ues = UESCalculator()
        rows = conn.execute("SELECT * FROM vacancies WHERE deleted_at IS NULL").fetchall()
        columns = [d[1] for d in conn.execute("PRAGMA table_info(vacancies)").fetchall()]
        updated = 0
        for row in rows:
            v = dict(zip(columns, row))
            for k in ("skills_json", "parsed_tasks", "parsed_requirements", "key_words"):
                jk = k.replace("_json", "") if k.endswith("_json") else k
                v[jk] = json.loads(v.get(k) or "[]")
            result = ues.evaluate(v, resume_keywords=None)
            conn.execute("""
                UPDATE vacancies SET score=?, category=?, gate_a_result=?, gate_b_result=?,
                override_applied=?, risks=?, cover_letter=?, resume_archetype=?
                WHERE id=?
            """, (
                result["score"], result["category"],
                json.dumps(result["gate_a"], ensure_ascii=False),
                json.dumps(result["gate_b"], ensure_ascii=False),
                result["override_applied"],
                json.dumps(result["risks"], ensure_ascii=False),
                result.get("cover_letter", ""),
                v.get("resume_archetype") or result.get("resume_archetype", ""),
                v["id"]
            ))
            updated += 1
        conn.commit()
        return {"ok": True, "updated": updated}
    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
    finally:
        conn.close()


@app.get("/api/vacancies")
def api_get_vacancies(status: str | None = None, profile_id: int | None = None, company: str | None = None, show_deleted: bool = False):
    vacancies = get_vacancies_from_db(profile_id, show_deleted)
    if status:
        vacancies = [v for v in vacancies if v.get("status") == status]
    if company:
        cl = company.lower().strip()
        vacancies = [v for v in vacancies if
                     cl in (v.get("company") or "").lower()
                     or (v.get("company") or "").lower() in cl
                     or (v.get("company_name") or "").lower() == cl]
    return {"items": vacancies, "total": len(vacancies)}


@app.get("/api/vacancies/by-company")
def api_vacancies_by_company():
    conn = get_connection()
    rows = conn.execute(
        """SELECT COALESCE(c.name, v.company) AS name, COUNT(*) as cnt FROM vacancies v
           LEFT JOIN companies c ON v.company_id = c.id
           WHERE v.deleted_at IS NULL AND v.company IS NOT NULL AND v.company != ''
           GROUP BY COALESCE(c.name, v.company)
           ORDER BY cnt DESC"""
    ).fetchall()
    conn.close()
    return {"items": [{"name": r["name"], "count": r["cnt"]} for r in rows]}


@app.get("/api/vacancies/{vacancy_id}/contacts")
def api_vacancy_contacts(vacancy_id: int):
    conn = get_connection()
    row = conn.execute("SELECT company_id, company FROM vacancies WHERE id = ? AND deleted_at IS NULL", (vacancy_id,)).fetchone()
    if not row:
        conn.close()
        return {"items": []}
    # Use company_id if available, fall back to company name text match
    if row["company_id"]:
        contacts = conn.execute(
            """SELECT c.id, c.name, c.role, c.telegram, c.email, c.phone, c.source, c.priority, c.notes, cp.name AS company_name
               FROM contacts c
               JOIN companies cp ON c.company_id = cp.id
               WHERE c.company_id = ?
               ORDER BY c.priority, c.name""",
            (row["company_id"],)
        ).fetchall()
    elif row["company"]:
        contacts = conn.execute(
            """SELECT c.id, c.name, c.role, c.telegram, c.email, c.phone, c.source, c.priority, c.notes, cp.name AS company_name
               FROM contacts c
               JOIN companies cp ON c.company_id = cp.id
               WHERE cp.name = ?
               ORDER BY c.priority, c.name""",
            (row["company"],)
        ).fetchall()
    else:
        contacts = []
    conn.close()
    return {"items": [dict(r) for r in contacts]}


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
    if result.get("company_id"):
        conn = get_connection()
        company = conn.execute("SELECT * FROM companies WHERE id = ?", (result["company_id"],)).fetchone()
        conn.close()
        if company:
            result["company_data"] = dict(company)
    elif result.get("company"):
        conn = get_connection()
        company = get_company_by_name(conn, result["company"])
        conn.close()
        if company:
            result["company_data"] = dict(company)
    return result


@app.get("/api/stats")
def api_get_stats(profile_id: int | None = None):
    vacancies = get_vacancies_from_db(profile_id)
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
    # Trash count
    conn = get_connection()
    trash_count = conn.execute("SELECT COUNT(*) FROM vacancies WHERE deleted_at IS NOT NULL").fetchone()[0]
    conn.close()
    # Trash by reason
    by_reason = {}
    conn2 = get_connection()
    for r in conn2.execute("SELECT delete_reason FROM vacancies WHERE deleted_at IS NOT NULL").fetchall():
        raw = r[0]
        if not raw:
            by_reason["Другое"] = by_reason.get("Другое", 0) + 1
            continue
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for reason in parsed:
                    by_reason[reason] = by_reason.get(reason, 0) + 1
            else:
                by_reason[str(parsed)] = by_reason.get(str(parsed), 0) + 1
        except (json.JSONDecodeError, TypeError):
            by_reason[raw] = by_reason.get(raw, 0) + 1
    conn2.close()
    return {
        "total": total,
        "by_status": by_status,
        "by_category": by_category,
        "trash": {"total": trash_count, "by_reason": by_reason},
    }


# ─── Report ───────────────────────────────────────────────────

from datetime import date, timedelta


@app.get("/api/report")
def api_report(from_date: str | None = None, to_date: str | None = None):
    today = date.today()
    if not to_date:
        to_date = today.isoformat()
    if not from_date:
        from_date = (today - timedelta(days=6)).isoformat()

    conn = get_connection()

    # New vacancies in period (all, including trashed)
    new_rows = conn.execute("""
        SELECT id, title, company, date(created_at) as d FROM vacancies
        WHERE date(created_at) >= ? AND date(created_at) <= ?
        ORDER BY created_at DESC
    """, [from_date, to_date]).fetchall()
    new_vacancies = [{"id": r[0], "title": r[1], "company": r[2], "date": r[3]} for r in new_rows]

    # Interactions completed in period (any type)
    done_rows = conn.execute("""
        SELECT i.id, i.type, date(i.completed_at) as d, c.name, cp.name AS company_name
        FROM interactions i
        JOIN contacts c ON i.contact_id = c.id
        LEFT JOIN companies cp ON c.company_id = cp.id
        WHERE i.completed_at IS NOT NULL AND date(i.completed_at) >= ? AND date(i.completed_at) <= ?
        ORDER BY i.completed_at DESC
    """, [from_date, to_date]).fetchall()
    completed = [{"id": r[0], "type": r[1], "date": r[2], "contact": r[3], "company": r[4] or ""} for r in done_rows]

    # Applications from vacancy status (not interactions)
    applied_rows = conn.execute("""
        SELECT id, title, company, date(COALESCE(responded_at, created_at)) as d
        FROM vacancies WHERE status = 'applied'
        AND date(COALESCE(responded_at, created_at)) >= ? AND date(COALESCE(responded_at, created_at)) <= ?
        ORDER BY responded_at DESC, created_at DESC
    """, [from_date, to_date]).fetchall()
    applications = [{"id": r[0], "title": r[1], "company": r[2], "date": r[3]} for r in applied_rows]

    # Rejections from vacancy status
    rej_rows = conn.execute("""
        SELECT id, title, company, date(COALESCE(responded_at, created_at)) as d
        FROM vacancies WHERE status = 'rejected'
        AND date(COALESCE(responded_at, created_at)) >= ? AND date(COALESCE(responded_at, created_at)) <= ?
        ORDER BY responded_at DESC, created_at DESC
    """, [from_date, to_date]).fetchall()
    rejections = [{"id": r[0], "title": r[1], "company": r[2], "date": r[3]} for r in rej_rows]

    # Invitations — vacancies with status invited/in_progress/offer (active pipeline)
    invited_rows = conn.execute("""
        SELECT id, title, company, status FROM vacancies WHERE deleted_at IS NULL AND status IN ('invited','in_progress','offer')
        ORDER BY created_at DESC
    """).fetchall()
    invitations = [{"id": r[0], "title": r[1], "company": r[2], "status": r[3]} for r in invited_rows]

    # Active interviews — subset in_progress + offer
    interview_rows = [i for i in invitations if i["status"] in ("in_progress", "offer")]

    # New contacts in period
    contact_rows = conn.execute("""
        SELECT c.id, c.name, cp.name AS company_name, date(c.created_at) as d
        FROM contacts c
        LEFT JOIN companies cp ON c.company_id = cp.id
        WHERE date(c.created_at) >= ? AND date(c.created_at) <= ?
        ORDER BY c.created_at DESC
    """, [from_date, to_date]).fetchall()
    new_contacts = [{"id": r[0], "name": r[1], "company": r[2] or "", "date": r[3]} for r in contact_rows]

    # Overdue interactions
    overdue_rows = conn.execute("""
        SELECT i.id, i.type, i.next_action_date, c.name, cp.name AS company_name
        FROM interactions i
        JOIN contacts c ON i.contact_id = c.id
        LEFT JOIN companies cp ON c.company_id = cp.id
        WHERE i.completed_at IS NULL AND date(i.next_action_date) < date('now')
        ORDER BY i.next_action_date ASC
    """).fetchall()
    overdue = [{"id": r[0], "type": r[1], "date": r[2], "contact": r[3], "company": r[4] or ""} for r in overdue_rows]

    # Category & status distribution (all vacancies, including trashed)
    by_category_rows = conn.execute("""
        SELECT COALESCE(category,'REJECT') as cat, COUNT(*) as cnt FROM vacancies
        WHERE date(created_at) >= ? AND date(created_at) <= ?
        GROUP BY cat ORDER BY cnt DESC
    """, [from_date, to_date]).fetchall()
    by_category = {r[0]: r[1] for r in by_category_rows}

    by_status_rows = conn.execute("""
        SELECT status, COUNT(*) as cnt FROM vacancies
        WHERE date(created_at) >= ? AND date(created_at) <= ?
        GROUP BY status ORDER BY cnt DESC
    """, [from_date, to_date]).fetchall()
    by_status = {r[0]: r[1] for r in by_status_rows}

    # Daily new vacancies trend (all, including trashed)
    daily_rows = conn.execute("""
        SELECT date(created_at) as d, COUNT(*) as cnt FROM vacancies
        WHERE date(created_at) >= ? AND date(created_at) <= ?
        GROUP BY d ORDER BY d ASC
    """, [from_date, to_date]).fetchall()
    daily_trend = [{"date": r[0], "count": r[1]} for r in daily_rows]

    # Trash reasons breakdown for vacancies trashed in period
    trash_in_period = conn.execute("""
        SELECT delete_reason, deleted_at FROM vacancies
        WHERE deleted_at IS NOT NULL AND date(deleted_at) >= ? AND date(deleted_at) <= ?
        ORDER BY deleted_at DESC
    """, [from_date, to_date]).fetchall()
    import json
    trash_by_reason = {}
    trash_items = []
    for r in trash_in_period:
        raw = r[0]
        items = []
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    items = parsed
                else:
                    items = [str(parsed)]
            except (json.JSONDecodeError, TypeError):
                items = [raw]
        else:
            items = ["Другое"]
        for reason in items:
            trash_by_reason[reason] = trash_by_reason.get(reason, 0) + 1
        if items:
            trash_items.append({"reasons": items, "date": r[1]})
    trash_breakdown = {"by_reason": trash_by_reason, "items": trash_items}

    # ── Funnel: all-time counts by pipeline stage ──
    funnel = {}
    funnel_rows = conn.execute("""
        SELECT status, COUNT(*) as cnt FROM vacancies WHERE deleted_at IS NULL GROUP BY status
    """).fetchall()
    stage_order = ["new", "applied", "invited", "in_progress", "offer"]
    for r in funnel_rows:
        funnel[r[0]] = r[1]
    # Normalize
    funnel = {s: funnel.get(s, 0) for s in stage_order}

    # ── Active companies (with pending/recent interactions) ──
    active_companies = []
    ac_rows = conn.execute("""
        SELECT cp.id, cp.name,
            COALESCE((SELECT COUNT(*) FROM interactions i
             JOIN contacts c ON i.contact_id = c.id
             WHERE c.company_id = cp.id AND i.completed_at IS NULL AND date(i.next_action_date) >= date('now', '-14 days')
            ), 0) as pending_actions,
            (SELECT MAX(i.created_at) FROM interactions i
             JOIN contacts c ON i.contact_id = c.id
             WHERE c.company_id = cp.id
            ) as last_activity,
            COALESCE((SELECT COUNT(*) FROM interactions i
             JOIN contacts c ON i.contact_id = c.id
             WHERE c.company_id = cp.id AND date(i.created_at) >= date('now', '-30 days')
            ), 0) as recent_actions
        FROM companies cp
        WHERE cp.id IN (
            SELECT DISTINCT c2.company_id FROM interactions i2
            JOIN contacts c2 ON i2.contact_id = c2.id
            WHERE date(i2.created_at) >= date('now', '-30 days') OR (i2.completed_at IS NULL AND date(i2.next_action_date) >= date('now', '-14 days'))
        )
        ORDER BY last_activity DESC
        LIMIT 30
    """).fetchall()
    for r in ac_rows:
        active_companies.append({
            "id": r[0], "name": r[1],
            "pending_actions": r[2], "last_activity": r[3],
            "recent_actions": r[4]
        })

    # ── Weekly trend: last 10 weeks ──
    weekly_trend = []
    wt_rows = conn.execute("""
        SELECT strftime('%Y-W%W', created_at) as week,
               COUNT(*) as cnt,
               SUM(CASE WHEN deleted_at IS NOT NULL THEN 1 ELSE 0 END) as deleted_cnt
        FROM vacancies
        WHERE created_at >= date('now', '-70 days')
        GROUP BY week ORDER BY week ASC
    """).fetchall()
    # Funnel per week (new in week / applied in week)
    for r in wt_rows:
        week_label = r[0]  # e.g. "2026-W26"
        # Parse week into readable label
        try:
            yr, wk = week_label.split("-W")
            import datetime
            first_day = datetime.datetime.strptime(f"{yr}-W{int(wk)}-1", "%Y-W%W-%w").date()
            week_str = first_day.strftime("%d.%m")
        except Exception:
            week_str = week_label
        weekly_trend.append({
            "week": week_label, "label": week_str,
            "new": r[1], "deleted": r[2]
        })

    conn.close()

    label_map = {"outreach": "Аутрич", "applied": "Отклик", "in_progress": "В работе",
                 "offer": "Оффер", "rejection": "Отказ", "archived": "В архив", "closed": "Закрыта"}

    # Build text summary
    def fmt_dd_mm_yy(d: str) -> str:
        return d[8:10] + '.' + d[5:7] + '.' + d[2:4] if len(d) >= 10 else d

    lines = [f"Отчёт за {fmt_dd_mm_yy(from_date)} – {fmt_dd_mm_yy(to_date)}",
             ""]
    lines.append(f"Новых вакансий: {len(new_vacancies)}")
    lines.append(f"Откликов: {len(applications)}")
    lines.append(f"Приглашений активно: {len(invitations)}")
    lines.append(f"Отказов: {len(rejections)}")
    lines.append(f"Новых контактов: {len(new_contacts)}")
    lines.append(f"Выполнено действий: {len(completed)}")
    lines.append(f"Просроченных действий: {len(overdue)}")
    lines.append(f"Удалено из поиска: {len(trash_in_period)}")
    lines.append("")

    trash_text = []
    for r_item in trash_items[:10]:
        trash_text.append(f"  • {r_item['date']}: {', '.join(r_item['reasons'])}")
    if trash_text:
        lines.append("Удалено из поиска:")
        lines.extend(trash_text)
        if len(trash_items) > 10:
            lines.append(f"  ... и ещё {len(trash_items) - 10}")
        if trash_by_reason:
            lines.append("По причинам:")
            for reason, cnt in sorted(trash_by_reason.items(), key=lambda x: -x[1]):
                lines.append(f"  • {reason}: {cnt}")
        lines.append("")

    if new_vacancies:
        lines.append("Новые вакансии:")
        for v in new_vacancies[:10]:
            lines.append(f"  • {v['title']} — {v['company']} ({v['date']})")
        if len(new_vacancies) > 10:
            lines.append(f"  ... и ещё {len(new_vacancies) - 10}")
        lines.append("")

    if applications:
        lines.append("Отклики:")
        for a in applications:
            lines.append(f"  • {a['title']} — {a['company']} ({a['date']})")
        lines.append("")

    if completed:
        lines.append("Выполненные действия:")
        for c_item in completed:
            lines.append(f"  • {c_item['company']} — {c_item['contact']}: {label_map.get(c_item['type'], c_item['type'])} ({c_item['date']})")
        lines.append("")

    if overdue:
        lines.append("Просроченные действия:")
        for o in overdue:
            lines.append(f"  • {o['company']} — {o['contact']}: {label_map.get(o['type'], o['type'])} (до {o['date']})")
        lines.append("")

    return {
        "period": {"from": from_date, "to": to_date},
        "new_vacancies": {"count": len(new_vacancies), "items": new_vacancies},
        "applications": {"count": len(applications), "items": applications},
        "invitations": {"count": len(invitations), "items": invitations},
        "active_interviews": {"count": len(interview_rows), "items": interview_rows},
        "rejections": {"count": len(rejections), "items": rejections},
        "new_contacts": {"count": len(new_contacts), "items": new_contacts},
        "completed": {"count": len(completed), "items": completed},
        "overdue": {"count": len(overdue), "items": overdue},
        "by_category": by_category,
        "by_status": by_status,
        "daily_trend": daily_trend,
        "trash_breakdown": trash_breakdown,
        "funnel": funnel,
        "active_companies": active_companies,
        "weekly_trend": weekly_trend,
        "text_summary": "\n".join(lines),
    }


# ─── Profiles (multi-resume) ──────────────────────────────────


@app.get("/api/profiles")
def api_get_profiles():
    profiles = get_all_profiles()
    return {"items": profiles}


@app.get("/api/profiles/{profile_id}")
def api_get_profile_by_id(profile_id: int):
    p = get_profile(None, profile_id)
    if not p:
        return JSONResponse(status_code=404, content={"error": "not found"})
    return p


@app.post("/api/profiles")
def api_create_profile(data: ProfileCreate):
    p = save_profile(None, data.model_dump())
    return {"ok": True, "profile": p}


@app.put("/api/profiles/{profile_id}")
def api_update_profile_by_id(profile_id: int, data: ProfileCreate):
    existing = get_profile(None, profile_id)
    if not existing:
        return JSONResponse(status_code=404, content={"error": "not found"})
    payload = data.model_dump()
    payload["id"] = profile_id
    p = save_profile(None, payload)
    return {"ok": True, "profile": p}


@app.delete("/api/profiles/{profile_id}")
def api_delete_profile(profile_id: int):
    delete_profile(None, profile_id)
    return {"ok": True}


# ─── Contacts ───────────────────────────────────────────────

@app.get("/api/companies/list")
def api_companies_list():
    conn = get_connection()
    rows = conn.execute("SELECT id, name, website, address FROM companies ORDER BY name").fetchall()
    conn.close()
    return {"items": [dict(r) for r in rows]}


@app.post("/api/companies/quick")
def api_create_company_quick(data: dict):
    name = data.get("name", "").strip()
    if not name:
        return JSONResponse(status_code=400, content={"ok": False, "error": "name required"})
    conn = get_connection()
    try:
        cur = conn.execute("INSERT INTO companies (name) VALUES (?)", (name,))
        conn.commit()
        company_id = cur.lastrowid
    except sqlite3.IntegrityError:
        existing = conn.execute("SELECT id FROM companies WHERE name=?", (name,)).fetchone()
        company_id = existing["id"] if existing else None
    conn.close()
    return {"ok": True, "id": company_id}


@app.put("/api/companies/{company_id}")
def api_update_company(company_id: int, data: dict):
    conn = get_connection()
    updates = []
    params = []
    for f in ['website', 'address']:
        if f in data:
            updates.append(f"{f}=?")
            params.append(data[f])
    if updates:
        params.append(company_id)
        conn.execute(f"UPDATE companies SET {','.join(updates)} WHERE id=?", params)
        conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/contacts/due-for-action")
def api_contacts_due_for_action(mode: str = 'overdue'):
    return {"items": get_contacts_due_for_action(None, mode)}


@app.get("/api/contacts/calendar-status")
def api_calendar_status():
    return get_calendar_status(None)


@app.get("/api/contacts/completed-on")
def api_completed_on(date: str = ''):
    if not date:
        return {"items": []}
    return {"items": get_completed_on_date(None, date)}


@app.get("/api/contacts")
def api_get_contacts(company_id: int | None = None, priority: str | None = None,
                     source: str | None = None):
    return {"items": get_contacts(None, company_id, priority, source)}


@app.get("/api/contacts/{contact_id}")
def api_get_contact(contact_id: int):
    c = get_contact(None, contact_id)
    if not c:
        return JSONResponse(status_code=404, content={"error": "not found"})
    c["interactions"] = get_interactions(None, contact_id=contact_id)
    if c["interactions"]:
        last = c["interactions"][0]
        c["next_action_date"] = last.get("next_action_date")
        c["next_action_time"] = last.get("next_action_time")
    return c


@app.post("/api/contacts")
def api_create_contact(data: ContactCreate):
    # Проверка на дубликат
    if data.name:
        if data.company_id:
            exists = get_connection().execute(
                "SELECT id FROM contacts WHERE name=? AND company_id=?",
                (data.name, data.company_id)
            ).fetchone()
        else:
            exists = get_connection().execute(
                "SELECT id FROM contacts WHERE name=? AND company_id IS NULL",
                (data.name,)
            ).fetchone()
        if exists:
            return JSONResponse(status_code=409, content={"ok": False, "error": "Контакт с таким именем уже существует"})
    c = save_contact(None, data.model_dump())
    return {"ok": True, "contact": c}


@app.put("/api/contacts/{contact_id}")
def api_update_contact(contact_id: int, data: ContactUpdate):
    try:
        existing = get_contact(None, contact_id)
        if not existing:
            return JSONResponse(status_code=404, content={"error": "not found"})
        payload = data.model_dump(exclude_none=True)
        payload["id"] = contact_id
        for field in ['name','company_id','role','source','priority','telegram','email','phone','vk','linkedin','extra_contacts','extra_phones','notes']:
            if field not in payload:
                payload[field] = existing.get(field)
        c = save_contact(None, payload)
        return {"ok": True, "contact": c}
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.delete("/api/contacts/{contact_id}")
def api_delete_contact(contact_id: int):
    delete_contact(None, contact_id)
    return {"ok": True}


# ─── Interactions ──────────────────────────────────────────

@app.get("/api/interactions")
def api_get_interactions(contact_id: int | None = None, vacancy_id: int | None = None):
    return {"items": get_interactions(None, contact_id=contact_id, vacancy_id=vacancy_id)}


@app.post("/api/interactions")
def api_create_interaction(data: InteractionCreate):
    try:
        i = save_interaction(None, data.model_dump())
        return {"ok": True, "interaction": i}
    except Exception as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})


@app.put("/api/interactions/{interaction_id}")
def api_update_interaction(interaction_id: int, data: InteractionCreate):
    try:
        existing = get_interaction(None, interaction_id)
        if not existing:
            return JSONResponse(status_code=404, content={"ok": False, "error": "not found"})
        payload = data.model_dump(exclude_none=True)
        payload["id"] = interaction_id
        i = save_interaction(None, payload)
        return {"ok": True, "interaction": i}
    except Exception as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})


@app.delete("/api/interactions/{interaction_id}")
def api_delete_interaction(interaction_id: int):
    try:
        conn = get_connection()
        conn.execute("DELETE FROM interactions WHERE id=?", (interaction_id,))
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})


@app.post("/api/interactions/{interaction_id}/complete")
def api_complete_interaction(interaction_id: int):
    try:
        existing = get_interaction(None, interaction_id)
        if not existing:
            return JSONResponse(status_code=404, content={"ok": False, "error": "not found"})
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection()
        conn.execute("UPDATE interactions SET completed_at = ? WHERE id = ?",
                     (now, interaction_id))
        conn.commit()
        conn.close()
        return {"ok": True, "completed_at": now}
    except Exception as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})


@app.post("/api/interactions/{interaction_id}/uncomplete")
def api_uncomplete_interaction(interaction_id: int):
    try:
        conn = get_connection()
        conn.execute("UPDATE interactions SET completed_at = NULL WHERE id = ?",
                     (interaction_id,))
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})


# ─── Scan ──────────────────────────────────────────────────

@app.post("/api/scan")
def api_run_scan(profile_id: int | None = None):
    if profile_id:
        profile = get_profile(None, profile_id)
        if not profile:
            return JSONResponse(status_code=404, content={"ok": False, "error": "profile not found"})
        # Convert resume_data + search_filters back to flat profile dict for scanner
        flat = dict(profile.get("resume_data", {}) or {})
        flat["search_filters"] = profile.get("search_filters", {})
        flat["matrix_data"] = profile.get("matrix_data", {})
        profile = flat
    else:
        profile = load_profile()

    conn = get_connection()

    # Get known hh_ids to skip detail fetching for already-scanned vacancies
    known = set()
    try:
        rows = conn.execute("SELECT hh_id FROM vacancies WHERE hh_id IS NOT NULL").fetchall()
        known = {str(r[0]) for r in rows}
    except Exception:
        pass

    try:
        results = run_scan(profile, known_ids=known)
    except requests.exceptions.Timeout:
        conn.close()
        return JSONResponse(status_code=504, content={"ok": False, "error": "HH.ru не ответил за 30 сек. Попробуйте позже."})
    except requests.exceptions.ConnectionError:
        conn.close()
        return JSONResponse(status_code=502, content={"ok": False, "error": "Нет соединения с HH.ru. Проверьте интернет."})
    except Exception as e:
        conn.close()
        return JSONResponse(status_code=500, content={"ok": False, "error": f"Ошибка сканирования: {str(e)}"})
    if not results:
        conn.close()
        return {"ok": True, "scanned": 0, "total": 0,
                "message": "Вакансий не найдено"}

    archetype = profile.get("archetype") or "01"

    scanned = 0
    new_count = 0
    for item in results:
        scanned += 1
        if item.get("_known"):
            continue
        item["resume_archetype"] = archetype
        result = save_vacancy(conn, item)
        if result["inserted"]:
            new_count += 1

        # Link to profile
        if profile_id and result.get("id"):
            try:
                link_vacancy_to_profile(conn, result["id"], profile_id)
            except Exception:
                pass
        elif result.get("id"):
            # Legacy: link to first profile (or use default)
            profiles = get_all_profiles(conn)
            if profiles:
                try:
                    link_vacancy_to_profile(conn, result["id"], profiles[0]["id"])
                except Exception:
                    pass

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
                company_id = save_company(conn, company_data)
            elif existing:
                company_id = existing["id"]
            else:
                company_id = None
            # Set company_id on the vacancy
            if company_id and result.get("id"):
                conn.execute("UPDATE vacancies SET company_id = ? WHERE id = ?", (company_id, result["id"]))

    conn.commit()

    # Get total in DB for context
    total_in_db = conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]

    conn.close()

    return {
        "ok": True,
        "scanned": scanned,
        "new": new_count,
        "total": len(results),
        "total_in_db": total_in_db,
        "message": f"HH.ru показал {len(results)} вакансий. Добавлено в БД: {new_count}, уже были: {scanned - new_count}. Всего в БД: {total_in_db}",
    }


@app.post("/api/vacancies/clean")
def api_clean_vacancies():
    delete_all_vacancies(None)
    return {"ok": True, "message": "Все вакансии удалены. Контакты и компании сохранены."}


class VacancyImport(BaseModel):
    url: str
    profile_id: int | None = None


@app.post("/api/vacancies/import")
def api_import_vacancy(data: VacancyImport):
    conn = get_connection()
    try:
        profile = None
        profile_id = data.profile_id
        if not profile_id:
            profiles = get_all_profiles(conn)
            if profiles:
                profile_id = profiles[0]["id"]
        if profile_id:
            profile = get_profile(conn, profile_id)
        vacancy = import_vacancy_by_url(data.url, profile)
        if not vacancy:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Не удалось загрузить вакансию по ссылке"})
        result = save_vacancy(conn, vacancy)
        if result.get("id") and profile_id:
            try:
                link_vacancy_to_profile(conn, result["id"], profile_id)
            except Exception:
                pass
        # Link to company
        company_name = vacancy.get("company")
        if company_name:
            existing = get_company_by_name(conn, company_name)
            if not existing and vacancy.get("hh_employer_id"):
                from src.collector import collect_all_company_data
                company_data = collect_all_company_data(
                    company_name,
                    hh_employer_id=vacancy.get("hh_employer_id"),
                )
                company_data["name"] = company_name
                company_id = save_company(conn, company_data)
            elif existing:
                company_id = existing["id"]
            else:
                company_id = None
            if company_id and result.get("id"):
                conn.execute("UPDATE vacancies SET company_id = ?, company = ? WHERE id = ?",
                             (company_id, existing.get("name") if existing else company_name, result["id"]))
        conn.commit()
        return {"ok": True, "vacancy_id": result["id"], "inserted": result["inserted"], "title": vacancy.get("title"), "category": vacancy.get("category")}
    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
    finally:
        conn.close()


class ManualVacancy(BaseModel):
    title: str
    company: str | None = None
    url: str | None = None
    description: str | None = None
    salary_from: float | None = None
    salary_to: float | None = None
    work_format: str | None = None
    location: str | None = None
    profile_id: int | None = None


@app.post("/api/vacancies/manual")
def api_create_manual_vacancy(data: ManualVacancy):
    conn = get_connection()
    try:
        # Try to parse publication date from description text
        published_at = None
        if data.description:
            m = re.search(r'(?:вакансия\s+)?опубликован[ао]?\s+(\d+)\s+(\S+)\s+(\d{4})', data.description)
            if m:
                published_at = f"{m.group(1)} {m.group(2)} {m.group(3)}"
        if not published_at:
            ru_months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря']
            now = datetime.now()
            published_at = f"{now.day} {ru_months[now.month - 1]} {now.year}"
        vacancy = {
            "hh_id": None,
            "title": data.title,
            "company": data.company,
            "url": data.url,
            "description": data.description,
            "salary_from": data.salary_from,
            "salary_to": data.salary_to,
            "work_format": data.work_format,
            "location": data.location,
            "status": "new",
            "published_at": published_at,
        }
        profile = None
        profile_id = data.profile_id
        if not profile_id:
            profiles = get_all_profiles(conn)
            if profiles:
                profile_id = profiles[0]["id"]
        if profile_id:
            profile = get_profile(conn, profile_id)
        if profile:
            from src.scanner import _enrich_with_ues
            _enrich_with_ues(vacancy, profile)
        result = save_vacancy(conn, vacancy)
        if result.get("id") and profile_id:
            try:
                link_vacancy_to_profile(conn, result["id"], profile_id)
            except Exception:
                pass
        conn.commit()
        return {"ok": True, "vacancy_id": result["id"], "title": vacancy.get("title"), "category": vacancy.get("category")}
    except Exception as e:
        conn.rollback()
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
    finally:
        conn.close()


@app.post("/api/scan-all")
def api_run_scan_all():
    conn = get_connection()
    profiles = get_all_profiles(conn)

    # Get known hh_ids once
    known = set()
    try:
        rows = conn.execute("SELECT hh_id FROM vacancies WHERE hh_id IS NOT NULL").fetchall()
        known = {str(r[0]) for r in rows}
    except Exception:
        pass

    conn.close()

    if not profiles:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Нет профилей для сканирования"})

    per_profile = []
    total_new = 0
    total_found = 0

    for p in profiles:
        sf = p.get("search_filters", {})
        if not sf or not sf.get("text"):
            per_profile.append({"profile_id": p["id"], "profile_name": p["name"], "skipped": True,
                                "message": "Нет фильтра поиска"})
            continue

        flat = dict(p.get("resume_data", {}) or {})
        flat["search_filters"] = sf
        flat["matrix_data"] = p.get("matrix_data", {})

        try:
            results = run_scan(flat, known_ids=known)
        except Exception as e:
            per_profile.append({"profile_id": p["id"], "profile_name": p["name"], "error": str(e)})
            continue

        if not results:
            per_profile.append({"profile_id": p["id"], "profile_name": p["name"], "found": 0})
            continue

        conn2 = get_connection()
        scanned = 0
        new_count = 0
        arch = p.get("archetype") or "01"
        for item in results:
            scanned += 1
            if item.get("_known"):
                continue
            item["resume_archetype"] = arch
            result = save_vacancy(conn2, item)
            if result["inserted"]:
                new_count += 1
                # Add newly inserted hh_id to known set so next profile skips it
                h = item.get("hh_id")
                if h:
                    known.add(str(h))
            if result.get("id"):
                try:
                    link_vacancy_to_profile(conn2, result["id"], p["id"])
                except Exception:
                    pass

            company_name = item.get("company")
            if company_name:
                existing = get_company_by_name(conn2, company_name)
                if not existing and item.get("hh_employer_id"):
                    from src.collector import collect_all_company_data
                    company_data = collect_all_company_data(
                        company_name,
                        hh_employer_id=item.get("hh_employer_id"),
                    )
                    company_data["name"] = company_name
                    company_id = save_company(conn2, company_data)
                elif existing:
                    company_id = existing["id"]
                else:
                    company_id = None
                if company_id and result.get("id"):
                    conn2.execute("UPDATE vacancies SET company_id = ? WHERE id = ?", (company_id, result["id"]))

        conn2.commit()
        conn2.close()

        total_new += new_count
        total_found += scanned
        per_profile.append({
            "profile_id": p["id"],
            "profile_name": p["name"],
            "found": scanned,
            "new": new_count,
        })

    total_in_db = 0
    conn3 = get_connection()
    total_in_db = conn3.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]
    conn3.close()

    return {
        "ok": True,
        "per_profile": per_profile,
        "total_found": total_found,
        "total_new": total_new,
        "total_in_db": total_in_db,
        "message": f"Отсканировано {len(per_profile)} профилей. Найдено {total_found} вакансий, новых: {total_new}. Всего в БД: {total_in_db}",
    }


@app.post("/api/import-retro")
def api_import_retro():
    try:
        report = import_retro()
        return {"ok": True, "report": report}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.post("/api/vacancies/{vacancy_id}/status")
def api_update_vacancy_status(vacancy_id: int, data: dict):
    status = data.get("status")
    if not status:
        return JSONResponse(status_code=400, content={"error": "status required"})
    conn = get_connection()
    now = datetime.now().isoformat()
    if status in ("applied", "rejected"):
        conn.execute("UPDATE vacancies SET status = ?, responded_at = ? WHERE id = ?", (status, now, vacancy_id))
    else:
        conn.execute("UPDATE vacancies SET status = ? WHERE id = ?", (status, vacancy_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/vacancies/{vacancy_id}/notes")
def api_update_vacancy_notes(vacancy_id: int, data: dict):
    notes = data.get("notes", "")
    conn = get_connection()
    conn.execute("UPDATE vacancies SET notes = ? WHERE id = ?", (notes, vacancy_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.put("/api/vacancies/{vacancy_id}/archetype")
def api_update_vacancy_archetype(vacancy_id: int, data: dict):
    archetype = data.get("archetype")
    if archetype not in ("01", "03"):
        return JSONResponse(status_code=400, content={"error": "archetype must be 01 or 03"})
    conn = get_connection()
    conn.execute("UPDATE vacancies SET resume_archetype = ? WHERE id = ?", (archetype, vacancy_id))
    conn.commit()
    conn.close()
    return {"ok": True}


# ─── Trash (soft delete) ───────────────────────────────────


TRASH_REASONS = [
    "Зарплата ниже ожидаемой",
    "Локация не подходит",
    "Не мой профиль/домен",
    "Дубль вакансии",
    "Не согласен с условиями",
    "Работодатель закрыл вакансию",
    "Другое",
]


@app.post("/api/vacancies/{vacancy_id}/trash")
def api_trash_vacancy(vacancy_id: int, data: dict):
    reasons = data.get("reasons", ["Другое"])
    # Validate against known reasons; custom "Другое" text is kept as-is
    validated = []
    for r in reasons:
        if r in TRASH_REASONS or r.strip():
            validated.append(r.strip())
    if not validated:
        validated = ["Другое"]
    conn = get_connection()
    trash_vacancy(conn, vacancy_id, validated)
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/vacancies/{vacancy_id}/restore")
def api_restore_vacancy(vacancy_id: int):
    conn = get_connection()
    restore_vacancy(conn, vacancy_id)
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/vacancies/{vacancy_id}")
def api_hard_delete_vacancy(vacancy_id: int):
    conn = get_connection()
    hard_delete_vacancy(conn, vacancy_id)
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/trash")
def api_get_trash():
    conn = get_connection()
    rows = conn.execute(
        """SELECT v.*, c.name AS company_name
           FROM vacancies v
           LEFT JOIN companies c ON v.company_id = c.id
           WHERE v.deleted_at IS NOT NULL
           ORDER BY v.deleted_at DESC"""
    ).fetchall()
    columns = [d[1] for d in conn.execute("PRAGMA table_info(vacancies)").fetchall()]
    columns.append("company_name")
    conn.close()
    return {"items": [dict(zip(columns, r)) for r in rows]}


@app.get("/api/trash-stats")
def api_trash_stats():
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM vacancies WHERE deleted_at IS NOT NULL").fetchone()[0]
    by_reason = {}
    rows = conn.execute("SELECT delete_reason FROM vacancies WHERE deleted_at IS NOT NULL").fetchall()
    import json
    for r in rows:
        raw = r[0]
        if not raw:
            by_reason["Другое"] = by_reason.get("Другое", 0) + 1
            continue
        try:
            reasons_list = json.loads(raw)
            if isinstance(reasons_list, list):
                for reason in reasons_list:
                    by_reason[reason] = by_reason.get(reason, 0) + 1
            else:
                by_reason[str(reasons_list)] = by_reason.get(str(reasons_list), 0) + 1
        except (json.JSONDecodeError, TypeError):
            by_reason[raw] = by_reason.get(raw, 0) + 1
    conn.close()
    return {"total": total, "by_reason": by_reason}


@app.get("/api/ues-config")
def api_get_ues_config():
    return load_ues_config()


@app.get("/", response_class=HTMLResponse)
def index_page():
    return render("index.html")


@app.get("/profile", response_class=HTMLResponse)
def profile_page():
    return render("profile.html")


@app.get("/contacts", response_class=HTMLResponse)
def contacts_page():
    return render("contacts.html")


@app.get("/matrix", response_class=HTMLResponse)
def matrix_page():
    return render("matrix.html")


@app.get("/vacancies", response_class=HTMLResponse)
def vacancies_page():
    return render("vacancies.html")


@app.get("/vacancies/{vacancy_id}", response_class=HTMLResponse)
def vacancy_detail_page(vacancy_id: int):
    return render("vacancy_detail.html", vacancy_id=vacancy_id)


# ─── Backup / Export ─────────────────────────────────────────

BACKUP_DIR = BASE_DIR / "data" / "backups"


@app.get("/backup", response_class=HTMLResponse)
def backup_page():
    backups = sorted(BACKUP_DIR.glob("*.db"), key=os.path.getmtime, reverse=True)[:10]
    exports = sorted(BACKUP_DIR.glob("*.json"), key=os.path.getmtime, reverse=True)[:10]
    return render("backup.html", backups=backups, exports=exports)


@app.get("/report", response_class=HTMLResponse)
def report_page():
    return render("report.html")


@app.post("/api/backup")
def api_create_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    db_path = BASE_DIR / "data" / "valuehunt.db"
    backup_db = BACKUP_DIR / f"valuehunt-{ts}.db"
    shutil.copy2(db_path, backup_db)
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    dump = {}
    for table in ["contacts", "companies", "vacancies", "interactions"]:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
        dump[table] = [dict(r) for r in rows]
    conn.close()
    backup_json = BACKUP_DIR / f"valuehunt-{ts}.json"
    with open(backup_json, "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, indent=2, default=str)
    # Cleanup — keep last 10 pairs
    all_db = sorted(BACKUP_DIR.glob("valuehunt-*.db"), key=lambda f: f.name)
    while len(all_db) > 10:
        old = all_db.pop(0)
        old.unlink(missing_ok=True)
        (old.with_suffix(".json")).unlink(missing_ok=True)
    return {"ok": True, "db": backup_db.name, "json": backup_json.name}


@app.get("/api/export/{table}")
def api_export_table(table: str):
    allowed = {"contacts", "companies", "vacancies", "interactions"}
    if table not in allowed:
        return JSONResponse(status_code=400, content={"error": "invalid table"})
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    return JSONResponse(content={"ok": True, "table": table, "items": data})


@app.on_event("startup")
def startup():
    init_db()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100)
