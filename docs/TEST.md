# ValueHunt — Test Guide

> Проверка новой функциональности спринта 1.13.0.
> Запускать сервер: `start_webui.py` или `.venv\Scripts\python -m uvicorn src.web.app:app`

---

## 1. Проверка таблиц contacts и interactions

### 1.1. БД создалась корректно
**Шаги:**
1. Останови сервер, удали `data/valuehunt.db`
2. Запусти сервер заново
3. Открой `http://127.0.0.1:8100/api/contacts`

**Ожидание:** `{"items": []}` — пустой список, статус 200.
**Почему:** `init_db()` выполняется при старте, `CREATE TABLE IF NOT EXISTS contacts` создаёт таблицу.

**Дополнительно — через консоль:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.db import get_connection; conn=get_connection(); print([r[0] for r in conn.execute('SELECT name FROM sqlite_master WHERE type=\'table\'').fetchall()])"
```
**Ожидание:** в списке есть `contacts` и `interactions`.

### 1.2. Создать контакт через UI
**Шаги:**
1. Открой `http://127.0.0.1:8100/contacts`
2. Нажми «+ Добавить контакт»
3. Заполни: Имя = «Тест HR», Роль = «HR», Источник = «HH», Приоритет = «A», Telegram = «@test_hr»
4. Сохрани

**Ожидание:** контакт появился в таблице, секция «A — важно».
**Почему:** POST `/api/contacts` → `save_contact()` → INSERT в таблицу `contacts`.

### 1.3. Добавить взаимодействие к контакту
**Шаги:**
1. Кликни на контакт «Тест HR» в таблице → открылась модалка
2. Внизу разверни «+ Добавить взаимодействие»
3. Тип = «Первое обращение», Направление = «Исходящее», Суть = «Написал в Telegram»
4. Результат = «Ожидание», Следующее действие = завтрашняя дата (YYYY-MM-DD)
5. Добавь

**Ожидание:** в истории взаимодействий появилась запись.
**Почему:** POST `/api/interactions` → `save_interaction()` → INSERT в `interactions`. Модалка перезагружает контакт через GET `/api/contacts/{id}`.

### 1.4. Просроченные действия
**Шаги:**
1. Открой `http://127.0.0.1:8100/contacts`
2. Посмотри верх страницы

**Ожидание:** если у контакта есть `next_action_date <= сегодня`, то блок «Просроченные действия» отображается с именем контакта и типом действия.
**Почему:** GET `/api/contacts/due-for-action` → `get_contacts_due_for_action()` → SQL с `WHERE next_action_date <= date('now')`.

### 1.5. Редактировать контакт
**Шаги:**
1. Кликни на контакт → модалка
2. Измени имя на «Тест HR 2», нажми Сохранить
3. Закрой модалку, открой её снова

**Ожидание:** имя изменилось на «Тест HR 2».
**Почему:** PUT `/api/contacts/{id}` → `save_contact()` → UPDATE в `contacts`.

### 1.6. Удалить контакт
**Шаги:**
1. Наведись на контакт в таблице, нажми ✕
2. Подтверди удаление

**Ожидание:** контакт исчез из таблицы.
**Почему:** DELETE `/api/contacts/{id}` → `delete_contact()` → DELETE FROM `contacts`.

### 1.7. Фильтрация контактов
**Шаги:**
1. Создай 2 контакта с разными приоритетами (S и C)
2. Выбери в фильтре «S — срочно»

**Ожидание:** отображается только контакт с priority=S.
**Почему:** GET `/api/contacts?priority=S` → `get_contacts()` → SQL с WHERE clause.

---

## 2. Проверка CHECK constraint на status

### 2.1. Статус из списка допускается
**Шаги:**
1. Открой детальную карточку вакансии: `http://127.0.0.1:8100/vacancies/{id}`
2. Смени статус на «applied»

**Ожидание:** статус изменился, ошибок нет.
**Почему:** POST `/api/vacancies/{id}/status` → UPDATE `vacancies SET status='applied'` — значение в списке разрешённых.

