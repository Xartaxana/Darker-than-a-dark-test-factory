---
id: AT-BUG-080
title: "swipe_to_text считает успехом ЛЮБОЕ присутствие якорного текста (в т.ч. обрезок в 9 px у нижней кромки вьюпорта), а вызывающие ищут СОСЕДА по той же строке — соседний узел ещё вне дерева; экземпляр TC-004 open_clear_all_dialog в RUN-20260816-1831 (остаток класса AT-BUG-048)"
type: test_debt
debt_kind: flaky_test
severity: major
status: Open
found_in: "framework commit e6203c2 (тестируемая сборка приложения: source_commit aa377e0ec9664fcd5439fec9391638fabf94f448, dev-local, versionCode 12 — от сборки НЕ зависит)"
fixed_in: ""
last_seen_in: "RUN-20260816-1831 (2026-08-16)"
test_cases: ["TC-004"]
runs: ["RUN-20260816-1831"]
duplicates: []
regression_of: ""
status_since: "2026-08-16T20:49:00Z"
updated: "2026-08-16T20:49:00Z"
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

# AT-BUG-080 — `swipe_to_text` доводит якорь до кромки вьюпорта, сосед по строке остаётся вне дерева

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность —
`framework/screens/base_screen.py::_swipe_search` (критерий успеха
`swipe_to_text`/`swipe_up_to_text`) и её call sites, которые СРАЗУ после свайпа
ищут узел-СОСЕД в той же строке (перечень — «Класс, а не экземпляр» ниже).
От сборки приложения не зависит: экран Settings в этой сборке не менялся
(диапазон `27d5cfd1..aa377e0e` трогает `PROJECT.md`,
`app/src/main/assets/ao3_bridge.js`, `ui/browser/BrowserViewModel.kt`).
Эмулятор `emulator-5554`, API 34, replay.

## Суть долга

`_swipe_search` (`base_screen.py:120-152`) объявляет успех, как только
`by_text(anchor)` ПРИСУТСТВУЕТ в дереве:

```python
if poll_for(lambda: self._probe_present(loc),
           timeout=SWIPE_SETTLE_TIMEOUT_S, interval=SWIPE_SETTLE_POLL_INTERVAL_S):
    return True, ""
```

«Присутствует» у UIAutomator означает «узел попал во вьюпорт хотя бы одним
пикселем» — bounds репортятся УЖЕ обрезанными по вьюпорту. Вызывающие же
опираются на более сильное условие — что в кадре вся СТРОКА, включая соседний
контрол:

```python
def open_clear_all_dialog(self):
    assert self.swipe_to_text("Clear all ratings"), "секция ... не найдена прокруткой"
    els = self.driver.find_elements(
        AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textStartsWith("Clear")')
    target = next((e for e in els if e.text.strip() != "Clear all ratings"), None)
    assert target is not None, "кнопка «Clear…» не найдена"
```

Когда раунд свайпа заканчивается ровно на моменте «якорь только что заглянул
снизу», `swipe_to_text` возвращает `True`, а сосед (`Text("Clear…")` внутри
`TextButton`) в дерево ещё не попал — ассерт падает сообщением, которое читается
как «кнопки нет в приложении».

Разрыв контракта известен с фикса `AT-BUG-048`: там первая версия фикса
сокращала дистанцию раунда и сломала ровно этот call site —
`open_clear_all_dialog` (цитата из чек-листа `AT-BUG-048`: «при частичной
дистанции этот сосед ещё не был в кадре»). Лечили тогда СЛЕДСТВИЕ (вернули
полную дистанцию раунда, чтобы landing-позиция совпадала с исходной), а не сам
контракт — «якорь виден» так и осталось слабее, чем «строка пригодна к
взаимодействию». Полная дистанция делает совпадение редким, но не невозможным:
достаточно, чтобы раунд закончился у самой кромки.

## Шаги воспроизведения (Given-When-Then)

**Given** второй сегмент полного регресса, 46 минут непрерывного pytest, 139
тестов до этого зелёные; открыт Settings (список много длиннее экрана:
Reader → Content Visibility → Saved AO3 Filters → Data → SYNC → Debug →
Clear all ratings — последняя строка списка)
**When** `test_smoke.py::test_clear_all_ratings` → `settings_steps.clear_all_ratings`
→ `SettingsScreen.open_clear_all_dialog` → `swipe_to_text("Clear all ratings")`
**Then (ожидалось)** строка «Clear all ratings» в кадре целиком, рядом —
`TextButton` с текстом «Clear…» (`SettingsScreen.kt:1313-1318`, рендерится
безусловно), тап открывает диалог «Clear all ratings?»
**Actual (фактически)** `AssertionError: кнопка «Clear…» не найдена`
(`settings_screen.py:38`). В page source падения:

