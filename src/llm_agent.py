import os
import json
from typing import Optional

LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
LLM_MODEL = "deepseek-chat"
LLM_BASE_URL = "https://api.deepseek.com"


class LLMAgent:
    def __init__(self, api_key: Optional[str] = None, model: str = LLM_MODEL):
        self.api_key = api_key or LLM_API_KEY
        self.model = model

    def analyze_vacancy(self, vacancy: dict) -> dict:
        return {
            "role_type": "unknown",
            "remote_real": False,
            "enterprise_scale": 5,
            "culture_notes": "",
            "risks": [],
            "score_estimate": 5,
            "summary": "",
        }

    def weekly_reflection(self, analytics_data: dict) -> str:
        return ""


def run_llm_analysis(vacancy: dict) -> dict:
    agent = LLMAgent()
    return agent.analyze_vacancy(vacancy)
