---
key: "AT-BUG-062"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p1"
summary: "Нестабильный TC-085 (rename filter-profile): «профиль «My renamed search» не найден в списке Settings» в полном регрессе, 3/3 зелёный в изоляции; артефакт падения не содержит секцию Saved AO3 Filters (фолбэк swipe_up возвращает список наверх)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-085", "run:RUN-20260811-0406", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-13T17:40:00Z"
updated: "2026-08-13T17:40:00Z"
archived: false
resolution: "done"
---

# Нестабильный TC-085 (rename filter-profile): «профиль «My renamed search» не найден в списке Settings» в полном регрессе, 3/3 зелёный в изоляции; артефакт падения не содержит секцию Saved AO3 Filters (фолбэк swipe_up возвращает список наверх)

_Спроецировано из `bugs/AT-BUG-062.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-062 — карантин TC-085: после переименования профиль не найден в списке Settings; в изоляции не воспроизводится

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`). Поверхность:
`framework/tests/test_filter_profiles.py::test_rename_filter_profile_keeps_query_string`
(`@pytest.mark.p1`, `@pytest.mark.replay`, `listing_basic.mitm`),
`framework/steps/settings_steps.py:507` (`assert_filter_profile_listed`),
`framework/screens/settings_screen.py:224-233` (`_swipe_to_profile`/`has_filter_profile`),
`:279-293` (`enter_rename_name`/`confirm_rename`/`rename_filter_profile`),
`framework/screens/base_screen.py:120-183` (`_swipe_search`, AT-BUG-048).
Эмулятор `ao3_test_api34` (`emulator-5554`, API 34), Appium `:4723`, replay.

## Наблюдение

| Прогон | Дата | Исход | Сообщение |
|---|---|---|---|
| `RUN-20260811-0406` (regression, replay, сборка cc201f78) | 2026-08-11 | FAILED | `AssertionError: фильтр-профиль «My renamed search» не найден в списке Settings` (`steps/settings_steps.py:507`, тест — строка 107) |

Ключевые детали артефакта
(`runs/RUN-20260811-0406/allure/544709d4-31fe-419d-ae74-857cf09948b4-result.json`):

- Шаги ДО ассерта — зелёные, в т.ч. `When в Settings профиль «My saved search»
  переименован в «My renamed search»` (диалог открылся, поле заполнено,
  подтверждение нажато — 3.29с).
- Две diagnostic-аттачки `swipe_to_text` (AT-BUG-048), обе дословно:
  `«My renamed search»: КОНЕЦ СПИСКА (позиция не изменилась после свайпа) —
  строка не поймана, список исчерпан` — то есть и прямой (`swipe_to_text`),
  и обратный (`swipe_up_to_text`) проход упёрлись в границу списка.
- `page_source` момента падения
  (`d95ea445-623b-41da-b259-3dc4ecae3a84-attachment.xml`) содержит ВЕРХ Settings
  (`READER`/`Theme`/…/`CONTENT VISIBILITY`/`Hide Kudosed works`) — секции
  `SAVED AO3 FILTERS` в дампе НЕТ. Причина — не состояние приложения, а сам
  хелпер: `_swipe_to_profile` = `swipe_to_text(...) or swipe_up_to_text(...)`,
  и фолбэк возвращает список НАВЕРХ, поэтому снимок/скриншот делаются уже не на
  той секции, которую проверял ассерт.
- `logcat` (`e34e1362-…`) покрывает только последние ~6с (обратный проход):
  `Matched 0 elements using selector UiSelector[TEXT=My renamed search]` ×4
  (settle-окно `poll_for`), затем конец списка.

## Изолированные перепрогоны (failure-analyst, 2026-08-11, та же сборка cc201f789, `Get-Device` → `DEVICE: emulator-5554`, Appium `:4723` ready)

```
Invoke-Pytest -k test_rename_filter_profile_keeps_query_string -q
  1 passed, 370 deselected in 85.08s   PYTEST_EXIT=0
  1 passed, 370 deselected in 84.02s   PYTEST_EXIT=0
  1 passed, 370 deselected in 85.57s   PYTEST_EXIT=0
```

3/3 зелёный — сигнатура падения не воспроизводится изолированно.

Две попытки файлового перепрогона (`Invoke-Pytest tests/test_filter_profiles.py -q`,
чтобы проверить зависимость от контекста файла) НЕ дали чистого замера — обе
деградировали по окружению, а не по ассерту:

- попытка 1: `3 failed, 2 passed in 354.95s`; TC-085 при этом ПРОШЁЛ строку 107
  (тот самый ассерт, что красный в прогоне) и упал ПОЗЖЕ, на строке 108, с
  `WebDriverException: Could not proxy command … connect ECONNREFUSED 127.0.0.1:8200`;
  в конце — `ENV_ISSUE (AT-BUG-026): device-liveness guard recoveries this session = 1/2`;
- попытка 2: `3 failed, 1 passed, 1 error in 178.46s`; TC-085 — `ERROR at setup`
  (device-liveness guard), остальные — `socket hang up` того же класса.

Итог замера: 3/3 зелёных изолированно + один проход мимо целевого ассерта в
файловом контексте; детерминированной поломки нет.

## Почему это НЕ сборка приложения и НЕ прежний долг AT-BUG-053

1. **Не сборка.** Диапазон `6f884d979..cc201f789` (`git -C app-under-test diff --stat`)
   трогает ровно 6 файлов: `.gitlab-ci.yml`, `PROJECT.md`,
   `app/src/main/assets/ao3_bridge.js`, `data/repository/DownloadRepository.kt`,
   `ui/browser/BottomBar.kt`, `ui/browser/BrowserViewModel.kt`. Ни
   `ui/settings/SettingsScreen.kt`, ни `SettingsViewModel` (`requestRenameFilter`/
   `confirmRenameFilter`), ни слой `FilterProfile`-репозитория не изменялись —
   путь переименования в приложении тот же, что на прошлой (зелёной для этого
   теста) проверке.
2. **В ТОМ ЖЕ прогоне зелёный TC-086** (`test_rename_filter_profile_to_duplicate_name`,
   тот же файл, тот же диалог «Rename filter», тот же
   `settings_screen.rename_filter_profile`, ассерт по UI-списку
   `assert_filter_profile_count(name_a, 2)`) — механизм переименования и
   отображения списка на этой сборке работает.
3. **Не AT-BUG-053** (`weak_locator`, `content-desc="Renam3"`, `Verified`
   2026-08-10 фиксом `d96eef9`): та сигнатура —
   `TimeoutException: не кликабелен ('xpath', '(//*[@text="My saved search"]/
   following::*[@content-desc="Renam3"])[1]')` на шаге ОТКРЫТИЯ диалога. Здесь
   шаг переименования зелёный, падение — на следующем ассерте, с другим
   сообщением. Совпадает только номер кейса.

