# ValueHunt — Developer Documentation

**Версия:** 1.14.0

## Архитектура

```
                      ┌─────────────────┐
                      │   HH.ru (сайт)  │
                      └────────┬────────┘
                               │ requests + BeautifulSoup
                      ┌────────▼────────┐
                      │   scanner.py    │  ← поиск + детали вакансий
                      └────────┬────────┘
                               │
                      ┌────────▼────────┐
                      │     ues.py      │  ← UES Calculator (Gates + Score)
                      └────────┬────────┘
                               │
                      ┌────────▼────────┐
                      │     db.py       │  ← SQLite (vacancies, companies,
                      │                 │     profiles, vacancy_profiles)
                      └────────┬────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
  ┌───────▼───────┐  ┌────────▼────────┐  ┌────────▼────────┐
  │  collector.py │  │  web/app.py     │  │  bot.py (загл.) │
  │  (данные о    │  │  FastAPI Web UI │  │  Telegram bot   │
  │   компаниях)  │  └────────┬────────┘  └─────────────────┘
  └───────────────┘           │
                    ┌─────────┴──────────┐
                    │  templates/        │
                    │  static/           │
                    └────────────────────┘
```

## Стек

- **Python 3.12+**
- **FastAPI** — REST API + страницы
- **SQLite** — вся data локально
- **Jinja2** — шаблоны HTML
- **BeautifulSoup + lxml** — парсинг HH.ru
- **SVG inline** — графики на дашборде (без библиотек)

## Структура проекта

```
ValueHunt/
├── src/
│   ├── scanner.py          # Парсинг HH.ru
│   ├── ues.py              # UES Calculator
│   ├── collector.py        # Данные о компаниях
│   ├── db.py               # SQLite — схемы, CRUD, профили
│   ├── gate_check.py       # VacancyGateCheck (Gate A/B thin wrapper)
│   └── web/
│       ├── app.py          # FastAPI — routes, API, pages
│       ├── templates/      # Jinja2: index, profile, vacancies, matrix, vacancy_detail
│       └── static/         # app.js (api, helpers), style.css
├── config/
│   ├── profile.json        # Legacy-профиль (одиночный)
│   ├── matrix.yaml         # Матрица скоринга
│   └── ues_config.json     # Настройки UES
├── data/
│   └── valuehunt.db        # SQLite (gitignored)
├── docs/
│   ├── DEV.md              # Разработчику
│   ├── USER.md             # Пользователю
│   └── ADMIN.md            # Администратору
├── CHANGELOG.md
├── requirements.txt
├── .gitignore
└── README.md
```

## Ключевые модули

### scanner.py — поиск вакансий

```python
from src.scanner import run_scan

# profile = словарь с ключами:
#   titles, keywords, salary_expectation, location,
#   work_formats, experienced, search_filters
results = run_scan(profile)
# → список dict с полями: hh_id, title, company, salary, score, category, ...
```

Механизм:
1. `HHScanner.search_vacancies(params)` — GET `https://hh.ru/search/vacancy`
2. Парсинг карточек (`vacancy-card`), извлечение hh_id, title, company, salary
3. Для каждой карточки: `get_vacancy_details(url)` — парсинг описания, навыков, контактов
4. `ues.calculate(vacancy)` — UES scoring

### ues.py — UES Calculator

```python
from src.ues import calculate

result = calculate(vacancy_dict, profile_dict)
# → { "score": 7.5, "category": "S", "gate_a": {...}, "gate_b": {...} }
```

**GATE A (отсечка):**
- work_format: remote/hybrid → pass, office → fail
- salary: ≥200k net → pass
- Если GATE A не пройден → категория REJECT

**GATE B (архетип):**
- 01 — Enterprise PM
- 03 — Product PM/PO
- Если не совпадает → категория REJECT

**Scoring (3 группы):**
| Группа | Вес | Критерии |
|--------|-----|----------|
| Компания | 35% | employment_type, enterprise_scale, culture, brand_stability, values_alignment |
| Вакансия | 35% | driver_alignment, tech_stack, benefits, career_path, training |
| Личное | 30% | experience_match, domain_match, geo, cultural |

**Категории:**
| Категория | Диапазон | Описание |
|-----------|----------|----------|
| S | 8.0+ | Идеально |
| A | 7.0+ | Отлично |
| B | 6.0+ | Хорошо |
| C | 5.0+ | Возможно |
| REJECT | <5.0 | Пропустить |

### gate_check.py — VacancyGateCheck

```python
from src.gate_check import evaluate

result = evaluate(vacancy_dict)
# → { "gate_a": {"passed": True, ...}, "gate_b": {"passed": True, ...}, "passed": True }
```

Тонкая обёртка (20 строк) над `UESCalculator._check_gate_a()` и `_check_gate_b()`. Без полного скоринга, без рисков, без рекомендаций. Для pre-filtering в массовом сканировании.

### db.py — база данных

