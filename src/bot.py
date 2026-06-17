import os
import logging
from typing import Optional

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
logger = logging.getLogger(__name__)


class JobMatchBot:
    def __init__(self, token: Optional[str] = None):
        self.token = token or TELEGRAM_TOKEN

    def send_message(self, chat_id: str, text: str) -> bool:
        logger.info(f"[BOT] Send to {chat_id}: {text[:50]}...")
        return True

    def send_vacancy_alert(self, chat_id: str, vacancy: dict) -> bool:
        lines = [
            f"*{vacancy.get('title', 'Без названия')}*",
            f"Компания: {vacancy.get('company', 'Не указана')}",
            f"Score: {vacancy.get('score', '?')} ({vacancy.get('category', '?')})",
            f"Ссылка: {vacancy.get('url', '')}",
        ]
        return self.send_message(chat_id, "\n".join(lines))


def run_bot(token: str) -> JobMatchBot:
    return JobMatchBot(token=token)