### 2.2. Статус вне списка — ошибка (только через консоль)
**Шаги:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.db import get_connection; conn=get_connection(); conn.execute(\"UPDATE vacancies SET status='INVALID' WHERE id=1\")"
```

**Ожидание:** `sqlite3.OperationalError` или ошибка от триггера.
**Почему:** триггер `trg_vacancies_status_update` проверяет NEW.status на каждом UPDATE.

### 2.3. INSERT с невалидным статусом — ошибка (только через консоль)
**Шаги:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.db import get_connection; conn=get_connection(); conn.execute(\"INSERT INTO vacancies (hh_id, title, status) VALUES ('test_bad_status', 'Test', 'bad_status')\")"
```

**Ожидание:** `sqlite3.OperationalError: Invalid vacancy status: bad_status`
**Почему:** триггер `trg_vacancies_status_check` срабатывает BEFORE INSERT.

---

## 3. Проверка VacancyGateCheck

### 3.1. Gate A pass + Gate B pass
**Шаги:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.gate_check import evaluate; r=evaluate({'title':'PM', 'description':'remote', 'salary_from':250000, 'location':'spb'}); print(r['passed'], r['gate_a']['passed'], r['gate_b']['passed'])"
```

**Ожидание:** `True True True`
**Почему:** ЗП ≥ 250k (salary_from), удалёнка (description содержит "remote"), локация СПб, Gate B — title содержит "PM" → архетип 01.

### 3.2. Gate A fail (офис, нет удалёнки)
**Шаги:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.gate_check import evaluate; r=evaluate({'title':'PM', 'description':'office', 'salary_from':250000, 'location':'msk'}); print(r['passed'], r['gate_a']['passed'])"
```

**Ожидание:** `False False`
**Почему:** description содержит "office", не содержит "remote"/"hybrid". Gate A: удалёнка → fail.

### 3.3. Gate B fail (не PM архетип)
**Шаги:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.gate_check import evaluate; r=evaluate({'title':'Водитель', 'description':'remote', 'salary_from':250000, 'location':'spb'}); print(r['passed'], r['gate_b']['passed'], r['gate_b'])"
```

**Ожидание:** `False False` с `"archetypes": []`
**Почему:** "Водитель" не соответствует ни keywords архетипа 01, ни архетипа 03.

### 3.4. Gate B pass (архетип 03 — Product)
**Шаги:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.gate_check import evaluate; r=evaluate({'title':'Product Manager', 'description':'remote, agile', 'salary_from':250000, 'location':'spb'}); print(r['passed'], r['gate_b']['archetypes'])"
```

**Ожидание:** `True ['03']`
**Почему:** "Product Manager" содержит keywords "product manager" и "product" → соответствует архетипу 03.

---

## 4. Проверка импорта из contacts.md

### 4.1. Запуск импорта
**Шаги:**
```powershell
cd ValueHunt
.venv\Scripts\python.exe scripts\import_contacts.py
```

**Ожидание:**
```
Импорт завершён:
  Компаний найдено: N
  Контактов импортировано: M
  Вакансий обновлено: K
  Взаимодействий импортировано: P
```
**Почему:** Скрипт парсит `contacts.md`, извлекает контакты, взаимодействия, сопоставляет компании и вакансии по имени (fuzzy match).

### 4.2. Проверка результата
**Шаги:**
1. Открой `http://127.0.0.1:8100/api/contacts`

**Ожидание:** список контактов из файла (с именами HR из 2ГИС, VK, Avito, OZON и т.д.).
**Почему:** импорт записал данные в таблицу `contacts`.

---

## 5. Проверка matrix.yaml → UESCalculator

### 5.1. UESCalculator использует keywords из matrix.yaml
**Шаги:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.ues import UESCalculator; u=UESCalculator(); kw=u._kw_map; print('Ключей из matrix.yaml:', len(kw)); print('Пример:', list(kw.keys())[:3])"
```

**Ожидание:** `Ключей из matrix.yaml: ~28` (все критерии из 7 групп). Пример: `['pm_po_hybrid', 'enterprise_scale', 'product_influence']`
**Почему:** `_load_keywords()` читает `matrix.yaml`, собирает `{criterion_id: {"positive": [...], "negative": [...]}}`.

### 5.2. Полный скоринг
**Шаги:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.ues import UESCalculator; u=UESCalculator(); r=u.evaluate({'title':'Senior Project Manager', 'description':'Enterprise remote DWH BI Kafka проекты, управление командой 10+ человек', 'salary_from':300000, 'skills':['PM','Agile','Scrum']}); print(f\"Score: {r['score']}, Category: {r['category']}, Gate A: {r['gate_a']['passed']}, Gate B: {r['gate_b']['passed']}\")"
```

**Ожидание:** `Score: ~7-9`, `Category: S/A`, `Gate A: True`, `Gate B: True`
**Почему:** вакансия проходит Gate A (remote, salary 300k), Gate B ("Project Manager" → архетип 01), скоринг находит совпадения по keywords: "enterprise", "dwh", "bi", "kafka", "управление".

---

## 6. Сквозной пользовательский сценарий

### 6.1. Полный цикл: сканирование → оценка → контакт
**Шаги:**
1. Запусти сервер
2. Открой Дашборд (`/`) → нажми «Запустить сканирование»
3. Дождись результата (30-60 сек)
4. Открой Вакансии (`/vacancies`) — видишь список с Score и категориями
5. Кликни на любую вакансию — видишь детали, можешь сменить статус
6. Открой Контакты (`/contacts`) — если есть HR-контакты, они в таблице
7. Кликни на контакт → видишь историю, можешь добавить follow-up
8. Выбери дату следующего действия (например, завтра)
9. На следующий день открой Контакты — блок «Просроченные действия» покажет контакт

**Ожидание:** все шаги выполняются без ошибок, данные консистентны между страницами.
**Почему:** единая БД SQLite, все модули читают/пишут через `db.py`.

---

---

## 7. Проверка Soft Delete (Корзина) — v0.3.0

### 7.1. Удаление с причиной через API
**Шаги:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.db import get_connection, trash_vacancy; conn=get_connection(); v=conn.execute('SELECT id FROM vacancies WHERE deleted_at IS NULL LIMIT 1').fetchone(); print('Vacancy ID:', v[0]); trash_vacancy(conn, v[0], 'Зарплата ниже ожидаемой'); print('OK')"
```

**Ожидание:** `Vacancy ID: N` → `OK`. Вакансия не удалена физически, но `deleted_at IS NOT NULL`.
**Почему:** `trash_vacancy()` делает `UPDATE vacancies SET deleted_at=datetime('now'), delete_reason=? WHERE id=?`.

### 7.2. Восстановление
**Шаги:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.db import get_connection, restore_vacancy; conn=get_connection(); v=conn.execute('SELECT id FROM vacancies WHERE deleted_at IS NOT NULL LIMIT 1').fetchone(); print('Trashed ID:', v[0]); restore_vacancy(conn, v[0]); print('Restored:', conn.execute('SELECT deleted_at, status FROM vacancies WHERE id=?', [v[0]]).fetchone())"
```

**Ожидание:** `Trashed ID: N` → `Restored: (None, 'new')`
**Почему:** `restore_vacancy()` очищает `deleted_at` и ставит `status='new'`.

### 7.3. Hard Delete (только из корзины)
**Шаги:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.db import get_connection, trash_vacancy, hard_delete_vacancy; conn=get_connection(); v=conn.execute('SELECT id FROM vacancies WHERE deleted_at IS NULL LIMIT 1').fetchone(); id=v[0]; trash_vacancy(conn, id, 'Другое'); hard_delete_vacancy(conn, id); print('Exists:', conn.execute('SELECT id FROM vacancies WHERE id=?', [id]).fetchone())"
```

**Ожидание:** `Exists: None` — запись физически удалена.
**Почему:** `hard_delete_vacancy()` проверяет `deleted_at IS NOT NULL` перед DELETE.

### 7.4. Удаление активной вакансии (без trash) не сработает
**Шаги:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.db import get_connection, hard_delete_vacancy; conn=get_connection(); v=conn.execute('SELECT id FROM vacancies WHERE deleted_at IS NULL LIMIT 1').fetchone(); print('Try hard delete active ID:', v[0]); hard_delete_vacancy(conn, v[0]); print('Still exists:', conn.execute('SELECT id FROM vacancies WHERE id=?', [v[0]]).fetchone() is not None)"
```

**Ожидание:** `Try hard delete active ID: N` → `Still exists: True` — не удалилась.
**Почему:** `hard_delete_vacancy()` содержит `AND deleted_at IS NOT NULL` в WHERE.

### 7.5. Корзина через UI
**Шаги:**
1. Открой любую вакансию: `http://127.0.0.1:8100/vacancies/{id}`
2. Нажми кнопку «🗑 Удалить»
3. Выбери причину в модалке, подтверди

**Ожидание:** вакансия исчезла со списка, появилась в корзине (`/trash`). Счётчик в боковом меню увеличился.

### 7.6. Восстановление и удаление навсегда через UI
**Шаги:**
1. Открой `/trash`
2. Найди удалённую вакансию, нажми «↩ Вернуть»

**Ожидание:** вакансия вернулась в список активных со статусом «Новые».
3. Нажми «× Удалить навсегда» на другой корзинной вакансии
4. Подтверди

**Ожидание:** вакансия исчезла из корзины, в БД её больше нет.

---

## 8. Проверка Drop-Out Scoring — v0.3.0

### 8.1. Критерий с keywords и 0 совпадений не штрафует
**Шаги:**
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.ues import UESCalculator; u=UESCalculator(); r=u.evaluate({'title':'PM', 'description':'test', 'salary_from':300000, 'skills':[]}); print(f'Score: {r[\"score\"]}, Active criteria: {r[\"score_detail\"][\"active_criteria\"]}/{r[\"score_detail\"][\"total_criteria\"]}')"
```

**Ожидание:** `Score: ~5.0-6.0`, `Active criteria: N/M` где N < M (часть критериев с keywords выпала из-за 0 совпадений).
**Почему:** `_score_groups()` считает только критерии с совпадениями >0 или без keywords. Падение с 7.65 до ~5.0 значит, что только Gate-фильтры + немного базовых совпадений сработали.

### 8.2. Критерий без keywords всегда участвует
Проверяется косвенно: criteria без keywords (fin_salary, comp_age, comp_hr, comp_ceo) всегда дают свою нормированную оценку.

---

## 9. Проверка reevaluate — v0.3.0

### 9.1. Массовый пересчёт всех активных вакансий
**Шаги:**
1. Открой `/matrix`
2. Нажми «Пересчитать UES»

**Ожидание:** все вакансии пересчитаны, ошибок нет. После обновления дашборда — актуальные баллы.
**Почему:** `/api/reevaluate` вызывает `u.evaluate()` для каждой активной вакансии. Предыдущий баг `d[0]` (cid вместо name) в `PRAGMA table_info` был исправлен на `d[1]`.

### 9.2. Изменение маトリцы → reevaluate
**Шаги:**
1. В `/matrix` измени вес любой группы или критерия
2. Нажми «Сохранить матрицу»
3. Должна появиться кнопка «Актуально для применения — пересчитать UES»

**Ожидание:** баллы на дашборде не изменились, пока не нажата кнопка пересчёта.

---

## Расшифровка: почему я получаю такой результат

### Как работает CHECK constraint на status
В SQLite нельзя добавить CHECK к существующей колонке через `ALTER TABLE`. Поэтому мы сделали два уровня защиты:
1. **Новые БД** — в `CREATE TABLE vacancies` прописан `CHECK(status IN (...))` → работает сразу
2. **Существующие БД** — два триггера (`BEFORE INSERT` и `BEFORE UPDATE OF status`) эмулируют CHECK

Если ты попытаешься записать `status='xyz'`:
- Через Python API (`POST /api/vacancies/{id}/status`) — FastAPI примет запрос, SQLite вернёт ошибку, API вернёт 500
- Напрямую в консоли — триггер вызовет `RAISE(ABORT)` → `sqlite3.OperationalError`

### Как работает VacancyGateCheck
Это 20-строчная обёртка над `UESCalculator._check_gate_a()` и `_check_gate_b()`. Она не делает полный скоринг (3 группы × 14 критериев), а только проверяет Gates. Нужна для быстрого pre-filtering в будущем pipeline массового сканирования.

Gate A проверяет:
1. **Удалёнка**: `work_format` вакансии или поиск в тексте "remote"/"удалён"/"гибрид"
2. **ЗП**: `salary_from >= 200k` (минимальный проход) или `salary_from >= 250k` (целевой)
3. **Локация**: Москва/СПб/удалёнка

Gate B проверяет:
- **Архетип 01**: keywords "project manager", "pm", "delivery manager", "enterprise", "руководитель проектов"...
- **Архетип 03**: keywords "product manager", "product owner", "po", "продукт"...

### Как UESCalculator использует matrix.yaml
При инициализации (`__init__`) загружает keywords из `matrix.yaml` в `_kw_map`. Когда `_rate_criterion()` вызывается для конкретного criterion_id:
1. Сначала ищет ID в `_kw_map` (из matrix.yaml) — если найден, использует эти keywords
2. Если не найден — падает на хардкод в `_get_keywords()`

Это позволяет со временем перенести все keywords из кода в конфиг без поломки существующей логики.

### Как работает импорт из contacts.md
Скрипт `import_contacts.py`:
1. Читает Markdown-файл, разбивает на блоки компаний (##)
2. Внутри каждого блока ищет секции: Контакты (таблица), Вакансии (таблица), История (таблица)
3. Маппит статусы: 🔵→new, 🟡→applied, 🟢→call, 🔷→in_progress, 🟣→offer, 🔴→rejected, ⚪→archived, ⚫→closed
4. Маппит типы взаимодействий: Отклик→outreach, Созвон→call, Собеседование→interview, Тестовое→test_task...
5. Пытается сопоставить компании по имени (сначала exact match, потом fuzzy — без пробелов/дефисов, регистронезависимо)
6. Пытается сопоставить вакансии по названию компании и части названия вакансии

Если компания не найдена — контакты импортируются без company_id (NULL). Это нормально для первого импорта. Позже, когда пользователь добавит эти компании через сканирование, можно будет связать вручную или через повторный импорт с fuzzy match.
