---
id: AT-BUG-053
title: "settings_screen.rename_filter_button_locator ищет content-desc «Renam3» вместо «Rename» — TC-085/TC-086 broken на шаге переименования профиля"
type: test_debt
debt_kind: weak_locator
severity: major
status: Open
found_in: "framework commit 2f26f8a (тестируемая сборка приложения 1.10 (versionCode 11), build 6455af0c — от сборки НЕ зависит)"
fixed_in: ""
last_seen_in: "RUN-20260804-1624 (2026-08-04)"
test_cases: ["TC-085", "TC-086"]
runs: ["RUN-20260804-1624"]
duplicates: []
regression_of: ""
status_since: "2026-08-04T22:20:45Z"
updated: "2026-08-04T22:20:45Z"
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

# AT-BUG-053 — локатор кнопки Rename несёт опечатанный content-desc «Renam3»

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: weak_locator`), поверхность
целиком в `framework/screens/settings_screen.py` (одна функция-локатор,
строка 269). От сборки приложения не зависит: приложение рисует
`IconButton` с `content-desc="Rename"` (`SettingsScreen.kt`, зафиксировано в
`requirements` обоих кейсов TC-085/TC-086, поле не менялось).

## Суть долга

Локатор кнопки переименования фильтр-профиля собирает xpath на
`@content-desc="Renam3"`:

```python
# framework/screens/settings_screen.py:269
return (AppiumBy.XPATH, f'(//*[@text="{name}"]/following::*[@content-desc="Renam3"])[1]')
```

Такого узла в дереве нет ни на одном экране — приложение рисует `Rename`.
Оба теста, использующие этот локатор, уходят в `broken` на первом же шаге
переименования (до содержательного ассерта):

| TC | Тест | Сообщение |
|---|---|---|
| TC-085 | `test_rename_filter_profile_keeps_query_string` | `TimeoutException: не кликабелен: ('xpath', '(//*[@text="My saved search"]/following::*[@content-desc="Renam3"])[1]')` |
| TC-086 | `test_rename_filter_profile_to_duplicate_name` | `TimeoutException: не кликабелен: ('xpath', '(//*[@text="Profile B"]/following::*[@content-desc="Renam3"])[1]')` |

Провенанс правки (не пересказ — дифф файла против байтовой копии
`scratchpad/rehearsal-backups/settings_screen.py` и `git log`): строка изменена
коммитом `2f26f8a` фреймворкового репозитория, было `Rename`, стало `Renam3`;
никакого изменения в приложении между последним зелёным прогоном
`RUN-20260803-2012` (оба кейса passed) и `RUN-20260804-1624` нет —
`state/app-under-test.yaml` в обоих прогонах несёт одну и ту же сборку
`1.10 (11)`, `source_commit 63f6aac3`, apk `6455af0c`.

## Как чинить (для test-maintainer)

Вернуть `content-desc="Rename"` в `rename_filter_button_locator`
(`framework/screens/settings_screen.py:269`) и прогнать TC-085/TC-086.
Проверить класс, не экземпляр: пройти по остальным локаторам
`settings_screen.py`, собранным на `@content-desc`, и сверить каждую строку с
фактическим `contentDescription` в `SettingsScreen.kt` — опечатка в
константе локатора не ловится ничем, кроме прогона самого теста
(red_probe кейса был снят 2026-07-21, до порчи).

## Ссылки

- Прогон: `runs/RUN-20260804-1624.md` (раздел «Падения и триаж», вердикт `TEST_BUG`)
- Артефакты падений: `runs/RUN-20260804-1624/allure/237b1d86-843b-47b9-b100-b37a206df5c1-result.json` (TC-085),
  `runs/RUN-20260804-1624/allure/4ff1ad91-6a42-42e3-acda-ac092071e281-result.json` (TC-086)
- Кейсы: `test-cases/filter-profiles/TC-085.md`, `test-cases/filter-profiles/TC-086.md`
