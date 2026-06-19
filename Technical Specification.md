# ValueHunt — Product Technical Specification

## Overview

ValueHunt — automated system for searching, evaluating, and applying to IT job vacancies based on the **UES (Unified Evaluation System)** methodology.

The system emulates the decision-making process of an experienced IT recruiter/PM: collects data on the company and vacancy, analyzes compatibility, calculates a score, generates recommendations, and (in Stage 2) automatically sends applications.

---

## Current State (v0.1)

The product can:
- Search for vacancies on HH by filter
- Compare results with a predefined value table
- Output a list of vacancies with compatibility scores
- Filter the list by score

This is a basic keyword/rule matching system with no intelligent analysis.

---

## Target State (v1.0 — Stage 1)

### Core Architecture

```
┌─────────────────────────────────────────────┐
│                  USER INTERFACE              │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐ │
│  │ Dashboard  │  Vacancy     │  Settings     │
│  │ (results)  │  Detail View │  (criteria)   │
│  └─────────┘  └──────────┘  └────────────┘ │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│              ANALYSIS ENGINE                  │
│  ┌────────────────┐  ┌──────────────────┐   │
│  │ HH Parser       │  │   Data Collector  │   │
│  │ (filters + list)│  │   (agent module)  │   │
│  └────────────────┘  └──────────────────┘   │
│  ┌────────────────┐  ┌──────────────────┐   │
│  │  UES Calculator │  │  Decision Engine  │   │
│  │  (scoring)      │  │  (gates + rules)  │   │
│  └────────────────┘  └──────────────────┘   │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│                DATA LAYER                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Vacancies  │  │ Companies │  │ Templates │  │
│  │ (DB)       │  │ (DB)      │  │ (DB)      │  │
│  └──────────┘  └──────────┘  └──────────┘  │
│  ┌──────────┐  ┌──────────┐                │
│  │ Scoring   │  │ Logs      │                │
│  │ Config    │  │ (history) │                │
│  └──────────┘  └──────────┘                │
└─────────────────────────────────────────────┘
```

---

## Component Specification

### 1. HH Parser & Filter Engine

**Function:** Search for vacancies on HH.ru with filters maximally identical to the HH website.

Required filters (matching HH interface):
- **Keywords** (text search with boolean OR: "Руководитель проектов" OR "PM" OR "Delivery Manager"...)
- **Region** (Moscow, Saint Petersburg, remote)
- **Work format** (remote, hybrid, office)
- **Employment type** (full-time, part-time)
- **Experience** (3-6 years, 6+ years)
- **Salary** (from/to)
- ** Industry** (IT, telecommunications, finance...)
- **Company size** (optional)
- **Exclude already applied** (by company name)

