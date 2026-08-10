---
id: AT-BUG-048
title: "BaseScreen.swipe_to_text проскакивает искомую секцию под нагрузкой (fling-инерция + опрос раз в свайп) — Settings докручивается до конца списка, ассерт «секция не найдена прокруткой»; экземпляр TC-093 в RUN-20260803-2012"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Verified
found_in: "framework commit e42eb8bb (тестируемая сборка приложения 1.10 (versionCode 11), build 6455af0c — от сборки НЕ зависит)"
fixed_in: "тестовая система: framework/screens/base_screen.py (swipe_to_text/swipe_up_to_text — общий _swipe_search: не-fling короткие свайпы на полную дистанцию раунда + settle-поллинг poll_for после каждого раунда вместо одного снимка; _scroll_fingerprint различает «конец списка» от «строка не найдена»), framework/core/waits.py (новый примитив poll_for), framework/tests/test_swipe_to_text_settle_unit.py (новая device-free регресс-проба, 5 сценариев); коммит присвоит координатор при приёмке — сборка приложения не при чём"
last_seen_in: "RUN-20260803-2012 (2026-08-03)"
test_cases: ["TC-093"]
runs: ["RUN-20260803-2012"]
duplicates: []
regression_of: ""
status_since: "2026-08-10T11:35:07Z"
updated: "2026-08-10T11:35:07Z"
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

# AT-BUG-048 — `swipe_to_text` теряет секцию из-за инерции свайпа (Settings, TC-093)

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность —
`framework/screens/base_screen.py:74-87` (`swipe_to_text`) и её 10 call sites в
`framework/screens/`/`framework/steps/`. От сборки приложения не зависит.
Эмулятор `ao3_test_api34` (emulator-5554), API 34, replay-режим.

## Суть долга

```python
def swipe_to_text(self, text: str, max_swipes: int = 8) -> bool:
    ...
    y1, y2 = int(size["height"] * 0.8), int(size["height"] * 0.25)
    for _ in range(max_swipes):
        self.driver.swipe(x, y1, x, y2, 400)
        if self.is_present(loc, timeout=1):
            return True
    return False
```

Свайп 400 мс на ~55% высоты экрана — это **fling**: Compose-список продолжает
ехать по инерции ПОСЛЕ возврата вызова. Проверка `is_present(..., timeout=1)`
делается один раз между свайпами, без ожидания оседания скролла. Под нагрузкой
(длинный прогон, медленные кадры) искомая строка успевает войти в вьюпорт и выйти
из него между двумя опросами — хелпер проскакивает секцию, докручивает список до
конца и возвращает `False`. Потребитель падает ассертом вида «секция … не найдена
прокруткой», что читается как «элемента нет в приложении», хотя он есть.

Экземпляр: `framework/screens/settings_screen.py:187-192`
(`tap_display_mode`) в TC-093.

## Шаги воспроизведения (Given-When-Then)

**Given** открыт экран Settings (список длиннее экрана: Reader → Content
Visibility → Saved AO3 Filters → Data → Debug), устройство под нагрузкой
**When** тест вызывает `settings_steps.set_display_mode(driver, "Dim")` →
`SettingsScreen.tap_display_mode` → `swipe_to_text("Display mode")`
**Then (ожидалось)** список останавливается на секции «Content Visibility», где
находится строка «Display mode» (`SettingsScreen.kt:716` секция, `:771` строка)
**Actual (фактически)** `AssertionError: секция «Display mode» не найдена
прокруткой (Content Visibility)`; на скриншоте падения список докручен до САМОГО
НИЗА (видны «Saved AO3 Filters» обрезком сверху, «Data», «Debug», «Clear all
ratings») — т.е. «Display mode» был проскочен, а не отсутствовал

## Частота

1 из 1 в RUN-20260803-2012 (полный regression). **0 из 3 при изолированном
перезапуске** (2026-08-03, дословный вывод — в триаж-разделе
`runs/RUN-20260803-2012.md`). В ТОМ ЖЕ прогоне за 20 минут до падения TC-092
(`test_dim_mode_dims_hidden_rating_blurb`, 21:56:02→21:56:28) успешно
воспользовался тем же `tap_display_mode` — контроль, что секция существует и
хелпер в принципе работает.

## Артефакты

- Allure result: `framework/allure-results/868d60dc-90c9-4f94-8ff9-48ff2a23f189-result.json`
- Скриншот падения: `framework/allure-results/9e5cc29b-9bbc-4727-aa0f-afb36d754c52-attachment.png`
  (Settings прокручен до конца: Data/Debug/«Clear all ratings»)
