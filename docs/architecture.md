# ValueHunt — Architecture Document

## Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Language | Python 3.11+ | Ubiquitous, readable, great for data processing |
| Database | SQLite | Zero-config, portable, file-based |
| Charts | Chart.js (CDN) | Beautiful charts, no build step |
| Reporting | Python string templates | Zero dependencies for HTML generation |
| CI/CD | GitHub Actions | Free, integrated with GitHub Pages |
| Hosting | GitHub Pages | Free static site hosting |

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   valuehunt/                         │
│                                                       │
│  data/                   src/                         │
│  ├── valuehunt.db   ◄───├── models.py                 │
│  ├── demo_data.py       ├── tracker.py                │
│                         ├── analytics.py              │
│  output/                └── report.py ──┐             │
│  └── index.html  ◄──────────────────────┘             │
│                                                       │
│  docs/                   .github/workflows/           │
│  ├── PRD.md              └── demo.yml                 │
│  └── architecture.md                                 │
└─────────────────────────────────────────────────────┘
```

## Data Model

```
┌──────────────┐       ┌──────────────────┐       ┌────────────────┐
│   companies   │       │   applications    │       │   activities    │
├──────────────┤       ├──────────────────┤       ├────────────────┤
│ id (PK)      │◄──────│ company_id (FK)   │       │ id (PK)        │
│ name (UQ)    │       │ id (PK)           │       │ app_id (FK)    │
│ industry     │       │ company_name      │       │ type           │
│ website      │       │ position          │       │ date           │
│ created_at   │       │ industry          │       │ description    │
└──────────────┘       │ source            │       │ created_at     │
                       │ status            │       └────────────────┘
                       │ score (0-10)      │
                       │ applied_at        │
                       │ notes             │
                       └──────────────────┘
```

## Status Workflow

```
viewed ──► invited ──► interview ──► offer ──► accepted
   │          │            │            │
   └──────────┴────────────┴────────────┴──► rejected
```

## Analytics Pipeline

1. **Data Layer** (`models.py`) — SQLite schema and connection management
2. **Tracker** (`tracker.py`) — CRUD operations for applications and activities
3. **Analytics** (`analytics.py`) — Aggregation queries for funnel, conversion, timeline
4. **Reporting** (`report.py`) — Template-based HTML generation with Chart.js

## Key Design Decisions

### SQLite over PostgreSQL
- No server setup required
- Single file, easy to backup and version
- Sufficient for single-user portfolio project

### String Templates over Jinja2
- Zero additional dependencies
- Simple enough for one-page dashboard
- Demonstrates understanding of fundamentals

### Chart.js CDN over Build Step
- No npm/webpack needed
- Instant chart rendering
- Works offline after first load

### Demo Data Script
- Self-contained seed data with realistic company names
- Deterministic (seeded random) for reproducible results
- 65 applications covering all funnel stages

## GitHub Actions Workflow

```yaml
name: Generate Dashboard
on:
  schedule:
    - cron: '0 6 * * *'   # daily at 06:00 UTC
  workflow_dispatch:        # manual trigger

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r requirements.txt
      - run: python src/report.py
      - uses: peaceiris/actions-gh-pages@v3
        with:
          publish_dir: ./output
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

## Deployment

The dashboard is deployed to GitHub Pages:
`https://<username>.github.io/valuehunt/`

The workflow generates a fresh dashboard daily and publishes it automatically.
