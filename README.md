# ValueHunt 🎯

**Job Search Analytics Dashboard for IT Professionals**

Track your IT job applications, measure funnel conversion, score vacancies with UES (Universal Evaluation Score), and visualize everything in a beautiful HTML dashboard — all offline, open-source, and free.

> Built as a portfolio project by an IT Project Manager who wanted data-driven answers to:  
> *"Where am I in the funnel? Which companies respond? What's my conversion rate?"*

---

## ✨ Features

- **Application Tracker** — Log applications with company, position, source, and UES score
- **Funnel Analytics** — Visual funnel: Viewed → Invited → Interview → Offer → Accepted
- **Conversion Rates** — Know your % at every stage
- **Dashboard** — Auto-generated HTML with Chart.js charts
- **Demo Data** — 65 realistic applications ready to explore
- **Zero Dependencies** — Pure Python stdlib + Chart.js (CDN)

## 📊 Dashboard Preview

*Dashboard showing funnel, conversion rates, timeline, score distribution, and top companies — generated as a static HTML page with Chart.js charts.*

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/outmilker/valuehunt.git
cd valuehunt

# 2. Run (pure Python — no pip install needed!)
python src/report.py

# 3. Open
open output/index.html
```

### With virtual environment (optional)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python src/report.py
```

## 📈 What Gets Measured

| Metric | Description |
|--------|-------------|
| Total Applications | All submitted applications |
| Companies Reached | Unique employers contacted |
| Avg UES Score | Mean score across all scored vacancies |
| Funnel Steps | Viewed → Invited → Interview → Offer → Accepted |
| Conversion Rates | % flow between funnel stages |
| Application Velocity | Applications per day / per week |
| Top Companies | Most-applied employers |
| Industry Breakdown | Distribution across industries |
| Score Distribution | How scores spread (0–10 scale) |

## 🏗️ Architecture

```
valuehunt/
├── src/
│   ├── models.py     # SQLite schema & connection
│   ├── tracker.py    # CRUD for applications
│   ├── analytics.py  # Funnel, conversion, stats
│   └── report.py     # HTML dashboard generator
├── data/
│   └── demo_data.py  # 65 demo applications
├── docs/
│   ├── PRD.md        # Product requirements
│   └── architecture.md
├── output/
│   └── index.html    # Generated dashboard
├── .github/workflows/
│   └── demo.yml      # GitHub Actions → Pages
└── README.md
```

## 🌐 GitHub Pages Demo

The dashboard auto-deploys daily to GitHub Pages:

👉 **https://outmilker.github.io/valuehunt/**

Trigger a manual rebuild from **Actions → Generate Dashboard → Run workflow**.

## 🧠 UES Score (Universal Evaluation Score)

Each vacancy is scored 0–10 based on:

| Factor | Weight |
|--------|--------|
| Role match | 35% |
| Company rating | 35% |
| Personal fit | 30% |

Scores are used to prioritize applications and track which vacancy types perform best.

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Database | SQLite |
| Charts | Chart.js (CDN) |
| CI/CD | GitHub Actions |
| Hosting | GitHub Pages |
| Dependencies | Zero (stdlib only) |

## 📄 License

MIT — free to use, modify, and share.

## 🙋 Why This Project?

This is a portfolio project demonstrating:

- **Product thinking** — PRD, architecture decisions, user stories
- **Data modeling** — Relational schema for job search tracking
- **Analytics engineering** — Funnel metrics, conversion calculations
- **Full-stack awareness** — Python backend → HTML/JS frontend
- **DevOps** — GitHub Actions CI/CD, GitHub Pages deployment
- **Communication** — Clear documentation, visual dashboards

---

*Built with ❤️ by an IT Project Manager who believes every job search should be data-driven.*