- Page source: `framework/allure-results/364d6d6e-27f5-4853-96e6-e3fb9715f5b7-attachment.xml`
  — в дереве присутствуют только тексты нижней части списка
  (`SAVED AO3 FILTERS`, `DATA`, `DEBUG`, `Clear all ratings`), «Display mode»
  вне вьюпорта
- Logcat: `framework/allure-results/12dd06bc-9110-4f56-a5f7-aa3ff21c22da-attachment.txt`

## Анализ (failure-analyst)

Почему это долг тестовой системы, а не приложения:

1. Контрол существует и не переименован: `SettingsScreen.kt:771` (`Text("Display
   mode")`) внутри секции `SectionHeader("Content Visibility")` (`:716`) — код
   приложения читан read-only, не менялся с 2026-06-28
   (`state/app-under-test.yaml`, `source_commit 63f6aac3`).
2. TC-092 в том же прогоне (та же сборка, тот же эмулятор, тот же хелпер) прошёл
   зелёным — APP_BUG/APP_CHANGED/SITE_CHANGED исключены.
3. Скриншот доказывает механизм: список НЕ застрял и не остался наверху, он уехал
   в самый низ — значит свайпы работали, а строку не заметили при опросе.
4. Изолированно 3/3 зелёных — падение не детерминированное, но причина
   установлена по артефактам (не «неизвестная нестабильность»).

## Критерий готовности (Fixed)

- [x] Сделать поиск устойчивым к инерции: опрашивать наличие текста в цикле ДО
      оседания скролла (например, короткий поллинг после каждого свайпа вместо
      одиночного `is_present(timeout=1)`), либо перейти на прокрутку без fling
      (несколько коротких свайпов / `mobile: scrollGesture` с percent), либо
      детектировать «список упёрся в конец» и не тратить остаток `max_swipes`.
      Сделано: `_swipe_search` (новый общий хелпер) режет один длинный fling-свайп
      на `SWIPE_MICRO_STEPS=3` коротких контролируемых свайпа (та же ПОЛНАЯ
      дистанция раунда — landing-позиция не изменилась относительно исходного
      кода, только способ её достичь), затем `poll_for` (новый примитив,
      `framework/core/waits.py`) опрашивает settle-окно (1.2s/0.3s шаг, ~5
      опросов) вместо одного `is_present(timeout=1)`.
- [x] Класс, а не экземпляр: фикс — в `BaseScreen._swipe_search`, общем для
      `swipe_to_text` И `swipe_up_to_text` (`base_screen.py`), сигнатуры (bool)
      не менялись — все 10 call sites (`settings_screen.is_rating_hidden`/
      `set_hide_rating`/`tap_display_mode`/`open_clear_all_dialog`/
      `_swipe_to_profile`, `saf_steps.open_settings_scrolled_to`,
      `library_steps` и др.) получили фикс без правки самих call sites.
- [x] Диагностика вместо ложного вывода: `_swipe_search` возвращает
      `(found, diagnostic)`; `swipe_to_text`/`swipe_up_to_text` кладут
      diagnostic в `self.last_swipe_diagnostic` И прикладывают к Allure
      (`_attach_swipe_diagnostic`, best-effort) при неуспехе — сообщение
      различает «КОНЕЦ СПИСКА» (отпечаток видимых текстов не изменился после
      раунда, `_scroll_fingerprint`) от «НЕ НАЙДЕНА ... список ещё двигался»
      (лимит `max_swipes` исчерпан, конец не достигнут).
- [x] Красная проба: `framework/tests/test_swipe_to_text_settle_unit.py` (сценарий
      `test_swipe_to_text_catches_narrow_visibility_window`, фейковые часы +
      фейковый driver, целевой текст «виден» только в узком окне фейкового
      времени [2.0, 2.5]) прогнан против ДОКОММИТНОЙ `base_screen.py` (git HEAD
      `e42eb8bb`, изолированная загрузка в отдельном процессе, репо не тронуто)
      standalone-скриптом с тем же фейковым driver+сценарием: `found=False`
      (8 свайпов, 12.01s реального времени — старый код ждёт РЕАЛЬНЫМ
      `time.sleep`, а фейковые часы без `poll_for` не продвигаются, окно
      видимости [2.0,2.5] никогда не наступает). Тот же сценарий против
      ПОСЛЕФИКСНОГО кода (постоянная проба) — `found=True` (5/5 в пермутации
      `Invoke-Pytest tests/test_swipe_to_text_settle_unit.py`). Дословный вывод
      обеих сторон — в отчёте test-maintainer этой сессии.
