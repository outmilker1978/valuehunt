import re
import json
import sys
import yaml
from pathlib import Path

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "ues_config.json"
MATRIX_YAML_PATH = BASE_DIR / "config" / "matrix.yaml"

DEFAULT_UES_CONFIG = {
    "profile_name": "Active Search",
    "gates": {
        "gate_a": {
            "remote": {"pass": ["remote", "hybrid"], "fail": ["office"]},
            "salary": {"min_pass": 200000, "target": 250000},
            "location": {"pass": ["msk", "spb", "remote"]},
        },
    },
    "scoring": {
        "match_curve": [
            {"matches": 0, "score": 5.0},
            {"matches": 1, "score": 6.0},
            {"matches": 2, "score": 7.0},
            {"matches": 3, "score": 8.0},
            {"matches": 4, "score": 9.0},
        ],
        "zero_keyword_default": 5.0,
        "stretch": {"enabled": False, "threshold": 5.0, "factor": 0.3},
        "classify": [
            {"min_score": 8.0, "category": "S", "recommendation": "apply_now"},
            {"min_score": 6.0, "category": "A", "recommendation": "apply"},
            {"min_score": 5.7, "category": "B", "recommendation": "apply_caution"},
            {"min_score": 5.0, "category": "C", "recommendation": "skip"},
        ],
        "override": {"company_min": 6.5, "fit_min": 6.0},
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


def load_matrix_keywords(path: str | Path | None = None) -> dict:
    """Load matrix.yaml and return {criterion_id: {keywords, weight, group_id, group_weight, ...}}."""
    path = Path(path) if path else MATRIX_YAML_PATH
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    result = {}
    for group in data.get("groups", []):
        gid = group["id"]
        gw = group.get("weight", 5)
        for crit in group.get("criteria", []):
            cid = crit["id"]
            result[cid] = {
                "name": crit.get("name", cid),
                "keywords": crit.get("keywords", []),
                "weight": crit.get("weight", 5),
                "group_id": gid,
                "group_name": group.get("name", gid),
                "group_weight": gw,
            }
    return result


def load_matrix_blocks(path: str | Path | None = None) -> list:
    """Load blocks from matrix.yaml."""
    path = Path(path) if path else MATRIX_YAML_PATH
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("blocks", [])


def load_matrix_gates(path: str | Path | None = None) -> dict:
    """Load gates (gate_b) from matrix.yaml."""
    path = Path(path) if path else MATRIX_YAML_PATH
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("gates", {})


def load_matrix_full(path: str | Path | None = None) -> dict:
    """Load full matrix.yaml dict."""
    path = Path(path) if path else MATRIX_YAML_PATH
    if not path.exists():
        return {"blocks": [], "gates": {}, "groups": []}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class UESCalculator:
    def __init__(self, config: dict | None = None):
        self.config = config or load_ues_config()
        self.scoring = self.config.get("scoring", DEFAULT_UES_CONFIG["scoring"])

    def evaluate(self, vacancy: dict, company: dict | None = None, resume_keywords: list[str] | None = None) -> dict:
        # Step 0: Check blocks (red flags) — reject immediately if matched
        block_result = self._check_blocks(vacancy)
        if block_result["rejected"]:
            risks = [{"level": "🔴", "text": r} for r in block_result["reasons"]]
            return {
                "score": 0,
                "category": "REJECT",
                "gate_a": {"passed": False, "reasons": block_result["reasons"]},
                "gate_b": {"passed": False, "reasons": [], "archetypes": [], "source": "blocked"},
                "override_applied": False,
                "groups": [{"id": "blocked", "name": "Заблокировано", "weight": 1, "score": 0, "criteria": []}],
                "risks": risks[:5],
                "recommendation": "skip",
            }

        gate_a = self._check_gate_a(vacancy)
        gate_b = self._check_gate_b(vacancy, resume_keywords)

        # Score groups — always, regardless of gates
        groups = self._score_groups(vacancy, company)
        override_applied = False

        # Override: when gate_a fails but gate_b passes and scores are high
        if not gate_a["passed"] and gate_b["passed"]:
            override = self._check_override(gate_a, gate_b, groups)
            if override["applied"]:
                gate_a["passed"] = True
                gate_a["override_reason"] = override["reason"]
                override_applied = True

        final_score, category = self._compute_final(groups, {"applied": override_applied})
        risks = self._generate_risks(gate_a, gate_b, groups)
        recommendation = self._classify_recommendation(category)

        return {
            "score": round(final_score, 2),
            "category": category,
            "gate_a": gate_a,
            "gate_b": gate_b,
            "override_applied": override_applied,
            "groups": groups,
            "risks": risks,
            "recommendation": recommendation,
        }

    def _build_text(self, vacancy: dict) -> str:
        parts = [
            vacancy.get("title") or "",
            vacancy.get("description") or "",
        ]
        skills = vacancy.get("skills", [])
        if isinstance(skills, list):
            parts.extend(skills)
        elif isinstance(skills, str):
            parts.append(skills)
        text = " ".join(parts).lower()
        # Normalize Russian: replace ё with е, common for job descriptions
        text = text.replace("ё", "е")
        return text

    def _check_blocks(self, vacancy: dict) -> dict:
        """Check block rules from matrix.yaml. Returns {'rejected': bool, 'reasons': list}."""
        text = self._build_text(vacancy).lower()
        title = (vacancy.get("title") or "").lower()
        blocks = load_matrix_blocks()
        reasons = []
        for block in blocks:
            if block.get("mode") != "reject":
                continue
            target = block.get("target", "full_text")
            haystack = text if target == "full_text" else title
            for kw in block.get("keywords", []):
                if re.search(re.escape(kw.lower().replace("ё", "е")), haystack, re.IGNORECASE):
                    reasons.append(f'Блок: {block["name"]} (найдено: "{kw}")')
                    break
        return {"rejected": len(reasons) > 0, "reasons": reasons}

    def _check_gate_a(self, vacancy: dict) -> dict:
        gates = self.config["gates"]["gate_a"]
        results = {}
        passed = True
        reasons = []

        # A1 Remote — priority: HH structured data > text heuristics
        is_remote = False
        is_hybrid = False
        work_format = (vacancy.get("work_format") or "").lower()
        if work_format in ("office",):
            results["remote"] = "fail"
            passed = False
            reasons.append("A1: Формат работы — офис (по данным HH)")
        elif work_format in ("remote", "hybrid"):
            results["remote"] = "pass"
            is_remote = work_format == "remote"
            is_hybrid = work_format == "hybrid"
        else:
            # Fallback: text analysis for weak signals
            raw_parts = [
                vacancy.get("title") or "",
                vacancy.get("description") or "",
            ]
            skills = vacancy.get("skills", [])
            if isinstance(skills, list):
                raw_parts.extend(skills)
            elif isinstance(skills, str):
                raw_parts.append(skills)
            raw_text = " ".join(raw_parts).lower()
            raw_text_norm = raw_text.replace("ё", "е")

            raw_is_remote = any(kw in raw_text_norm for kw in
                ["remote", "удален", "wfh", "work from home", "дистанционно"])
            raw_is_hybrid = any(kw in raw_text_norm for kw in ["hybrid", "гибрид", "смешан"])
            is_office = any(kw in raw_text_norm for kw in ["office", "офис", "full day", "полный день"]) and not (raw_is_remote or raw_is_hybrid)
            if raw_is_remote or raw_is_hybrid:
                results["remote"] = "pass"
                is_remote = raw_is_remote
                is_hybrid = raw_is_hybrid
            else:
                results["remote"] = "fail"
                passed = False
                reasons.append("A1: Не указана удалёнка или гибрид")

        # A2 Salary — с учётом net/gross
        def _to_net(salary_value: float | int | None, text: str) -> float | None:
            if salary_value is None:
                return None
            text_lower = text.lower()
            # Сначала ищем модификатор в тексте (описание вакансии)
            if re.search(r'\b(?:gross|до вычета|до уплаты налогов|до вычета налогов)\b', text_lower):
                return round(float(salary_value) * 0.87)
            # Если в тексте нет модификатора, смотрим по умолчанию: gross
            return float(salary_value)

        desc_text = (vacancy.get("description") or "") + " " + (vacancy.get("title") or "")
        salary_from = vacancy.get("salary_from")
        salary_to = vacancy.get("salary_to")
        salary_from_net = _to_net(salary_from, desc_text) if salary_from else None
        salary_to_net = _to_net(salary_to, desc_text) if salary_to else None
        min_pass = gates["salary"]["min_pass"]
        target = gates["salary"]["target"]
        if salary_from_net is not None and salary_from_net >= min_pass:
            results["salary"] = "pass"
            gross_tag = ""
            if salary_from != salary_from_net:
                gross_tag = f" (gross→{salary_from_net:.0f} net)"
            if salary_from_net >= target:
                results["salary_detail"] = f"от {salary_from_net:.0f} ≥ {target}{gross_tag}"
            else:
                results["salary_detail"] = f"от {salary_from_net:.0f} ≥ {min_pass}, можно обсудить {target}{gross_tag}"
        elif salary_from_net is not None and salary_from_net < min_pass:
            results["salary"] = "fail"
            results["salary_detail"] = f"от {salary_from_net:.0f} < {min_pass}"
            passed = False
            reasons.append(f"A2: ЗП от {salary_from_net:.0f} ниже порога {min_pass}")
        elif not salary_from and salary_to_net is not None and salary_to_net >= target:
            results["salary"] = "pass"
            results["salary_detail"] = f"до {salary_to_net:.0f} ≥ {target}"
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
        if is_remote or is_hybrid:
            results["location"] = "pass"
        elif any(city in location for city in ["москв", "санкт-петербург", "spb", "msk"]):
            results["location"] = "pass"
        else:
            results["location"] = "fail"
            passed = False
            reasons.append("A3: Локация вне Москвы/СПб, не удалёнка и не гибрид")

        return {
            "passed": passed,
            "reasons": reasons,
            "details": results,
        }

    def _check_gate_b(self, vacancy: dict, resume_keywords: list[str] | None = None) -> dict:
        """Gate B — Archetype fit check from matrix.yaml (word match mode)."""
        text = self._build_text(vacancy)

        # Check resume keywords (substring mode — these are the user's CV keywords)
        resume_match = False
        if resume_keywords and len(resume_keywords) > 0:
            for kw in resume_keywords:
                if not kw or len(kw.strip()) < 2:
                    continue
                if re.search(re.escape(kw.strip()), text, re.IGNORECASE):
                    resume_match = True
                    break

        # Read gate_b from matrix.yaml — word match mode
        gates = load_matrix_gates().get("gate_b", {})
        matched = []
        for arch_id, arch in gates.items():
            keywords = arch.get("keywords", [])
            match_mode = arch.get("match_mode", "word")
            arch_label = arch_id.replace("archetype_", "")
            for kw in keywords:
                kw_norm = kw.strip().lower().replace("ё", "е")
                if match_mode == "word":
                    pattern = r'(?<!\w)' + re.escape(kw_norm) + r'(?!\w)'
                else:
                    pattern = re.escape(kw_norm)
                if re.search(pattern, text, re.IGNORECASE):
                    matched.append(arch_label)
                    break
            if matched:
                break

        if resume_match or matched:
            return {"passed": True, "archetypes": matched or ["resume_match"], "source": "resume_keywords" if resume_match else "config"}
        return {"passed": False, "archetypes": [], "reason": "Ни один архетип не совпал"}

    def _score_groups(self, vacancy: dict, company: dict | None) -> list:
        """Score groups using matrix.yaml criteria and keywords.
        All criteria participate — non-matching get 5.0 (neutral / expected).
        Criteria with weight=0 are excluded. Groups with all weight=0 criteria are skipped."""
        matrix_keywords = load_matrix_keywords()
        text = self._build_text(vacancy)

        # Phase 1: compute scores for all non-zero criteria
        scored = []
        for cid, cdef in matrix_keywords.items():
            cw = cdef.get("weight", 0)
            if cw == 0:
                continue
            if not cdef.get("keywords"):
                score = self.scoring.get("zero_keyword_default", 5.0)
            else:
                score = self._rate_criterion_keywords(cid, cdef, text, vacancy)
            scored.append((cid, cdef, cw, score))

        # Phase 2: build groups — all criteria included (non-matching = 5.0)
        group_map = {}
        for cid, cdef, cw, score in scored:
            gid = cdef["group_id"]
            if gid not in group_map:
                group_map[gid] = {
                    "id": gid,
                    "name": cdef["group_name"],
                    "weight": cdef["group_weight"],
                    "criteria": [],
                }
            group_map[gid]["criteria"].append({
                "id": cid,
                "name": cdef["name"],
                "weight": cw,
                "score": score,
            })

        results = []
        for gid, g in group_map.items():
            if g["weight"] == 0:
                continue
            criteria = g["criteria"]
            if not criteria:
                continue
            raw_max = sum(c["weight"] * 10 for c in criteria)
            raw = sum(c["score"] * c["weight"] for c in criteria)
            group_score = round(raw / raw_max * 10, 2) if raw_max > 0 else 0
            results.append({
                "id": gid,
                "name": g["name"],
                "weight": g["weight"],
                "score": group_score,
                "criteria": criteria,
            })
        return results

    def _rate_criterion_keywords(self, cid: str, cdef: dict, text: str, vacancy: dict) -> float:
        keywords = cdef.get("keywords", [])
        if not keywords:
            return 6.0
        matches = 0
        for kw in keywords:
            if not kw:
                continue
            kw_norm = kw.strip().lower().replace("ё", "е")
            if re.search(re.escape(kw_norm), text, re.IGNORECASE):
                matches += 1
            else:
                words = kw_norm.split()
                if len(words) > 1:
                    sig = [w for w in words if len(w) > 2]
                    if len(sig) >= 2 and all(re.search(re.escape(w), text) for w in sig):
                        matches += 1
        # Look up score from config-driven match_curve
        curve = self.scoring.get("match_curve", [])
        score = 5.0
        for entry in sorted(curve, key=lambda x: x["matches"]):
            if matches >= entry["matches"]:
                score = entry["score"]
        return score

    def _check_override(self, gate_a: dict, gate_b: dict, groups: list) -> dict:
        if gate_a.get("passed"):
            return {"applied": False}
        if not gate_b.get("passed"):
            return {"applied": False}
        g_company = next((g for g in groups if g["id"] == "company"), None)
        g_role = next((g for g in groups if g["id"] == "role"), None)
        g_tech = next((g for g in groups if g["id"] == "tech"), None)
        g_culture = next((g for g in groups if g["id"] == "culture"), None)
        company_score = g_company["score"] if g_company else 0
        fit_scores = [g["score"] for g in [g_role, g_tech, g_culture] if g]
        fit_avg = sum(fit_scores) / len(fit_scores) if fit_scores else 0
        ov = self.scoring.get("override", {})
        c_min = ov.get("company_min", 6.5)
        f_min = ov.get("fit_min", 6.0)
        if company_score >= c_min and fit_avg >= f_min:
            return {
                "applied": True,
                "reason": f"High Potential Override: Company={company_score}≥{c_min}, Fit={fit_avg:.1f}≥{f_min}",
            }
        return {"applied": False}

    def _compute_final(self, groups: list, override: dict) -> tuple:
        total = sum(g["score"] * g["weight"] for g in groups)
        max_total = sum(g["weight"] * 10 for g in groups)
        raw = total / max_total * 10 if max_total > 0 else 0
        # Apply stretch if enabled in config
        stretch = self.scoring.get("stretch", {})
        if stretch.get("enabled") and raw > stretch.get("threshold", 5.0):
            final = min(10.0, raw + (raw - stretch["threshold"]) * stretch.get("factor", 0.3))
        else:
            final = raw
        final = round(final, 2)
        category = self._classify(final, override["applied"])
        return final, category

    def _classify(self, score: float, override_applied: bool) -> str:
        levels = self.scoring.get("classify", DEFAULT_UES_CONFIG["scoring"]["classify"])
        for entry in sorted(levels, key=lambda x: -x["min_score"]):
            if score >= entry["min_score"]:
                return entry["category"]
        return "REJECT" if not override_applied else "C"

    def _classify_recommendation(self, category: str) -> str:
        levels = self.scoring.get("classify", DEFAULT_UES_CONFIG["scoring"]["classify"])
        for entry in levels:
            if entry["category"] == category:
                return entry.get("recommendation", "skip")
        return "skip"

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

    def _reject(self, gate_a: dict, gate_b: dict, groups: list | None = None) -> dict:
        risks = []
        if not gate_a.get("passed"):
            for r in gate_a.get("reasons", []):
                risks.append({"level": "🔴", "text": r})
        if groups:
            total = sum(g["score"] * g["weight"] for g in groups)
            max_total = sum(g["weight"] * 10 for g in groups)
            score = round(total / max_total * 10, 2) if max_total > 0 else 0
        else:
            score = 0
        category = self._classify(score, False)
        return {
            "score": score,
            "category": category,
            "gate_a": gate_a,
            "gate_b": gate_b,
            "override_applied": False,
            "groups": groups if groups else [{"id": "rejected", "name": "Отклонено", "score": 0, "criteria": []}],
            "risks": risks[:5],
            "recommendation": "skip",
        }