**Requirements:**
- Parse HH via official API or direct parsing (legal compliance)
- Update frequency: min 1 time per day, configurable
- Store raw vacancy data before analysis
- Filter should NOT lose vacancies that match the query (HH's own filters must be replicated 1:1)

---

### 2. Data Collector Agent (AI-based)

**Function:** Replicate our manual process of collecting data on the company and vacancy.

For each vacancy, the agent must collect:

#### Track A: Company Data
| Source | What to extract |
|--------|----------------|
| HH employer page | Rating, % recommend, reviews count, Top-XXX status |
| Company website | Products, values, team, blog |
| DreamJob (dreamjob.ru) | Reviews: pros, cons, salary, culture |
| Habr Career (career.habr.com) | Rating, salary by role, reviews |
| TAdviser | Profile, projects, revenue, employees |
| CNews / RBC | Rankings, news, mentions |
| VC.ru / Habr | Publications: culture, tech, cases |
| GitHub | Organization, repos, stack, code quality |
| Social media (VK, TG) | Official channels, posts, engagement |
| General search "[company] отзывы" | Forum discussions, Telegram channels |
| Legal check (ЕГРЮЛ, arbitration court) | Cleanliness, lawsuits, bankruptcy risk |

#### Track B: Vacancy Data
| Source | What to extract |
|--------|----------------|
| HH vacancy text | Tasks, requirements, conditions, stack |
| Task mapping | Each task → match user's experience (Y/N/partial) |
| Requirement mapping | Each requirement → match (Y/N/partial) |
| Key words extraction | 10-15 verbs + nouns for cover letter |
| Format & location | Remote/hybrid/office, city |
| Salary | Stated / not stated / range |
| Stack → intersection | Familiar / not familiar / not needed for PM |
| Drivers → vacancy match | Tasks = drive / neutral / not drive |

**Agent requirements:**
- Use LLM (DeepSeek API, YandexGPT, GigaChat) for text analysis and synthesis
- All data sources must be accessible from Russia (no OpenRouter, no Render)
- Caching: don't re-fetch the same company twice (store in Companies DB)
- Confidence level: mark data as "verified" / "extracted" / "not found" for scoring weighting

---

### 3. UES Calculator (Scoring Engine)

Implement the **UES (Unified Evaluation System)** v2.1 methodology:

#### 3.1 GATE A (Hard Filters)
| Filter | Pass | Fail |
|--------|------|------|
| A1 Remote | Full remote OR hybrid (≥2 days/week, SPb/Msk) | Office-only OR office in other region |
| A2 Salary | Stated ≥200k net OR "by interview" + basis for 250k+ | <200k OR "by interview" for discounter |
| A3 Location | Office in SPb/Msk OR remote | Office in region without remote |

Any fail → REJECT (unless Override applies).

#### 3.2 GATE B (Resume Archetype)
- 01 Enterprise PM: PM, PMO, enterprise, integration ✅
- 03 Product PM-PO: Product, PO, hybrid PM/PO ✅
- Neither → REJECT

#### 3.3 Group 1: Company Score (35 points)

| # | Criterion | Weight | Scale | Source |
|---|-----------|--------|-------|--------|
| C1 | Employment type | 9 | 1-10 | Vacancy format section |
| C2 | Enterprise scale | 8 | 1-10 | Company profile (revenue, employees, clients) |
| C3 | Culture | 7 | 1-10 | HH rating, DreamJob, Habr reviews |
| C4 | Brand/stability | 6 | 1-10 | Rankings, market position, age |
| C5 | Values alignment | 5 | 1-10 | Publications, blog, values page |

#### 3.4 Group 2: Vacancy Score (35 points)

| # | Criterion | Weight | Scale | Source |
|---|-----------|--------|-------|--------|
| V1 | Driver alignment | 10 | 1-10 | Task analysis: match with user drivers |
| V2 | Tech stack | 7 | 1-10 | Stack → user knowledge intersection |
| V3 | Benefits | 6 | 1-10 | DMS, training, career track |
| V4 | Career path | 6 | 1-10 | Growth opportunities, promotions |
| V5 | Training | 6 | 1-10 | Courses, certifications, conferences |

#### 3.5 Group 3: Personal Fit (30 points)

| # | Criterion | Weight | Scale | Source |
|---|-----------|--------|-------|--------|
| F1 | Experience match | 9 | 1-10 | Task mapping from Phase 2B |
| F2 | Domain match | 7 | 1-10 | Industry/domain experience |
| F3 | Geo compatibility | 7 | 1-10 | Remote/SPb/travel/commuting |
| F4 | Cultural compatibility | 7 | 1-10 | Management style, values, team |

#### 3.6 Formula

```
Score = (G1 + G2 + G3) / 1000 × 10

G1 (max 350) = Σ(score × weight) for Group 1
G2 (max 350) = Σ(score × weight) for Group 2
G3 (max 300) = Σ(score × weight) for Group 3
Total max = 1000
```

#### 3.7 Scale

| Score | Category | Meaning |
|:-----:|:--------:|---------|
| 8.5+ | **S** | Ideal — apply immediately |
| 7.0-8.4 | **A** | Strong — apply |
| 6.0-6.9 | **B** | Decent — apply with caution |
| 5.0-5.9 | **C** | Weak — skip unless special |
| <5.0 | **REJECT** | Not worth time |

#### 3.8 Override Rule: "High Potential Override"

If GATE A fails (remote or location), but:
1. G1 (Company) ≥ 7.0
2. G3 (Personal Fit) ≥ 6.0
3. V1 (Drivers) ≥ 7/10

Then **recommend applying "on your terms"**: propose remote with willingness for business trips.

In this case:
- Score calculated as if GATE A passed
- GATE A fail logged as 🟡 risk "requires discussion"
- Cover letter strategy: transparent about format, propose compromise

#### 3.9 Handling "от X" salary notation

"от 230 000 ₽" ≠ "до 230 000 ₽". If salary is stated as "от X" and X is below 250k threshold — it's a PASS (user can propose 250k within the range). Only "до X" or exact amount below threshold counts as FAIL.

---

### 4. Decision Engine

Generates three outputs for each vacancy:

#### Output 1: Score + Category
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCORE: X.X / 10 → [S/A/B/C/REJECT]

Group 1 (Company):    X.X/10
Group 2 (Vacancy):    X.X/10
Group 3 (Fit):        X.X/10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### Output 2: Risks (🔴🟡🟢)
```
🔴 CRITICAL (deal-breakers)
  1. [what] → [why, source]

🟡 WARNINGS (verify at interview)
  1. [what] → [what to clarify]

🟢 CONFIRMED (verified matches)
  1. [what] → [why good]
```

#### Output 3: Action + Cover Letter
```
📄 RESUME: 01 (Enterprise PM) / 03 (Product PM-PO)

✉️ COVER LETTER
  Key words from vacancy:
    • [word/phrase 1]
    • [word/phrase 2]
  Structure:
    [scheme: who → why → what I can do (with number)
     → work format → salary]
  Hook:
    [1 achievement matching their tasks]
```

---

### 5. Settings / Criteria Configuration

User must be able to:
- View all scoring criteria with current weights and values
- Adjust weights (1-10) for each criterion
- Change GATE A thresholds (salary minimum, remote preference)
- Toggle GATE B on/off for each resume archetype
- Override individual scores manually (with reason logged)
- Save multiple configurations as profiles (e.g., "Active Search", "Passive Monitoring", "Dream Companies")

---

### 6. User Interface (Dashboard)

#### Main Screen: Vacancy List
- Search results with filters (matching HH)
- Each vacancy card shows: title, company, salary, location, **Score + Category badge** (color-coded S/A/B/C/REJECT)
- Sort by: score, date, salary
- Filter by: category, gate status, already analyzed/new
- Status per vacancy: new / analyzed / applied / rejected / archived

#### Detail View: Vacancy Analysis
- Score card (Group 1/2/3 breakdown)
- Risks (🔴🟡🟢)
- Company profile (all collected data)
- Vacancy profile (parsed tasks, requirements, stack)
- Generated cover letter (editable)
- Resume selector (01 or 03)
- Apply button → opens HH page or sends via API (Stage 2)

#### History View
- All processed vacancies with statuses
- Statistics: total analyzed, applied, interview rate, offer rate
- Company blacklist/greylist
- Time-series: applications per day, score distribution

---

### 7. Data Layer

#### Vacancies DB
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| hh_id | string | HH vacancy ID |
| title | string | Vacancy title |
| company_name | string | Company name |
| company_id | FK | Link to Companies DB |
| salary_from | int | Min salary |
| salary_to | int | Max salary |
| salary_currency | string | RUB/USD/EUR |
| work_format | enum | remote/hybrid/office |
| location | string | City |
| experience | string | Required experience |
| description_raw | text | Raw HH description |
| parsed_tasks | json | Extracted tasks |
| parsed_requirements | json | Extracted requirements |
| key_words | json[] | Extracted keywords |
| url | string | HH url |
| created_at | timestamp | First seen |
| status | enum | new/analyzed/applied/rejected/archived |

#### Companies DB
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| name | string | Company name |
| hh_employer_id | string | HH employer ID |
| website | string | URL |
| hh_rating | float | HH employer rating |
| hh_recommend_pct | int | % recommend |
| dreamjob_summary | text | DreamJob reviews summary |
| habr_summary | text | Habr Career summary |
| tadviser_profile | text | TAdviser data |
| revenue | string | Revenue data |
| employees | int | Headcount |
| culture_tags | json[] | Culture descriptors |
| stack_tags | json[] | Tech stack tags |
| legal_status | text | Legal data |
| overall_score | float | Company score (cached) |
| last_updated | timestamp | Last fetch |
| data_confidence | enum | verified/extracted/not_found |

#### Scoring Config DB
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| profile_name | string | Config profile name |
| criteria | json | All criteria with weights and thresholds |
| gates | json | Gate A/B configuration |
| is_active | bool | Currently active config |
| created_at | timestamp | Created |

#### Templates DB
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| name | string | Template name |
| archetype | enum | 01 / 03 |
| body_template | text | Letter template with placeholders |
| format_block | text | Work format paragraph |
| salary_block | text | Salary expectation paragraph |
| is_default | bool | Default for archetype |

#### Logs DB (History)
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| vacancy_id | FK | Vacancy analyzed |
| score | float | Final score |
| category | enum | S/A/B/C/REJECT |
| gate_a_result | json | GATE A details |
| gate_b_result | json | GATE B details |
| override_applied | bool | Override used |
| decision | enum | apply/skip/monitor |
| cover_letter | text | Generated letter |
| resume_used | enum | 01/03 |
| applied_at | timestamp | When sent |
| response_at | timestamp | Response date |
| notes | text | User notes |

---

## Stage 2: Automated Applications (v2.0)

### Additional Components:

#### 8. HH Auth & Application Module
- Store HH credentials securely (local env, not in repo)
- Open vacancy page in browser for manual confirmation OR
- Send application via HH API (if available) or browser automation (Playwright)
- **User confirmation required** before each send
- Track application status (sent / viewed / rejected / invited)

#### 9. Cover Letter Generator
- Based on templates DB
- Fill placeholders: vacancy title, key words, tasks → experience mapping
- Generate format block (remote/commute paragraph)
- Generate salary block
- Allow manual editing before sending

#### 10. Application Queue
- Batch applications with user review
- Priority queue by score
- Rate limiting (don't send too many per day)
- A/B testing of different letter templates (future)

---

## User Personas

### Primary: Denis (IT PM, job seeker)
- 20+ years PM experience, 7+ in Enterprise IT
- SPb + Stavropol, remote-first with business trips
- 250k+ net salary target
- Tech stack: DWH/BI, ERP, enterprise integration
- Drivers: methodologies, processes, data, analytics, "supporting coordinator"
- Uses: DeepSeek API, YandexGPT, GitHub Actions, open-source only

### Configuration Example (Denis's Profile)
```
Salary min: 250,000 ₽ net
Remote priority: yes
Location: SPb + Stavropol
Resume archetype: 01 (Enterprise PM) / 03 (Product PM-PO)
Experience: 20+ years
Key strengths: portfolio management, cross-functional coordination, PMO
```

---

## Technical Constraints

- **Open-source only**: all dependencies must be open-source
- **Free services**: GitHub Actions (CI/CD), SQLite (DB), Python (backend)
- **AI accessible from Russia**: DeepSeek API direct, YandexGPT/GigaChat as fallback
- **No OpenRouter, no Render**
- **Playwright** for browser automation (if needed in Stage 2)
- **Tauri** for desktop app (if needed)
- **All data stored locally**: user's device or own server

---

## Development Priority (Stage 1)

| Priority | Component | Effort | Dependencies |
|:--------:|-----------|--------|:------------:|
| P0 | HH Parser + Filter Engine | Medium | HH API access |
| P0 | UES Calculator (core scoring) | Medium | Criteria config |
| P0 | Data Collector Agent (basic) | High | LLM API access |
| P1 | Settings UI (criteria config) | Medium | Calculator done |
| P1 | Dashboard (vacancy list) | Medium | Parser done |
| P1 | Detail View (analysis display) | Medium | All P0 done |
| P2 | Companies DB + caching | Low | Collector done |
| P2 | Override Rule Engine | Low | Calculator done |
| P2 | Templates DB | Low | - |
| P3 | History & Statistics | Medium | DB schema done |

---

## Development Priority (Stage 2)

| Priority | Component | Effort | Dependencies |
|:--------:|-----------|--------|:------------:|
| P0 | HH Auth | Low | - |
| P0 | Cover Letter Generator | Medium | Templates DB |
| P1 | Application Queue | Medium | Auth + Generator |
| P1 | Manual confirmation flow | Medium | Queue |
| P2 | Playwright automation | High | Auth |

---

## Key Terms / Glossary

| Term | Definition |
|------|------------|
| **UES (Unified Evaluation System)** | 4-phase evaluation cycle with 2 parallel tracks (Company + Vacancy), 3 scoring groups (35/35/30), 4 gates |
| **GATE A** | Hard filters: remote, salary, location. Any fail → REJECT |
| **GATE B** | Resume archetype check: 01 (Enterprise PM) or 03 (Product PM-PO) |
| **High Potential Override** | If GATE A fails but company is strong + fit is high → apply "on your terms" |
| **Group 1 (Company)** | 35 points: employment, scale, culture, brand, values |
| **Group 2 (Vacancy)** | 35 points: driver alignment, stack, benefits, career, training |
| **Group 3 (Personal Fit)** | 30 points: experience, domain, geo, culture |
| **ValueHunt** | Product name: automated job search + evaluation + application system |

---

## Document References

- UES (Unified Evaluation System) v2.1 — `C:\Users\Hamster\Documents\Work\03 Развитие\ИПР\Контекст для HR агента\UES - Единая система оценки.md`
- Company Funnel — `C:\Users\Hamster\Documents\Work\03 Развитие\ИПР\Контекст для HR агента\Воронка IT-компаний России.md`
- Cover Letter Templates — `C:\Users\Hamster\Documents\Work\03 Развитие\ИПР\Контекст для HR агента\Шаблоны сопроводительных.md`
- Scoring results — `C:\Users\Hamster\Documents\Work\chat_logs\scoring_results.md`
