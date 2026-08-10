---
id: AT-BUG-053
title: "settings_screen.rename_filter_button_locator ищет content-desc «Renam3» вместо «Rename» — TC-085/TC-086 broken на шаге переименования профиля"
type: test_debt
debt_kind: weak_locator
severity: major
status: Fixed
found_in: "framework commit 2f26f8a (тестируемая сборка приложения 1.10 (versionCode 11), build 6455af0c — от сборки НЕ зависит)"
fixed_in: "d96eef9"
last_seen_in: "RUN-20260810-0146 (2026-08-10)"
test_cases: ["TC-085", "TC-086"]
runs: ["RUN-20260804-1624", "RUN-20260810-0146"]
duplicates: []
regression_of: ""
status_since: "2026-08-10T09:34:00Z"
updated: "2026-08-10T09:34:00Z"
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

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-10 | 1.10 (11), сборка приложения не тронута (test_debt в обвязке) | `Invoke-Pytest -k "test_rename_filter_profile" -v` (TC-085 `test_rename_filter_profile_keeps_query_string`, TC-086 `test_rename_filter_profile_to_duplicate_name`) — 3 прогона подряд | run1 `2 passed, 312 deselected in 131.56s (0:02:11)`, run2 `2 passed, 312 deselected in 131.26s (0:02:11)`, run3 `2 passed, 312 deselected in 126.87s (0:02:06)`, все три `PYTEST_EXIT=0` | Fixed (test-maintainer; таблица верификации D1 — за fix-verifier следующим проходом) |

## Обсуждение

**2026-08-10T09:34:00Z — test-maintainer, фикс (B4):**

Причина устранена по месту (не замаскирована): `_rename_button_locator`
(`framework/screens/settings_screen.py:269`) собирал xpath на
`@content-desc="Renam3"` — опечатка коммита `2f26f8a`. Заменено на
`@content-desc="Rename"`, сверено с местом рендера
(`SettingsScreen.kt:852`, `IconButton(onClick = {
viewModel.requestRenameFilter(filter) })` → `Icon(...,
contentDescription = "Rename", ...)`). Ассерт кейсов не менялся —
TC-085/TC-086 проверяли и проверяют переименование профиля по существу,
падение было исключительно на шаге открытия диалога (клик по
несуществующему узлу).

**Класс, не экземпляр — сверка ОСТАЛЬНЫХ `@content-desc`-локаторов
`settings_screen.py` с `SettingsScreen.kt` (read-only):**

| Локатор | Строка фреймворка | Строка приложения | Совпадает? |
|---|---|---|---|
| `_rename_button_locator` (`content-desc="Rename"`, после фикса) | `settings_screen.py:269` | `SettingsScreen.kt:852` `contentDescription = "Rename"` | Да |
| `_delete_button_locator` (`content-desc="Delete"`) | `settings_screen.py:236` | `SettingsScreen.kt:860` `contentDescription = "Delete"` | Да |

Других локаторов, собранных на `@content-desc="..."` (буквальный литерал
в XPath/UiSelector), в файле нет — сверено `Grep` по паттерну
`@content-desc="` (2 совпадения, оба выше). Остальные упоминания
`content-desc` в файле — только докстринги/комментарии (строки 85, 110,
136, 163, 205, 208, 212, 254), не исполняемый код. Прочие локаторы файла
опираются на `@text`/`@checkable`/`className`, вне поверхности этого
долга (класс `weak_locator` здесь — именно опечатанный литерал
content-desc). Новых аналогичных дефектов не найдено — правку класса
завершать некуда.

Прогон `Invoke-Pytest -k "test_rename_filter_profile" -v` — 3 раза
подряд, все зелёные (см. таблица верификации выше), `Get-Device` →
`DEVICE: emulator-5554` перед прогонами.

`git status --porcelain -- app-under-test/` — пустой вывод (сверено до
и после правки); дифф целиком в `framework/screens/settings_screen.py`
(1 строка), коммит `d96eef9`.

Новых блокеров/долгов в ходе работы не найдено (фикстуры/сидинг/replay
не затронуты, живое дерево доступно штатно).

Статус: `Open` → `Fixed`. Лок снят.

## Ссылки

- Прогон: `runs/RUN-20260804-1624.md` (раздел «Падения и триаж», вердикт `TEST_BUG`)
- Артефакты падений: `runs/RUN-20260804-1624/allure/237b1d86-843b-47b9-b100-b37a206df5c1-result.json` (TC-085),
  `runs/RUN-20260804-1624/allure/4ff1ad91-6a42-42e3-acda-ac092071e281-result.json` (TC-086)
- Кейсы: `test-cases/filter-profiles/TC-085.md`, `test-cases/filter-profiles/TC-086.md`
