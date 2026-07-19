---
id: AT-BUG-021
title: "Эмулятор дважды отваливается mid-test на driver.get()/switch_to.context внутри open_live_listing (Sort&Filter форма) — DevTools disconnected -> adb device not found; кандидат-сиблинг AT-BUG-016"
type: test_debt
debt_kind: broken_environment
severity: major
status: Open
found_in: "test-automator (canary batch C, 2026-07-19): при автоматизации TC-078..083 (include/exclude main-pairing чекбоксы + save-filter идемпотентность, живая форма Sort&Filter archiveofourown.org/tags/Fluff/works — та же тяжёлая live-страница, что фигурировала в AT-BUG-016) эмулятор ДВАЖДЫ отвалился ПОСРЕДИ прогона на одном и том же вызове (driver.get/switch_to.context внутри open_live_listing) с идентичной сигнатурой: WebDriverException 'disconnected: not connected to DevTools', сразу за которой — 'adb: device emulator-5554 not found' для всех дальнейших действий той же сессии. Get-Device -> NO DEVICE оба раза; Appium health-check (/status) отвечал 200 оба раза — деградация на уровне устройства/qemu, не Appium-сервера. Start-Emulator успешно поднимал эмулятор заново оба раза, но следующий же live-навигационный вызов ронял его снова. Fail-fast критерий (2 идентичных env-класс фейла на одном шаге, docs/06 §5) достигнут — воркер честно остановился, НЕ форсировал закрытие, automated_by нигде не проставлен, статусы TC-078..083 не менялись (остались Approved)."
fixed_in: ""
last_seen_in: ""
test_cases: ["TC-078", "TC-079", "TC-080", "TC-081", "TC-082", "TC-083"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-19T06:05:00Z"
updated: "2026-07-19T06:05:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
lock: ""
---

# AT-BUG-021 — эмулятор крашится mid-test на live Sort&Filter форме (кандидат-сиблинг AT-BUG-016)

## Окружение
- `emulator-5554`, WHPX-гипервизор, Appium 2 + UiAutomator2.
- Live-навигация на `archiveofourown.org/tags/Fluff/works` (реальная тяжёлая
  страница AO3) через `open_live_sort_filter_form_relationship_ready` /
  `open_live_listing` — та же страница, что фигурирует в `bugs/AT-BUG-016.md`
  (TC-040, теперь Fixed) и её эксплицитно названный, но НЕ подтверждённый
  сиблинг `browser_screen.py` живая work-страница.

## Суть долга

2 идентичных env-класс отказа подряд на одном и том же шаге (docs/06 §5
критерий fail-fast достигнут):
1. `WebDriverException: disconnected: not connected to DevTools` внутри
   `driver.get()`/`switch_to.context()` (`open_live_listing`).
2. Немедленно вслед — `adb: device 'emulator-5554' not found` для ЛЮБОГО
   дальнейшего действия той же сессии.
3. `Get-Device` -> `NO DEVICE` (позитивная сверка, не голый env-негатив).
4. Appium `/status` -> 200 ОБА раза — сам Appium-сервер жив, деградация
   именно на уровне устройства/эмулятора.
5. `Start-Emulator` поднимал эмулятор заново успешно оба раза — но
   следующий же live-навигационный вызов ронял его снова (не единичный
   сбой, воспроизводимо на одном и том же классе действия).

Ни одного РЕАЛЬНОГО теста-фейла за всю сессию batch C — вся написанная
логика/локаторы (include/exclude relationship-чекбоксы через `<dd>`, не
`<ul>` как предполагало имя переменной в `ao3_bridge.js`; идемпотентность
save-filter-button) кода не задета, инфраструктура (`selectors.py`,
`sort_filter_form_page.py`, `browser_steps.py`, `test_ao3_selectors.py`)
оставлена в дереве рабочей, `arch_check.py` 0/0.

## Гипотеза класса (D-0043, не подтверждена — только названа)

`bugs/AT-BUG-016.md` (Fixed) диагностировал и устранил КОНКРЕТНЫЙ путь
qemu-краша (`0xc0000005`) для ОДНОЙ фикстуры (`sort_filter_form.mitm`,
TC-040) — форвардящей live-контент из-за неполной self-contained записи.
Этот баг (AT-BUG-021) бьёт по ТОЙ ЖЕ странице, но через ДРУГОЙ путь
(`open_live_listing`/`open_live_sort_filter_form_relationship_ready` —
`@pytest.mark.live` navigate, не replay-фикстура вообще, форвард не
применим как причина). Сигнатура отказа тоже ИНАЯ (DevTools disconnect +
adb device not found, не qemu Windows Event Log `0xc0000005` — не
подтверждено НИ намеренной сверкой Event Log, ни отсутствием). Общее —
только сама тяжёлая live-страница и WHPX-эмулятор под нагрузкой её
рендера. Это может быть (а) ТОТ ЖЕ класс системной хрупкости под тяжёлым
live-рендером, не до конца устранённый узким фиксом AT-BUG-016, ЛИБО (б)
независимая причина (напр. Appium DevTools-сессия отваливается по
собственному таймауту при долгой live-навигации, не связано с GPU/qemu
вообще). Диагноз не проводился — вне мандата test-automator (fail-fast
protocol, docs/06 §5, требует остановки, не продолжения диагностики).

## Критерий готовности (Fixed)

1. Диагностика (critic или test-maintainer со сверкой Windows Event Log на
   `qemu-system-x86_64.exe` в момент краха — тот же метод, что установил
   причину AT-BUG-016): подтвердить/опровергнуть qemu-краш vs
   Appium/DevTools-таймаут как непосредственную причину.
2. В зависимости от диагноза — либо расширить фикс AT-BUG-016 (self-contained
   запись/облегчение рендера) на путь `open_live_listing`, либо починить
   таймаут/устойчивость DevTools-сессии на длинных live-навигациях.
3. TC-078..083 доведены до 3 зелёных прогонов подряд каждый, `automated_by`
   заполнен (инфраструктура уже готова — работы гораздо меньше нуля).

## Обсуждение

**2026-07-19T06:05:00Z — координатор (Lead, Sonnet, dispatch_skipped
диагностики в этом проходе):** заведено по итогам fail-fast остановки
test-automator (canary batch C). Диагностика НЕ выполнена в этом проходе —
бюджет /qa-loop 15 и время сессии, дальнейший device-прогон отложен на
следующий проход. Кейсы TC-078..083 остаются `Approved`, `automated_by`
пуст, локи сняты координатором (воркер не снял после fail-fast остановки).
Инфраструктура (`selectors.py`/`sort_filter_form_page.py`/`browser_steps.py`
дополнения + `test_ao3_selectors.py` тела 6 новых тестов) оставлена в
рабочем дереве НЕЗАКОММИЧЕННОЙ — коммит этой правки откладывается до
диагностики (правки, написанные против недиагностированной нестабильной
среды, не должны попадать в историю как "готовая работа" раньше времени;
альтернатива — закоммитить с явной пометкой "unverified, blocked by
AT-BUG-021" — решение за принимающим следующего прохода).
