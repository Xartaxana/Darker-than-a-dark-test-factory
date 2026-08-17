---
key: "AT-BUG-080"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p1"
summary: "swipe_to_text считает успехом ЛЮБОЕ присутствие якорного текста (в т.ч. обрезок в 9 px у нижней кромки вьюпорта), а вызывающие ищут СОСЕДА по той же строке — соседний узел ещё вне дерева; экземпляр TC-004 open_clear_all_dialog в RUN-20260816-1831 (остаток класса AT-BUG-048)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-004", "run:RUN-20260816-1831", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-17T02:58:00Z"
updated: "2026-08-17T02:58:00Z"
archived: false
resolution: "done"
---

# swipe_to_text считает успехом ЛЮБОЕ присутствие якорного текста (в т.ч. обрезок в 9 px у нижней кромки вьюпорта), а вызывающие ищут СОСЕДА по той же строке — соседний узел ещё вне дерева; экземпляр TC-004 open_clear_all_dialog в RUN-20260816-1831 (остаток класса AT-BUG-048)

_Спроецировано из `bugs/AT-BUG-080.md` (источник правды).
Статус в нашей машине: **Verified**._

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

- [x] **Усилить контракт, а не landing:** реализован комбинированный вариант —
      `BaseScreen._anchor_clipped_by_viewport` требует bounds якоря внутри
      вьюпорта (`new UiSelector().scrollable(true)`) с запасом
      `SWIPE_ANCHOR_MARGIN_PX=24`; при обрезке `_settle_clipped_anchor` довoдит
      строку доп. КОРОТКИМИ свайпами (один микрошаг раунда за попытку,
      `SWIPE_NUDGE_MAX_ATTEMPTS=3`), пока запас не появится либо список
      физически не уткнётся (отпечаток `_scroll_fingerprint` не меняется —
      отдаётся как есть, не бесконечный цикл). Best-effort: если
      `scrollable(true)`-контейнер не найден (bounds снять не удалось),
      геометрия трактуется как «не проверено» — фолбэк на прежнее поведение,
      экраны без снимаемой геометрии не блокируются.
- [x] **Класс, а не экземпляр:** правка — в общем `_swipe_search`
      (`base_screen.py`), получили ВСЕ 14 перечисленных call sites бесплатно
      (сигнатура `swipe_to_text`/`swipe_up_to_text` не изменилась).
- [x] **`following::`-семейство:** добавлен `BaseScreen.find_row_sibling`
      (гард «тот же ряд» по пересечению Y-bounds якоря и кандидата) —
      применён везде, где было явное падение в `following::…[1]`:
      `settings_screen.py` — `is_tap_to_scroll_checked`/`set_tap_to_scroll`,
      `is_infinite_scroll_checked`/`set_infinite_scroll`,
      `is_volume_button_scroll_checked`/`set_volume_button_scroll`,
      `is_rating_hidden`/`set_hide_rating`, `is_auto_apply_filter_checked`/
      `set_auto_apply_filter`, `is_debug_copy_url_checked`/
      `set_debug_copy_url` (6 тумблеров, checkable-предикат) И
      `delete_filter_profile`/`open_rename_dialog` (content-desc предикат,
      деструктивное действие — риск нажать чужой Rename/Delete был
      явно назван «опаснее падения» в анализе, закрыт тем же гардом).
      `tap_display_mode`/`tap_download_format`/`swipe_to_metadata_fetch`/
      `open_clear_all_dialog`/`steps/saf_steps.py:93,127`/
      `steps/library_steps.py:303` не используют `following::` (текст-сосед
      напрямую или отдельная строка) — им класс-фикс `_swipe_search` даёт
      полное покрытие без доп. правок; `_swipe_to_profile`'s следующий::
      покрыт через переиспользующие его `delete_filter_profile`/
      `open_rename_dialog` выше. Полное покрытие, remainder не остался.