- вьюпорт `android.widget.ScrollView` — `bounds="[0,296][1080,2064]"`;
- якорь `TextView text="Clear all ratings"` — `bounds="[42,2055][293,2064]"`,
  то есть **9 px по высоте** у самой нижней кромки (свайп остановлен, как
  только узел заглянул во вьюпорт);
- подзаголовок той же строки `Permanently delete all work ratings`
  (`SettingsScreen.kt:1307-1311`) в дереве **отсутствует вовсе** — он ниже кромки;
- кнопка присутствует СТРУКТУРНО, но без текста: кликабельный
  `android.view.View bounds="[876,2031][1038,2064]"` → дочерний
  `android.widget.Button text="" bounds="[876,2041][1038,2064]"`; узла с текстом
  «Clear…» в дереве нет;
- подстрока `Clear` встречается во всём XML **ровно один раз** — это сам якорь,
  поэтому `textStartsWith("Clear")` вернул единственный элемент, он же был
  отфильтрован как неклик. лейбл, и `target` оказался `None`.

## Частота

1 из 1 в `RUN-20260816-1831` (полный регресс, сегмент 2, ~46 мин под нагрузкой).
**0 из 3 при изолированном перезапуске** (2026-08-16, `emulator-5554` сверен
`Get-Device` → `DEVICE: emulator-5554`; дословный вывод — в триаж-разделе
`runs/RUN-20260816-1831.md`). Контроль, что и сборка, и хелпер в принципе
работают: тот же TC-004 зелёный в соседнем smoke ТОЙ ЖЕ сборки
(`RUN-20260816-1758`) и в предыдущем полном регрессе
(`RUN-20260815-0337`, `source_commit 59be96c6`).

## Артефакты

- Allure result: `runs/RUN-20260816-1831/allure/9cabdc8d-8069-480a-bc4e-ba6d361df6da-result.json`
  (`as_id: TC-004`, `status: failed`, шаг «Свайп к «Clear all ratings» и подтверждение»)
- Скриншот падения: `runs/RUN-20260816-1831/allure/5fe792e3-1c66-4b05-99ee-0e9b18218fdf-attachment.png`
  (строка «Clear all ratings» видна обрезком в 1-2 пикселя под «Show copy-URL
  button», прямо над нижней навигацией)
- Page source: `runs/RUN-20260816-1831/allure/0696fef5-b7a0-461d-ab28-23cf343e5fce-attachment.xml`
- Logcat: `runs/RUN-20260816-1831/allure/53fe67d3-5de3-430a-99e2-8320322b9812-attachment.txt`
  (402 строки, ни одного совпадения по `ANR|FATAL|onTrimMemory|am_kill|Choreographer|Davey|died`)
- Context: `runs/RUN-20260816-1831/allure/60ab1f93-f2dd-4117-b513-dd013fb38b2c-attachment.txt`
  (`context=NATIVE_APP` — WebView ни при чём)
- Аттачки `swipe_to_text diagnostic` НЕТ — прямое доказательство, что сам свайп
  отработал успешно (диагностика цепляется только при неуспехе,
  `base_screen.py:185-195`)

## Анализ (failure-analyst)

Почему это долг тестовой системы, а не приложения/окружения/сайта:

1. **Кнопка есть в приложении и рендерится безусловно:**
   `SettingsScreen.kt:1313-1318` — `TextButton(onClick = { viewModel.requestClearAll() })
   { Text("Clear…") }` внутри `Row`, без единого условия по состоянию
   (ни `enabled`, ни `if (hasRatings)`). В дереве падения её контейнер
   присутствует — отсутствует только ТЕКСТ, потому что узел ниже кромки вьюпорта.
2. **Сборка ни при чём:** диапазон `27d5cfd1..aa377e0e` (один коммит `aa377e0`
   «Fix undo-at-ceiling, infinite-scroll navigation traps, and copy-URL guard»)
   не трогает `ui/settings/`; baseline-предковость подтверждена
   (`git merge-base --is-ancestor` EXIT=0). Тот же тест зелёный на ЭТОЙ ЖЕ
   сборке в соседнем прогоне.
