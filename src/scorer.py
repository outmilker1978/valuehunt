import re
import yaml
from pathlib import Path

MATRIX_PATH = Path(__file__).resolve().parent.parent / "config" / "matrix.yaml"


class VacancyScorer:
    def __init__(self, matrix_path: str | Path = MATRIX_PATH):
        with open(matrix_path, encoding="utf-8") as f:
            self.matrix = yaml.safe_load(f)
        self.groups = self.matrix.get("groups", [])

    def calculate(self, vacancy: dict) -> dict:
        text = self._build_text(vacancy)
        group_scores = []
        for group in self.groups:
            group_score = self._score_group(group, vacancy, text)
            group_scores.append(group_score)

        total_weight = sum(g["weight"] for g in self.groups)
        final_score = (
            sum(gs["score"] * gs["weight"] for gs in group_scores) / total_weight
            if total_weight > 0 else 0
        )
        category = self._classify(final_score)

        return {
            "score": round(final_score, 2),
            "category": category,
            "groups": group_scores,
        }

    def _build_text(self, vacancy: dict) -> str:
        parts = [
            vacancy.get("title", ""),
            vacancy.get("description", ""),
        ]
        skills = vacancy.get("skills", [])
        if isinstance(skills, list):
            parts.extend(skills)
        elif isinstance(skills, str):
            parts.append(skills)
        return " ".join(parts).lower()

    def _score_group(self, group: dict, vacancy: dict, text: str) -> dict:
        criteria = group.get("criteria", [])
        scores = []
        for c in criteria:
            rating = self._rate_criterion(c, vacancy, text)
            scores.append({
                "id": c["id"],
                "name": c["name"],
                "rating": rating,
                "weight": c["weight"],
            })

        total_weight = sum(s["weight"] for s in scores)
        group_score = (
            sum(s["rating"] * s["weight"] for s in scores) / total_weight
            if total_weight > 0 else 0
        )

        return {
            "id": group["id"],
            "name": group["name"],
            "weight": group["weight"],
            "score": round(group_score, 2),
            "criteria": scores,
        }

    def _rate_criterion(self, criterion: dict, vacancy: dict, text: str) -> float:
        cid = criterion["id"]

        if cid == "salary_fix":
            return self._rate_salary_fix(vacancy)
        if cid == "salary_transparent":
            return self._rate_salary_transparent(vacancy)
        if cid == "no_outstaff":
            return self._rate_no_outstaff(text)

        keywords = criterion.get("keywords", [])
        if not keywords:
            return 5.0

        matches = sum(1 for kw in keywords if re.search(re.escape(kw), text))
        ratio = matches / len(keywords)
        return round(1 + ratio * 9, 1)

    @staticmethod
    def _rate_salary_fix(vacancy: dict) -> float:
        salary_from = vacancy.get("salary_from")
        if salary_from and int(salary_from) >= 250000:
            return 10.0
        if salary_from and int(salary_from) >= 200000:
            return 7.0
        if salary_from and int(salary_from) >= 150000:
            return 4.0
        salary_to = vacancy.get("salary_to")
        if salary_to and int(salary_to) >= 300000:
            return 6.0
        return 3.0

    @staticmethod
    def _rate_salary_transparent(vacancy: dict) -> float:
        has_from = vacancy.get("salary_from") is not None
        has_to = vacancy.get("salary_to") is not None
        if has_from and has_to:
            return 10.0
        if has_from or has_to:
            return 7.0
        return 3.0

    @staticmethod
    def _rate_no_outstaff(text: str) -> float:
        positive = ["прямой найм", "direct hire", "в штат", "штат",
                     "in-house", "собственная разработка"]
        negative = ["аутстафф", "outstaff", "outsource", "аутсорс", "аутсорсинг"]

        pos_matches = sum(1 for kw in positive if re.search(re.escape(kw), text))
        neg_matches = sum(1 for kw in negative if re.search(re.escape(kw), text))

        if neg_matches > 0:
            return 2.0
        if pos_matches > 0:
            return 8.0
        return 5.0

    @staticmethod
    def _classify(score: float) -> str:
        if score >= 8.5:
            return "A"
        elif score >= 7.0:
            return "Б"
        elif score >= 6.0:
            return "В"
        return "мимо"


def run_scorer(vacancy: dict, matrix_path: str | Path = MATRIX_PATH) -> dict:
    scorer = VacancyScorer(matrix_path=matrix_path)
    return scorer.calculate(vacancy)
