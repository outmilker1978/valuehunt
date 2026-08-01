# ValueHunt — Техническое задание (полная версия)

> Полный текст ТЗ на продукт умного поиска работы.
> Архитектура, матрица оценки, модули, сценарии, БД, промпты.

_Содержание перенесено из README.md._

---

## 1. Цель

Автоматизировать воронку поиска работы: сбор → оценка → отклик → трекинг → рефлексия. Замена ручного перебора HH на систему с LLM-анализом и персональной матрицей ценностей.

---

## 2. Архитектура

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
                       │  gate_check.py  │  ← Gate A/B thin wrapper
                       └────────┬────────┘
                                │
                       ┌────────▼────────┐
                       │     db.py       │  ← SQLite (vacancies, companies,
                       │                 │     profiles, contacts, interactions)
                       └────────┬────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
  ┌───────▼───────┐   ┌────────▼────────┐   ┌────────▼────────┐
  │  collector.py │   │  web/app.py     │   │  bot.py (загл.) │
  │  (данные о    │   │  FastAPI Web UI │   │  Telegram bot   │
  │  компаниях)   │   └────────┬────────┘   └─────────────────┘
  └───────────────┘            │
                     ┌─────────┴──────────┐
                     │  templates/        │
                     │  static/           │
                     └────────────────────┘