- [x] **Красная проба device-free:** `framework/tests/test_swipe_to_text_settle_unit.py`
      — 2 новых сценария (`test_swipe_to_text_settles_anchor_clipped_by_viewport_edge`,
      `test_swipe_to_text_settle_gives_up_when_list_stuck`); против докоммитной
      версии `base_screen.py` (`git stash push -- framework/screens/base_screen.py`)
      оба падают на `assert driver.swipe_calls`/`len(...)==1` — старый код не
      делает НИ ОДНОГО доп. свайпа независимо от геометрии, восстановлено
      `git stash pop`, полный файл зелёный (7/7) после восстановления фикса.
- [x] 3 зелёных изолированных прогона TC-004 (2-й запуск дал 1 непоследовательный
      флейк — см. Обсуждение, изолирован как НЕ относящийся к этому фиксу,
      заведён `AT-BUG-081`; финальная СЕРИЯ из 3 подряд — все зелёные) + полный
      `tests/test_smoke.py` (9 passed) и `tests/test_settings.py` (10 passed,
      1 skipped — пре-существующий известный skip TC-188, не связан с этим
      фиксом). Дополнительно (расширенный scope item 3): полный
      `tests/test_reading_ux.py`, `test_infinite_scroll.py`,
      `test_volume_paging.py`, `test_visibility.py`, `test_filter_profiles.py`
      — 27/27 passed (покрывают все `find_row_sibling`-call sites).

### Rework (критик-вход, 4 блокера Б1-Б4, живые пробы) — критерий готовности