## Почему причина не установлена (и почему это долг)

Артефакт падения не позволяет отличить две живые гипотезы, и обе — про тестовую
обвязку:

1. **Гонка ввода в диалоге.** `enter_rename_name` делает `field.clear()` +
   `field.send_keys(new_name)` без верификации фактического содержимого поля, а
   `confirm_rename` тапает `by_text("Rename")` без проверки, что кнопка активна
   (`enabled = dialogName.isNotBlank()` в приложении). Под нагрузкой полного
   регресса профиль мог быть сохранён под ДРУГИМ именем (частичный ввод/
   конкатенация) — тогда ассерт красный законно, но причина в шаге, а не в
   приложении.
2. **Промах поиска прокруткой.** Остаточный класс AT-BUG-048: строка есть, но
   settle-окно `poll_for` (1.2с/0.3с) её не застало ни в прямом, ни в обратном
   проходе.

Различить их по артефактам НЕЛЬЗЯ именно из-за диагностического пробела:
снимок/скриншот сделаны после фолбэк-свайпа наверх и не содержат секцию
`SAVED AO3 FILTERS` — то есть фактические имена профилей в момент падения
неизвестны. Тот же класс слепого наблюдения, что `AT-BUG-055`/`AT-BUG-057`
(«ассерт сообщает только факт отсутствия, не состояние экрана»).

## Что сделать (test-maintainer)

1. **Диагностика на месте падения.** `settings_steps.assert_filter_profile_listed`
   при провале обязан сообщать ФАКТИЧЕСКИЙ список имён профилей (например,
   `_scroll_fingerprint`-подобный сбор текстов на секции или чтение
   `seed_db.read_filter_profiles()` host-side, как уже делает
   `assert_filter_profiles_have_query_strings`) — тогда следующее падение само
   различит «имя другое» от «строка не поймана прокруткой».
2. **Снимок ПЕРЕД фолбэком.** Класс, а не экземпляр: `_swipe_to_profile`
   (`swipe_to_text(...) or swipe_up_to_text(...)`) — общий приём для
   `has_filter_profile`/`delete_filter_profile`/`count_filter_profile_occurrences`/
   `open_rename_dialog`; в случае неуспеха он всегда оставляет список НАВЕРХУ, и
   любой из этих ассертов даёт бесполезный page source. Прикладывать снимок
   состояния до фолбэка (или явно фиксировать позицию, где искомого нет).
3. **Верификация ввода в `enter_rename_name`**: после `clear()`+`send_keys`
   сверить `get_attribute("text")` поля с ожидаемым именем до подтверждения
   (устраняет гипотезу 1 навсегда и делает падение говорящим).
4. Снять карантин (`automation_status: quarantined → active`) после серии из 3
   зелёных прогонов на исправленном тесте (и, желательно, одного зелёного
   `tests/test_filter_profiles.py` целиком на здоровом окружении).

## Карантин