```

---

## 3. Матрица оценки (расширенная)

### 3.1. Структура

Каждый критерий — группа из подкритериев (оценка 1-10 + вес внутри группы). Финальный Score = средневзвешенное по группам.

### 3.2. Группы критериев

#### Группа 1. Роль и содержание работы (вес группы: 10)

| Подкритерий | Вес | Описание |
|------------|:---:|----------|
| Роль PM/PO (гибрид) | 10 | Совмещение Project и Product Owner |
| Enterprise-масштаб | 9 | Крупные заказчики, сложные интеграции |
| Продуктовое влияние | 9 | Бэклог, roadmapping, дашборды метрик |
| Полный цикл | 8 | От discovery до пост-поддержки |

#### Группа 2. Условия работы (вес группы: 10)

| Подкритерий | Вес | Описание |
|------------|:---:|----------|
| Удалёнка 100% | 10 | Работа из любой точки |
| Гибрид (офис по необходимости) | 8 | Разовые встречи/командировки |
| Офис Москва | 4 | Только если поездки раз в 2-4 недели |
| Командировки | 6 | Готовность к поездкам |

#### Группа 3. Финансы (вес группы: 9)

| Подкритерий | Вес | Описание |
|------------|:---:|----------|
| Фикс от 250k net | 10 | Минимальный порог |
| Вилка указана | 7 | Прозрачность компании |
| IT-аккредитация | 6 | Налоговые льготы |
| ДМС (стоматология) | 5 | Полис с первого дня |

#### Группа 4. Компания и репутация (вес группы: 8)

| Подкритерий | Вес | Описание |
|------------|:---:|----------|
| Рейтинг HH (Top-50/100) | 8 | Зрелость HR-функции |
| Dream Job / отзывы | 7 | Реальная культура |
| Возраст компании (3+ лет) | 6 | Стабильность |
| Медийность CEO/команды | 7 | Прозрачность |

#### Группа 5. Карьера и развитие (вес группы: 8)

| Подкритерий | Вес | Описание |
|------------|:---:|----------|
| Карьерная лестница | 9 | Грейды, понятный рост |
| Обучение за счёт | 8 | Конференции, курсы, сертификации |
| Менторство/наставничество | 7 | Культура развития |
| Трек до PPM/CPO | 9 | Долгосрочный путь |

#### Группа 6. Технологический стек (вес группы: 7)

| Подкритерий | Вес | Описание |
|------------|:---:|----------|
| AI/ML-инструменты | 8 | Актуальность |
| Data / BI / DWH | 8 | Основная экспертиза |
| Современный стек | 7 | CI/CD, Docker, K8s, не legacy |
| Продуктовые метрики | 8 | Data-driven культура |

#### Группа 7. Культура и процессы (вес группы: 7)

| Подкритерий | Вес | Описание |
|------------|:---:|----------|
| Зрелые Agile-процессы | 9 | Не хаос, не бюрократия |
| Прозрачность в найме | 8 | Быстрая обратная связь |
| Отсутствие аутстаффа | 7 | Прямой найм |
| Соцпакет | 6 | ДМС, спорт, питание |

### 3.3. Формула расчёта

```
Score_группы = Σ(оценка_подкритерия × вес_подкритерия) / Σ(весов_подкритериев)
Финальный_Score = Σ(Score_группы × вес_группы) / Σ(весов_групп)
```

### 3.4. Шкала решений

| Score | Категория | Действие |
|:-----:|:---------:|----------|
| 8.5-10 | A | Идеальное попадание |
| 7.0-8.4 | Б | Сильное совпадение |
| 6.0-6.9 | В | Компромисс |
| < 6.0 | — | Пропустить |

---

## 4. Модули системы

### 4.1. Модуль анкетирования
- Интерфейс заполнения матрицы (группы + подкритерии)
- Привязка резюме HH (по ID)
- Настройка степени автоматизации (авто/вручную по категориям)
- Сохранение профиля в JSON/YAML

### 4.2. Модуль сбора вакансий (кронер)
**Периодичность**: каждые 4 часа (настраивается)

**Источники**:
- HH API (основной): поиск по фильтрам, полное описание вакансии
- Dream Job: отзывы о компании (если доступен парсинг)
- Сайт компании: описание, ценности (LLM-анализ)

**Фильтры поиска** (из профиля пользователя):
- Регионы: СПб + Москва
- Должности: Руководитель проектов, PM, Product Manager, PO, Delivery Manager, Enterprise PM
- Проф. роли: 107, 73
- Отрасли: 7.540, 7.539
- Ключевые слова из набора (Enterprise, Senior, Head of Delivery и т.д.)

### 4.3. Модуль оценки (LLM-агент)
**Задачи LLM**:
1. Семантический анализ вакансии — о чём реально эта роль
2. Извлечение: формат работы (реальная удалёнка?), стек, культура
3. Проверка компании: рейтинг, отзывы, новости
4. Расчёт Score по матрице
5. Присвоение категории (A/Б/В/мимо)

**Модель**: DeepSeek через прямой API (доступен в РФ)

### 4.4. Модуль отклика (автовеб)
**Технология**: Playwright (headless-браузер)

**Действия**:
1. Авторизация на HH (сессия, cookie)
2. Выбор резюме (01 или 03) по типу вакансии
3. Подстановка сопроводительного письма (шаблон 01 или 03 + адаптация)
4. Отклик
5. Запись результата в БД

**Триггеры**:
- Score В (6.0-6.9) → автоотклик без подтверждения
- Score Б (7.0-8.4) → подготовить, ждать одобрения
- Score A (8.5-10) → уведомление + ручной отклик

### 4.5. Модуль CRM / Трекер
**Сущности**:
- Вакансия: ссылка, компания, Score, статус, даты
- Контакт: HR, имя, телефон, Telegram, LinkedIn
- Коммуникация: дата, тип (отклик/письмо/звонок), заметки

**Статусы**:
- Новое → Откликнуто → Приглашение → Собеседование (1/2/N) → Оффер / Отказ / Архив

---

## 5. Пользовательские сценарии

### Сценарий 1. Первичная настройка (единожды)
1. Открыть Web UI в браузере
2. Заполнить матрицу ценностей (веса групп, оценки подкритериев)
3. Указать ID резюме HH
4. Выбрать степень автоматизации
5. Сохранить профиль

### Сценарий 2. Ежедневная работа
1. Получить уведомление в Telegram: «Найдено 3 новых вакансии»
2. Открыть дашборд
3. Просмотреть топ по Score: A-1, Б-2, автоотклик-0
4. Для A/Б: прочитать LLM-анализ, отредактировать письмо, нажать «Откликнуться»
5. Playwright делает отклик, статус → «Откликнуто»

### Сценарий 3. Еженедельная рефлексия
1. Получить автоотчёт в Telegram / на почту
2. Просмотреть графики: неделя к неделе
3. Прочитать рекомендации: «Фильтр по ЗП даёт 0 результатов — пора расширить»

### Сценарий 4. CRM (работа с контактами)
1. Открыть карточку вакансии
2. Увидеть контакт HR (если найден)
3. Нажать «Напомнить через 3 дня»
4. Получить напоминание
5. Написать HR в Telegram по шаблону

---

## 6. Структура БД (SQLite) — текущая (v1.13.0)

```sql
-- Профили (мульти-профили)
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    hh_resume_id TEXT,
    resume_name TEXT,
    resume_data TEXT,
    search_filters TEXT,
    matrix_data TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Связь вакансия ↔ профиль (many-to-many)
