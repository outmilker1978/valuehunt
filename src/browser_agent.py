import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BrowserAgent:
    def __init__(self, headless: bool = True):
        self.headless = headless

    async def respond_to_vacancy(self, vacancy_url: str, resume_type: str = "01") -> bool:
        logger.info(
            f"[BROWSER] Would respond to {vacancy_url} with resume {resume_type}"
        )
        return True

    async def close(self):
        pass


def run_browser_agent(headless: bool = True) -> BrowserAgent:
    return BrowserAgent(headless=headless)
