import random
from datetime import datetime, timedelta
from src.models import init_db, get_connection
from src.tracker import add_application, update_status

random.seed(42)

COMPANIES = [
    ("Яндекс", "IT"),
    ("СберТех", "IT"),
    ("Т-Банк", "Fintech"),
    ("VK", "IT"),
    ("Ozon Tech", "E-commerce"),
    ("Wildberries", "E-commerce"),
    ("Avito", "IT"),
    ("Ланит", "IT Consulting"),
    ("Инфосистемы Джет", "IT Consulting"),
    ("Nexign", "Telecom"),
    ("Диасофт", "Fintech"),
    ("Luxms", "IT Consulting"),
    ("IBS", "IT Consulting"),
    ("КРОК", "IT Consulting"),
    ("Positive Technologies", "Cybersecurity"),
    ("Kaspersky Lab", "Cybersecurity"),
    ("Билайн", "Telecom"),
    ("МТС", "Telecom"),
    ("Ростелеком", "Telecom"),
    ("Газпромнефть-ЦР", "Oil & Gas"),
    ("РЖД", "Transport"),
    ("Аэрофлот Тех", "Aviation"),
    ("1С", "Software"),
    ("СКБ Контур", "Software"),
    ("Softline", "IT Consulting"),
    ("МойОфис", "Software"),
    ("Аквариус", "Hardware"),
    ("YADRO", "Hardware"),
    ("Selectel", "Cloud"),
    ("HuntFlow", "HR Tech"),
    ("Альфа-Банк", "Fintech"),
    ("Открытие", "Fintech"),
    ("ВТБ", "Fintech"),
    ("Райффайзенбанк", "Fintech"),
    ("Тинькофф", "Fintech"),
    ("EPS", "IT Consulting"),
    ("Рексофт", "IT Consulting"),
    ("Аплана", "IT Consulting"),
    ("КОРУС Консалтинг", "IT Consulting"),
    ("Форсайт", "Software"),
    ("ДоксВижн", "Software"),
]

POSITIONS = [
    "IT Project Manager",
    "Product Manager",
    "Senior IT Project Manager",
    "Program Manager",
    "Delivery Manager",
    "Project Manager (Enterprise)",
    "Product Owner",
    "Digital Project Manager",
    "Technical Project Manager",
    "Head of PMO",
]

SOURCES = ["hh", "linkedin", "habr", "telegram"]

STATUSES = ["viewed", "invited", "interview", "offer", "rejected", "accepted"]

STATUS_WEIGHTS = [0.50, 0.20, 0.15, 0.05, 0.08, 0.02]


def generate():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM activities")
    conn.execute("DELETE FROM applications")
    conn.execute("DELETE FROM companies")
    conn.commit()
    conn.close()

    today = datetime.now()
    applications = []

    for i in range(65):
        days_ago = random.randint(0, 90)
        applied = today - timedelta(days=days_ago)
        applied_str = applied.strftime("%Y-%m-%d")

        company_name, industry = random.choice(COMPANIES)
        position = random.choice(POSITIONS)

        score = round(random.uniform(2.0, 9.8), 2)
        source = random.choice(SOURCES)

        status = random.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]

        app_id = add_application(
            company_name=company_name,
            position=position,
            applied_at=applied_str,
            industry=industry,
            source=source,
            url=f"https://hh.ru/vacancy/{random.randint(100000, 999999)}",
            score=score,
            notes=f"Demo application #{i + 1} — {position} at {company_name}",
        )

        if status in ("invited", "interview", "offer", "rejected", "accepted"):
            invite_day = days_ago - random.randint(1, 14)
            invite_date = today - timedelta(days=invite_day)
            update_status(
                app_id, "invited",
                activity_date=invite_date.strftime("%Y-%m-%d"),
                description="Invitation received",
            )

        if status in ("interview", "offer", "rejected", "accepted"):
            interview_day = days_ago - random.randint(3, 21)
            interview_date = today - timedelta(days=interview_day)
            update_status(
                app_id, "interview",
                activity_date=interview_date.strftime("%Y-%m-%d"),
                description="Interview completed",
            )

        if status in ("offer", "rejected", "accepted"):
            reply_day = days_ago - random.randint(5, 28)
            reply_date = today - timedelta(days=reply_day)
            if status == "offer":
                update_status(
                    app_id, "offer",
                    activity_date=reply_date.strftime("%Y-%m-%d"),
                    description="Offer received",
                )
            elif status == "rejected":
                update_status(
                    app_id, "rejected",
                    activity_date=reply_date.strftime("%Y-%m-%d"),
                    description="Rejected after interview",
                )

        if status == "accepted":
            accept_day = days_ago - random.randint(7, 30)
            accept_date = today - timedelta(days=accept_day)
            update_status(
                app_id, "accepted",
                activity_date=accept_date.strftime("%Y-%m-%d"),
                description="Offer accepted",
            )

        applications.append(
            {"company": company_name, "position": position, "status": status, "score": score}
        )

    print(f"Inserted {len(applications)} demo applications")
    return applications


if __name__ == "__main__":
    generate()
