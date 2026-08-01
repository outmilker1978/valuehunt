import os
import re
import json
import requests
from urllib.parse import urljoin, urlparse

DEEPSEEK_API = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})


# ─── Vacancy analysis ──────────────────────────────────────────

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
    tasks = _extract_section(text, ["задачи", "чем предстоит заниматься", "обязанности",
                                      "что нужно делать", "key responsibilities",
                                      "вам предстоит", "задачи, с которыми предстоит"])
    requirements = _extract_section(text, ["требования", "qualifications", "must have",
                                            "что мы ждём", "что мы ждем",
                                            "мы ждём, что вы", "мы ждем, что вы",
                                            "мы ждём от кандидата", "мы ждем от кандидата",
                                            "необходимые навыки",
                                            "мы ищем", "кого мы ищем", "будет плюсом",
                                            "наши ожидания", "что мы ожидаем",
                                            "вы нам подходите, если",
                                            "какие знания и навыки",
                                            "идеальный кандидат",
                                            "что для нас важно", "что важно для нас",
                                            "для нас важн", "что ждём от кандидата",
                                            "что ждем от кандидата",
                                            "что для этого необходимо",
                                            "что ждём от тебя", "что ждем от тебя"])
    key_words = _extract_keywords(text, _KEYWORD_POOL)
    section_text = " ".join(tasks + requirements)
    if section_text:
        extra = _extract_keywords(section_text, _KEYWORD_POOL)
        key_words.extend(kw for kw in extra if kw not in key_words)
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
5. "location": city/location
Return ONLY valid JSON, no other text.
Vacancy: {vacancy.get('title', '')}
Description: {vacancy.get('description', '')[:3000]}"""
    try:
        resp = SESSION.post(llm["endpoint"], headers={
            "Authorization": f"Bearer {llm['api_key']}",
            "Content-Type": "application/json",
        }, json={
            "model": llm["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1000,
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        result = json.loads(content)
        result["method"] = "llm"
        result["confidence"] = "verified"
        return result
    except Exception:
        return _analyze_vacancy_keyword(vacancy)


# ─── Company: HH employer page ─────────────────────────────────

def collect_company_from_hh(hh_employer_id: str) -> dict:
    if not hh_employer_id:
        return {"data_confidence": "not_found"}
    url = f"https://hh.ru/employer/{hh_employer_id}"
    try:
        resp = SESSION.get(url, timeout=10)
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


# ─── Company: Yandex search ────────────────────────────────────

def collect_company_from_yandex(company_name: str) -> dict:
    """Search Yandex for '[company] отзывы', parse snippets."""
    result = {"data_confidence": "not_found", "yandex_snippets": []}
    if not company_name:
        return result
    query = f"{company_name} отзывы"
    url = "https://yandex.ru/search"
    try:
        resp = SESSION.get(url, params={"text": query, "numdoc": "10"}, timeout=10)
        resp.raise_for_status()
    except Exception:
        return result

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "lxml")

    snippets = []
    for item in soup.find_all("li", class_=re.compile(r"serp-item")):
        link = item.find("a", href=True)
        text_block = item.find("span", class_=re.compile(r"text|extended|snippet"))
        if not link or not text_block:
            continue
        snip = text_block.get_text(strip=True)
        if snip and len(snip) > 30:
            snippets.append({
                "url": link["href"],
                "text": snip[:500],
            })
        if len(snippets) >= 5:
            break

    if not snippets:
        # fallback: try picking any text blocks
        for div in soup.find_all("div", class_=re.compile(r"organic|content|snippet"), limit=8):
            texts = div.get_text(" ", strip=True)
            if texts and len(texts) > 40:
                snippets.append({"url": "", "text": texts[:500]})
            if len(snippets) >= 5:
                break

    if snippets:
        result["yandex_snippets"] = snippets
        result["data_confidence"] = "extracted"
    return result


# ─── Company: website ──────────────────────────────────────────

def collect_company_from_website(company_url: str) -> dict:
    """Fetch company website, extract about/values/culture pages."""
    result = {"data_confidence": "not_found"}
    if not company_url:
        return result
    if not company_url.startswith("http"):
        company_url = "https://" + company_url
    try:
        resp = SESSION.get(company_url, timeout=10)
        resp.raise_for_status()
    except Exception:
        return result

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "lxml")
    page_text = soup.get_text(" ", strip=True)[:5000]
    result["main_text"] = page_text

    # Extract about/career page URLs
    domain = urlparse(company_url).netloc
    about_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if any(kw in text for kw in ["about", "о компании", "about us", "about company",
                                       "карьера", "career", "why us", "ценности",
                                       "values", "culture"]):
            full_url = urljoin(company_url, href)
            if domain in full_url and full_url != company_url:
                about_links.append(full_url)

    # Fetch up to 2 inner pages (about + careers)
    extra_texts = []
    for link in about_links[:2]:
        try:
            r = SESSION.get(link, timeout=8)
            r.raise_for_status()
            s = BeautifulSoup(r.text, "lxml")
            extra_texts.append(s.get_text(" ", strip=True)[:3000])
        except Exception:
            pass

    all_text = page_text + "\n" + "\n".join(extra_texts)
    result["website_text"] = all_text[:8000]
    result["data_confidence"] = "extracted"

    # Extract culture tags from text
    culture_kw = {
        "innovation": ["инновации", "innovation", "технологии", "technology", "digital"],
        "people": ["люди", "people", "team", "команда", "таланты", "talent"],
        "result": ["результат", "result", "quality", "качество", "excellence"],
        "agile": ["agile", "scrum", "гибкие", "lean", "быстро"],
        "enterprise": ["enterprise", "крупный", "корпоративный", "b2b", "b2g"],
        "startup": ["startup", "стартап", "growth", "рост", "масштабирование"],
    }
    low = all_text.lower()
    tags = []
    for tag, kws in culture_kw.items():
        if any(kw in low for kw in kws):
            tags.append(tag)
    result["culture_tags"] = tags
    return result


# ─── Orchestrator ──────────────────────────────────────────────

def collect_all_company_data(company_name: str, hh_employer_id: str = None,
                              website: str = None) -> dict:
    """Run all 3 collectors and merge results."""
    result = {"name": company_name, "data_confidence": "not_found"}

    # 1. HH
    if hh_employer_id:
        hh_data = collect_company_from_hh(hh_employer_id)
        result.update(hh_data)
        if hh_data.get("hh_rating"):
            result["data_confidence"] = "extracted"
        if not website and hh_data.get("website"):
            website = hh_data["website"]

    # 2. Website (use HH website or company name)
    site_url = website or f"https://{company_name.lower().replace(' ', '')}.ru"
    if site_url:
        try:
            site_data = collect_company_from_website(site_url)
            if site_data.get("data_confidence") == "extracted":
                result["website_text"] = site_data.get("website_text")
                result["culture_tags"] = site_data.get("culture_tags")
                result["data_confidence"] = "extracted"
        except Exception:
            pass

    # 3. Yandex search
    try:
        ya_data = collect_company_from_yandex(company_name)
        if ya_data.get("data_confidence") == "extracted":
            result["yandex_snippets"] = ya_data.get("yandex_snippets")
    except Exception:
        pass

    return result


# ─── Helpers ───────────────────────────────────────────────────

def _build_text(vacancy: dict) -> str:
    parts = [vacancy.get("title", ""), vacancy.get("description", "")]
    skills = vacancy.get("skills", [])
    if isinstance(skills, list):
        parts.extend(skills)
    elif isinstance(skills, str):
        parts.append(skills)
    return "\n".join(parts)


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
    "agile coach", "pmo", "portfolio management",
]


_SECTION_STOP_WORDS = [
    "обязанности", "задачи", "требования", "мы ищем", "кого мы ищем",
    "что мы ждём", "что мы ждем",
    "мы ждём, что вы", "мы ждем, что вы",
    "наши ожидания", "будет плюсом", "ключевые навыки",
    "мы предлагаем", "что мы предлагаем", "условия", "преимущества",
    "бенефиты", "чем предстоит заниматься", "о вас", "о нас",
]


def _extract_section(text: str, headers: list[str]) -> list[str]:
    result = []
    lines = text.split("\n")
    if len(lines) > 1:
        capturing = False
        for line in lines:
            stripped = line.strip().lower()
            # Start capture on matching header
            if any(h in stripped for h in headers):
                capturing = True
                continue
            if capturing:
                if not stripped:
                    continue
                # Stop on next section header (short line with a section word)
                if any(w in stripped for w in _SECTION_STOP_WORDS) and len(stripped) < 60 and (stripped.endswith(":") or stripped.endswith(".") or len(stripped) < 40):
                    capturing = False
                    continue
                if len(stripped) > 10:
                    result.append(stripped[:200])
                if len(result) >= 5:
                    break
    # Fallback: extract from continuous text after header match
    if not result:
        low = text.lower()
        for h in headers:
            idx = low.find(h)
            if idx >= 0:
                chunk = text[idx + len(h):idx + len(h) + 500]
                import re as _re
                for sentence in _re.split(r'(?<=[.!?])\s+', chunk):
                    sentence = sentence.strip()
                    if sentence and len(sentence) > 10:
                        result.append(sentence[:200])
                    if len(result) >= 5:
                        break
            if len(result) >= 5:
                break
    return result


def _extract_keywords(text: str, pool: list[str]) -> list[str]:
    return [kw for kw in pool if re.search(re.escape(kw), text, re.IGNORECASE)]
