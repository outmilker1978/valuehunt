import re
import time
import json
from urllib.parse import urljoin, urlencode

import requests
import cloudscraper
from bs4 import BeautifulSoup

HH_BASE = "https://hh.ru"
HH_SEARCH_URL = f"{HH_BASE}/search/vacancy"
HH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class HHScanner:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": HH_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        })

    def search_vacancies(self, params: dict) -> list[dict]:
        all_items = []
        base_params = dict(params)
        per_page = int(params.get("items_on_page", 100))
        for page in range(5):
            page_params = dict(base_params)
            page_params['page'] = str(page)
            last_exc = None
            for attempt in range(3):
                try:
                    response = self.session.get(HH_SEARCH_URL, params=page_params, timeout=20)
                    if response.status_code in (403, 404, 429):
                        if attempt < 2 and response.status_code != 403:
                            time.sleep((attempt + 1) * 3)
                            continue
                        break
                    response.raise_for_status()
                    html = response.text
                    soup = BeautifulSoup(html, "lxml")
                    items = []
                    for card in soup.find_all("div", class_=re.compile(r"vacancy-card")):
                        item = self._parse_card(card)
                        if item:
                            items.append(item)
                    all_items.extend(items)

                    # Also extract ALL hh_ids from embedded JSON (userLabelsForVacancies)
                    # — catches vacancies rendered client-side by the React SPA
                    json_ids = self._extract_all_ids(html)
                    if json_ids:
                        found_ids = {it["hh_id"] for it in all_items if it.get("hh_id")}
                        for hid in json_ids:
                            if hid not in found_ids:
                                all_items.append({
                                    "hh_id": str(hid),
                                    "url": f"https://hh.ru/vacancy/{hid}",
                                    "title": "",
                                    "company": None,
                                    "salary_from": None,
                                    "salary_to": None,
                                })

                    # If fewer items than per_page, this was the last page
                    if len(items) < per_page:
                        return all_items
                    break
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
                    last_exc = e
                    if attempt < 2:
                        time.sleep((attempt + 1) * 2)
                    continue
            if last_exc:
                break
        return all_items

    def _extract_all_ids(self, html: str) -> list[str]:
        """Extract all vacancy hh_ids from embedded JSON in search results page."""
        m = re.search(r'"userLabelsForVacancies":(\{[^}]+\})', html)
        if not m:
            return []
        try:
            obj = json.loads(m.group(1))
            return list(obj.keys())
        except json.JSONDecodeError:
            return []

    def get_vacancy_details(self, vacancy_url: str) -> dict:
        last_exc = None
        user_agents = [
            HH_USER_AGENT,
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
        ]
        for attempt in range(3):
            try:
                headers = {"Referer": HH_SEARCH_URL, "User-Agent": user_agents[attempt % len(user_agents)]}
                response = self.session.get(vacancy_url, timeout=15, headers=headers)
                if response.status_code in (403, 404):
                    print(f"  [WARN] {response.status_code} for {vacancy_url}")
                    if attempt < 2:
                        time.sleep((attempt + 1) * 5)
                        continue
                    return self._get_vacancy_playwright(vacancy_url) or {}
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "lxml")
                result = self._parse_detail(soup)
                if result.get("_captcha"):
                    if attempt < 2:
                        delay = (attempt + 1) * 8
                        print(f"  [CAPTCHA] retry {attempt+1} in {delay}s...")
                        time.sleep(delay)
                        continue
                    return result
                return result
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
                last_exc = e
                if attempt < 2:
                    time.sleep((attempt + 1) * 3)
                continue
        return self._get_vacancy_playwright(vacancy_url) or {}

    def _get_vacancy_playwright(self, vacancy_url: str) -> dict:
        """Fallback: fetch via Playwright with user's real Chrome profile (headed)."""
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                import os
                user_data = os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\User Data')
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=user_data,
                    channel="chrome",
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                page = context.new_page()
                page.goto(vacancy_url, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_function(
                        "() => { const h = document.querySelector('h1'); return h && !h.innerText.includes('HeadHunter') && !h.innerText.includes('Подтвердите'); }",
                        timeout=40000
                    )
                except Exception:
                    pass
                html = page.content()
                context.close()
                if "Подтвердите" in html[:2000] or "captcha" in html.lower()[:2000]:
                    return {}
                soup = BeautifulSoup(html, "lxml")
                result = self._parse_detail(soup)
                if result.get("title"):
                    print("  [PLAYWRIGHT] vacancy loaded via Chrome")
                    return result
                return {}
        except Exception:
            pass
        return {}

    def _flatten_param(self, val):
        """Convert list or scalar to HH param format."""
        if val is None:
            return None
        if isinstance(val, list):
            if not val:
                return None
            return val  # requests will handle list as repeated param
        s = str(val).strip()
        return s if s else None

    def build_search_params(self, profile: dict) -> dict:
        filters = profile.get("search_filters", {})
        text = filters.get("text", "")
        if not text:
            text_parts = filters.get("titles", ["IT project manager", "product manager"])
            text = " OR ".join(text_parts[:5])

        salary_from = filters.get("salary_from") or filters.get("salary")

        param_spec = {
            "text": text,
            "area": self._resolve_areas(filters.get("regions", [])),
            "professional_role": self._flatten_param(filters.get("professional_roles", [107, 73])),
            "order_by": filters.get("order_by", "publication_time"),
            "items_on_page": filters.get("items_on_page") or filters.get("per_page", "100"),
            "search_period": str(max(1, int(filters.get("search_period") or "1")) + 1) if filters.get("search_period") else None,
            "experience": self._flatten_param(filters.get("experience")),
            "employment_form": self._flatten_param(filters.get("employment") or filters.get("employment_form")),
            "schedule": self._flatten_param(filters.get("schedule")),
            "salary": self._flatten_param(salary_from),
            "salary_mode": filters.get("salary_mode"),
            "search_field": self._flatten_param(filters.get("search_field")),
            "industry": filters.get("industry"),
            "education": filters.get("education"),
            "work_format": self._flatten_param(filters.get("work_format") or filters.get("work_formats")),
            "ored_clusters": "true" if filters.get("ored_clusters") else None,
        }
        return {k: v for k, v in param_spec.items() if self._flatten_param(v) is not None}

    def _parse_card(self, card) -> dict | None:
        try:
            link_tag = card.find("a", attrs={"data-qa": "serp-item__title"})
            if not link_tag:
                return None

            title = link_tag.get_text(strip=True)
            href = link_tag.get("href", "")

            hh_id = None
            id_match = re.search(r"/vacancy/(\d+)", href)
            if id_match:
                hh_id = id_match.group(1)
                href = f"https://hh.ru/vacancy/{hh_id}"

            if not title or not hh_id:
                return None

            company_tag = card.find(
                "a", attrs={"data-qa": "vacancy-serp__vacancy-employer"}
            )
            if not company_tag:
                company_tag = card.find(
                    "span", attrs={"data-qa": "vacancy-serp__vacancy-employer"}
                )
            if not company_tag:
                company_tag = card.find(class_=re.compile(r"company-name"))
            if not company_tag:
                company_tag = card.find(class_=re.compile(r"vacancy-name-wrapper"))
            company = company_tag.get_text(strip=True) if company_tag else None

            salary_tag = card.find(
                "span", attrs={"data-qa": "vacancy-serp__vacancy-compensation"}
            )
            if not salary_tag:
                salary_tag = card.find(class_=re.compile(r"compensation|salary"))
            salary_text = salary_tag.get_text(strip=True) if salary_tag else None
            salary_from, salary_to = self._parse_salary(salary_text)

            return {
                "hh_id": hh_id,
                "title": title,
                "company": company,
                "url": href,
                "salary_from": salary_from,
                "salary_to": salary_to,
            }
        except Exception:
            return None

    def _parse_detail(self, soup) -> dict:
        title = ""
        t_tag = soup.find("h1")
        if t_tag:
            title = t_tag.get_text(strip=True)

        # Captcha / bot check — HH returned a challenge instead of vacancy
        if "Подтвердите, что вы не робот" in title or "captcha" in soup.get_text(" ", strip=True).lower():
            return {"_captcha": True}

        hh_employer_id = None
        company = None
        # Try multiple selectors for company name + employer ID
        for selector, attr in [
            ("span[data-qa='vacancy-company-name']", "href"),
            ("a[data-qa='vacancy-company-name']", "href"),
            ("div[data-qa='vacancy-company'] a", "href"),
            ("a.company-link", "href"),
        ]:
            tag = soup.select_one(selector)
            if tag:
                company = tag.get_text(strip=True)
                href = tag.get(attr or "href", "")
                m = re.search(r"/employer/(\d+)", href)
                if m:
                    hh_employer_id = m.group(1)
                    break
        if not hh_employer_id:
            for a in soup.find_all("a", href=True):
                if "/employer/" in a["href"]:
                    m = re.search(r"/employer/(\d+)", a["href"])
                    if m:
                        hh_employer_id = m.group(1)
                        if not company:
                            company = a.get_text(strip=True)
                        break
        if not hh_employer_id:
            # Try script tag with employer data
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        for key in ["hiringOrganization", "employer"]:
                            val = data.get(key, {})
                            if isinstance(val, dict):
                                eid = val.get("identifier", val.get("@id", ""))
                                if eid:
                                    hh_employer_id = str(eid)
                                if not company:
                                    company = val.get("name") or val.get("legalName")
                except (json.JSONDecodeError, TypeError):
                    pass

        # Extract structured fields from HH vacancy page
        work_format = None
        experience = None
        location = None
        published_at = None

        # Published date
        for div in soup.find_all("div", class_=re.compile(r"magritte-text")):
            text = div.get_text(" ", strip=True)
            if "опубликован" in text.lower():
                date_span = div.find("span")
                if date_span:
                    published_at = date_span.get_text(strip=True)
                else:
                    m = re.search(r'опубликована?\s*(.+?)(?:\s*[вв]\s|$)', text)
                    if m:
                        published_at = m.group(1).strip()
                break

        # Location from HH header (vacancy-view-raw-address)
        loc_el = soup.find(attrs={"data-qa": "vacancy-view-raw-address"})
        if loc_el:
            addr_text = loc_el.get_text(" ", strip=True)
            # Extract city (first meaningful part before comma)
            city = addr_text.split(",")[0].strip()
            if city:
                location = city

        # HR contacts
        hr_contacts = None
        contacts_block = soup.find("div", attrs={"data-qa": "vacancy-contacts"})
        if contacts_block:
            hr_contacts = contacts_block.get_text(" ", strip=True)[:500]
        else:
            contact_section = soup.find("div", attrs={"data-qa": "vacancy-employer-contacts"})
            if contact_section:
                hr_contacts = contact_section.get_text(" ", strip=True)[:500]

        key_skills_block = soup.find("div", attrs={"data-qa": "vacancy-key-skills"})
        if key_skills_block:
            for item in key_skills_block.find_all("div", class_=re.compile(r"vacancy-key-skill")):
                label_tag = item.find("span", class_=re.compile(r"label"))
                value_tag = item.find("span", class_=re.compile(r"value"))
                if label_tag and value_tag:
                    label = label_tag.get_text(strip=True).lower()
                    value = value_tag.get_text(strip=True)
                    if "формат работы" in label or "график" in label:
                        work_format = value.lower()
                    elif "опыт работы" in label:
                        experience = value
                    elif any(w in label for w in ["регион", "город", "адрес", "локация"]):
                        location = value
                    elif any(w in label for w in ["занятость", "оформление"]):
                        if not work_format and "удалён" in value.lower() or "remote" in value.lower():
                            work_format = "remote"

        # Fallback: scan all text for key info
        full_text = soup.get_text(" ", strip=True).lower()
        if not work_format:
            if "формат работы" in full_text:
                idx = full_text.find("формат работы")
                chunk = full_text[idx:idx+200]
                if "удалён" in chunk or "remote" in chunk:
                    work_format = "remote"
                elif "гибрид" in chunk:
                    work_format = "hybrid"
                elif "офис" in chunk or "на месте" in chunk:
                    work_format = "office"
                else:
                    work_format = "office"  # HH: "на месте работодателя" etc → office
            elif "удаленная работа" in full_text:
                work_format = "remote"
            elif "гибрид" in full_text:
                work_format = "hybrid"

        desc = ""

        d_tag = soup.find(
            "div",
            attrs={"data-qa": "vacancy-description"},
        )
        if d_tag:
            desc = d_tag.get_text("\n", strip=True)

        skills = []
        skill_section = soup.find("div", attrs={"data-qa": "vacancy-skill-list"})
        if skill_section:
            for tag in skill_section.find_all("li"):
                skills.append(tag.get_text(strip=True))
        if not skills:
            for s_tag in soup.find_all(
                attrs={"data-qa": "skills-element"},
            ):
                skills.append(s_tag.get_text(strip=True))

        result = {
            "title": title,
            "hh_employer_id": hh_employer_id,
            "description": desc,
            "skills": skills,
        }
        if company:
            result["company"] = company
        if work_format:
            result["work_format"] = work_format
        if experience:
            result["experience"] = experience
        if location:
            result["location"] = location
        if published_at:
            result["published_at"] = published_at
        if hr_contacts:
            result["hr_contacts"] = hr_contacts
        return result

    @staticmethod
    def _parse_salary(text: str | None) -> tuple:
        if not text:
            return None, None
        nums = re.findall(r"\d[\d\u202f\s]*\d", text)
        nums = [int(n.replace("\u202f", "").replace(" ", "")) for n in nums]
        if "от" in text and nums:
            return nums[0], None
        if "до" in text and nums:
            return None, nums[0]
        if len(nums) >= 2:
            return nums[0], nums[1]
        if nums:
            return nums[0], None
        return None, None

    @staticmethod
    def _resolve_areas(regions: list[str]) -> list[str] | None:
        area_map = {
            "Москва": "1",
            "Санкт-Петербург": "2",
            "Россия": "113",
        }
        codes = []
        for r in regions:
            if r.isdigit():
                codes.append(r)
            elif area_map.get(r):
                codes.append(area_map[r])
        return codes if codes else None


def run_scan(profile: dict, with_ues: bool = True, known_ids: set | None = None) -> list[dict]:
    scanner = HHScanner()
    params = scanner.build_search_params(profile)
    items = scanner.search_vacancies(params)
    known = known_ids or set()
    results = []
    for i, item in enumerate(items):
        hh_id = item.get("hh_id")
        if not item.get("url"):
            continue
        # Skip detail fetch for already-known vacancies
        if hh_id and str(hh_id) in known:
            item["_known"] = True
            results.append(item)
            continue
        if i == 0:
            time.sleep(5)
        else:
            time.sleep(3)
        details = scanner.get_vacancy_details(item["url"])
        if not details or details.get("_captcha"):
            reason = "captcha" if details.get("_captcha") else "empty"
            print(f"  [SKIP] {item.get('hh_id','?')} — {reason}")
            continue
        item.update(details)
        if with_ues:
            _enrich_with_ues(item, profile)
        results.append(item)
    return results


def import_vacancy_by_url(url: str, profile: dict | None = None) -> dict | None:
    """Fetch a single HH vacancy by URL, enrich with UES, return dict ready for save_vacancy."""
    m = re.search(r"/vacancy/(\d+)", url)
    if not m:
        return None
    hh_id = m.group(1)
    detail_url = f"https://hh.ru/vacancy/{hh_id}"

    scanner = HHScanner()
    details = scanner.get_vacancy_details(detail_url)
    if not details or not details.get("title"):
        return None

    vacancy = {
        "hh_id": hh_id,
        "url": detail_url,
        "title": details.get("title", ""),
        "company": details.get("company"),
        "hh_employer_id": details.get("hh_employer_id"),
        "description": details.get("description", ""),
        "skills": details.get("skills", []),
        "work_format": details.get("work_format"),
        "location": details.get("location"),
        "experience": details.get("experience"),
        "published_at": details.get("published_at"),
        "hr_contacts": details.get("hr_contacts"),
        "salary_from": details.get("salary_from"),
        "salary_to": details.get("salary_to"),
    }

    if profile:
        _enrich_with_ues(vacancy, profile)
    return vacancy


def _enrich_with_ues(vacancy: dict, profile: dict):
    from src.ues import UESCalculator
    from src.collector import analyze_vacancy_llm
    analysis = analyze_vacancy_llm(vacancy)
    # Keep original HH work_format if available — LLM can override only if HH didn't detect it
    hh_work_format = vacancy.get("work_format")
    vacancy.update(analysis)
    if hh_work_format:
        vacancy["work_format"] = hh_work_format

    # Detect work_format and location (use structured data if available, fallback to text)
    if not vacancy.get("work_format"):
        text = " ".join([
            vacancy.get("title", ""),
            vacancy.get("description", ""),
        ]).lower()
        if any(kw in text for kw in ["remote", "удалён", "wfh", "дистанционно"]):
            vacancy["work_format"] = "remote"
        elif any(kw in text for kw in ["hybrid", "гибрид", "смешан"]):
            vacancy["work_format"] = "hybrid"
        else:
            vacancy["work_format"] = "office"
    if not vacancy.get("location"):
        text = (vacancy.get("title", "") + " " + vacancy.get("description", "")).lower()
        for city, label in {"москв": "Москва", "санкт-петербург": "Санкт-Петербург",
                            "msk": "Москва", "spb": "Санкт-Петербург",
                            "минск": "Минск", "minsk": "Минск",
                            "казан": "Казань", "kzn": "Казань",
                            "екатеринбург": "Екатеринбург", "ekb": "Екатеринбург",
                            "новосибир": "Новосибирск", "nsk": "Новосибирск",
                            "нижний новгород": "Нижний Новгород", "nn": "Нижний Новгород",
                            "самар": "Самара", "краснодар": "Краснодар",
                            "ростов": "Ростов-на-Дону", "уф": "Уфа",
                            "челябинск": "Челябинск", "красноярск": "Красноярск",
                            "перм": "Пермь", "воронеж": "Воронеж",
                            "волгоград": "Волгоград", "тольятти": "Тольятти",
                            "алабуга": "Алабуга", "сочи": "Сочи",
                            "калининград": "Калининград", "тул": "Тула",
                            "твер": "Тверь", "брянск": "Брянск",
                            "рязан": "Рязань", "пенз": "Пенза",
                            "липецк": "Липецк", "астрахан": "Астрахань",
                            "владимир": "Владимир", "смоленск": "Смоленск",
                            "дальний восток": "Дальний Восток", "хабаров": "Хабаровск",
                            "владивосток": "Владивосток", "иркутск": "Иркутск",
                            "томск": "Томск"}.items():
            if city in text:
                vacancy["location"] = label
                break
    # UES evaluation
    ues = UESCalculator()
    resume_kw = profile.get("resume_data", {}).get("keywords", [])
    result = ues.evaluate(vacancy, resume_keywords=resume_kw)
    vacancy["score"] = result["score"]
    vacancy["category"] = result["category"]
    vacancy["gate_a_result"] = result["gate_a"]
    vacancy["gate_b_result"] = result["gate_b"]
    vacancy["override_applied"] = result["override_applied"]
    vacancy["risks"] = result["risks"]
    vacancy["recommendation"] = result["recommendation"]
    vacancy["groups"] = result["groups"]
