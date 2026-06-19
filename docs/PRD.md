# ValueHunt — Product Requirements Document

## 1. Product Overview

ValueHunt is an open-source job search tracker and analytics tool for IT professionals. It helps candidates manage applications, track funnel progression, score vacancies using the UES (Universal Evaluation Score), and generate visual dashboards to optimize their job search strategy.

**Tagline:** *Track, score, and win your next IT role.*

---

## 2. Target Audience

- IT professionals actively searching for jobs (PM, PO, developers, analysts)
- Career changers tracking application progress
- Anyone applying to 10+ positions who wants data-driven insights

---

## 3. Problem Statement

Job seekers submit dozens of applications across multiple platforms (HH.ru, LinkedIn, Telegram channels) with no structured way to:
- Track which companies responded
- Measure conversion rates at each funnel stage
- Identify which industries/roles generate the best response
- Analyze their application velocity over time

---

## 4. Core Features (MVP)

| Feature | Description |
|---------|-------------|
| Application Tracker | Log job applications with company, position, source, date |
| Status Workflow | View → Invited → Interview → Offer → Accepted/Rejected |
| Funnel Analytics | Visual funnel with conversion rates at each stage |
| UES Scoring | Rate each vacancy 0–10 using Universal Evaluation Score |
| Dashboard | HTML dashboard with charts: funnel, timeline, score distribution, top companies |
| Demo Data | Pre-populated 65 realistic applications for immediate demo |

---

## 5. User Stories

- As a job seeker, I want to see how many applications I submitted this month
- As a job seeker, I want to know my interview-to-offer conversion rate
- As a job seeker, I want to identify which companies respond most often
- As a job seeker, I want to track which industries have the most openings
- As a PM, I want to showcase a portfolio project with real architecture

---

## 6. Metrics Tracked

- Total applications, companies contacted
- Funnel: viewed → invited → interview → offer → accepted
- Conversion rates at each stage (%)
- Average UES score across all applications
- Average response time (days from application to first reply)
- Application velocity (per day / per week)
- Top companies by application count
- Industry breakdown
- Score distribution (0–10 scale)

---

## 7. Out of Scope (MVP)

- Automated vacancy scraping (delegated to companion tool)
- Cover letter generation
- Integration with HH.ru / LinkedIn APIs
- Multi-user support
- Mobile app

---

## 8. Future Roadmap

- **v0.2** — Telegram bot for quick logging
- **v0.3** — CSV import/export
- **v0.4** — GitHub Actions cron for daily dashboard regeneration
- **v0.5** — Company research integration (rating, reviews)
