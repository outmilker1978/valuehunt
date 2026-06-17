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

    def build_search_params(self, profile: dict) -> dict:
        filters = profile.get("search_filters", {})
        text_parts = filters.get("titles", [])
        if not text_parts:
            text_parts = ["IT project manager", "product manager"]
        text = " OR ".join(text_parts[:5])
        params = {
            "text": text,
            "area": self._resolve_areas(filters.get("regions", [])),
            "professional_role": ",".join(
                str(r) for r in filters.get("professional_roles", [107, 73])
            ),
            "order_by": "publication_time",
            "per_page": "50",
            "search_period": "7",
        }
        # Remove empty values
        return {k: v for k, v in params.items() if v}

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
        c_tag = soup.find(
            "span",
            attrs={"data-qa": "vacancy-company-name"},
        )
        if c_tag:
            company = c_tag.get_text(strip=True)

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


def run_scan(profile: dict) -> list[dict]:
    scanner = HHScanner()
    params = scanner.build_search_params(profile)
    items = scanner.search_vacancies(params)
    results = []
    for item in items:
        if item.get("url"):
            details = scanner.get_vacancy_details(item["url"])
            item.update(details)
            results.append(item)
    return results
