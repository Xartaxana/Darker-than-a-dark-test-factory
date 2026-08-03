---
id: AT-BUG-048
title: "BaseScreen.swipe_to_text проскакивает искомую секцию под нагрузкой (fling-инерция + опрос раз в свайп) — Settings докручивается до конца списка, ассерт «секция не найдена прокруткой»; экземпляр TC-093 в RUN-20260803-2012"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Open
found_in: "framework commit e42eb8bb (тестируемая сборка приложения 1.10 (versionCode 11), build 6455af0c — от сборки НЕ зависит)"
fixed_in: ""
last_seen_in: "RUN-20260803-2012 (2026-08-03)"
test_cases: ["TC-093"]
runs: ["RUN-20260803-2012"]
duplicates: []
regression_of: ""
status_since: "2026-08-03T20:35:00Z"
updated: "2026-08-03T20:35:00Z"
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

- [ ] Сделать поиск устойчивым к инерции: опрашивать наличие текста в цикле ДО
      оседания скролла (например, короткий поллинг после каждого свайпа вместо
      одиночного `is_present(timeout=1)`), либо перейти на прокрутку без fling
      (несколько коротких свайпов / `mobile: scrollGesture` с percent), либо
      детектировать «список упёрся в конец» и не тратить остаток `max_swipes`.
- [ ] Класс, а не экземпляр: фикс — в `BaseScreen.swipe_to_text` (и симметрично
      `swipe_up_to_text`, `base_screen.py:89-105`), чтобы его получили все 10
      call sites (`settings_screen.is_rating_hidden`/`set_hide_rating`/
      `tap_display_mode`, `saf_steps.open_settings_scrolled_to`,
      `open_clear_all_dialog`, `_swipe_to_profile` и др.), а не один TC-093.
- [ ] Диагностика вместо ложного вывода: при неуспехе сообщение ассерта должно
      различать «строки нет в списке» и «прокрутка дошла до конца, строка не
      поймана» (в текущем виде обе ситуации выглядят как «секция не найдена»).
- [ ] Красная проба: воспроизвести проскок искусственно (замедлить опрос /
      увеличить инерцию) — ДО фикса `swipe_to_text` возвращает `False` при
      существующей строке, ПОСЛЕ — `True`.
- [ ] 3 зелёных прогона подряд TC-093 изолированно + зелёный `test_visibility.py`
      и `test_settings.py` целиком.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**[failure-analyst @ 2026-08-03T20:35:00Z]** Заведён по вердикту `TEST_BUG`
падения TC-093 в `runs/RUN-20260803-2012.md`. Собрат по классу «ожидание слабее,
чем требует шаг» — `AT-BUG-047` (барьер перед WebView-навигацией), заведён тем же
ходом; кода общего нет, фиксы независимы.