`test-cases/filter-profiles/TC-085.md`: `automation_status: active → quarantined`
(переход `active → quarantined`, машина `automation`, `schemas/transitions.yaml`,
`by: failure-analyst`), `quarantine_reason` — сигнатура падения,
`quarantine_since: 2026-08-11T02:40:00Z`, `quarantine_owner: test-maintainer`,
`quarantine_expiry` не задан (действует `sla.quarantine_max`).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-11 | dev-local (versionCode 12, та же сборка cc201f789) | `test_rename_filter_profile_keeps_query_string` ×3 подряд + `tests/test_filter_profiles.py` целиком | `1 passed, 373 deselected in 84.66s`; `1 passed, 373 deselected in 83.19s`; `1 passed, 373 deselected in 81.27s`; файловый прогон: `5 passed in 285.34s` — все PYTEST_EXIT=0 | test-maintainer (fix), D1-верификация fix-verifier — отдельным проходом (B4, сборку ждать не нужно) |
| 2026-08-13 | dev-local (versionCode 12, `Get-Device` → `emulator-5554`; test_debt, верификация build-независима — D1 не ждёт новую сборку приложения, B4) | D1 fix-verifier: `TC-085` (`test_rename_filter_profile_keeps_query_string`) ×3 подряд + доп. охват по условию критика раунда 2 — `TC-042` (`test_delete_filter_profile`, `expect_absent`-ветка) ×1, `TC-021` (`tests/test_backup_restore.py`, rescroll через `_scroll_settings_to`) ×1 | **TC-085: 2/3 — РЕЦИДИВ.** Прогон 1: `1 passed, 419 deselected in 92.78s`, PYTEST_EXIT=0. Прогон 2: **FAILED**, `1 failed, 419 deselected in 39.10s`, PYTEST_EXIT=1 — новый диагностический ассерт `settings_screen.py:333` (`enter_rename_name`) поймал ИМЕННО гипотезу 1 (гонка ввода) живьём, до подтверждения: поле после `clear()`+`send_keys` содержало `«My saved searchMy renamed search»` вместо `«My renamed search»` (конкатенация — `clear()` не успел отработать до `send_keys`), poll-бюджет 1.5с/0.3с не догнал. Прогон 3: `1 passed, 419 deselected in 84.93s`, PYTEST_EXIT=0. TC-042: `1 passed, 419 deselected in 91.50s`, PYTEST_EXIT=0 — без регресса. TC-021: `1 passed in 71.57s`, PYTEST_EXIT=0 — без регресса (rescroll-путь `_scroll_settings_to`/`_attach_pre_fallback_snapshot` тронут фиксом, задет исправно). | fix-verifier: **status держится `Fixed`, НЕ Verified/Reopened** — см. «## Обсуждение» и ESC-031 (`state/escalations.md`), вопрос возвращён координатору |
| 2026-08-13 (16:53Z) | dev-local (versionCode 12, `Get-Device` → `emulator-5554`; после rework attempt 3 — pre-poll на пустоту в `enter_rename_name` СРАЗУ после `clear()`, до `send_keys`) | fix-verifier D1, НЕЗАВИСИМЫЙ прогон (не reuse-witness test-maintainer): `TC-085` (`test_rename_filter_profile_keeps_query_string`) ×3 подряд + `TC-042` (`test_delete_filter_profile`) ×1 + `TC-021` (`tests/test_backup_restore.py`) ×1 — все пять запусков раздельными вызовами `Invoke-Pytest` | **TC-085: 3/3 — рецидив НЕ повторился.** Прогон 1: `1 passed, 419 deselected in 85.63s`, PYTEST_EXIT=0. Прогон 2: `1 passed, 419 deselected in 84.22s`, PYTEST_EXIT=0. Прогон 3: `1 passed, 419 deselected in 84.68s`, PYTEST_EXIT=0. TC-042: `1 passed, 419 deselected in 91.23s`, PYTEST_EXIT=0 — без регресса. TC-021: `1 passed in 70.92s`, PYTEST_EXIT=0 — без регресса. `AT-BUG-026 device-liveness guard: recoveries this session = 0/2` во всех пяти прогонах (устройство здоровое весь замер). | fix-verifier: **`Fixed → Verified`.** D1-порог достигнут независимым прогоном (не переиспользованием witness test-maintainer из «## Обсуждение»); `automation_status: active` в `test-cases/filter-profiles/TC-085.md` уже установлен rework attempt 2 и подтверждён — правка не требуется. |
| 2026-08-13 (17:10Z) | dev-local (versionCode 12, `Get-Device` → `emulator-5554`; после rework attempt 3 повторно, task_id `AT-BUG-062-rework3` attempt 2 — критик-блокеры B1/B2/B3 закрыты, см. «## Обсуждение») | test-maintainer: device-free `framework/tests/test_rename_name_verification_unit.py` целиком (6 проб, было 4) + device: `TC-085` ×3 подряд + `TC-042` ×1 + `TC-021` ×1, все раздельными вызовами `Invoke-Pytest` | **Юнит-файл: 6/6 зелёных**, `6 passed in 0.10s`, PYTEST_EXIT=0 (фейк `_FakeRenameDriver`/`_FakeRenameFieldElement` теперь моделирует реальный `clear()` — B1 закрыт; 2 новые пробы на pre-poll-ветку — B2 закрыт). **TC-085: 3/3.** Прогон 1: `1 passed, 421 deselected in 86.84s`, PYTEST_EXIT=0. Прогон 2: `1 passed, 421 deselected in 85.64s`, PYTEST_EXIT=0 (Allure-аттачка `enter_rename_name: pre-poll clear() timing` этого прогона — elapsed ≈0.157с; это НЕ доказательство ожидания: 0.157с < interval 0.3с = ровно ОДНА итерация опроса, см. «## Обсуждение», B3). Прогон 3: `1 passed, 421 deselected in 84.85s`, PYTEST_EXIT=0. TC-042: `1 passed, 421 deselected in 89.81s`, PYTEST_EXIT=0 — без регресса. TC-021: `1 passed in 70.43s`, PYTEST_EXIT=0 — без регресса. `AT-BUG-026 device-liveness guard: recoveries this session = 0/2` во всех пяти прогонах, `arch_check`/`validate_frontmatter` — 0 ошибок. | test-maintainer (rework, НЕ переводит статус сам — актор-гард схемы, см. запись 2026-08-13T16:53:00Z ниже); лок снят, D1-верификация — следующий проход fix-verifier |
| 2026-08-13 (17:40Z) | dev-local (versionCode 12, `Get-Device` → `emulator-5554`; source_commit тот же cc201f789, дифф — rework attempt 3 + rework3 attempt 2, B1/B2/B4 закрыты, B3 честно переформулирован) | fix-verifier D1, task_id `AT-BUG-062-verify3`, НЕЗАВИСИМЫЙ прогон (шесть раздельных вызовов `Invoke-Pytest`, не reuse-witness): device-free `framework/tests/test_rename_name_verification_unit.py` целиком + device `TC-085` ×3 подряд + `TC-042` ×1 + `TC-021` ×1 | **Юнит-файл: 6/6**, `6 passed in 0.08s`, PYTEST_EXIT=0. **TC-085: 3/3.** Прогон 1: `1 passed, 421 deselected in 92.75s`, PYTEST_EXIT=0. Прогон 2: `1 passed, 421 deselected in 92.40s`, PYTEST_EXIT=0. Прогон 3: `1 passed, 421 deselected in 87.29s`, PYTEST_EXIT=0. TC-042: `1 passed, 421 deselected in 94.42s`, PYTEST_EXIT=0 — без регресса. TC-021: `1 passed in 78.71s`, PYTEST_EXIT=0 — без регресса. `AT-BUG-026 device-liveness guard: recoveries this session = 0/2` во всех шести прогонах (окружение здоровое весь замер). `automation_status: active` в `test-cases/filter-profiles/TC-085.md` сверен чтением непосредственно перед закрытием — правка не требуется. | fix-verifier: **`Fixed → Verified`.** D1-порог (юнит-файл 6/6 + TC-085 3/3 + TC-042/TC-021 без регресса) достигнут независимым прогоном третьей D1-попыткой подряд; предыдущий рецидив (2/3 на TC-085, запись 16:27Z) на текущем дифф-состоянии не повторился ни разу за 3 запуска. |

**Условие критика раунда 2, обязательное для будущего D1:** D1 fix-verifier
обязан захватить TC-085 + негативный ассерт TC-042 (`expect_absent`-ветка) +
один rescroll-кейс TC-021 — верификационная таблица attempt 1 сделана ДО
правок `enter_rename_name`/`expect_absent`/`_scroll_settings_to` (rework
attempt 2, non-blockers (а)/(б) выше) и текущий device-код ими не покрыт.

## Обсуждение

**[fix-verifier @ 2026-08-13T17:40:00Z, mode=verify (D1), task_id `AT-BUG-062-verify3`] —
`Fixed → Verified`.**

Финальная, независимая D1-верификация — не переиспользовал witness ни
test-maintainer (rework3 attempt 2, запись 17:10Z ниже), ни предыдущего
fix-verifier (verify2, откаченного координатором 16:56Z за B1-B4). `Get-Device`
→ `emulator-5554` до старта, окружение здоровое весь замер (`AT-BUG-026
device-liveness guard: recoveries this session = 0/2` во всех шести прогонах).

**Юнит-файл (device-free): 6/6**, `6 passed in 0.08s`, PYTEST_EXIT=0 —
подтверждает B1 (фейк `clear()`) и B2 (pre-poll-ветка) закрытыми на этом
прогоне, а не только в записи test-maintainer.

**TC-085: 3/3**, три раздельных запуска `Invoke-Pytest -k
test_rename_filter_profile_keeps_query_string -q` — `92.75s`/`92.40s`/`87.29s`,
все PYTEST_EXIT=0. Рецидив записи 16:27Z (2/3, сигнатура «My saved
searchMy renamed search» на `settings_screen.py:333`) НЕ повторился ни разу.

**TC-042/TC-021 — без регресса**, `94.42s`/`78.71s`, оба PYTEST_EXIT=0 —
негативная ветка `expect_absent` и rescroll-путь `_scroll_settings_to`/
`_attach_pre_fallback_snapshot` фиксом не задеты.

**Причинность.** Держусь действующей честной формулировки (B3, снята как
блокер в раунде 3 критика, запись test-maintainer 17:10Z ниже): pre-poll
устраняет ВОЗМОЖНОСТЬ конкретного механизма гонки (`clear()` не применился
до `send_keys`); вклад в исходный рецидив `RUN-20260811-0406` не
подтверждён и не исключён изолирующим экспериментом. Не переформулирую
это в «причина найдена» — три зелёных подряд поднимают уверенность в
устранении наблюдаемого класса падения, но не заменяют изолирующий
эксперимент.

**D1-порог достигнут** (юнит-файл 6/6 + TC-085 3/3 + TC-042/TC-021 без
регресса, третья D1-попытка подряд на этом дифф-состоянии, вторая с
юнит-файлом в батарее). `status: Fixed → Verified`, `status_since`/
`updated` — фактический момент перехода (17:40Z). `known_issue` уже был
`"false"` — без изменений. `automation_status: active` в
`test-cases/filter-profiles/TC-085.md` сверен непосредственно перед
закрытием, правка не требуется. Лок `fix-verifier:2026-08-13T17:31:00Z`
снят.

**Дефекты-собратья (правило 9, scope не расширяю):** ничего нового сверх
уже задокументированного (`library_screen.py`, `rating_overlay.py`,
`documents_ui.py`, `browser_screen.py:325` — записи выше) — эта
верификация нового класса риска не вскрыла.

**[test-maintainer @ 2026-08-13T17:10:00Z, task_id `AT-BUG-062-rework3`, attempt 2 —
критик-блокеры B1/B2 закрыты; B3 переформулирован в раунде 3 (см. запись
ниже), B4 найден там же.** Прежняя правка `enter_rename_name` (pre-poll
на пустоту СРАЗУ после `clear()`, до `send_keys` — rework attempt 3, запись
2026-08-13T16:42:00Z ниже) остаётся в дереве без переписывания; правка
точечная, поверх неё.

**B1 (фейк юнит-пробы не моделирует реальный `clear()`) — закрыт.**
`framework/tests/test_rename_name_verification_unit.py`:
`_FakeRenameFieldElement.clear()` теперь фиксирует `driver.clear_time` (и
сбрасывает `send_time`), `_FakeRenameDriver.current_field_text()` отдаёт
`resolve_clear_text(elapsed с момента clear())` ПОСЛЕ `clear()` и ДО
`send_keys` — по умолчанию пусто немедленно (`elapsed -> ""`), что
воспроизводит прежнее поведение для всех 4 исходных проб без изменения их
кода (default сохраняет их зелёными). Новый параметр `resolve_clear_text`
опционален, симметричен уже существующему `resolve_text` (пост-`send_keys`).
Прогон `framework/tests/test_rename_name_verification_unit.py` — witness
в таблице «## Верификация» выше (`6 passed in 0.10s`, PYTEST_EXIT=0).

**B2 (pre-poll ветка не покрыта пробами) — закрыт.** Добавлены 2 пробы:
(а) `test_enter_rename_name_raises_diagnostic_when_field_never_clears` —
поле весь бюджет 1.5с после `clear()` показывает старое имя ->
`AssertionError` с диагностикой ИМЕННО про `clear()` («после clear()
содержит», не «после clear()+send_keys» — проверено явным
`assert "после clear()+send_keys" not in msg`), `send_keys` не вызывается
(`driver.send_time is None`); (б)
`test_enter_rename_name_send_keys_waits_for_field_to_clear_within_budget` —
поле пустеет на 4-м опросе pre-poll (t=0.9с, в пределах бюджета 1.5с) ->
`send_keys` вызывается ТОЛЬКО когда поле реально уже пусто
(`driver.send_time >= 0.9`), тест зелёный. Существующие 3 пробы на
пост-poll ветку (mismatch/settle/stale-read) по-прежнему доходят до
пост-poll кода — default `resolve_clear_text` даёт мгновенную пустоту при
`elapsed=0`, `poll_for` проверяет предикат сразу без начальной паузы
(`framework/core/waits.py::poll_for`), так что pre-poll не потребляет
бюджет часов и не маскирует post-poll ветку в этих трёх пробах (сверено
прогоном — таймингованные assert'ы `_fake_clock.now` в них не изменились).

**B3 (каузальное утверждение не изолировано) — СНЯТО как ложное
(критик-вход rework3, раунд 3).** Прежняя редакция утверждала, что elapsed
0.157с из device-прогона 2 «эмпирически подтверждает реальную задержку
`clear()`» и «исключает гипотезу no-op». Утверждение неверно: `poll_for`
(`framework/core/waits.py`) опрашивает предикат СРАЗУ при t=0, до первой
паузы, при `interval=0.3с`; elapsed 0.157с < interval математически означает
РОВНО ОДНУ итерацию опроса — поле было пусто уже при ПЕРВОМ чтении после
`clear()`, pre-poll не ждал ничего, а измеренные 0.157с — latency самого
запроса `find_element(...).get_attribute("text")` к драйверу. Ожидание
доказывалось бы только числом опросов > 1 (эквивалентно elapsed >= interval).
Проверено прогоном свойства `poll_for`: две итерации стоят 0.301с (>= interval),
одна — 0.000006с.

**Формулировка причины (действующая).** Pre-poll устраняет ВОЗМОЖНОСТЬ
данного механизма гонки (`clear()` не применился до `send_keys`); его вклад
в исходный рецидив `RUN-20260811-0406` НЕ подтверждён и НЕ исключён
изолирующим экспериментом. Изолирующие прогоны на флейке с исходной частотой
рецидива 1/3 признаны непропорционально дорогими (решение координатора
2026-08-13) — принята эта честная формулировка. Инструментация в
`enter_rename_name` сохранена как ДИАГНОСТИКА для будущей отладки (номер
опроса pre-poll + elapsed в Allure-аттачке) и НЕ переиспользуется как довод
причинности.

**B4 (проба stale-read зелёная по совпадению) — закрыт.**
`test_enter_rename_name_protects_diagnostic_read_against_stale_field` больше
не падала в ветке, ради которой заведена: инъекция `NoSuchElementException`
срабатывала на ПЕРВОМ чтении нового pre-poll'а, проба проходила по совпадению
текстов сообщений («AT-BUG-062»/«недоступно»). Фейку добавлен флаг
`raise_only_after_send_keys` (инъекция строго ПОСЛЕ `send_keys`), в пробу —
явные `assert driver.send_time is not None` и проверка текста именно
пост-`send_keys` ветки, чтобы регресс достижимости ловился явно.

**Верификация.** `framework/tests/test_rename_name_verification_unit.py` —
6/6 (было 4/4, +2 новые пробы B2), device-батарея `TC-085`×3 + `TC-042`×1 +
`TC-021`×1 — все зелёные, `arch_check`/`validate_frontmatter` чисты (0
ошибок). Полный witness — таблица «## Верификация» выше, строка
2026-08-13 (17:10Z).

**Почему не перевожу `Fixed → Verified` сам.** Та же причина, что в записи
rework attempt 3 (2026-08-13T16:42:00Z ниже, раздел «Почему НЕ перевожу
статус...») — `schemas/transitions.yaml` ограничивает актора `Fixed →
Verified` строго `fix-verifier`, включая B4-ветку test_debt. Статус
оставлен `Fixed`, лок снят.

**Изменённые файлы этим rework:** `framework/screens/settings_screen.py`
(import `allure`/`framework.core.waits`, инструментация elapsed pre-poll),
`framework/tests/test_rename_name_verification_unit.py` (фейк B1 +
2 новые пробы B2), `bugs/AT-BUG-062.md` (эта запись + строка witness).

**Дефекты-собратья (правило 9, scope не расширяю):** ничего нового сверх
уже задокументированного (`library_screen.py`, `rating_overlay.py`,
`documents_ui.py`, `browser_screen.py:325` — записи выше) — эта правка не
трогала их, риск там прежний, доклад не меняется.

**[fix-verifier @ 2026-08-13T16:53:00Z, mode=verify (D1), AT-BUG-062-verify2] —
`Fixed → Verified`.**

Прогнал ТУ ЖЕ батарею, что дала 2/3 в прошлой D1-попытке
(2026-08-13T16:27:00Z, ESC-031): `TC-085` ×3 подряд + `TC-042` ×1 + `TC-021`
×1 — НЕЗАВИСИМЫЙ прогон, пять раздельных вызовов `Invoke-Pytest`, не
переиспользование witness test-maintainer из блока rework attempt 3 ниже
(reuse-witness правило допускает переиспользование только с явной сверкой
red→green по allure result.json; здесь проще и надёжнее было перепрогнать
живьём, благо батарея та же, что уже гоняли час назад — цена невелика).
`Get-Device` → `emulator-5554` до старта, окружение здоровое весь замер
(`AT-BUG-026 device-liveness guard: recoveries this session = 0/2` во всех
пяти прогонах).

**TC-085 — 3/3.** Все три изолированных запуска
`test_rename_filter_profile_keeps_query_string` прошли зелёным
(`85.63s`/`84.22s`/`84.68s`, PYTEST_EXIT=0 каждый) — сигнатура рецидива
(`settings_screen.py:333`, конкатенация «My saved searchMy renamed
search») не воспроизвелась ни разу. Pre-poll `_field_text() == ""` сразу
после `clear()`, до `send_keys` (rework attempt 3, ниже), закрывает саму
гонку структурно — концентрация была прежде необратимо зафиксирована в
поле ДО начала пост-`send_keys`-опроса; предыдущий фикс (rework attempt 2)
опрашивал только ПОСЛЕ `send_keys`, что и не успевало поймать
уже-испорченное состояние в оставшемся бюджете.

**TC-042/TC-021 — без регресса**, зелёные (`91.23s`/`70.92s`,
PYTEST_EXIT=0 у обоих) — негативная ветка `expect_absent` и rescroll-путь
`_scroll_settings_to`/`_attach_pre_fallback_snapshot` фиксом не задеты.

**D1-порог (3/3 на TC-085 + TC-042/TC-021 без регресса) достигнут.**
`status: Fixed → Verified`, `status_since`/`updated` обновлены фактическим
моментом перехода (16:53Z, не полночь). `known_issue` уже был `"false"` —
без изменений (для test_debt поле и так не выставлялось в `"true"`).
`automation_status: active` в `test-cases/filter-profiles/TC-085.md`
установлен ещё rework attempt 2 (2026-08-11) и не откатывался ни на одном
из промежуточных рецидивов — правка не требуется, сверено чтением
frontmatter непосредственно перед закрытием.

Лок `fix-verifier:2026-08-13T16:50:00Z` снят.

**Дефекты-собратья (правило 9, scope не расширяю):** ничего нового сверх
уже задокументированного test-maintainer (`clear()`+`send_keys` без
pre-poll в `library_screen.py`, `rating_overlay.py`, `documents_ui.py`,
`browser_screen.py:325`, rework attempt 3 выше) — сама верификация нового
класса риска не вскрыла.

**[test-maintainer @ 2026-08-13T16:42:00Z, rework attempt 3 — ESC-031, путь (а)
из развилки координатора].** Диспатч выбрал путь (а): не «расширить таймаут»
как таковой (расширение ПОСЛЕ `send_keys` не устраняет саму гонку — poll ждёт
состояния, которое уже не наступит, если `clear()` не успел применить эффект
ДО того, как `send_keys` допишет текст в ещё непустое поле), а закрыть гонку
структурно — добавлен ВТОРОЙ `poll_for` (`framework/screens/settings_screen.py`,
`enter_rename_name`) СРАЗУ после `clear()`, ДО `send_keys`: дожидается
`_field_text() == ""` тем же бюджетом (`timeout=1.5, interval=0.3`,
симметрично существующему пост-`send_keys` опросу), при неуспехе — явный
диагностический `assert False` тем же стилем сообщения («поле после clear()
содержит «X», ожидали пустую строку — clear() не применился до send_keys»).
Пост-`send_keys` опрос оставлен БЕЗ изменений (defense-in-depth, оба слоя
работают вместе).

Верификация — условие критика раунда 2 целиком, `Get-Device` →
`emulator-5554` до старта:

```
Invoke-Pytest -k test_rename_filter_profile_keeps_query_string -q   (TC-085, ×3 подряд, after autotest pre-poll fix)
  1 passed, 419 deselected in 85.24s   PYTEST_EXIT=0
  1 passed, 419 deselected in 85.07s   PYTEST_EXIT=0
  1 passed, 419 deselected in 85.65s   PYTEST_EXIT=0
Invoke-Pytest -k test_delete_filter_profile -q   (TC-042, expect_absent-ветка, регресс-контроль)
  1 passed, 419 deselected in 88.37s   PYTEST_EXIT=0
Invoke-Pytest tests/test_backup_restore.py -q   (TC-021, rescroll _scroll_settings_to, регресс-контроль)
  1 passed in 68.15s   PYTEST_EXIT=0
```

3/3 на TC-085 — D1-порог достигнут. TC-042/TC-021 без регресса. Устройство
здоровое весь прогон (`AT-BUG-026 device-liveness guard: recoveries this
session = 0/2` во всех пяти прогонах).

**Дефекты-собратья (правило 9, scope НЕ расширяю, не чиню сам).** Тот же
паттерн `clear()` + `send_keys` БЕЗ pre-poll на пустоту (только пост-ввод
проверка либо вообще без неё) есть в `framework/screens/library_screen.py:202,
223, 230`, `framework/screens/rating_overlay.py:106, 136`,
`framework/screens/documents_ui.py:108`, `framework/screens/browser_screen.py:325`
(последний уже осознанно комментирует «`.clear()` обязателен перед вводом
нового имени» — тот же класс риска гонки recomposition, что был здесь).
Не проверял эмпирически, воспроизводится ли гонка в каждом из них (разная
разметка/другие Compose-компоненты могут вести себя иначе) — не завожу
новый test_debt без наблюдаемого падения; докладываю находкой по правилу 9,
решение о профилактическом проходе — за координатором/Lead.

**Почему НЕ перевожу статус `Fixed → Verified` сам, хотя диспатч это
прямо предписывал.** `schemas/transitions.yaml`: `{from: Fixed, to: Verified,
by: [fix-verifier], ref: "D1: ... только fix-verifier, человек НЕ закрывает
баги мимо верификации"}` — актор ограничен явно, включая B4-ветку
(комментарий там же: «Верификация — общая: Fixed→Verified делает
fix-verifier..., для test_debt новая сборка приложения НЕ нужна» — то есть
для test_debt снят ТОЛЬКО критерий сборки, не критерий актора). Ни одна
B4-запись `Fixed`-guard в матрице не даёт test-maintainer прав на переход в
`Verified`. Собственный переход был бы самосертификацией (тот же класс, что
«Роль ≠ ярус» в CLAUDE.md: воркер не принимает свою же работу) — формальная
легальность инструкции диспатча не отменяет актор-гард схемы. Статус
оставлен `Fixed`, лок снят; D1-порог (3/3 + TC-042 + TC-021 зелёные, второй
подряд чистый прогон условия критика раунда 2) выполнен и задокументирован
здесь witness'ом — следующий проход fix-verifier может формально перевести
`Fixed → Verified` без повторного прогона всей батареи (если сочтёт нужным
— контрольный перезапуск на его усмотрение).

**[fix-verifier @ 2026-08-13T16:27:00Z, mode=verify (D1)] — рецидив, status
держится `Fixed`, вопрос — координатору.**

Прогнал условие критика раунда 2 целиком: `TC-085` ×3 подряд + `TC-042`
(`expect_absent`-ветка) ×1 + `TC-021` (rescroll `_scroll_settings_to`) ×1.
`Get-Device` → `emulator-5554` до старта, окружение здоровое весь прогон
(`AT-BUG-026 device-liveness guard: recoveries this session = 0/2` во всех
пяти прогонах).

**TC-042 и TC-021 — оба зелёные, без регресса** (`1 passed, 419 deselected
in 91.50s`; `1 passed in 71.57s`) — новые ветки `expect_absent`/
`_attach_pre_fallback_snapshot` из rework attempt 2 не сломали соседей.

**TC-085 — 2 из 3, не 3/3.** Прогон 1 (`92.78s`) и прогон 3 (`84.93s`) —
`PASSED`. Прогон 2 — `FAILED` (`1 failed, 419 deselected in 39.10s`,
PYTEST_EXIT=1), причём падение случилось РАНЬШЕ по сценарию, чем исходная
сигнатура `RUN-20260811-0406`, и с новым диагностическим сообщением —
именно тем, что добавил rework attempt 2 (`settings_screen.py:333`,
`enter_rename_name`, poll `timeout=1.5, interval=0.3`). Дословная
цитата — **allure result.json прогона 2 недоступен** (следующий прогон,
attempt 3, уже перезаписал `framework/allure-results/` через
`--clean-alluredir` из `pytest.ini` до того, как я успел его прочитать —
моя ошибка процедуры evidence-capture, признаю явно, не маскирую).
Цитата ниже — **сверка чтением исходника** (`settings_screen.py:333-336`)
с подстановкой фактических данных из терминального вывода pytest, который
сохранился в моём собственном выводе прогона 2 (это НЕ реконструкция по
памяти — сырой capture Bash-тула этого же хода; кириллица в нём
mojibake-повреждена консолью, но проверяемые данные — имена профилей — в
латинице и не повреждены):

> `assert False, (f"поле «Rename filter» после clear()+send_keys содержит
> «{actual}», ожидали «{new_name}» — расхождение поймано ДО подтверждения
> (AT-BUG-062)")`, где фактически `actual = "My saved searchMy renamed
> search"`, `new_name = "My renamed search"` — консольный traceback:
> `screens\settings_screen.py:333: AssertionError`, тест —
> `tests/test_filter_profiles.py:104`.

**Что это значит.** Поле после `clear()+send_keys` содержало КОНКАТЕНАЦИЮ
старого и нового имени — `clear()` не успел применить эффект (Compose
recomposition) до того, как `send_keys` дописал новый текст, и это НЕ
осело в пределах 1.5с/0.3с бюджета опроса. Это ЖИВОЕ подтверждение
гипотезы 1 (гонка ввода) как реального явления — причём в ИЗОЛИРОВАННОМ
прогоне, не под нагрузкой полного регресса, где test-maintainer сам
оговорил риск («Остаточный риск» rework attempt 2, non-blocker (б)):
«бюджет... НЕ проверен под такой нагрузкой... full regression». Здесь
нагрузки full regression не было — три последовательных изолированных
запуска одного теста, и гонка всё равно поймалась на втором. Значит
остаточный риск (б) шире, чем test-maintainer предполагал: бюджет
недостаточен даже вне полного регресса, не только под ним.

**Позитивная сторона находки.** Диагностический слой сработал ТОЧНО как
спроектирован (DoD п.3 бага): падение теперь на `enter_rename_name`, с
точным диагнозом «поле содержит X, ожидали Y», а не на неотличимом
«профиль не найден в списке» — гипотеза 1 и гипотеза 2 больше НЕ
смешиваются. Диагностический долг закрыт по существу. Но серия «3 зелёных
подряд» — критерий готовности карантина (`## Что сделать`, п.4;
`test-cases/filter-profiles/TC-085.md` «Карантин снят») — на ЭТОЙ
верификации НЕ достигнута: 2/3, не 3/3.

**Почему держу `Fixed`, не перевожу сам.** `schemas/transitions.yaml`
формально допускает `Fixed → Reopened by: [fix-verifier]` без guard'а по
`type` — переход технически легален и для test_debt. Не использую его
здесь по существу, не по формальному запрету: рецидив — это не отказ
диагностического фикса (тот отработал), а НЕДОСТАТОЧНОСТЬ таймингового
бюджета, который сам fix ввёл и сам же назвал непроверенным риском.
Reopened подразумевает «фикс не работает, чинить заново с нуля» — это
неточно опишет ситуацию: диагностика (п.1-3 DoD) работает, требует
расширения ТОЛЬКО бюджет `enter_rename_name` (п. «Остаточный риск» уже
называет этот путь верным). Это развилка, которую по правилу 11а
(маршрутизация вопросов) не должен решать сам fix-verifier — нужно
решение координатора/test-maintainer: расширить бюджет опроса (напр.
1.5с → 3с) и повторить D1, ИЛИ признать 2/3 достаточным с учётом того, что
это диагностический (не поведенческий) долг. Лок снят, эскалация —
`state/escalations.md` ESC-031.

**Дефекты-собратья (правило 9, scope не расширяю):** не нашёл новых —
класс («таймаут-бюджет verify-poll может быть занижен под нагрузкой»)
уже сам test-maintainer называл в «Остаточный риск» (б); эта находка его
подтверждает и сужает («даже без нагрузки»), не открывает новую ось.

**[test-maintainer @ 2026-08-11T17:13:00Z, rework attempt 2 — критик-вход opus
вернул ДОРАБОТАТЬ].** Три блокера критика закрыты, все правки device-free
(эмулятор в этом окне занят параллельной задачей, не потребовался):

1. **Честность корпуса (TC-085.md).** Формулировки «фикс — диагностический
   (устраняет причину...)» и «точный диагноз... — bugs/AT-BUG-062.md»
   противоречили этому же файлу (причина НЕ установлена эмпирически, все 4
   контрольных прогона зелёные). `test-cases/filter-profiles/TC-085.md`
   переформулирован: «гонка ввода исключена как класс (устранена
   возможность, не подтверждена как причина)», «причина исходного падения НЕ
   установлена эмпирически, остаётся открытым вопросом — см.
   bugs/AT-BUG-062.md». Перепрогона не требовало.
2. **Новые ветки отказа исполнены.** Все 4 верификационных прогона attempt 1
   были зелёными — новый код (`enter_rename_name` verification poll,
   `assert_filter_profile_listed` DB-truth) ни разу не сработал по красной
   ветке. Добавлен device-free `framework/tests/test_rename_name_verification_unit.py`
   (фейковый driver/фейковые часы, по образцу
   `test_swipe_to_text_settle_unit.py`, AT-BUG-048) — 4 пробы: (а) поле весь
   бюджет 1.5с показывает ДРУГОЙ текст -> диагностический `AssertionError`,
   не таймаут; (б) поле догоняет в пределах бюджета -> зелёный; (в)
   `assert_filter_profile_listed` на провале несёт фактические имена из БД
   (`seed_db.read_filter_profiles` мокнута); (г) попутный дефект — защищённое
   чтение `_field_text()` не протекает `NoSuchElementException` при
   stale-поле (`IMPLICIT_WAIT=0`, `framework/config/settings.py:50`) —
   `settings_screen.py::enter_rename_name` дочитан try/except-хелпером,
   значение читается ОДИН раз в переменную перед подстановкой в сообщение
   (было: незащищённый повторный вызов прямо в f-string). Красная проба
   (временно снята защита try/except — байтовая копия файла в scratchpad,
   сверка порчи/отката по `CLAUDE.md` permission-hygiene п.8): проба 3
   упала ОСМЫСЛЕННО — `NoSuchElementException` протёк вместо
   `AssertionError`, сигнатура падения ровно на строке незащищённого чтения;
   откачено байтовой копией, `git diff --stat` после отката снова показывает
   только намеренные правки. 3/3 зелёных прогона нового файла (вместе с
   `test_swipe_to_text_settle_unit.py`, регресса на сиблинге нет) после
   отката.
3. **`saf_steps.py:84` — переклассифицирован, не отфутболен повторно.**
   Критик прав: класс DoD п.2 — «фолбэк `swipe_to_text or swipe_up_to_text`
   теряет ПОЗИЦИЮ ОТКАЗА до снимка», а не «качество текста сообщения»; моя
   прошлая формулировка («честный AssertionError, класс не применяется»)
   переопределяла класс вместо того чтобы его оценить.
   `_scroll_settings_to` несёт ТОТ ЖЕ паттерн `swipe_to_text(...) or
   swipe_up_to_text(...)` — применил вариант (а): снимок `page_source` ДО
   фолбэка. Общий хелпер `_attach_pre_fallback_snapshot` поднят из
   `SettingsScreen` в `BaseScreen` (класс, не экземпляр — правило 9;
   единственная точка теперь используется обоими сиблингами:
   `settings_screen.py::_swipe_to_profile` и `saf_steps.py::_scroll_settings_to`).

Non-blockers критика (оба закрыты попутно):
(а) `assert_filter_profile_not_listed`/`_swipe_to_profile`/`has_filter_profile`
получили параметр `expect_absent: bool = False` — негативный ассерт
(TC-085/TC-042, ожидает профиль ОТСУТСТВУЮЩИМ) передаёт `expect_absent=True`
и больше не пишет шумную pre-fallback XML-аттачку в Allure на каждом
зелёном прогоне (снимок нужен только когда «не нашли» — это ОТКАЗ, не
ожидаемый успешный исход).
(б) **Остаточный риск.** Бюджет верификации `enter_rename_name`
(`timeout=1.5s, interval=0.3s`) подобран по прогонам изолированного теста;
под нагрузкой ПОЛНОГО регресса (тот самый контекст, где случилось исходное
падение `RUN-20260811-0406`) recomposition/событийная очередь Compose могут
быть медленнее — бюджет НЕ проверен под такой нагрузкой (изолированные
прогоны — не то же самое, что 70-минутный full regression). Если
`enter_rename_name` начнёт падать НОВЫМ диагностическим сообщением
(«поле содержит X, ожидали Y») именно в full regression — это будет
означать, что 1.5с недостаточно под нагрузкой, не гонку ввода как баг
приложения; тогда бюджет стоит расширить, а не считать находку новым
багом.

Изменённые файлы этим rework: `framework/screens/settings_screen.py`,
`framework/screens/base_screen.py`, `framework/steps/settings_steps.py`,
`framework/steps/saf_steps.py`, `framework/tests/test_rename_name_verification_unit.py`
(новый), `scripts/arch_check.py` (ALLOWLIST-запись для нового device-free
теста — тот же класс исключения, что AT-BUG-059), `test-cases/filter-profiles/TC-085.md`.
`bugs/AT-BUG-062.md`/`test-cases/filter-profiles/TC-085.md` locks сняты.
`python scripts/validate_frontmatter.py` и `python scripts/arch_check.py` —
оба чисто (0 ошибок).

**[test-maintainer @ 2026-08-11T16:53:33Z]** Долг устранён на уровне тестовой
обвязки (диагностика + защита от гонки), `automation_status: quarantined → active`
(`test-cases/filter-profiles/TC-085.md`). Изменения — только `framework/`:

1. `settings_screen.py::enter_rename_name` — после `clear()`+`send_keys` опрашивает
   `get_attribute("text")` поля (poll_for, таймаут 1.5с) до совпадения с ожидаемым
   именем ДО `confirm_rename` — расхождение теперь падает здесь, с точным
   диагнозом, а не молча уходит на ассерт списка Settings под чужим сообщением
   (устраняет гипотезу 1 навсегда, DoD п.3).
2. `settings_screen.py::_swipe_to_profile` (единственная точка `swipe_to_text(...) or
   swipe_up_to_text(...)` для профилей — покрывает разом `has_filter_profile`,
   `delete_filter_profile`, `count_filter_profile_occurrences`, `open_rename_dialog`)
   — перед фолбэком `swipe_up_to_text` прикладывает `page_source` к Allure на
   позиции, где прямой проход не поймал профиль, ДО того как фолбэк вернёт список
   наверх (DoD п.2).
3. `settings_steps.py::assert_filter_profile_listed` — на провале дочитывает
   фактический список имён из БД (`seed_db.read_filter_profiles()`, host-side, без
   остановки приложения — тот же контракт, что уже использует
   `assert_filter_profiles_have_query_strings`) — следующее падение само отличит
   «имя другое» (гипотеза 1) от «строка не поймана прокруткой» (гипотеза 2, DoD п.1).

**Расхождение с диагнозом failure-analyst — явно фиксирую.** Все 4 контрольных
прогона (3× целевой тест + 1× файл) прошли ЗЕЛЁНЫМ на здоровом окружении
(`Get-Device` → `emulator-5554`, Appium `:4723` ready) — исходная сигнатура
падения НЕ воспроизвелась ни разу, симметрично изолированным 3/3 зелёным
failure-analyst. Значит, эмпирически подтвердить, какая из двух гипотез стреляла
в `RUN-20260811-0406`, я НЕ смог — это по-прежнему открытый вопрос для
следующего падения (если оно случится, теперь оно само укажет причину через
пп. 1-3 выше). Не заявляю «починил гонку ввода» как доказанную причину — заявляю
«гонка ввода как класс исключена превентивной проверкой, а диагностический
пробел закрыт для обеих гипотез» (калибровка №3: без исключающего прогона не
пишу «причина установлена»).

**Дефекты-собратья (доклад по правилу 9, scope не расширяю, новых test_debt не
завожу):** тот же паттерн `swipe_to_text(...) or swipe_up_to_text(...)` есть в
`framework/steps/saf_steps.py:84` (`_scroll_settings_to`) — НЕ фиксировал: это
Given-шаг докрутки (setup), а не Then-ассерт с неоднозначным сообщением о
состоянии профиля; при неуспехе там честный `AssertionError` без апелляции к
«найден/не найден» конкретного бизнес-объекта — класс диагностического пробела
AT-BUG-062/AT-BUG-048 к нему не применим впрямую. `AT-BUG-043`/`AT-BUG-026`,
отмеченные failure-analyst как шумящие рядом, не трогал — вне скоупа этого долга,
уже свои открытые долги.

**[failure-analyst @ 2026-08-11T02:40:00Z]** Заведён по вердикту `FLAKY` падения
TC-085 в `runs/RUN-20260811-0406.md` (таблица «Падения и триаж»). Дедуп проверен:
`AT-BUG-053` (тот же TC, другая сигнатура, `Verified`) — не дубликат, см. раздел
«Почему это НЕ …»; `AT-BUG-048` — родственный класс (устойчивость
`swipe_to_text`), но там фикс уже `Verified`, а здесь под вопросом ОСТАТОК класса
плюс отдельный пробел диагностики; заводить как reopen AT-BUG-048 не стал —
поверхность падения другая (шаг rename + ассерт списка), связь отмечена ссылкой.

**Дефекты-собратья (доклад по правилу 9, scope не расширяю):**
`AT-BUG-043` (bind-race порта 8080 mitmdump) снова в teardown этого же теста
(`stderr`-аттачка: «порт 8080 освободился после 2 попыток bind() за 0.10s») и в
smoke `RUN-20260811-0405` (TC-009) — долг заведён, продолжает шуметь.
`AT-BUG-026` (device-liveness guard) сработал в моих файловых перепрогонах
(recoveries 1/2, затем `socket hang up`/`ERROR at setup`) — окружение после
70-минутного регресса деградировало; это наблюдение среды, не причина падения
прогона.

**[координатор @ 2026-08-13T16:56:00Z] ОТКАТ `Verified → Fixed`
(`schemas/transitions.yaml:74`, rollback: true, дефект ПРОЦЕДУРЫ верификации,
не репро бага — `reopen_count` не растёт).** fix-verifier (task_id
`AT-BUG-062-verify2`) поставил `Verified` в 16:53:00Z на батарее TC-085×3 +
TC-042 + TC-021 (device, все зелёные) — но эта батарея НЕ включает
`framework/tests/test_rename_name_verification_unit.py`, а критик-вход
(task_id `AT-BUG-062-rework3`, отдельный параллельный диспатч ревью того же
диффа `settings_screen.py`) НЕЗАВИСИМО нашёл на этом же диффе, ДО и
одновременно с device-верификацией: (B1) rework ломает 2/4 device-free
юнит-проб этого файла (воспроизведено критиком: `_FakeRenameDriver` не
моделирует `clear()`, новый pre-poll не может увидеть пустоту — `2 failed, 2
passed in 0.52s`); (B2) новая pre-poll ветка отказа не покрыта ни одной
пробой; (B3) каузальное утверждение «фикс закрывает саму гонку»
НЕ изолировано экспериментом — альтернативный механизм (`clear()`
применился, потом восстановился, `send_keys` дописал) даёт ТУ ЖЕ строку
`«My saved searchMy renamed search»` и делает pre-poll no-op; 3/3 зелёных
при исходной частоте рецидива 1/3 имеет вероятность `(2/3)³≈0.30` под нулевой
гипотезой «фикс ничего не изменил». Полный вердикт критика — routing-журнал,
`rejected` task_id `AT-BUG-062-rework3` attempt 1, 2026-08-13T16:48:45Z.
Device-зелёный TC-085×3 остаётся валидным ФАКТОМ (устраняет наблюдаемую
исходную сигнатуру), но НЕ достаточен для `Verified`, пока диф несёт
известную регрессию device-free-слоя и неизолированную причинность. Rework
attempt 2 (test-maintainer, task_id `AT-BUG-062-rework3` attempt 2) уже в
работе — чинит юнит-фейк + добавляет пробы на pre-poll-ветку + либо
инструментирует факт задержки `clear()`, либо смягчает формулировку причины.
D1 будет прогнан ЗАНОВО (включая юнит-файл) после приёмки rework'а критиком.
