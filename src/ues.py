import re
import json
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "ues_config.json"

DEFAULT_UES_CONFIG = {
    "profile_name": "Active Search",
    "gates": {
        "gate_a": {
            "remote": {"pass": ["remote", "hybrid"], "fail": ["office"]},
            "salary": {"min_pass": 200000, "target": 250000},
            "location": {"pass": ["msk", "spb", "remote"]},
        },
        "gate_b": {
            "archetype_01": {
                "keywords": [
                    "project manager", "pm", "delivery manager", "program manager",
                    "enterprise", "руководитель проектов", "менеджер проектов",
                    "pmo", "pmo-менеджер", "управление проектами",
                ],
            },
            "archetype_03": {
                "keywords": [
                    "product manager", "product owner", "po", "продукт",
                    "продуктовый менеджер", "владелец продукта", "продукт-менеджер",
                    "product", "hybrid pm", "pm/po",
                ],
            },
        },
    },
    "groups": {
        "company": {
            "weight": 35,
            "criteria": {
                "employment_type": {"weight": 9, "name": "Тип занятости"},
                "enterprise_scale": {"weight": 8, "name": "Enterprise-масштаб"},
                "culture": {"weight": 7, "name": "Культура и репутация"},
                "brand_stability": {"weight": 6, "name": "Бренд и стабильность"},
                "values_alignment": {"weight": 5, "name": "Ценностное совпадение"},
            },
        },
        "vacancy": {
            "weight": 35,
            "criteria": {
                "driver_alignment": {"weight": 10, "name": "Драйверы и задачи"},
                "tech_stack": {"weight": 7, "name": "Технологический стек"},
                "benefits": {"weight": 6, "name": "Бенефиты"},
                "career_path": {"weight": 6, "name": "Карьерный трек"},
                "training": {"weight": 6, "name": "Обучение"},
            },
        },
        "personal_fit": {
            "weight": 30,
            "criteria": {
                "experience_match": {"weight": 9, "name": "Опыт и навыки"},
                "domain_match": {"weight": 7, "name": "Отраслевой опыт"},
                "geo_compatibility": {"weight": 7, "name": "Гео-совместимость"},
                "cultural_compatibility": {"weight": 7, "name": "Культурная совместимость"},
            },
        },
    },
}


def load_ues_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict:
    path = Path(path)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_UES_CONFIG


