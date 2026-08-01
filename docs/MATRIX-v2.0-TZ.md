# ТЗ: Внедрение матрицы ценностей v2.0

**Исходник:** `config/matrix.yaml` → заменить на содержимое `docs/MATRIX-v2.0-SPEC.md`  
**Полное описание (все детали):** `docs/MATRIX-v2.0-SPEC.md` — читать после этого ТЗ

## Суть одной серией

### 1. Новая структура matrix.yaml
- Было: 7 групп, 28 критериев
- Стало: **8 групп, 32 критерия** (добавлена группа «Отраслевой интерес», группа «Условия работы» перераспределена)
- Все веса, имена, keywords — заменить на указанные в SPEC
- Порядок групп и критериев сохранить как в SPEC
- **Блоки (gambling, non-PM role, gamedev)** — временно оставить как есть (из текущей ues_config.json), не менять до отдельного обсуждения

### 2. Подключить YAML к скорингу
- matrix.yaml → единственный источник kw для UESCalculator
- Удалить хардкодный `kw_map` из `ues.py` (строки 268-324)
- Читать keywords из matrix.yaml, а не из Python-словаря

### 3. Блоки (red flags) — вынести в matrix.yaml
Секция `blocks` в корне YAML (см. SPEC раздел 4):
- `ban_gambling` — full_text, reject
- `ban_non_pm_role` — title, reject (двуязычный — английские + русские не-PM роли)
- `ban_gamedev` — full_text, reject

Проверять ДО Gate'ов. При совпадении → score=0, REJECT, без скоринга.

### 4. Gate B — исправить матчинг
Было: проверка подстроки (например, «руководитель» входит в «руководитель отдела продаж» → false pass)
Стало: проверка целых биграмм/слов (word match mode)
- archetype_01 (Enterprise PM) — keywords из SPEC 5.2
- archetype_03 (Hybrid PM-PO) — keywords из SPEC 5.2

### 5. Gate A — добавить net/gross preprocessing
Перед проверкой salary:
- gross / до вычета → × 0.87
- net / на руки → как есть
- неопределено → gross

### 6. Scoring — обновить параметры
```yaml
match_curve: [[0, 5.0], [1, 6.0], [2, 7.0], [3, 8.0], [4, 9.0]]
zero_keyword_default: 5.0
stretch: disabled
```

### 7. Weight = 0 («неважно»)
Расширить движок: если weight=0
- критерий не ищет keywords
- не участвует в сумме весов группы (denominator)
- не отображается в анализе как failed

То же для группы: weight=0 → группа исключена из финала

### 8. Тест — 10 вакансий из SPEC раздела 10
После внедрения проверить:
- ECOS → REJECT (gambling block)
- Риверхаус → REJECT (non-PM role)
- Azur Games → REJECT (gamedev)
- Северсталь → ~4.5 C
- КРОК → REJECT
- VK → REJECT
- Остальные — допуск ±0.5

## Порядок работ
1. matrix.yaml → новая структура (8 групп, 32 критерия)
2. UESCalculator → читает YAML вместо kw_map
3. blocks → секция в matrix.yaml + логика reject
4. Gate A + salary net/gross preprocessing
5. Gate B → word match mode
6. Scoring params → новые значения
7. Weight=0 → модификация расчёта
8. Регресс-тест (10 вакансий)