**Таблицы:**

- `profiles` — мульти-профили (id, name, resume_data JSON, search_filters JSON, matrix_data JSON)
- `vacancies` — вакансии (hh_id UNIQUE, title, company, score, category, status, ...), status имеет CHECK constraint (new/applied/follow_up/call/in_progress/offer/rejected/archived/closed)
- `vacancy_profiles` — связь many-to-many (vacancy_id, profile_id)
- `companies` — данные о компаниях
- `contacts` — HR-контакты (name, role, source, priority S/A/B/C, telegram, email, phone, vk, linkedin, notes, company_id → FK)
- `interactions` — история взаимодействий (contact_id, vacancy_id, type, direction, summary, outcome, next_action_date)
- `logs` — история решений

**Soft Delete (v0.3.0):**
- `deleted_at TEXT`, `delete_reason TEXT` — колонки в `vacancies`
- Все SELECT к `vacancies` фильтруют `WHERE deleted_at IS NULL`
- `trash_vacancy(conn, id, reason)` — устанавливает `deleted_at = now`
- `restore_vacancy(conn, id)` — очищает `deleted_at`, ставит `status = 'new'`
- `hard_delete_vacancy(conn, id)` — `DELETE WHERE id=? AND deleted_at IS NOT NULL`
- `get_trashed_vacancies(conn)` — `SELECT ... WHERE deleted_at IS NOT NULL`

**Drop-out scoring (v0.3.0):**
- Критерии с keywords и 0 совпадений → выпадают из расчёта (не штрафуют)
- Критерии без keywords (пустой список) — всегда участвуют
- Если активных критериев < 6 → fallback на старую логику (все участвуют)
- Реализация: `UESCalculator._score_groups()`

**Config loading (v0.3.0):**
- `UESCalculator.__init__()`: `config or load_ues_config()` — читает `ues_config.json` по умолчанию

**Ключевые функции:**

```python
save_vacancy(conn, vacancy)      # INSERT OR IGNORE → {"inserted": bool, "id": int}
get_all_profiles(conn=None)      # список профилей
get_profile(conn, profile_id)    # один профиль
save_profile(conn, data)          # создать/обновить профиль
delete_profile(conn, profile_id)  # удалить профиль + связи
link_vacancy_to_profile(conn, vacancy_id, profile_id)
trash_vacancy(conn, id, reason)  # soft delete
restore_vacancy(conn, id)        # restore from trash
hard_delete_vacancy(conn, id)    # permanent delete
get_trashed_vacancies(conn)      # list trashed
```

## API endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/profiles` | Список всех профилей |
| GET | `/api/profiles/{id}` | Данные профиля |
| POST | `/api/profiles` | Создать профиль |
| PUT | `/api/profiles/{id}` | Обновить профиль |
| DELETE | `/api/profiles/{id}` | Удалить профиль |
| GET | `/api/profile` | Legacy-профиль (profile.json) |
| POST | `/api/profile` | Сохранить legacy-профиль |
| GET | `/api/vacancies?profile_id=&status=` | Список вакансий |
| GET | `/api/vacancies/{id}` | Детали вакансии |
| GET | `/api/stats?profile_id=` | Статистика |
| POST | `/api/scan?profile_id=` | Запустить сканирование |
| POST | `/api/vacancies/{id}/status` | Обновить статус |
| GET | `/api/matrix` | Матрица скоринга |
| POST | `/api/matrix/save` | Сохранить матрицу |
| GET | `/api/ues-config` | Конфигурация UES |
| POST | `/api/profile/import-hh` | Импорт резюме с HH по ID |
| POST | `/api/profile/upload-resume` | Загрузка TXT-резюме |
| GET | `/api/contacts` | Список контактов (опционально ?company_id=) |
| GET | `/api/contacts/due-for-action` | Контакты с просроченным next_action_date |
| GET | `/api/contacts/{id}` | Детали контакта + interactions |
| POST | `/api/contacts` | Создать контакт |
| PUT | `/api/contacts/{id}` | Обновить контакт |
| DELETE | `/api/contacts/{id}` | Удалить контакт |
| GET | `/api/interactions?contact_id=&vacancy_id=` | Список взаимодействий |
| POST | `/api/interactions` | Создать взаимодействие |
| GET | `/api/matrix` | Матрица скоринга |
| POST | `/api/matrix/save` | Сохранить матрицу |

## Добавление новой страницы

1. Создай шаблон в `src/web/templates/` (extends `base.html`)
2. Добавь route в `src/web/app.py` (GET /page → render("page.html"))
3. При необходимости добавь API endpoint

## Пометка для себя: типовые ошибки

- `save_profile` конфликтует: в app.py есть `save_legacy_profile` (profile.json) и импорт `save_profile` из db.py (multi-profile)
- Все SVG-графики рисуются inline — нет Chart.js или D3
- Периоды на дашборде считаются по `published_at` (дата публикации на HH), не по `created_at`