def save_ues_config(config: dict, path: str | Path = DEFAULT_CONFIG_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


class UESCalculator:
    def __init__(self, config: dict | None = None):
        self.config = config or DEFAULT_UES_CONFIG

    def evaluate(self, vacancy: dict, company: dict | None = None) -> dict:
        gate_a = self._check_gate_a(vacancy)
        gate_b = self._check_gate_b(vacancy)

        if gate_a["passed"] and gate_b["passed"]:
            pass
        elif not gate_a["passed"] or not gate_b["passed"]:
            partial = self._score_groups(vacancy, company)
            override = self._check_override(gate_a, partial)
            if override["applied"]:
                gate_a["passed"] = True
                gate_a["override_reason"] = override["reason"]
                groups = partial
                final_score, category = self._compute_final(groups, override)
                risks = self._generate_risks(gate_a, gate_b, groups)
                return {
                    "score": round(final_score, 2),
                    "category": category,
                    "gate_a": gate_a,
                    "gate_b": gate_b,
                    "override_applied": True,
                    "groups": groups,
                    "risks": risks,
                    "recommendation": "apply_terms",
                }
            else:
                return self._reject(gate_a, gate_b)

        groups = self._score_groups(vacancy, company)
        final_score, category = self._compute_final(groups, {"applied": False})
        risks = self._generate_risks(gate_a, gate_b, groups)
        recommendation = self._classify_recommendation(category)

        return {
            "score": round(final_score, 2),
            "category": category,
            "gate_a": gate_a,
            "gate_b": gate_b,
            "override_applied": False,
            "groups": groups,
            "risks": risks,
            "recommendation": recommendation,
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

    def _check_gate_a(self, vacancy: dict) -> dict:
        text = self._build_text(vacancy)
        gates = self.config["gates"]["gate_a"]
        results = {}
        passed = True
        reasons = []

        # A1 Remote
        wf = (vacancy.get("work_format") or "").lower()
        title_lower = (vacancy.get("title") or "").lower()
        desc_lower = (vacancy.get("description") or "").lower()
        is_remote = any(kw in text for kw in ["remote", "удалён", "удален", "wfh", "work from home", "дистанционно"])
        is_hybrid = any(kw in text for kw in ["hybrid", "гибрид", "смешан"])
        is_office = any(kw in text for kw in ["office", "офис", "full day", "полный день"]) and not is_remote
        if is_remote or is_hybrid:
            results["remote"] = "pass"
        else:
            results["remote"] = "fail"
            passed = False
            reasons.append("A1: Не указана удалёнка или гибрид")

        # A2 Salary
        salary_from = vacancy.get("salary_from")
        salary_to = vacancy.get("salary_to")
        min_pass = gates["salary"]["min_pass"]
        target = gates["salary"]["target"]
        if salary_from and salary_from >= min_pass:
            results["salary"] = "pass"
            if salary_from >= target:
                results["salary_detail"] = f"от {salary_from} ≥ {target}"
            else:
                results["salary_detail"] = f"от {salary_from} ≥ {min_pass}, можно обсудить {target}"
        elif salary_from and salary_from < min_pass:
            results["salary"] = "fail"
            results["salary_detail"] = f"от {salary_from} < {min_pass}"
            passed = False
            reasons.append(f"A2: ЗП от {salary_from} ниже порога {min_pass}")
        elif not salary_from and salary_to and salary_to >= target:
            results["salary"] = "pass"
            results["salary_detail"] = f"до {salary_to} ≥ {target}"
        elif not salary_from:
            results["salary"] = "pass"
            results["salary_detail"] = "ЗП не указана — можно предложить свою"
        else:
            results["salary"] = "fail"
            passed = False
            reasons.append(f"A2: ЗП не соответствует порогу")

        # A3 Location
        location = (vacancy.get("location") or "").lower()
        loc_pass = gates["location"]["pass"]
        if is_remote:
            results["location"] = "pass"
        elif any(city in location for city in ["москв", "санкт-петербург", "spb", "msk"]):
            results["location"] = "pass"
        else:
            results["location"] = "fail"
            passed = False
            reasons.append("A3: Локация вне Москвы/СПб и не удалёнка")

        return {
            "passed": passed,
            "reasons": reasons,
            "details": results,
        }

    def _check_gate_b(self, vacancy: dict) -> dict:
        text = self._build_text(vacancy)
        gates = self.config["gates"]["gate_b"]
        matched = []
        for arch_id, arch in gates.items():
            keywords = arch.get("keywords", [])
            arch = arch_id.replace("archetype_", "")
            if any(re.search(re.escape(kw), text, re.IGNORECASE) for kw in keywords):
                matched.append(arch)
                break
        if not matched:
            return {"passed": False, "archetypes": [], "reason": "Ни один архетип не совпал"}
        return {"passed": True, "archetypes": matched}

    def _score_groups(self, vacancy: dict, company: dict | None) -> dict:
        groups_config = self.config["groups"]
        text = self._build_text(vacancy)
        results = []
        for group_id, group_cfg in groups_config.items():
            criteria_scores = []
            for cid, cc in group_cfg["criteria"].items():
                score = self._rate_criterion(cid, cc, vacancy, company, text)
                criteria_scores.append({
                    "id": cid,
                    "name": cc["name"],
                    "weight": cc["weight"],
                    "score": score,
                })
            group_raw_max = sum(c["weight"] * 10 for c in criteria_scores)
            group_raw = sum(c["score"] * c["weight"] for c in criteria_scores)
            group_score_out_of_10 = round(group_raw / group_raw_max * 10, 2) if group_raw_max > 0 else 0
            results.append({
                "id": group_id,
                "name": {
                    "company": "Компания",
                    "vacancy": "Вакансия",
                    "personal_fit": "Личное соответствие",
                }.get(group_id, group_id),
                "weight": group_cfg["weight"],
                "score": group_score_out_of_10,
                "criteria": criteria_scores,
            })
        return results

    def _rate_criterion(self, cid: str, cc: dict, vacancy: dict, company: dict | None, text: str) -> float:
        kw_map = {
            "employment_type": {
                "positive": ["полная занятость", "full-time", "full time", "direct hire", "прямой найм", "в штат"],
                "negative": ["outstaff", "аутстафф", "outsource", "аутсорс"],
            },
            "enterprise_scale": {
                "positive": ["enterprise", "крупный", "корпоративный", "big data", "highload", "тысяч пользователей"],
            },
            "culture": {
                "positive": ["agile", "scrum", "kanban", "feedback", "обратная связь",
                              "развитие", "training", "обучение", "менторство"],
            },
            "brand_stability": {
                "positive": ["топ работодатель", "best employer", "рейтинг", "стабильный",
                              "крупнейший", "лидер рынка", "аккредитован"],
            },
            "values_alignment": {
                "positive": ["ценности", "values", "миссия", "mission", "культура",
                              "прозрачность", "openness"],
            },
            "driver_alignment": {
                "positive": ["руководитель", "управление", "lead", "leadership", "координация",
                              "методология", "процессы", "стратегия", "развитие"],
            },
            "tech_stack": {
                "positive": ["dwh", "bi", "data", "аналитика", "etl", "integration",
                              "системная интеграция", "api", "cloud"],
            },
            "benefits": {
                "positive": ["дмс", "dms", "страхование", "спорт", "gym", "питание",
                              "lunch", "соцпакет", "social package"],
            },
            "career_path": {
                "positive": ["карьерный рост", "грейд", "grade", "повышение", "promotion",
                              "карьера", "senior", "lead", "руководитель"],
            },
            "training": {
                "positive": ["обучение", "training", "курсы", "courses", "конференции",
                              "certification", "сертификация", "образование"],
            },
            "experience_match": {
                "positive": ["project management", "управление проектами", "менеджер проектов",
                              "pm", "product management", "team lead"],
            },
            "domain_match": {
                "positive": ["интеграция", "integration", "enterprise", "крупный",
                              "b2b", "b2g", "dwh", "bi", "data"],
            },
            "geo_compatibility": {
                "positive": ["удалённо", "remote", "гибрид", "hybrid", "санкт-петербург",
                              "москва", "командировки", "business trips"],
            },
            "cultural_compatibility": {
                "positive": ["agile", "scrum", "kanban", "гибкие методологии",
                              "результат", "result", "команда", "team"],
            },
        }
        mapping = kw_map.get(cid)
        if not mapping:
            return 5.0
        positive = mapping.get("positive", [])
        negative = mapping.get("negative", [])
        pos_matches = sum(1 for kw in positive if re.search(re.escape(kw), text, re.IGNORECASE))
        neg_matches = sum(1 for kw in negative if re.search(re.escape(kw), text, re.IGNORECASE))
        if neg_matches > pos_matches:
            return 3.0
        if pos_matches == 0:
            return 5.0
        boost = min(pos_matches / 2.0, 1.0) * 5.0
        return round(5.0 + boost, 1)

    def _check_override(self, gate_a: dict, groups: list) -> dict:
        if gate_a.get("passed"):
            return {"applied": False}
        g1 = next((g for g in groups if g["id"] == "company"), None)
        g3 = next((g for g in groups if g["id"] == "personal_fit"), None)
        v1 = None
        if groups:
            for g in groups:
                for c in g.get("criteria", []):
                    if c["id"] == "driver_alignment":
                        v1 = c["score"]
        g1_score = g1["score"] if g1 else 0
        g3_score = g3["score"] if g3 else 0
        if g1_score >= 7.0 and g3_score >= 6.0 and (v1 or 0) >= 7.0:
            return {
                "applied": True,
                "reason": f"High Potential Override: G1={g1_score}≥7, G3={g3_score}≥6, V1={v1}≥7",
            }
        return {"applied": False}

    def _compute_final(self, groups: list, override: dict) -> tuple:
        total = sum(g["score"] * g["weight"] for g in groups)
        max_total = sum(g["weight"] * 10 for g in groups)
        final = total / max_total * 10 if max_total > 0 else 0
        category = self._classify(final, override["applied"])
        return final, category

    def _classify(self, score: float, override_applied: bool) -> str:
        if score >= 8.5:
            return "S"
        elif score >= 7.0:
            return "A"
        elif score >= 6.0:
            return "B"
        elif score >= 5.0:
            return "C"
        else:
            return "REJECT" if not override_applied else "C"

    def _classify_recommendation(self, category: str) -> str:
        return {"S": "apply_now", "A": "apply", "B": "apply_caution", "C": "skip", "REJECT": "skip"}.get(category, "skip")

    def _generate_risks(self, gate_a: dict, gate_b: dict, groups: list) -> list:
        risks = []
        if not gate_a.get("passed"):
            for r in gate_a.get("reasons", []):
                risks.append({"level": "🔴", "text": r})
        for g in groups:
            for c in g.get("criteria", []):
                if c["score"] < 4.0:
                    risks.append({"level": "🟡", "text": f"{c['name']}: низкая оценка ({c['score']}/10)"})
        for g in groups:
            for c in g.get("criteria", []):
                if c["score"] >= 8.0:
                    risks.append({"level": "🟢", "text": f"{c['name']}: высокая оценка ({c['score']}/10)"})
                    break
        return risks[:10]

    def _reject(self, gate_a: dict, gate_b: dict) -> dict:
        risks = []
        if not gate_a.get("passed"):
            for r in gate_a.get("reasons", []):
                risks.append({"level": "🔴", "text": r})
        return {
            "score": 0,
            "category": "REJECT",
            "gate_a": gate_a,
            "gate_b": gate_b,
            "override_applied": False,
            "groups": [{"id": "rejected", "name": "Отклонено", "score": 0, "criteria": []}],
            "risks": risks[:5],
            "recommendation": "skip",
        }
