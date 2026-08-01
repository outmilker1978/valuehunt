# ValueHunt — Admin Documentation

## Запуск

### Через готовую сборку (exe)

```powershell
# Просто запусти файл
.\ValueHunt.exe
```

Сервер запускается на http://127.0.0.1:8100. Браузер открывается автоматически.

При первом запуске:
- Создаётся `config/` с дефолтными настройками (profile.json, matrix.yaml, ues_config.json)
- Создаётся `data/valuehunt.db` — SQLite БД
- Все файлы — рядом с exe, копируй папку куда хочешь

### Из исходников (Python)

```powershell
# Из папки проекта
cd C:\...\ValueHunt
.\.venv\Scripts\python.exe start_webui.py
```

Сервер запускается на `http://127.0.0.1:8100`

**start_webui.py** делает:
```python
from src.web.app import app
import uvicorn
uvicorn.run(app, host="127.0.0.1", port=8100)
```

## Перезапуск

```powershell
# Windows — убить процесс python, запустить снова
Stop-Process -Name "python" -Force
.\.venv\Scripts\python.exe start_webui.py
```

## Сборка релиза

```powershell
pip install pyinstaller
pyinstaller --onedir --name ValueHunt ^
  --add-data "src/web/templates;src/web/templates" ^
  --add-data "src/web/static;src/web/static" ^
  --add-data "config;config" ^
  --add-data ".env.example;." ^
  --exclude-module test --exclude-module pytest ^
  --collect-submodules src start_webui.py
```

Результат: `dist/ValueHunt/ValueHunt.exe` + `_internal/` + `config/` (копируется при первом запуске).

## Данные

Вся data хранится локально:

| Файл | Назначение |
|------|-----------|
| `data/valuehunt.db` | SQLite — вакансии, профили, компании, контакты, взаимодействия |
| `config/profile.json` | Legacy-профиль (активный) |
| `config/matrix.yaml` | Матрица скоринга |
| `config/ues_config.json` | Настройки UES Calculator |

База данных создаётся автоматически при первом запуске (`init_db()` в `src/db/app.py`).

## Обновление схемы БД

Новые таблицы добавляются в `SCHEMA_SQL` в `src/db.py`.
Миграции существующих таблиц — в `SCHEMA_MIGRATIONS` (ALTER TABLE).

### Soft Delete (v0.3.0)

Добавлены колонки `deleted_at TEXT` и `delete_reason TEXT` в таблицу `vacancies`.
CHECK-constraint на `status` расширен: `'trash'` добавлен в список допустимых значений.

Миграция существующей БД:
```python
ALTER TABLE vacancies ADD COLUMN deleted_at TEXT;
ALTER TABLE vacancies ADD COLUMN delete_reason TEXT;
```

Все SELECT-запросы к `vacancies` фильтруют `WHERE deleted_at IS NULL`.
Запросы к корзине — `WHERE deleted_at IS NOT NULL`.

**API эндпоинты корзины:**

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/vacancies/{id}/trash` | Удалить с причиной `{"reason": "..."}` |
| POST | `/api/vacancies/{id}/restore` | Восстановить |
| DELETE | `/api/vacancies/{id}` | Удалить навсегда (только из корзины) |
| GET | `/api/trash` | Список удалённых |
| GET | `/api/trash-stats` | Статистика: общее + по причинам |

**При удалении (`/api/vacancies/{id}/trash`):**
- `deleted_at = datetime('now')`
- `delete_reason = reason` (из списка: Зарплата ниже ожидаемой, Локация не подходит, Не мой профиль/домен, Дубль вакансии, Нет удалёнки, Другое)

**При восстановлении (`/api/vacancies/{id}/restore`):**
- `deleted_at = NULL, delete_reason = NULL`
- `status = 'new'`

**Страница:** `/trash` — таблица удалённых с возможностью вернуть или удалить навсегда.

## Окружение

Файл `.env` (опционально):
```
DEEPSEEK_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=...
```

## Порт

По умолчанию 8100. Чтобы сменить:
```python
# start_webui.py
uvicorn.run(app, host="127.0.0.1", port=8100)  # ← поменять порт
```

## Логирование

Uvicorn пишет в stdout. При проблемах — включи debug:
```python
uvicorn.run(app, host="127.0.0.1", port=8100, log_level="debug")
```

## Импорт контактов из contacts.md

```powershell
.\.venv\Scripts\python.exe scripts\import_contacts.py
```

Скрипт парсит `C:\Users\Hamster\Documents\Work\03 Развитие\ИПР\contacts.md` и импортирует:
- Контакты (name, role, source, priority, telegram, email, vk)
- Взаимодействия (type, direction, summary, outcome)
- Пытается сопоставить компании и вакансии по имени (fuzzy match)

Результат: «Контактов импортировано: N, Взаимодействий импортировано: M»

## Проверка здоровья

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8100/" -UseBasicParsing
# → 200 OK
```

## Зависимости

Установка:
```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
```

Основные:
- fastapi, uvicorn — веб-сервер
- jinja2 — шаблоны
- requests, beautifulsoup4, lxml — парсинг HH
- pyyaml — конфиги
- python-dotenv — окружение
- pydantic — модели данных

## Бэкап

Скопируй папку `data/` целиком:
```powershell
Copy-Item -Path "data" -Destination "data_backup_YYYY-MM-DD" -Recurse
```

Вся остальная конфигурация — в `config/` (текстовые файлы, под git).