3. **Не окружение:** `recoveries this session = 0/2` в обоих сегментах,
   `ENV_ISSUE`-токена нет, в logcat нет FATAL/ANR/onTrimMemory, 289 из 290
   тестов прогона зелёные (в т.ч. 6 других тестов того же `test_smoke.py` и
   весь `test_settings.py`), Appium-сессия жива (page source и скриншот сняты
   штатно в teardown).
4. **Причина установлена по артефактам, а не «неизвестная нестабильность»:**
   геометрия из page source (якорь 9 px у кромки 2064, сосед вне дерева)
   однозначно называет механизм; недетерминизм — только в том, на каком
   пикселе остановился раунд свайпа.

## Критерий готовности (Fixed)

- [ ] **Усилить контракт, а не landing:** успех `swipe_to_text` должен означать
      «строка пригодна к взаимодействию», а не «якорь виден хотя бы пикселем».
      Варианты (выбор за test-maintainer): требовать, чтобы bounds якоря целиком
      лежали внутри вьюпорта с запасом (высота узла не обрезана / нижняя граница
      < низа скроллера минус порог) и доводить строку доп. коротким свайпом;
      либо после успеха ждать появления соседнего узла строки.
- [ ] **Класс, а не экземпляр:** правка — в общем `_swipe_search`
      (`base_screen.py`), чтобы её получили ВСЕ call sites, а не один
      `open_clear_all_dialog`. Call sites, зависящие от соседа по строке:
      `settings_screen.py` — `open_clear_all_dialog` (:34, текст-сосед
      «Clear…»), `is_tap_to_scroll_checked` (:124), `is_infinite_scroll_checked`
      (:151), `is_volume_button_scroll_checked` (:179), `is_rating_hidden`
      (:205), `tap_display_mode` (:229), `tap_download_format` (:245),
      `is_auto_apply_filter_checked` (:266), `_swipe_to_profile` (:319 —
      `Rename`/`Delete` по `following::`), `swipe_to_metadata_fetch` (:493),
      `is_debug_copy_url_checked` (:545); `steps/saf_steps.py:93,127`;
      `steps/library_steps.py:303`.
- [ ] **Отдельно проверить `following::`-семейство (опаснее падения):** у
      тумблеров сосед берётся как
      `(//*[@text="<подпись>"]/following::*[@checkable="true"])[1]`. Если СВОЙ
      `Switch` строки не попал в дерево (та же обрезка), `[1]` возьмёт
      checkable-узел СЛЕДУЮЩЕЙ строки — тест не упадёт, а прочитает ЧУЖОЕ
      состояние (ложно-зелёный/ложно-красный вместо честного отказа). Нужен
      либо гард «сосед принадлежит той же строке» (сверка bounds по Y), либо
      доведение строки в кадр до поиска.
- [ ] **Красная проба device-free:** расширить
      `framework/tests/test_swipe_to_text_settle_unit.py` сценарием «якорь
      присутствует, но обрезан кромкой; соседний узел ещё не в дереве» —
      против докоммитного `base_screen.py` он обязан быть красным.
- [ ] 3 зелёных изолированных прогона TC-004 + полный `tests/test_smoke.py` и
      `tests/test_settings.py` (тот же урок, что в `AT-BUG-048`: регресс
      landing-дистанции ловится именно соседними файлами, а не целевым TC).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**[failure-analyst @ 2026-08-16T20:49:00Z]** Заведён по вердикту `TEST_BUG`
падения TC-004 в `runs/RUN-20260816-1831.md`. Прямой ОСТАТОК класса
`AT-BUG-048` (Verified): там усилили способ ДОСТИЖЕНИЯ landing-позиции
(не-fling микросвайпы + settle-поллинг), здесь не усилён сам КРИТЕРИЙ УСПЕХА
(«якорь виден» ≠ «строкой можно пользоваться»). `automation_status` кейса
TC-004 оставлен `active` — карантин не ставлю: причина названа точно, фикс
адресный, а p0-smoke без покрытия дороже одного редкого красного (тот же
прецедент, что `AT-BUG-047`/`AT-BUG-048` в `RUN-20260803-2012`).
