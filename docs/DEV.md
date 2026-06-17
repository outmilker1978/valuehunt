# JobMatch — Developer Documentation

## Prerequisites

- Python 3.12+
- Git
- GitHub account
- HH API access token (see USER.md)

## Setup

```bash
# Clone repository
git clone <repo-url> personal-recruiter
cd personal-recruiter

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Create environment file
cp .env.example .env
# Edit .env with your tokens
```

## Project Structure

```
personal-recruiter/
├── src/                    # Source code
│   ├── scanner.py          # HH API parser
│   ├── scorer.py           # Vacancy scoring engine
│   ├── llm_agent.py        # LLM analysis (future)
│   ├── bot.py              # Telegram bot
│   ├── browser_agent.py    # Playwright auto-respond (future)
│   ├── db.py               # SQLite models
│   └── reporter.py         # Weekly reports (future)
├── config/                 # Configuration
│   ├── profile.json        # User profile + search filters
│   └── matrix.yaml         # Scoring matrix (7 groups)
├── data/                   # Local data (gitignored)
├── docs/                   # Dashboard + docs
├── .github/workflows/      # CI/CD
├── requirements.txt
└── README.md
```

## Modules

### scanner.py — HH API Parser

Class `HHScanner` fetches vacancies from HeadHunter API.

```python
from src.scanner import HHScanner

scanner = HHScanner(access_token="your_token")
params = {"text": "Project Manager", "area": "1,2"}  # Moscow + SPb
items = scanner.search_vacancies(params)
details = scanner.get_vacancy_details(items[0]["id"])
```

**Methods:**
- `search_vacancies(params)` — search with HH filters, returns list
- `get_vacancy_details(id)` — full vacancy description
- `build_search_params(profile)` — build params from profile.json

### scorer.py — Scoring Engine

Class `VacancyScorer` evaluates a vacancy against the matrix.

```python
from src.scorer import VacancyScorer

scorer = VacancyScorer()
result = scorer.calculate(vacancy_dict)
# Returns: { "score": 7.5, "category": "Б", "groups": [...] }
```

**Scoring logic (v0.1, keyword-based):**
1. Build search text from title + description + skills (lowercased)
2. For each criterion, match keywords against text via regex
3. Convert match ratio to 1-10 scale
4. Special rules: salary_fix checks numeric value, no_outstaff penalizes outstaff keywords
5. Final Score = weighted average across all groups

**Categories:**
| Score | Category | Action |
|-------|----------|--------|
| 8.5-10 | A | Ideal match |
| 7.0-8.4 | Б | Strong match |
| 6.0-6.9 | В | Compromise |
| < 6.0 | — | Skip |

### db.py — SQLite Database

```python
from src.db import init_db, get_connection, save_vacancy

init_db()
conn = get_connection()
save_vacancy(conn, vacancy_data)
```

**Tables:** profile, matrix, vacancies, contacts, communications, analytics

### bot.py — Telegram Bot (stub)

Placeholder for python-telegram-bot integration.

## Configuration

### profile.json

```json
{
  "name": "Брель Денис",
  "hh_resume_id": "your_resume_id",
  "search_filters": {
    "regions": ["Санкт-Петербург", "Москва"],
    "titles": ["PM", "Product Manager", "PO"],
    "professional_roles": [107, 73],
    "keywords": ["Enterprise", "Senior"]
  }
}
```

### matrix.yaml

7 groups with criteria, weights, and keywords for scoring.

## GitHub Actions

Workflow `.github/workflows/daily_scanner.yml` runs every 4 hours.

**Secrets required:**
- `HH_ACCESS_TOKEN` — HH API token
- `DEEPSEEK_API_KEY` — DeepSeek API key (future)
- `TELEGRAM_BOT_TOKEN` — Telegram bot token (future)
- `TELEGRAM_CHAT_ID` — Your Telegram chat ID (future)

## Roadmap

### v0.1 (current)
- [x] Project structure
- [x] Config: profile.json, matrix.yaml
- [x] HH API scanner
- [x] Keyword-based scorer
- [ ] Telegram bot (/today, /stats)
- [ ] GitHub Actions cron
- [ ] SQLite persistence
- [ ] Dashboard (GitHub Pages)

### v0.2
- [ ] LLM agent (DeepSeek)
- [ ] Auto-response via Playwright
- [ ] Better scoring with semantic analysis
- [ ] Weekly reflection reports

### v1.0
- [ ] Tauri desktop app
- [ ] CRM with reminders
- [ ] Full analytics dashboard