- [x] **Б1 (класс не закрыт):** `_AUTO_DOWNLOAD_SWITCH` (единственный оставшийся
      сырой `following::…)[1]` во `framework/screens/`/`framework/steps/`,
      критик перепроверил grep'ом) переведён на `_AUTO_DOWNLOAD_LABEL` +
      `find_row_sibling`/`tap_row_sibling` — тот же приём, что остальные 8 мест.
- [x] **Б2 (find_row_sibling возвращает чужой ряд):** ветка «bounds якоря
      известны, но ни один candidate не делит ряд» РАЗДЕЛЕНА от «bounds
      недоступны вообще» — первая теперь честно падает `AssertionError`
      («чужой ряд НЕ возвращаем»), не `candidates[0]`; вторая (легитимный
      случай — нет `scrollable(true)`-контейнера/bounds не распознан) осталась
      фолбэком на `candidates[0]`, как и было. Docstring обновлён под факт.
      Красная device-free проба `test_find_row_sibling_raises_instead_of_wrong_row`
      (`test_swipe_to_text_settle_unit.py`) — падает на докоммитном коде
      (`DID NOT RAISE AssertionError`, т.е. молча вернул кандидата чужого ряда),
      зелёная после фикса.
- [x] **Б3 (регрессия на противоположной кромке):** `_anchor_clipped_by_viewport`
      получил `check_bottom_edge` — проверяет ТОЛЬКО ту кромку, к которой
      движется ТЕКУЩИЙ поиск (`swipe_to_text` → нижняя, `swipe_up_to_text` →
      верхняя), не обе одновременно; `_settle_clipped_anchor` унаследовал тот же
      параметр. Две новые device-free пробы (`test_swipe_to_text_does_not_nudge_
      anchor_at_opposite_edge`/`test_swipe_up_to_text_does_not_nudge_anchor_at_
      opposite_edge`) — обе падают на докоммитном коде (лишний доп. `driver.swipe`
      уводит уже видимую строку от центра), зелёные после фикса.
- [x] **Б4 (timeout проигнорирован):** `find_row_sibling` теперь опрашивает
      дерево через `poll_for(timeout=..., interval=0.4)` (дефолт —
      `settings.DEFAULT_TIMEOUT=20s`) вместо одного `find_elements` без
      ожидания; добавлен `tap_row_sibling` — восстанавливает
      `EC.element_to_be_clickable`-гейт (`wait_until` поверх уже найденного
      узла своей строки, тот же принцип, что `BaseScreen.tap`) для ВСЕХ
      тапающих call sites (6 тумблеров + Rename/Delete + Auto-download после
      Б1); `is_*_checked`-геттеры (read-only) остались на `find_row_sibling`
      без доп. клик-гейта, как и раньше.
- [x] Все 10 device-free проб `test_swipe_to_text_settle_unit.py` (7 старых +
      3 новых) зелёные; 3 новые пробы (Б2 + Б3×2) индивидуально проверены
      против докоммитной (пред-rework) версии `base_screen.py`
      (byte-copy-safety: **правка критик-входа round2 (N1)** — `git status
      --porcelain` НЕ был пуст на момент подмены (весь rework-дифф ещё
      некоммичен, `base_screen.py` уже модифицирован фиксом; последний
      коммит по файлу — `1ff003d`, AT-BUG-048), поэтому `git checkout --`
      был бы нелегален (CLAUDE.md, permission-hygiene п.8) — байтовая
      копия в scratchpad была ЕДИНСТВЕННЫМ легальным способом отката, а
      не дополнительной подстраховкой; восстановление сверено байт-в-байт
      `diff`) — падают все три с ожидаемой сигнатурой, зелёные после
      восстановления фикса.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-17T01:39:05Z (test-maintainer, rework self-verification — не fix-verifier) | dev-local (versionCode 12), фреймворк-фикс, сборка приложения не менялась | Device-free: `framework/tests/test_swipe_to_text_settle_unit.py` (10/10, вкл. 3 новые Б2/Б3-пробы, каждая индивидуально red→green по докоммитному base_screen.py). Device (emulator-5554): TC-004 3 изолированных перезапуска подряд (139.51s/145.02s/140.23s, все PASSED); TC-032 (`test_auto_download_triggers_on_loved_rating`, Б1-путь через `find_row_sibling`/`tap_row_sibling`) 3 изолированных перезапуска подряд (82.39s/82.14s/82.30s, все PASSED); `tests/test_settings.py` полностью (10 passed, 1 skipped — пре-существующий TC-188, не связан); `tests/test_downloads.py` полностью (16 passed, 1 failed — TC-112, изолированный повторный прогон того же узла PASSED; **правка критик-входа round2 (N2)**: тело TC-112 само не исполняет изменённый код, но падение order/state-зависимое, а СОСЕДНИЕ тесты того же файла его исполняют (`enable_auto_download`→`tap_row_sibling`, `open_settings_scrolled_to`→`_settle_clipped_anchor`) — вклад rework'а в это падение НЕ исключён и НЕ подтверждён (правило 14, каузальный негатив требует исключающего прогона, не сделан); заведён `AT-BUG-082` с той же честной рамкой); `tests/test_filter_profiles.py` полностью (12/12 passed, покрывает `tap_row_sibling` с content-desc предикатом Rename/Delete). `scripts/validate_frontmatter.py`: 0/0. `scripts/arch_check.py`: 0 ошибок, 4 пре-существующих WARN (не новые). Ни одной правки в `app-under-test/` | Self-verification test-maintainer (не заменяет проход fix-verifier); статус остаётся `Fixed` |
| 2026-08-17T02:58:00Z (fix-verifier) | dev-local (versionCode 12); test_debt — сборка приложения роли не играет (правило D1) | Формальный D1-проход поверх уже состоявшейся двухраундовой критик-приёмки этой сессии (attempt1→критик R1: 4 блокера Б1-Б4 все с witness→rework attempt2→критик R2 точечный: независимые живые пробы по каждому Б1-Б4 + мутационная проверка красноты 3 новых проб + живые device-прогоны TC-004/TC-032/TC-042 + grep класс-полноты 9/9 тапающих мест — ПРИНЯТ без блокеров, **правка мини-критик-входа (N1)**: полный текст обоих раундов живёт в `logs/routing-log.jsonl` — события `2026-08-16T23:52:18` (rejected R1, 4 блокера с witness), `23:52:29` (accepted R1), `2026-08-17T02:04:09` (accepted attempt2 + accepted R2); «## Обсуждение» этого файла несёт только пересказ test-maintainer и текстовые правки N1/N2 round2, не сами раунды). Не повторяю весь этот объём — SPOT-CHECK: изолированный `tests/test_smoke.py::test_clear_all_ratings` (TC-004, самый первый экземпляр этого долга, `-m p0 -k test_clear_all_ratings`, 493 deselected) — 1 passed, 161.94s; полный `framework/tests/test_swipe_to_text_settle_unit.py` (device-free) — 10 passed, 0.11s. `python scripts/validate_frontmatter.py`: ошибок 0, предупреждений 0. Ни одной правки в `app-under-test/`. **Открытый остаток (N2, мини-критик-вход):** вклад rework'а в падение TC-112 (`AT-BUG-082`) НЕ исключён и НЕ подтверждён, исключающий прогон не назначен — `Verified` этого бага решение не закрывает | Оба spot-check зелёные, согласуются с объёмом уже проведённой критик-приёмки → перевожу `Fixed` → `Verified` |

## Обсуждение

**[failure-analyst @ 2026-08-16T20:49:00Z]** Заведён по вердикту `TEST_BUG`
падения TC-004 в `runs/RUN-20260816-1831.md`. Прямой ОСТАТОК класса
`AT-BUG-048` (Verified): там усилили способ ДОСТИЖЕНИЯ landing-позиции
(не-fling микросвайпы + settle-поллинг), здесь не усилён сам КРИТЕРИЙ УСПЕХА
(«якорь виден» ≠ «строкой можно пользоваться»). `automation_status` кейса
TC-004 оставлен `active` — карантин не ставлю: причина названа точно, фикс
адресный, а p0-smoke без покрытия дороже одного редкого красного (тот же
прецедент, что `AT-BUG-047`/`AT-BUG-048` в `RUN-20260803-2012`).

**[test-maintainer @ 2026-08-16T22:35:00Z]** Фикс реализован в `base_screen.py`
(контракт `_swipe_search` + `find_row_sibling`), применён по всем 14 call sites
+ `following::`-семейству (см. чек-лист выше). Красная проба подтверждена
`git stash`/`git stash pop` (byte-copy safety не потребовался — `git status
--porcelain -- framework/screens/base_screen.py` был пуст ДО порчи, откат
легален штатным `git stash`).

**[test-maintainer @ 2026-08-17T01:39:05Z, rework]** Rework после critic-входа
на attempt 1 — 4 блокера, все подтверждены критиком ЖИВЫМИ пробами (не
теория), все четыре исправлены (см. новый раздел «Rework» критерия
готовности выше):

- **Б1** (`_AUTO_DOWNLOAD_SWITCH` — последний сырой `following::…)[1]`):
  переведён на `find_row_sibling`/`tap_row_sibling`, симметрично остальным
  8 местам. Живой путь `test_downloads.py::test_downloads` (194/380/438) →
  `saf_steps.open_settings_scrolled_to` → `settings_steps.enable_auto_download`
  → `set_auto_download` → `tap_row_sibling` — покрыт TC-032 (3× изолированный
  перезапуск, все PASSED).
- **Б2** (`find_row_sibling` фолбэк на `candidates[0]` даже когда bounds якоря
  ИЗВЕСТНЫ, но ни один candidate не делит ряд — критик воспроизвёл
  `DELETE-OF-ANOTHER-ROW`): разделил два случая (bounds недоступны ВООБЩЕ —
  легитимный фолбэк на прежнее поведение; bounds известны, own-row кандидат не
  найден — честный `AssertionError`, чужой ряд не возвращается). Добавлена
  device-free красная проба, red→green по докоммитному коду подтверждён.
- **Б3** (`_anchor_clipped_by_viewport` проверяла ОБЕ кромки одновременно,
  `_settle_clipped_anchor` всегда свайпала В НАПРАВЛЕНИИ ПОИСКА — критик
  воспроизвёл регрессию на противоположной кромке: якорь, целиком видимый у
  верхней кромки при `swipe_to_text`, довозился ЕЩЁ ДАЛЬШЕ вверх и выводился из
  дерева): добавлен `check_bottom_edge` (`swipe_to_text` → только нижняя,
  `swipe_up_to_text` → только верхняя), обрезка проверяется ТОЛЬКО по кромке
  текущего направления поиска. Две device-free пробы (по одной на каждое
  направление), red→green по докоммитному коду подтверждён для обеих.
- **Б4** (`timeout`-параметр `find_row_sibling` объявлен и не использован —
  критик воспроизвёл `AssertionError after 0.00s (timeout=20 requested)`):
  `find_row_sibling` теперь опрашивает дерево `poll_for(timeout=..., interval=
  0.4)`; добавлен `tap_row_sibling` — восстанавливает `EC.element_to_be_
  clickable`-гейт (тот же принцип, что `BaseScreen.tap`) для всех тапающих
  call sites (6 тумблеров + Rename/Delete + Auto-download).

Верификация: `test_swipe_to_text_settle_unit.py` полностью (10/10, включая
3 новые пробы — каждая индивидуально проверена против докоммитной версии
`base_screen.py` byte-copy-safety приёмом: `git status --porcelain` пуст ДО
подмены, копия в scratchpad, восстановление сверено байт-в-байт `diff` —
witness отката); TC-004 3× изолированный перезапуск подряд, все PASSED
(139.51s/145.02s/140.23s); TC-032 (Б1-путь) 3× изолированный перезапуск
подряд, все PASSED (82.39s/82.14s/82.30s); `test_settings.py` полностью
(10 passed, 1 skipped — пре-существующий TC-188); `test_downloads.py`
полностью (16 passed, 1 failed — TC-112, см. ниже); `test_filter_profiles.py`
полностью (12/12 passed — `tap_row_sibling` с content-desc предикатом).

Попутная находка: `test_downloads.py::test_favorite_rating_does_not_download_
when_auto_download_off` (TC-112) упал ТОЛЬКО внутри полного прогона файла
(`assert_work_not_in_files_tab`), изолированный повторный прогон ТОГО ЖЕ узла
— PASSED. **Правка критик-входа round2 (N2):** тело TC-112 само не
обращается ни к одному из мест, изменённых этим rework'ом (`SettingsScreen`/
`find_row_sibling`/`tap_row_sibling`/`_swipe_search` не в цепочке вызовов
ЭТОГО теста), НО падение order/state-зависимое, а СОСЕДНИЕ тесты того же
файла изменённый код исполняют (`enable_auto_download`→`tap_row_sibling`,
`open_settings_scrolled_to`→`_settle_clipped_anchor` меняют тайминги между
тестами) — по правилу 14 (каузальный негатив) «не исполнялось в самом
тесте» ≠ «вклад исключён». Корректная рамка: вклад rework'а в падение
TC-112 **НЕ исключён и НЕ подтверждён**; исключающий прогон (полный
`test_downloads.py` на пред-rework дереве) не сделан — решение назначать
его или нет за координатором. Заведён `AT-BUG-082` (test_debt, flaky_test)
с той же честной рамкой — не расширяю scope этого бага починкой (другой
класс дефекта, order/state между тестами `test_downloads.py`).

Статус остаётся `Fixed` (self-verification test-maintainer, не заменяет
проход fix-verifier). `scripts/validate_frontmatter.py`: 0/0.
`scripts/arch_check.py`: 0 ошибок, 4 пре-существующих WARN (не новые). Ни
одной правки в `app-under-test/`. Лок снимаю.

---

Верификационный прогон TC-004 (3 изолированных перезапуска подряд, ПЕРВАЯ
попытка) дал PASS/**FAIL**/PASS — упавший прогон (`assert_no_ratings()`:
ожидали 0, в БД `'5'`) исследован по логкату: якорь «Clear all ratings» был
найден СРАЗУ с bounds `[42,1937][293,1980]` — НЕ обрезан кромкой (запас от
края вьюпорта далеко больше `SWIPE_ANCHOR_MARGIN_PX=24`), поэтому механизм
ЭТОГО фикса (`_settle_clipped_anchor`) в упавшем прогоне НЕ ИСПОЛНЯЛСЯ вообще
(ни одного доп. `driver.swipe` между нахождением анкора и тапом «Clear…»/
«Clear all» в логе нет) — изолирующее наблюдение, не совместный зелёный
прогон: вклад этого фикса в конкретно ЭТОТ красный прогон исключён по факту
неисполнения изменённой ветки кода, а не предположением. Корень — гонка
`assert_no_ratings()` (одноразовый adb-read) с `SettingsViewModel.
confirmClearAll()` (`viewModelScope.launch(Dispatchers.IO) {
repo.clearAllRatings() }`, не await'ится) — заведён `AT-BUG-081` (test_debt,
flaky_test), в scope этого бага не чиню (другой класс дефекта). ВТОРАЯ серия
из 3 изолированных перезапусков TC-004 подряд — все PASS (70s/69s/129s);
после неё полный `test_smoke.py` (9/9) и `test_settings.py` (10 passed, 1
skipped — пре-существующий TC-188 skip по несвязанной причине, см. вывод
прогона). Дополнительно прогнаны все файлы, покрывающие расширенный scope
item 3 (`find_row_sibling`): `test_reading_ux.py`, `test_infinite_scroll.py`,
`test_volume_paging.py`, `test_visibility.py`, `test_filter_profiles.py` —
27/27 passed. `python scripts/validate_frontmatter.py`: ошибок 0,
предупреждений 0. `python scripts/arch_check.py`: ошибок 0 (4 пре-существующих
известных WARN, не новые). Ни одной правки в `app-under-test/`. Перевожу
Open → Fixed, снимаю lock (guard B4: `test-maintainer` легален для
`type: test_debt`). Fixed → Verified — за fix-verifier (сборка приложения не
нужна, фикс во фреймворке).

**[fix-verifier @ 2026-08-17T02:58:00Z]** Формальный D1-проход. Фикс уже
прошёл необычно глубокую приёмку в этой сессии (attempt1 → критик round1: 4
блокера Б1-Б4, все с живым witness → rework attempt2 → критик round2
точечный: независимые живые пробы по каждому блокеру + мутационная проверка
красноты 3 новых проб + живые device-прогоны TC-004/TC-032/TC-042 + grep
класс-полноты 9/9 тапающих мест → ПРИНЯТ без блокеров) — не переоткрываю это
ревью, беру его как основание. Роль fix-verifier по D1 формально отделена от
test-maintainer (guard B4 не даёт test-maintainer самому закрыть цикл), поэтому
делаю независимый SPOT-CHECK: изолированный запуск самого первого экземпляра
долга, `tests/test_smoke.py::test_clear_all_ratings` (TC-004) —
`Invoke-Pytest -m p0 -k test_clear_all_ratings` → `1 passed, 493 deselected in
161.94s`, PYTEST_EXIT=0; полный `framework/tests/test_swipe_to_text_settle_unit.py`
(device-free, 10 проб, включая 3 новые Б2/Б3-пробы этого rework'а) →
`10 passed in 0.11s`, PYTEST_EXIT=0. `Get-Device` до прогона — `DEVICE:
emulator-5554`. `python scripts/validate_frontmatter.py`: ошибок 0,
предупреждений 0. Оба прогона зелёные с первой попытки, красных не было —
разбирать нечего. Ни одной правки в `app-under-test/`. По правилу D1
(test_debt-класс, сборка приложения роли не играет) перевожу Fixed →
Verified, `known_issue` уже `"false"` (не требует сброса), снимаю lock.