CREATE TABLE vacancy_profiles (
    vacancy_id INTEGER NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    PRIMARY KEY (vacancy_id, profile_id)
);

-- Вакансии
CREATE TABLE vacancies (
    id INTEGER PRIMARY KEY,
    hh_id TEXT UNIQUE,
    title TEXT,
    company TEXT,
    url TEXT,
    salary_from INTEGER,
    salary_to INTEGER,
    salary_currency TEXT DEFAULT 'RUB',
    description TEXT,
    skills_json TEXT,
    work_format TEXT,
    location TEXT,
    experience TEXT,
    published_at TEXT,
    hr_contacts TEXT,
    parsed_tasks TEXT,
    parsed_requirements TEXT,
    key_words TEXT,
    score REAL,
    category TEXT,
    gate_a_result TEXT,
    gate_b_result TEXT,
    override_applied INTEGER DEFAULT 0,
    risks TEXT,
    cover_letter TEXT,
    resume_archetype TEXT,
    llm_analysis TEXT,
    llm_generated INTEGER DEFAULT 0,
    status TEXT DEFAULT 'new' CHECK(status IN ('new','applied','follow_up','call','in_progress','offer','rejected','archived','closed')),
    created_at TEXT DEFAULT (datetime('now')),
    responded_at TEXT,
    archived_at TEXT
);

-- Компании
CREATE TABLE companies (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,
    hh_employer_id TEXT,
    website TEXT,
    hh_rating REAL,
    hh_recommend_pct INTEGER,
    hh_reviews_count INTEGER,
    culture_tags TEXT,
    stack_tags TEXT,
    overall_score REAL,
    data_confidence TEXT DEFAULT 'not_found',
    created_at TEXT DEFAULT (datetime('now'))
);

