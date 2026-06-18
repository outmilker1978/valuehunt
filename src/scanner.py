import re
from urllib.parse import urljoin, urlencode

import requests
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
        self.session.headers.update({"User-Agent": HH_USER_AGENT})

    def search_vacancies(self, params: dict) -> list[dict]:
        response = self.session.get(HH_SEARCH_URL, params=params)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        items = []

        for card in soup.find_all("div", class_=re.compile(r"vacancy-card")):
            item = self._parse_card(card)
            if item:
                items.append(item)

        return items

    def get_vacancy_details(self, vacancy_url: str) -> dict:
        response = self.session.get(vacancy_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        return self._parse_detail(soup)

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
        text_parts = filters.get("titles", [])
        if not text_parts:
            text_parts = ["IT project manager", "product manager"]
        text = " OR ".join(text_parts[:5])

        salary_from = filters.get("salary_from") or profile.get("salary_expectation")

        param_spec = {
            "text": text,
            "area": self._resolve_areas(filters.get("regions", [])),
            "professional_role": ",".join(
                str(r) for r in filters.get("professional_roles", [107, 73])
            ),
            "order_by": "publication_time",
            "per_page": "50",
            "search_period": filters.get("search_period", "7"),
            "experience": self._flatten_param(filters.get("experience")),
            "employment": self._flatten_param(filters.get("employment")),
            "schedule": self._flatten_param(filters.get("schedule")),
            "salary": self._flatten_param(salary_from),
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

        company = ""
        hh_employer_id = None
        c_tag = soup.find(
            "span",
            attrs={"data-qa": "vacancy-company-name"},
        )
        if c_tag:
            company = c_tag.get_text(strip=True)
            parent_a = c_tag.find_parent("a")
            if parent_a:
                href = parent_a.get("href", "")
                m = re.search(r"/employer/(\d+)", href)
                if m:
                    hh_employer_id = m.group(1)
        if not hh_employer_id:
            employer_link = soup.find("a", attrs={"data-qa": "vacancy-employer-profile"})
            if employer_link:
                href = employer_link.get("href", "")
                m = re.search(r"/employer/(\d+)", href)
                if m:
                    hh_employer_id = m.group(1)

        desc = ""
        d_tag = soup.find(
            "div",
            attrs={"data-qa": "vacancy-description"},
        )
        if d_tag:
            desc = d_tag.get_text(" ", strip=True)

        skills = []
        for s_tag in soup.find_all(
            "span",
            attrs={"data-qa": "bloko-tag__text"},
        ):
            skills.append(s_tag.get_text(strip=True))
        if not skills:
            for s_tag in soup.find_all(
                "span",
                attrs={"data-qa": "skills-element"},
            ):
                skills.append(s_tag.get_text(strip=True))
        if not skills:
            skill_section = soup.find(
                "div",
                attrs={"data-qa": "vacancy-skill-list"},
            )
            if skill_section:
                for tag in skill_section.find_all("li"):
                    skills.append(tag.get_text(strip=True))

        return {
            "title": title,
            "company": company,
            "hh_employer_id": hh_employer_id,
            "description": desc,
            "skills": skills,
        }

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
    def _resolve_areas(regions: list[str]) -> str:
        area_map = {
            "Москва": "1",
            "Санкт-Петербург": "2",
        }
        codes = [area_map.get(r) for r in regions if area_map.get(r)]
        return ",".join(codes) if codes else ""


def run_scan(profile: dict, with_ues: bool = True) -> list[dict]:
    scanner = HHScanner()
    params = scanner.build_search_params(profile)
    items = scanner.search_vacancies(params)
    results = []
    for item in items:
        if item.get("url"):
            details = scanner.get_vacancy_details(item["url"])
            item.update(details)
            if with_ues:
                _enrich_with_ues(item, profile)
            results.append(item)
    return results


def _enrich_with_ues(vacancy: dict, profile: dict):
    from src.ues import UESCalculator
    from src.collector import analyze_vacancy_llm
    analysis = analyze_vacancy_llm(vacancy)
    vacancy.update(analysis)

    # Detect work_format and location from text
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
    for city in ["москв", "санкт-петербург", "msk", "spb"]:
        if city in text:
            vacancy["location"] = {"москв": "Москва", "санкт-петербург": "Санкт-Петербург",
                                    "msk": "Москва", "spb": "Санкт-Петербург"}.get(city, city)
            break
    # UES evaluation
    ues = UESCalculator()
    result = ues.evaluate(vacancy)
    vacancy["score"] = result["score"]
    vacancy["category"] = result["category"]
    vacancy["gate_a_result"] = result["gate_a"]
    vacancy["gate_b_result"] = result["gate_b"]
    vacancy["override_applied"] = result["override_applied"]
    vacancy["risks"] = result["risks"]
    vacancy["recommendation"] = result["recommendation"]
    vacancy["groups"] = result["groups"]
