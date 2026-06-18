import os
import re
import json
import requests

DEEPSEEK_API = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"


def get_llm_client():
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY")
    if not api_key:
        return None
    return {"api_key": api_key, "endpoint": DEEPSEEK_API, "model": DEEPSEEK_MODEL}


def analyze_vacancy_llm(vacancy: dict, llm: dict | None = None) -> dict:
    if not llm:
        return _analyze_vacancy_keyword(vacancy)
    try:
        return _analyze_via_llm(vacancy, llm)
    except Exception:
        return _analyze_vacancy_keyword(vacancy)


def _analyze_vacancy_keyword(vacancy: dict) -> dict:
    text = _build_text(vacancy).lower()

    tasks = _extract_section(text, ["задачи", "чем предстоит заниматься", "обязанности", "что нужно делать",
                                      "key responsibilities", "responsibilities"])
    requirements = _extract_section(text, ["требования", "required", "qualifications", "must have",
                                            "что мы ждём", "необходимые навыки"])
    conditions = _extract_section(text, ["условия", "мы предлагаем", "conditions", "benefits", "what we offer"])
    key_words = _extract_keywords(text, _KEYWORD_POOL)

    return {
        "parsed_tasks": tasks[:5],
        "parsed_requirements": requirements[:5],
        "key_words": key_words[:15],
        "method": "keyword",
        "confidence": "extracted",
    }


def _analyze_via_llm(vacancy: dict, llm: dict) -> dict:
    prompt = f"""Analyze this IT job vacancy and return a JSON object with:
1. "parsed_tasks": list of 3-5 main tasks (in Russian)
2. "parsed_requirements": list of 3-5 requirements (in Russian)
3. "key_words": 10-15 key words/phrases for a cover letter (in Russian)
4. "work_format": "remote", "hybrid", or "office"
5. "experience": required experience years or range
6. "location": city/location

Return ONLY valid JSON, no other text.

Vacancy: {vacancy.get('title', '')}
Description: {vacancy.get('description', '')[:3000]}"""

    try:
        resp = requests.post(
            llm["endpoint"],
            headers={
                "Authorization": f"Bearer {llm['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": llm["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 1000,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        result = json.loads(content)
        result["method"] = "llm"
        result["confidence"] = "verified"
        return result
    except Exception as e:
        return _analyze_vacancy_keyword(vacancy)


def collect_company_from_hh(hh_employer_id: str) -> dict:
    """Fetch basic company data from HH employer page."""
    if not hh_employer_id:
        return {"data_confidence": "not_found"}
    url = f"https://hh.ru/employer/{hh_employer_id}"
    try:
        resp = requests.get(url, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
        }, timeout=10)
        resp.raise_for_status()
    except Exception:
        return {"data_confidence": "not_found", "hh_employer_id": hh_employer_id}

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "lxml")

    result = {"hh_employer_id": hh_employer_id, "data_confidence": "extracted"}

    rating_tag = soup.find("span", attrs={"data-qa": "employer-rating"})
    if rating_tag:
        try:
            result["hh_rating"] = float(rating_tag.get_text(strip=True))
        except ValueError:
            pass

    recommend_tag = soup.find("span", attrs={"data-qa": "employer-recommend-percent"})
    if recommend_tag:
        try:
            result["hh_recommend_pct"] = int(recommend_tag.get_text(strip=True).rstrip("%"))
        except ValueError:
            pass

    website_tag = soup.find("a", attrs={"data-qa": "employer-website"})
    if website_tag:
        result["website"] = website_tag.get("href")

    return result


def _build_text(vacancy: dict) -> str:
    parts = [vacancy.get("title", ""), vacancy.get("description", "")]
    skills = vacancy.get("skills", [])
    if isinstance(skills, list):
        parts.extend(skills)
    elif isinstance(skills, str):
        parts.append(skills)
    return " ".join(parts)


_KEYWORD_POOL = [
    "project management", "pm", "product management", "product owner",
    "delivery management", "agile", "scrum", "kanban", "lean",
    "управление проектами", "руководитель проектов", "менеджер проектов",
    "продукт", "развитие", "стратегия", "методология", "процессы",
    "enterprise", "интеграция", "dwh", "bi", "data", "аналитика",
    "команда", "team", "lead", "координация", "взаимодействие",
    "remote", "удалёнка", "гибрид", "hybrid",
    "b2b", "b2g", "крупный заказчик", "системная интеграция",
    "импортозамещение", "цифровизация", "трансформация",
    "есть", "agile coach", "pmo", "portfolio management",
]


def _extract_section(text: str, headers: list[str]) -> list[str]:
    lines = text.split("\n")
    result = []
    capturing = False
    for line in lines:
        stripped = line.strip().lower()
        if any(h in stripped for h in headers):
            capturing = True
            continue
        if capturing:
            if stripped and len(stripped) > 10:
                result.append(stripped[:200])
            if len(result) >= 5:
                break
    return result


def _extract_keywords(text: str, pool: list[str]) -> list[str]:
    found = []
    for kw in pool:
        if re.search(re.escape(kw), text, re.IGNORECASE):
            found.append(kw)
    return found
