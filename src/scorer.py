import yaml
from pathlib import Path
from typing import Any

MATRIX_PATH = Path(__file__).resolve().parent.parent / "config" / "matrix.yaml"


class VacancyScorer:
    def __init__(self, matrix_path: str | Path = MATRIX_PATH):
        with open(matrix_path, encoding="utf-8") as f:
            self.matrix = yaml.safe_load(f)
        self.groups = self.matrix.get("groups", [])

    def calculate(self, vacancy: dict) -> dict:
        group_scores = []
        for group in self.groups:
            group_score = self._score_group(group, vacancy)
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

    def _score_group(self, group: dict, vacancy: dict) -> dict:
        criteria = group.get("criteria", [])
        scores = []
        for c in criteria:
            rating = self._rate_criterion(c, vacancy)
            scores.append({
                "id": c["id"],
                "name": c["name"],
                "rating": rating,
                "weight": c["weight"],
            })

        total_criteria_weight = sum(s["weight"] for s in scores)
        group_score = (
            sum(s["rating"] * s["weight"] for s in scores) / total_criteria_weight
            if total_criteria_weight > 0 else 0
        )

        return {
            "id": group["id"],
            "name": group["name"],
            "weight": group["weight"],
            "score": round(group_score, 2),
            "criteria": scores,
        }

    def _rate_criterion(self, criterion: dict, vacancy: dict) -> float:
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