- [x] 3 зелёных прогона подряд TC-093 изолированно (`Invoke-Pytest
      tests/test_visibility.py::test_display_mode_hide_to_dim_live_push`,
      44.06s/44.67s/46.29s) + зелёный `test_visibility.py` целиком (6 passed,
      248.89s) и `test_settings.py` целиком (8 passed, 405.97s) — все
      `PYTEST_EXIT=0`.

**Регрессия, пойманная и починенная в ходе фикса (не осталась в дереве):**
первая версия фикса разбивала ПОЛНУЮ дистанцию раунда на 3 коротких свайпа и
возвращала `True`, как только текст замечен ВНУТРИ раунда (после 1-го/2-го
мини-свайпа) — это сокращало фактическую дистанцию прокрутки относительно
исходного кода и ломало `test_clear_all_ratings_badge_persists_without_reload`
(`test_settings.py`, TC-020): `open_clear_all_dialog` ищет соседний узел
`textStartsWith("Clear")` РЯДОМ с «Clear all ratings» СРАЗУ после
`swipe_to_text` — при частичной дистанции этот сосед ещё не был в кадре.
Исправлено до сдачи: полная дистанция раунда проходится ВСЕГДА (как в
исходном коде), проверка присутствия — только ПОСЛЕ полного раунда, но
settle-окном (несколько опросов), а не одним снимком. Обнаружено ПОЛНЫМ
прогоном `test_settings.py` (шаг 4 DoD, не только TC-093) — иллюстрация,
зачем DoD требует полных прогонов файлов-соседей, а не только целевого TC.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-10 | framework fix commit `1ff003d` (HEAD); тестируемая сборка приложения source_commit `6f884d979a5c19465c6d8647737376864f424555` (`6f884d97`), version_name `dev-local`, version_code `12`, built_at `2026-08-10T10:38:57Z` — от сборки приложения долг не зависит, версия приведена для полноты строки | (1) `tests/test_swipe_to_text_settle_unit.py` — device-free юнит-слайс, 5 сценариев: `Invoke-Pytest tests/test_swipe_to_text_settle_unit.py -q` → `5 passed in 0.05s`, `PYTEST_EXIT=0`; (2) TC-093 изолированно на устройстве: `Invoke-Pytest -k test_display_mode_hide_to_dim_live_push` → `1 passed, 344 deselected in 46.09s`, `PYTEST_EXIT=0` | оба прогона зелёные, независимо от witness maintainer'а в «Обсуждении» | Verified |

## Обсуждение

**[failure-analyst @ 2026-08-03T20:35:00Z]** Заведён по вердикту `TEST_BUG`
падения TC-093 в `runs/RUN-20260803-2012.md`. Собрат по классу «ожидание слабее,
чем требует шаг» — `AT-BUG-047` (барьер перед WebView-навигацией), заведён тем же
ходом; кода общего нет, фиксы независимы.

**[test-maintainer @ 2026-08-10T11:30:11Z]** Fixed. Класс закрыт в
`BaseScreen._swipe_search` (общий хелпер `swipe_to_text`/`swipe_up_to_text`) +
новый `waits.poll_for`; все 5 пунктов критерия выполнены (см. чеклист выше,
дословный вывод red-probe и прогонов — там же). Первая версия фикса словила
СВОЙ собственный регресс (сократила дистанцию прокрутки за раунд, сломав
`test_clear_all_ratings_badge_persists_without_reload`/TC-020) — поймано
полным прогоном `test_settings.py`, а не изолированным TC-093, и починено до
сдачи (детали — в чеклисте). Новый device-free регресс-гвард
`framework/tests/test_swipe_to_text_settle_unit.py` (5 сценариев) добавлен в
дерево постоянно. Диф не закоммичен — коммит узким списком за координатором.
Лок снят.

**[fix-verifier @ 2026-08-10T11:35:07Z]** Verified. Дифф уже в HEAD коммитом
`1ff003d` (проверено `git log`). Независимое подтверждение двумя прогонами:
(1) device-free `Invoke-Pytest tests/test_swipe_to_text_settle_unit.py -q` →
`5 passed in 0.05s`, `PYTEST_EXIT=0`; (2) device, TC-093 изолированно
`Invoke-Pytest -k test_display_mode_hide_to_dim_live_push` →
`1 passed, 344 deselected in 46.09s`, `PYTEST_EXIT=0` (эмулятор
`emulator-5554` присутствовал, сверено `Get-Device`). Оба зелёные, витнесс
maintainer'а в верхней реплике подтверждён вживую. Fixed→Verified, лок снят
(не переустанавливался, был уже закрыт maintainer'ом).