-- Контакты (HR)
CREATE TABLE contacts (
    id INTEGER PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    role TEXT,
    source TEXT NOT NULL DEFAULT 'other' CHECK(source IN ('HH','Telegram','LinkedIn','recommendation','VK','email','other')),
    priority TEXT DEFAULT 'B' CHECK(priority IN ('S','A','B','C')),
    telegram TEXT,
    email TEXT,
    phone TEXT,
    vk TEXT,
    linkedin TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Взаимодействия
CREATE TABLE interactions (
    id INTEGER PRIMARY KEY,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    vacancy_id INTEGER REFERENCES vacancies(id) ON DELETE SET NULL,
    type TEXT NOT NULL CHECK(type IN ('outreach','follow_up','call','interview','test_task','offer','rejection','other')),
    direction TEXT NOT NULL CHECK(direction IN ('outbound','inbound')),
    summary TEXT,
    outcome TEXT CHECK(outcome IN ('pending','positive','negative')),
    next_action_date TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Логи решений
CREATE TABLE logs (
    id INTEGER PRIMARY KEY,
    vacancy_id INTEGER,
    score REAL,
    category TEXT,
    decision TEXT,
    cover_letter TEXT,
    resume_used TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (vacancy_id) REFERENCES vacancies(id)
);
```

---

## 7. Prompts для LLM-агента (MVP)

### Prompt анализа вакансии
```
Ты — HR-аналитик. Проанализируй вакансию и компанию для кандидата IT PM/PO.

Данные:
- Название вакансии: {title}
- Компания: {company}
- Описание: {description}
- Требования: {requirements}
- Ключевые навыки: {skills}

Оцени по шкале 1-10:
1. Роль PM/PO (гибрид)?
2. Enterprise-масштаб?
3. Реальная удалёнка или декларативная?
4. Зрелость процессов (Agile, метрики)?
5. Интересный стек (AI/ML, BI)?
6. Прозрачность (указана ЗП? описана культура?)
7. Риски (аутстафф? бюрократия? токсичность?)

Верни JSON:
{
  "role_type": "PM/PO/hybrid/other",
  "remote_real": true/false,
  "enterprise_scale": 1-10,
  "culture_notes": "...",
  "risks": ["..."],
  "score_estimate": 1-10,
  "summary": "2-3 предложения"
}
```

### Prompt еженедельной рефлексии
```
Ты — HRBP. Проанализируй статистику поиска работы за неделю.
...
```

---

## 8. Технический стек

| Компонент | Решение | Обоснование |
|-----------|---------|-------------|
| Язык бэкенда | Python | HH API, LLM, Playwright — всё на Python |
| Фреймворк | FastAPI | Легковесный REST |
| База данных | SQLite | Один пользователь, не надо сервера |
| Очередь | GitHub Actions (cron) | Бесплатно, без Redis |
| Автоматизация | Playwright | Современнее Selenium |
| LLM | DeepSeek (прямой API) | Доступен в РФ, есть бесплатный tiers |
| Десктоп | Tauri (Rust + HTML/JS) | Лёгкий |
| Бот | python-telegram-bot | Бесплатно |
| Хостинг | GitHub Pages | Статика бесплатно |

---

## 9. Файловая структура репозитория (текущая)

```
ValueHunt/
├── .github/workflows/daily_scanner.yml
├── scripts/
│   └── import_contacts.py       # Импорт contacts.md → SQLite
├── src/
│   ├── scanner.py               # HH.ru парсер (BeautifulSoup)
│   ├── ues.py                   # UES Calculator (Gates + Score)
│   ├── gate_check.py            # VacancyGateCheck (Gate A/B thin)
│   ├── scorer.py                # VacancyScorer (legacy, deprecated)
│   ├── collector.py             # Данные о компаниях
│   ├── llm_agent.py             # LLM-анализ (заглушка)
│   ├── bot.py                   # Telegram-бот (заглушка)
│   ├── browser_agent.py         # Playwright-отклик (заглушка)
│   ├── reporter.py              # Еженедельный отчёт (заглушка)
│   ├── db.py                    # SQLite — схемы + CRUD
│   └── web/
│       ├── app.py               # FastAPI — routes, API, pages
│       ├── templates/           # Jinja2: index, profile, vacancies, contacts, ...
│       └── static/              # style.css, app.js
├── config/
│   ├── profile.json             # Legacy-профиль
│   ├── matrix.yaml              # Матрица скоринга (7 групп)
│   └── ues_config.json          # Настройки UES
├── data/
│   └── valuehunt.db             # SQLite (gitignored)
├── docs/
│   ├── USER.md                  # Пользовательская инструкция
│   ├── DEV.md                   # Документация разработчика
│   ├── ADMIN.md                 # Администрирование
│   ├── SPEC.md                  # Техническое задание
│   └── TEST.md                  # Тест-кейсы
├── CHANGELOG.md
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 10. План на первый релиз (v0.1)

1. **Сканер** — парсинг HH API, сохранение в SQLite
2. **Scorer** — расчёт Score по матрице (первая версия без LLM, на keywords)
3. **Web UI** — редактирование профиля, матрицы, просмотр вакансий
4. **Telegram-бот** — уведомление о новых вакансиях с Score
5. **GitHub Actions** — автоматический запуск раз в 4 часа

---

## 11. Ограничения (open-source / РФ)

### По стеку
- **Только open-source**: Python, FastAPI, Playwright, Tauri, SQLite — все MIT/BSD лицензии
- **Бесплатные сервисы**: GitHub Actions (2000 мин/мес), GitHub Pages, Telegram Bot API

### По AI
- **DeepSeek API** — доступен напрямую из РФ, есть бесплатный tiers
- **Альтернативы для РФ**: YandexGPT, GigaChat от Сбера

### По работе HH
- **HH API** — открытый, доступен из РФ, 2000 запросов/сутки бесплатно
- **Отклики** — только через Playwright (браузер), HH API не позволяет откликаться
- **Данные**: все персональные данные хранятся локально
