---
id: AT-BUG-079
title: "Квотирование shell-команд в adb.py неполное: run_as_file_or_raise и push_app_file интерполируют пути БЕЗ защиты"
type: test_debt
debt_kind: broken_environment
severity: minor
status: Open
found_in: "triaged from D1-AT-BUG-069 round2 (critic-вход, 2026-08-16T00:15:00Z), class_completeness audit"
fixed_in: ""
last_seen_in: ""
test_cases: []
runs: []
duplicates: []
regression_of: "AT-BUG-069"
status_since: "2026-08-16T00:15:00Z"
updated: "2026-08-16T00:15:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

# AT-BUG-079 — Asymmetric shell-quotation: run_as_file_or_raise и push_app_file БЕЗ кавычек

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: broken_environment`) — не зависит от сборки приложения, весь код в `framework/core/adb.py` и вызывающих функциях.

## Суть долга

Сиблинг-класс AT-BUG-069 (B4-фикс `pull_app_file` квотирования, коммит `6bc81f3`). При анализе полноты class-coverage квотирования remote-shell-команд найдены ДВЕ функции, строящие команды БЕЗ защиты от пробелов/метасимволов в путях:

1. **`framework/core/adb.py:378` (`run_as_file_or_raise`)**
   ```python
   out = shell(
       f"run-as {_PKG} sh -c 'cat {path} 2>/dev/null; "
       f"echo {_RUN_AS_FILE_RC_SENTINEL}$?'",
       timeout=timeout,
   )
   ```
   Интерполяция `{path}` без кавычек. Вызывается из `app_steps.py:323` через `_TABS_PREFS_PATH` (`framework/data/consts.py` или эквивалент).

2. **`framework/core/adb.py:556` (`push_app_file`)**
   ```python
   cp_copy = _run(["-s", settings.DEVICE_NAME, "shell", 
       f"run-as {_PKG} cp {tmp} {rel_path}"])
   ```
   Интерполяция `{tmp}` и `{rel_path}` без кавычек. Вызывается из `seed_db.py:557` и других мест инициализации БД.

Класс уязвимости идентичен тому, что чинили в `pull_app_file` (B4, AT-BUG-069 фикс): пробел/пустая строка/метасимволы в `path`/`rel_path` вызовут неправильный парсинг shell'ом и могут привести к hang, потере данных или неопределённому поведению.

## Статус достижимости

**Недостижимо СЕЙЧАС** (latent debt):
- Критик перечислил все ТЕКУЩИЕ вызывающие стороны обеих функций — все передают module-константы без пробелов и метасимволов (`_TABS_PREFS_PATH`, `_DB_REL`, `_WAL`, `_SHM`, где все пути = строки типа `"files/ao3_ratings.db"`)
- `push_app_file` вдобавок громко фейлит (returncode проверяется и выбрасывает `RuntimeError` при ошибке), что снижает вероятность undetected-отказа
- Приоритет низкий, но поверхность для будущих регрессий существует

## Анализ

**Почему это test_debt, а не просто оставить:**

1. **Класс дефекта известен:** AT-BUG-069 (B4-фикс) установил precedent квотирования всех интерполяций в shell-командах. Эти ДВЕ функции остались неполные по той же логике.

2. **D-0043 (CLAUDE.md, "Чини класс, а не экземпляр"):** Дефект-класс = "unquoted shell interpolation в adb-командах". Узкий экземпляр (`pull_app_file`) уже зачинен; остальные узкие экземпляры того же класса (`run_as_file_or_raise`, `push_app_file`) требуют симметричного лечения, иначе молчаливое оставление аналога = нарушение.

3. **Не регрессия AT-BUG-069:** Код-трассировка показывает, что `run_as_file_or_raise` и `push_app_file` остались неизменёнными после B4-фикса `pull_app_file` (другие функции, не затронутые коммитом `6bc81f3`).

## Рекомендация фикса

Добавить кавычки (простые `'` внутри f-string, или использовать f-string + экранирование):

```python
# run_as_file_or_raise (line 378):
out = shell(
    f"run-as {_PKG} sh -c 'cat '{path}' 2>/dev/null; "
    f"echo {_RUN_AS_FILE_RC_SENTINEL}$?'",
    timeout=timeout,
)
# или более безопасно — экранировать одинарные кавычки в пути:
safe_path = path.replace("'", "'\\''")
out = shell(
    f"run-as {_PKG} sh -c 'cat '{safe_path}' 2>/dev/null; "
    f"echo {_RUN_AS_FILE_RC_SENTINEL}$?'",
    timeout=timeout,
)
```

```python
# push_app_file (line 556):
cp_copy = _run(["-s", settings.DEVICE_NAME, "shell", 
    f"run-as {_PKG} cp '{tmp}' '{rel_path}'"])
# или с экранированием:
safe_tmp = tmp.replace("'", "'\\''")
safe_rel = rel_path.replace("'", "'\\''")
cp_copy = _run(["-s", settings.DEVICE_NAME, "shell", 
    f"run-as {_PKG} cp '{safe_tmp}' '{safe_rel}'"])
```

## Связанные находки

- **AT-BUG-069** — B4-фикс `pull_app_file` квотирования; этот долг — остаток того же класса дефектов (asymmetric shell-quotation)
- **D-0043 (CLAUDE.md)** — "Чини класс, а не экземпляр"; обязанность доклада аналогов по полноте покрытия

## Частота

Не наблюдалась в текущих проходах (все вызывающие передают безопасные константы), но класс дефекта реален и может проявиться при будущих изменениях путей или вводимых пользователем данных.

## Верификация (заполняет test-maintainer)

| Дата | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|

## Обсуждение

**[qa @ 2026-08-16T00:15:00Z]**

Триаж критик-входа D1 AT-BUG-069, раунд 2 (class_completeness audit). При поиске всех remote-shell-команд в `framework/core/adb.py` (следуя прецеденту AT-BUG-069 B4-фикса `pull_app_file`) найдены ещё две функции с неполным квотированием интерполяций: `run_as_file_or_raise` (line 378) и `push_app_file` (line 556).

Недостижимо СЕЙЧАС (все текущие вызывающие передают module-константы без пробелов/метасимволов, `push_app_file` громко фейлит при ошибке), но класс дефекта существует и требует симметричного лечения по D-0043. Приоритет низкий, так как latent и не блокирует текущие тесты.

Severity: **minor** — latent debt, недостижимо сегодня, но требует очистки для эффектности механизма класса.

Awaiting: none

## Чек-лист качества

- [x] Проверены дубликаты среди открытых AT-BUG-* (`bugs/AT-BUG-*.md`, status != Verified/Rejected)
- [x] Точные позиции в коде: `framework/core/adb.py:378` и `:556`
- [x] Severity обоснована — latent, недостижимо СЕЙЧАС, низкий приоритет
- [x] Сиблинг AT-BUG-069 и класс дефекта идентифицированы
- [x] Рекомендация фикса приложена (примеры квотирования)
- [x] Все текущие вызывающие названы и перечислены (полнота audit)
- [x] Ни одного изменения в тестовой системе не внесено; только анализ
- [x] Долг-класс определён (asymmetric shell-quotation, broken_environment)
