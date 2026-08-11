---
key: "AT-BUG-062"
project: "AO3"
issueType: "bug"
status: "bug-open"
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
created: "2026-08-11T02:40:00Z"
updated: "2026-08-11T02:40:00Z"
archived: false
resolution: null
---

# Нестабильный TC-085 (rename filter-profile): «профиль «My renamed search» не найден в списке Settings» в полном регрессе, 3/3 зелёный в изоляции; артефакт падения не содержит секцию Saved AO3 Filters (фолбэк swipe_up возвращает список наверх)

_Спроецировано из `bugs/AT-BUG-062.md` (источник правды).
Статус в нашей машине: **Open**._

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

## Обсуждение

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
