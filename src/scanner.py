import os
import requests
from typing import Optional

HH_API_BASE = "https://api.hh.ru"
HH_USER_AGENT = "JobMatch/1.0 (brel.denis@gmail.com)"


class HHScanner:
    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("HH_ACCESS_TOKEN", "")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": HH_USER_AGENT,
        })
        if self.access_token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.access_token}"
            })

    def search_vacancies(self, params: dict) -> list[dict]:
        url = f"{HH_API_BASE}/vacancies"
        response = self.session.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("items", [])

    def get_vacancy_details(self, vacancy_id: str) -> dict:
        url = f"{HH_API_BASE}/vacancies/{vacancy_id}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def build_search_params(self, profile: dict) -> dict:
        filters = profile.get("search_filters", {})
        params = {
            "text": " ".join(filters.get("keywords", [])),
            "area": self._resolve_areas(filters.get("regions", [])),
            "professional_role": ",".join(
                str(r) for r in filters.get("professional_roles", [])
            ),
            "industry": ",".join(filters.get("industries", [])),
            "per_page": 50,
            "order_by": "publication_time",
        }
        return {k: v for k, v in params.items() if v}

    @staticmethod
    def _resolve_areas(regions: list[str]) -> str:
        area_map = {
            "Москва": "1",
            "Санкт-Петербург": "2",
        }
        codes = [area_map.get(r) for r in regions if area_map.get(r)]
        return ",".join(codes) if codes else ""


def run_scan(profile: dict, token: str) -> list[dict]:
    scanner = HHScanner(access_token=token)
    params = scanner.build_search_params(profile)
    items = scanner.search_vacancies(params)
    results = []
    for item in items:
        details = scanner.get_vacancy_details(item["id"])
        results.append({
            "hh_id": details["id"],
            "title": details.get("name"),
            "company": details.get("employer", {}).get("name"),
            "url": details.get("alternate_url"),
            "salary_from": details.get("salary", {}).get("from"),
            "salary_to": details.get("salary", {}).get("to"),
            "description": details.get("description"),
            "skills": [s["name"] for s in details.get("key_skills", [])],
        })
    return results
